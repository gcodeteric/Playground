"""
Modulo de execucao de ordens para o bot de trading autonomo.

Gere a submissao, modificacao e cancelamento de ordens no Interactive Brokers
via ib_insync. Implementa rate limiting, retries e tracking completo de ordens
bracket (entrada + stop-loss + take-profit) por nivel de grid.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

# Garante event loop activo antes de importar ib_insync em Python 3.14+
if sys.version_info >= (3, 10):
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

from ib_insync import (
    Contract,
    IB,
    LimitOrder,
    MarketOrder,
    Order,
    StopOrder,
    Trade,
)

if TYPE_CHECKING:
    from typing import Protocol

    from src.ib_requests import IBRateLimiter, IBRequestExecutor

    class IBConnection(Protocol):
        """Protocolo para a ligacao ao Interactive Brokers."""

        ib: IB
        rate_limiter: IBRateLimiter
        request_executor: IBRequestExecutor


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_MAX_RETRIES: int = 3
_RETRY_DELAY_BASE: float = 0.5  # segundos, com backoff exponencial
_TERMINAL_ORDER_STATUSES = {
    "Filled",
    "Cancelled",
    "ApiCancelled",
    "Inactive",
}


class OrderStatus(str, Enum):
    """Estados possiveis de uma ordem."""

    PENDING = "PendingSubmit"
    SUBMITTED = "Submitted"
    PRE_SUBMITTED = "PreSubmitted"
    FILLED = "Filled"
    CANCELLED = "Cancelled"
    INACTIVE = "Inactive"
    API_PENDING = "ApiPending"
    API_CANCELLED = "ApiCancelled"
    UNKNOWN = "Unknown"


# ---------------------------------------------------------------------------
# Dataclass — informacao completa de uma ordem
# ---------------------------------------------------------------------------


@dataclass
class OrderInfo:
    """Informacao detalhada de uma ordem individual."""

    order_id: int
    grid_id: str
    level: int
    status: str
    contract: Contract
    action: str          # 'BUY' ou 'SELL'
    quantity: int
    price: float         # preco de entrada (limit)
    stop: float          # preco do stop-loss
    target: float        # preco do take-profit
    logical_trade_key: str = ""
    leg_type: str = "parent"
    parent_id: int = 0   # ID da ordem-pai (bracket)
    stop_order_id: int = 0
    tp_order_id: int = 0
    fill_price: float = 0.0
    filled_quantity: int = 0
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Converte para dicionario serializavel."""
        return {
            "order_id": self.order_id,
            "logical_trade_key": self.logical_trade_key,
            "leg_type": self.leg_type,
            "grid_id": self.grid_id,
            "level": self.level,
            "status": self.status,
            "contract": str(self.contract),
            "action": self.action,
            "quantity": self.quantity,
            "price": self.price,
            "stop": self.stop,
            "target": self.target,
            "parent_id": self.parent_id,
            "stop_order_id": self.stop_order_id,
            "tp_order_id": self.tp_order_id,
            "fill_price": self.fill_price,
            "filled_quantity": self.filled_quantity,
            "created_at": self.created_at,
        }


@dataclass
class BracketInfo:
    """Identidade lógica de um bracket completo."""

    logical_trade_key: str
    grid_id: str
    level: int
    action: str
    quantity: int
    price: float
    stop: float
    target: float
    parent_order_id: int
    stop_order_id: int
    tp_order_id: int
    created_at: float = field(default_factory=time.time)

    def order_ids(self) -> tuple[int, int, int]:
        return (
            self.parent_order_id,
            self.stop_order_id,
            self.tp_order_id,
        )


from src.ib_requests import (
    IBRateLimiter,
    IBRequestExecutor,
    classify_ib_error,
)


class RateLimiter(IBRateLimiter):
    """Alias retrocompativel para testes antigos."""

    def __init__(self, max_per_second: int = 45) -> None:
        # Mantem o comportamento legado: apenas limite por segundo,
        # sem cooldown de pedidos identicos nem janela historica longa.
        super().__init__(
            max_requests=max_per_second,
            request_window_seconds=1.0,
            identical_cooldown_seconds=0.0,
            max_order_messages_per_second=max_per_second,
        )

    async def acquire(self) -> float:
        """Mantem a interface simples usada pelos testes antigos."""
        return await super().acquire(
            "legacy-rate-limiter",
            category="order",
            request_cost=1,
            order_messages=1,
        )


# ---------------------------------------------------------------------------
# Order Manager
# ---------------------------------------------------------------------------


class OrderManager:
    """
    Gestor central de ordens para o bot de trading.

        Responsabilidades:
    - Submissao de ordens bracket (entrada + stop + take-profit)
    - Cancelamento individual e por grid
    - Modificacao de precos
    - Consulta de posicoes e ordens abertas
    - Rate limiting para respeitar limites do IB API
    - Retries automáticos apenas quando a operação é segura para retry
    """

    def __init__(self, ib_connection: IBConnection) -> None:
        self.ib: IB = ib_connection.ib
        self._pending_orders: dict[int, OrderInfo] = {}
        self._brackets_by_key: dict[str, BracketInfo] = {}
        self._rate_limiter: IBRateLimiter = ib_connection.rate_limiter
        self._request_executor: IBRequestExecutor = ib_connection.request_executor

        # Registar callbacks para actualizacao de estado
        self.ib.orderStatusEvent += self._on_order_status
        self.ib.errorEvent += self._on_error

        logger.info("OrderManager inicializado com sucesso")

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _on_order_status(self, trade: Trade) -> None:
        """Callback invocado pelo ib_insync quando o estado de uma ordem muda."""
        order_id = trade.order.orderId
        new_status = trade.orderStatus.status

        if order_id in self._pending_orders:
            info = self._pending_orders[order_id]
            old_status = info.status
            info.status = new_status

            if new_status == OrderStatus.FILLED:
                info.fill_price = trade.orderStatus.avgFillPrice
                info.filled_quantity = int(trade.orderStatus.filled)
                logger.info(
                    "Ordem %d [%s] (grid=%s, nivel=%d) PREENCHIDA a %.4f — "
                    "quantidade: %d",
                    order_id,
                    info.leg_type,
                    info.grid_id,
                    info.level,
                    info.fill_price,
                    info.filled_quantity,
                )
            elif new_status == OrderStatus.CANCELLED:
                logger.info(
                    "Ordem %d [%s] (grid=%s, nivel=%d) CANCELADA",
                    order_id,
                    info.leg_type,
                    info.grid_id,
                    info.level,
                )
            else:
                logger.debug(
                    "Ordem %d [%s]: estado alterado de %s para %s",
                    order_id,
                    info.leg_type,
                    old_status,
                    new_status,
                )

    def _on_error(
        self, reqId: int, errorCode: int, errorString: str, contract: Any
    ) -> None:
        """Callback invocado pelo ib_insync quando ocorre um erro do IB API."""
        # Codigos informativos (nao sao erros reais)
        informational_codes = {2104, 2106, 2158, 2119}
        if errorCode in informational_codes:
            return

        decision = classify_ib_error(errorCode, errorString)
        if decision is not None and decision.scope == "order":
            message = (
                f"Erro operacional IB em ordens [{decision.action}] "
                f"codigo={decision.error_code}: {decision.message}"
            )
            log_fn = logger.error if decision.severity == "error" else logger.warning
            log_fn("%s (reqId=%d, contrato=%s)", message, reqId, contract)
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._request_executor._send_alert(message))
            except RuntimeError:
                logger.debug(
                    "Sem event loop activo para alerta de erro IB em ordens (%d).",
                    decision.error_code,
                )
            return

        logger.warning(
            "Erro IB — reqId=%d, codigo=%d: %s (contrato=%s)",
            reqId,
            errorCode,
            errorString,
            contract,
        )

    # ------------------------------------------------------------------
    # Validacao de precos
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_bracket_prices(
        action: str,
        entry_price: float,
        stop_price: float,
        take_profit_price: float,
    ) -> None:
        """
        Valida a coerencia dos precos de um bracket order.

        Para BUY:
            stop < entry < take_profit

        Para SELL:
            take_profit < entry < stop

        Levanta ValueError se os precos forem incoerentes.
        """
        if entry_price <= 0 or stop_price <= 0 or take_profit_price <= 0:
            raise ValueError(
                f"Todos os precos devem ser positivos: "
                f"entrada={entry_price}, stop={stop_price}, "
                f"alvo={take_profit_price}"
            )

        if action.upper() == "BUY":
            if not (stop_price < entry_price < take_profit_price):
                raise ValueError(
                    f"Precos incoerentes para BUY: "
                    f"stop ({stop_price}) deve ser < "
                    f"entrada ({entry_price}) deve ser < "
                    f"alvo ({take_profit_price})"
                )
        elif action.upper() == "SELL":
            if not (take_profit_price < entry_price < stop_price):
                raise ValueError(
                    f"Precos incoerentes para SELL: "
                    f"alvo ({take_profit_price}) deve ser < "
                    f"entrada ({entry_price}) deve ser < "
                    f"stop ({stop_price})"
                )
        else:
            raise ValueError(
                f"Accao invalida: {action!r}. Deve ser 'BUY' ou 'SELL'."
            )

    # ------------------------------------------------------------------
    # Submissao de ordens
    # ------------------------------------------------------------------

    @staticmethod
    def _is_terminal_status(status: str) -> bool:
        return status in _TERMINAL_ORDER_STATUSES

    def _get_active_bracket(self, logical_trade_key: str) -> BracketInfo | None:
        bracket = self._brackets_by_key.get(logical_trade_key)
        if bracket is None:
            return None

        if any(
            (
                info := self._pending_orders.get(order_id)
            ) is not None and not self._is_terminal_status(info.status)
            for order_id in bracket.order_ids()
        ):
            return bracket

        self._brackets_by_key.pop(logical_trade_key, None)
        return None

    def _sync_bracket_tracking(self, logical_trade_key: str) -> None:
        if logical_trade_key not in self._brackets_by_key:
            return
        self._get_active_bracket(logical_trade_key)

    @staticmethod
    def build_logical_trade_key(grid_id: str, level: int, action: str = "BUY") -> str:
        """Constrói a chave lógica estável de um bracket de entrada."""
        return f"{grid_id}:{level}:{action.upper()}:entry"

    @staticmethod
    def _rehydrated_leg_status(level_status: str, leg_type: str) -> str:
        """Infere um estado inicial conservador para tracking reidratado."""
        if level_status == "bought":
            if leg_type == "parent":
                return OrderStatus.FILLED
            return OrderStatus.SUBMITTED
        if level_status == "pending":
            if leg_type == "parent":
                return OrderStatus.SUBMITTED
            return OrderStatus.PENDING
        if level_status == "sold":
            if leg_type == "tp":
                return OrderStatus.FILLED
            return OrderStatus.CANCELLED
        if level_status == "stopped":
            if leg_type == "stop":
                return OrderStatus.FILLED
            return OrderStatus.CANCELLED
        return OrderStatus.CANCELLED

    @staticmethod
    def _normalize_order_ref(order: Any) -> str:
        """Normaliza orderRef vindo do broker."""
        return str(getattr(order, "orderRef", "") or "").strip()

    @staticmethod
    def _parse_logical_trade_key(logical_trade_key: str) -> tuple[str, int, str] | None:
        """Extrai (grid_id, level, action) de uma chave lógica de bracket."""
        parts = logical_trade_key.split(":")
        if len(parts) < 4 or parts[-1] != "entry":
            return None
        try:
            level = int(parts[-3])
        except ValueError:
            return None
        grid_id = ":".join(parts[:-3])
        action = parts[-2].upper()
        if not grid_id:
            return None
        return grid_id, level, action

    @staticmethod
    def _trade_leg_type(trade: Trade) -> str:
        """Classifica a perna de uma trade aberta do broker."""
        order = trade.order
        parent_id = int(getattr(order, "parentId", 0) or 0)
        if parent_id == 0:
            return "parent"
        order_type = str(getattr(order, "orderType", "") or "").upper()
        if order_type in {"STP", "STP LMT", "STOP"}:
            return "stop"
        return "tp"

    def _register_bracket_tracking(
        self,
        *,
        logical_trade_key: str,
        grid_id: str,
        level: int,
        action: str,
        contract: Contract,
        quantity: int,
        entry_price: float,
        stop_price: float,
        take_profit_price: float,
        parent_order_id: int,
        stop_order_id: int,
        tp_order_id: int,
        parent_status: str,
        stop_status: str,
        tp_status: str,
        parent_fill_price: float = 0.0,
        stop_fill_price: float = 0.0,
        tp_fill_price: float = 0.0,
        parent_filled_quantity: int = 0,
        stop_filled_quantity: int = 0,
        tp_filled_quantity: int = 0,
    ) -> BracketInfo:
        """Regista um bracket completo no tracking local."""
        bracket_info = BracketInfo(
            logical_trade_key=logical_trade_key,
            grid_id=grid_id,
            level=level,
            action=action.upper(),
            quantity=quantity,
            price=entry_price,
            stop=stop_price,
            target=take_profit_price,
            parent_order_id=parent_order_id,
            stop_order_id=stop_order_id,
            tp_order_id=tp_order_id,
        )
        reverse_action = "SELL" if action.upper() == "BUY" else "BUY"

        parent_info = OrderInfo(
            order_id=parent_order_id,
            logical_trade_key=logical_trade_key,
            leg_type="parent",
            grid_id=grid_id,
            level=level,
            status=parent_status,
            contract=contract,
            action=action.upper(),
            quantity=quantity,
            price=entry_price,
            stop=stop_price,
            target=take_profit_price,
            parent_id=parent_order_id,
            stop_order_id=stop_order_id,
            tp_order_id=tp_order_id,
            fill_price=parent_fill_price,
            filled_quantity=parent_filled_quantity,
        )
        self._pending_orders[parent_order_id] = parent_info

        if stop_order_id:
            stop_info = OrderInfo(
                order_id=stop_order_id,
                logical_trade_key=logical_trade_key,
                leg_type="stop",
                grid_id=grid_id,
                level=level,
                status=stop_status,
                contract=contract,
                action=reverse_action,
                quantity=quantity,
                price=entry_price,
                stop=stop_price,
                target=take_profit_price,
                parent_id=parent_order_id,
                stop_order_id=stop_order_id,
                tp_order_id=tp_order_id,
                fill_price=stop_fill_price,
                filled_quantity=stop_filled_quantity,
            )
            self._pending_orders[stop_order_id] = stop_info

        if tp_order_id:
            tp_info = OrderInfo(
                order_id=tp_order_id,
                logical_trade_key=logical_trade_key,
                leg_type="tp",
                grid_id=grid_id,
                level=level,
                status=tp_status,
                contract=contract,
                action=reverse_action,
                quantity=quantity,
                price=entry_price,
                stop=stop_price,
                target=take_profit_price,
                parent_id=parent_order_id,
                stop_order_id=stop_order_id,
                tp_order_id=tp_order_id,
                fill_price=tp_fill_price,
                filled_quantity=tp_filled_quantity,
            )
            self._pending_orders[tp_order_id] = tp_info

        self._brackets_by_key[logical_trade_key] = bracket_info
        self._sync_bracket_tracking(logical_trade_key)
        return bracket_info

    def _register_broker_bracket(self, logical_trade_key: str, trades: list[Trade]) -> BracketInfo | None:
        """Reconstrói um bracket activo a partir das openTrades do broker."""
        parsed = self._parse_logical_trade_key(logical_trade_key)
        if parsed is None or not trades:
            return None
        grid_id, level, action = parsed

        legs: dict[str, Trade] = {}
        for trade in trades:
            legs[self._trade_leg_type(trade)] = trade

        parent_trade = legs.get("parent")
        child_trade = legs.get("stop") or legs.get("tp")
        contract = (
            parent_trade.contract if parent_trade is not None
            else child_trade.contract if child_trade is not None
            else None
        )
        if contract is None:
            return None

        parent_order = parent_trade.order if parent_trade is not None else None
        stop_trade = legs.get("stop")
        tp_trade = legs.get("tp")
        stop_order = stop_trade.order if stop_trade is not None else None
        tp_order = tp_trade.order if tp_trade is not None else None

        quantity = int(
            getattr(parent_order, "totalQuantity", 0)
            or getattr(stop_order, "totalQuantity", 0)
            or getattr(tp_order, "totalQuantity", 0)
            or 0
        )
        entry_price = float(getattr(parent_order, "lmtPrice", 0.0) or 0.0)
        stop_price = float(getattr(stop_order, "auxPrice", 0.0) or 0.0)
        take_profit_price = float(getattr(tp_order, "lmtPrice", 0.0) or 0.0)
        parent_order_id = int(getattr(parent_order, "orderId", 0) or 0)
        if parent_order_id == 0:
            parent_order_id = int(
                getattr(stop_order, "parentId", 0) or getattr(tp_order, "parentId", 0) or 0
            )
        if parent_order_id == 0:
            return None

        return self._register_bracket_tracking(
            logical_trade_key=logical_trade_key,
            grid_id=grid_id,
            level=level,
            action=action,
            contract=contract,
            quantity=quantity,
            entry_price=entry_price,
            stop_price=stop_price,
            take_profit_price=take_profit_price,
            parent_order_id=parent_order_id,
            stop_order_id=int(getattr(stop_order, "orderId", 0) or 0),
            tp_order_id=int(getattr(tp_order, "orderId", 0) or 0),
            parent_status=(
                str(parent_trade.orderStatus.status)
                if parent_trade is not None and parent_trade.orderStatus
                else OrderStatus.UNKNOWN
            ),
            stop_status=(
                str(stop_trade.orderStatus.status)
                if stop_trade is not None and stop_trade.orderStatus
                else OrderStatus.CANCELLED
            ),
            tp_status=(
                str(tp_trade.orderStatus.status)
                if tp_trade is not None and tp_trade.orderStatus
                else OrderStatus.CANCELLED
            ),
            parent_fill_price=float(
                getattr(parent_trade.orderStatus, "avgFillPrice", 0.0)
                if parent_trade is not None and parent_trade.orderStatus else 0.0
            ),
            stop_fill_price=float(
                getattr(stop_trade.orderStatus, "avgFillPrice", 0.0)
                if stop_trade is not None and stop_trade.orderStatus else 0.0
            ),
            tp_fill_price=float(
                getattr(tp_trade.orderStatus, "avgFillPrice", 0.0)
                if tp_trade is not None and tp_trade.orderStatus else 0.0
            ),
            parent_filled_quantity=int(
                getattr(parent_trade.orderStatus, "filled", 0)
                if parent_trade is not None and parent_trade.orderStatus else 0
            ),
            stop_filled_quantity=int(
                getattr(stop_trade.orderStatus, "filled", 0)
                if stop_trade is not None and stop_trade.orderStatus else 0
            ),
            tp_filled_quantity=int(
                getattr(tp_trade.orderStatus, "filled", 0)
                if tp_trade is not None and tp_trade.orderStatus else 0
            ),
        )

    def _get_broker_bracket(self, logical_trade_key: str) -> BracketInfo | None:
        """Procura um bracket activo no broker usando orderRef como chave idempotente."""
        trades = [
            trade for trade in self.ib.openTrades()
            if self._normalize_order_ref(trade.order) == logical_trade_key
        ]
        if not trades:
            return None
        return self._register_broker_bracket(logical_trade_key, trades)

    def sync_tracking_from_open_orders(self, open_orders: list[dict[str, Any]]) -> int:
        """Sincroniza estados locais com o snapshot actual de ordens abertas do broker."""
        updated = 0
        by_ref: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for order in open_orders:
            order_ref = str(order.get("order_ref", "") or "").strip()
            if order_ref:
                by_ref[order_ref].append(order)
            order_id = int(order.get("order_id", 0) or 0)
            info = self._pending_orders.get(order_id)
            if info is None:
                continue
            info.status = str(order.get("status") or info.status)
            info.fill_price = float(order.get("avg_fill_price", info.fill_price) or info.fill_price)
            info.filled_quantity = int(order.get("filled", info.filled_quantity) or info.filled_quantity)
            updated += 1

        for order_ref, orders in by_ref.items():
            if order_ref in self._brackets_by_key:
                continue
            parsed = self._parse_logical_trade_key(order_ref)
            if parsed is None:
                continue
            broker_ids = {int(order.get("order_id", 0) or 0) for order in orders}
            tracked_ids = broker_ids & set(self._pending_orders.keys())
            if tracked_ids:
                parent_order_id = int(
                    next((o.get("order_id", 0) for o in orders if int(o.get("parent_id", 0) or 0) == 0), 0)
                    or next((o.get("parent_id", 0) for o in orders if int(o.get("parent_id", 0) or 0) > 0), 0)
                    or 0
                )
                if parent_order_id == 0:
                    continue
                self._register_bracket_tracking(
                    logical_trade_key=order_ref,
                    grid_id=parsed[0],
                    level=parsed[1],
                    action=parsed[2],
                    contract=self._pending_orders[next(iter(tracked_ids))].contract,
                    quantity=int(float(orders[0].get("quantity", 0) or 0)),
                    entry_price=float(orders[0].get("limit_price", 0.0) or 0.0),
                    stop_price=float(next((o.get("stop_price", 0.0) for o in orders if o.get("stop_price")), 0.0) or 0.0),
                    take_profit_price=float(
                        next(
                            (
                                o.get("limit_price", 0.0)
                                for o in orders
                                if int(o.get("parent_id", 0) or 0) > 0 and not o.get("stop_price")
                            ),
                            0.0,
                        ) or 0.0
                    ),
                    parent_order_id=parent_order_id,
                    stop_order_id=int(next((o.get("order_id", 0) for o in orders if o.get("stop_price")), 0) or 0),
                    tp_order_id=int(
                        next(
                            (
                                o.get("order_id", 0)
                                for o in orders
                                if int(o.get("parent_id", 0) or 0) > 0 and o.get("limit_price") and not o.get("stop_price")
                            ),
                            0,
                        ) or 0
                    ),
                    parent_status=str(next((o.get("status") for o in orders if int(o.get("parent_id", 0) or 0) == 0), OrderStatus.UNKNOWN)),
                    stop_status=str(next((o.get("status") for o in orders if o.get("stop_price")), OrderStatus.CANCELLED)),
                    tp_status=str(
                        next(
                            (
                                o.get("status")
                                for o in orders
                                if int(o.get("parent_id", 0) or 0) > 0 and o.get("limit_price") and not o.get("stop_price")
                            ),
                            OrderStatus.CANCELLED,
                        )
                    ),
                )
                updated += len(orders)
        return updated

    def rehydrate_grid_orders(self, grid: Any, contract: Contract) -> int:
        """
        Reconstroi o tracking mínimo a partir das grids persistidas.

        Esta rotina não recria ordens no broker. Apenas restabelece identidade
        lógica suficiente para:
        - impedir re-submissões duplicadas após restart
        - preservar consulta básica de estado por order_id
        - permitir monitorização conservadora de grids activas
        """
        if getattr(grid, "status", None) == "closed":
            return 0

        restored = 0
        for level in getattr(grid, "levels", []):
            buy_order_id = getattr(level, "buy_order_id", None)
            if buy_order_id is None:
                continue

            trade_key = self.build_logical_trade_key(grid.id, level.level, "BUY")
            if self._get_active_bracket(trade_key) is not None:
                continue
            if any(
                oid is not None and oid in self._pending_orders
                for oid in (
                    buy_order_id,
                    getattr(level, "stop_order_id", None),
                    getattr(level, "sell_order_id", None),
                )
            ):
                continue

            level_status = str(getattr(level, "status", "pending"))
            stop_order_id = int(getattr(level, "stop_order_id", None) or 0)
            tp_order_id = int(getattr(level, "sell_order_id", None) or 0)
            quantity = int(getattr(level, "quantity", 0) or 0)
            if quantity <= 0:
                continue

            bracket_info = BracketInfo(
                logical_trade_key=trade_key,
                grid_id=grid.id,
                level=level.level,
                action="BUY",
                quantity=quantity,
                price=float(level.buy_price),
                stop=float(level.stop_price),
                target=float(level.sell_price),
                parent_order_id=int(buy_order_id),
                stop_order_id=stop_order_id,
                tp_order_id=tp_order_id,
            )

            parent_info = OrderInfo(
                order_id=int(buy_order_id),
                logical_trade_key=trade_key,
                leg_type="parent",
                grid_id=grid.id,
                level=level.level,
                status=self._rehydrated_leg_status(level_status, "parent"),
                contract=contract,
                action="BUY",
                quantity=quantity,
                price=float(level.buy_price),
                stop=float(level.stop_price),
                target=float(level.sell_price),
                parent_id=int(buy_order_id),
                stop_order_id=stop_order_id,
                tp_order_id=tp_order_id,
                fill_price=(
                    float(level.buy_price) if level_status in {"bought", "sold", "stopped"} else 0.0
                ),
                filled_quantity=quantity if level_status in {"bought", "sold", "stopped"} else 0,
            )
            self._pending_orders[parent_info.order_id] = parent_info
            restored += 1

            if stop_order_id:
                stop_info = OrderInfo(
                    order_id=stop_order_id,
                    logical_trade_key=trade_key,
                    leg_type="stop",
                    grid_id=grid.id,
                    level=level.level,
                    status=self._rehydrated_leg_status(level_status, "stop"),
                    contract=contract,
                    action="SELL",
                    quantity=quantity,
                    price=float(level.buy_price),
                    stop=float(level.stop_price),
                    target=float(level.sell_price),
                    parent_id=int(buy_order_id),
                    stop_order_id=stop_order_id,
                    tp_order_id=tp_order_id,
                    fill_price=float(level.stop_price) if level_status == "stopped" else 0.0,
                    filled_quantity=quantity if level_status == "stopped" else 0,
                )
                self._pending_orders[stop_info.order_id] = stop_info
                restored += 1

            if tp_order_id:
                tp_info = OrderInfo(
                    order_id=tp_order_id,
                    logical_trade_key=trade_key,
                    leg_type="tp",
                    grid_id=grid.id,
                    level=level.level,
                    status=self._rehydrated_leg_status(level_status, "tp"),
                    contract=contract,
                    action="SELL",
                    quantity=quantity,
                    price=float(level.buy_price),
                    stop=float(level.stop_price),
                    target=float(level.sell_price),
                    parent_id=int(buy_order_id),
                    stop_order_id=stop_order_id,
                    tp_order_id=tp_order_id,
                    fill_price=float(level.sell_price) if level_status == "sold" else 0.0,
                    filled_quantity=quantity if level_status == "sold" else 0,
                )
                self._pending_orders[tp_info.order_id] = tp_info
                restored += 1

            self._brackets_by_key[trade_key] = bracket_info
            self._sync_bracket_tracking(trade_key)

        if restored > 0:
            logger.info(
                "Tracking reidratado para grid %s: %d ordem(ns) restaurada(s).",
                getattr(grid, "id", "unknown"),
                restored,
            )
        return restored

    async def submit_bracket_order(
        self,
        contract: Contract,
        action: str,
        quantity: int,
        entry_price: float,
        stop_price: float,
        take_profit_price: float,
        grid_id: str,
        level: int,
        logical_trade_key: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Submete uma ordem bracket (entrada limit + stop-loss + take-profit).

        Parametros
        ----------
        contract : Contract
            Contrato IB (Stock, Forex, Future, etc.).
        action : str
            'BUY' ou 'SELL'.
        quantity : int
            Quantidade a transaccionar.
        entry_price : float
            Preco limite de entrada.
        stop_price : float
            Preco do stop-loss.
        take_profit_price : float
            Preco do take-profit.
        grid_id : str
            Identificador unico da grid a que pertence esta ordem.
        level : int
            Nivel da grid (0, 1, 2, ...).

        Retorna
        -------
        dict | None
            Dicionario com informacao da ordem submetida, ou None em caso
            de falha apos todas as tentativas.
        """
        # Validar precos antes de qualquer tentativa
        try:
            self._validate_bracket_prices(
                action, entry_price, stop_price, take_profit_price
            )
        except ValueError as exc:
            logger.error(
                "Validacao de precos falhou para grid=%s, nivel=%d: %s",
                grid_id,
                level,
                exc,
            )
            return None

        if quantity <= 0:
            logger.error(
                "Quantidade invalida (%d) para grid=%s, nivel=%d",
                quantity,
                grid_id,
                level,
            )
            return None

        trade_key = logical_trade_key or self.build_logical_trade_key(
            grid_id,
            level,
            action,
        )
        existing_bracket = self._get_active_bracket(trade_key)
        if existing_bracket is not None:
            logger.warning(
                "Bracket duplicado bloqueado para %s (grid=%s, nivel=%d). "
                "A reutilizar bracket activo existente.",
                trade_key,
                grid_id,
                level,
            )
            parent_info = self._pending_orders.get(existing_bracket.parent_order_id)
            if parent_info is not None:
                return parent_info.to_dict()
            return {
                "order_id": existing_bracket.parent_order_id,
                "logical_trade_key": trade_key,
                "grid_id": grid_id,
                "level": level,
                "action": action.upper(),
                "quantity": quantity,
                "price": entry_price,
                "stop": stop_price,
                "target": take_profit_price,
                "stop_order_id": existing_bracket.stop_order_id,
                "tp_order_id": existing_bracket.tp_order_id,
            }

        broker_bracket = self._get_broker_bracket(trade_key)
        if broker_bracket is not None:
            logger.warning(
                "Bracket duplicado bloqueado por ordem já aberta no broker para %s "
                "(grid=%s, nivel=%d).",
                trade_key,
                grid_id,
                level,
            )
            parent_info = self._pending_orders.get(broker_bracket.parent_order_id)
            if parent_info is not None:
                return parent_info.to_dict()
            return {
                "order_id": broker_bracket.parent_order_id,
                "logical_trade_key": trade_key,
                "grid_id": grid_id,
                "level": level,
                "action": action.upper(),
                "quantity": quantity,
                "price": entry_price,
                "stop": stop_price,
                "target": take_profit_price,
                "stop_order_id": broker_bracket.stop_order_id,
                "tp_order_id": broker_bracket.tp_order_id,
            }

        reverse_action = "SELL" if action.upper() == "BUY" else "BUY"

        async def _submit() -> dict[str, Any]:
            # Criar as tres ordens do bracket manualmente
            # para controlo total sobre os IDs
            parent = LimitOrder(
                action=action.upper(),
                totalQuantity=quantity,
                lmtPrice=entry_price,
                transmit=False,
            )
            parent.orderId = self.ib.client.getReqId()
            parent.orderRef = trade_key

            stop_order = StopOrder(
                action=reverse_action,
                totalQuantity=quantity,
                stopPrice=stop_price,
                transmit=False,
                parentId=parent.orderId,
            )
            stop_order.orderId = self.ib.client.getReqId()
            stop_order.orderRef = trade_key

            tp_order = LimitOrder(
                action=reverse_action,
                totalQuantity=quantity,
                lmtPrice=take_profit_price,
                transmit=True,
                parentId=parent.orderId,
            )
            tp_order.orderId = self.ib.client.getReqId()
            tp_order.orderRef = trade_key

            parent_trade = self.ib.placeOrder(contract, parent)
            self.ib.placeOrder(contract, stop_order)
            self.ib.placeOrder(contract, tp_order)

            await asyncio.sleep(0.1)
            self.ib.sleep(0)

            bracket_info = BracketInfo(
                logical_trade_key=trade_key,
                grid_id=grid_id,
                level=level,
                action=action.upper(),
                quantity=quantity,
                price=entry_price,
                stop=stop_price,
                target=take_profit_price,
                parent_order_id=parent.orderId,
                stop_order_id=stop_order.orderId,
                tp_order_id=tp_order.orderId,
            )

            parent_info = OrderInfo(
                order_id=parent.orderId,
                logical_trade_key=trade_key,
                leg_type="parent",
                grid_id=grid_id,
                level=level,
                status=parent_trade.orderStatus.status
                if parent_trade.orderStatus
                else OrderStatus.PENDING,
                contract=contract,
                action=action.upper(),
                quantity=quantity,
                price=entry_price,
                stop=stop_price,
                target=take_profit_price,
                parent_id=parent.orderId,
                stop_order_id=stop_order.orderId,
                tp_order_id=tp_order.orderId,
            )
            stop_info = OrderInfo(
                order_id=stop_order.orderId,
                logical_trade_key=trade_key,
                leg_type="stop",
                grid_id=grid_id,
                level=level,
                status=OrderStatus.PENDING,
                contract=contract,
                action=reverse_action,
                quantity=quantity,
                price=entry_price,
                stop=stop_price,
                target=take_profit_price,
                parent_id=parent.orderId,
                stop_order_id=stop_order.orderId,
                tp_order_id=tp_order.orderId,
            )
            tp_info = OrderInfo(
                order_id=tp_order.orderId,
                logical_trade_key=trade_key,
                leg_type="tp",
                grid_id=grid_id,
                level=level,
                status=OrderStatus.PENDING,
                contract=contract,
                action=reverse_action,
                quantity=quantity,
                price=entry_price,
                stop=stop_price,
                target=take_profit_price,
                parent_id=parent.orderId,
                stop_order_id=stop_order.orderId,
                tp_order_id=tp_order.orderId,
            )

            self._pending_orders[parent.orderId] = parent_info
            self._pending_orders[stop_order.orderId] = stop_info
            self._pending_orders[tp_order.orderId] = tp_info
            self._brackets_by_key[trade_key] = bracket_info

            logger.info(
                "Ordem bracket submetida com sucesso — "
                "grid=%s, nivel=%d, accao=%s, qtd=%d, "
                "entrada=%.4f, stop=%.4f, alvo=%.4f "
                "(IDs: pai=%d, stop=%d, tp=%d)",
                grid_id,
                level,
                action.upper(),
                quantity,
                entry_price,
                stop_price,
                take_profit_price,
                parent.orderId,
                stop_order.orderId,
                tp_order.orderId,
            )

            return parent_info.to_dict()

        try:
            # Contenção de segurança: ordens que criam exposição não fazem retry
            # automático até existir dedupe/idempotência por trade lógico.
            return await self._request_executor.run(
                "submit_bracket_order",
                f"order:{grid_id}:{level}:{action.upper()}",
                _submit,
                category="order",
                request_cost=3,
                order_messages=3,
                max_retries=1,
                base_delay=_RETRY_DELAY_BASE,
            )
        except Exception:
            logger.error(
                "Submissão da ordem bracket falhou sem retry automático — "
                "grid=%s, nivel=%d. Ordem NÃO submetida para evitar duplicação de exposição.",
                grid_id,
                level,
            )
            return None

    # ------------------------------------------------------------------
    # Cancelamento de ordens
    # ------------------------------------------------------------------

    async def cancel_order(self, order_id: int) -> bool:
        """
        Cancela uma ordem individual com retries.

        Parametros
        ----------
        order_id : int
            ID da ordem a cancelar.

        Retorna
        -------
        bool
            True se a ordem foi cancelada com sucesso.
        """
        async def _cancel() -> bool:
            target_trade: Trade | None = None
            for trade in self.ib.openTrades():
                if trade.order.orderId == order_id:
                    target_trade = trade
                    break

            if target_trade is None:
                logger.warning(
                    "Ordem %d nao encontrada nas ordens abertas "
                    "(pode ja ter sido preenchida ou cancelada)",
                    order_id,
                )
                removed = self._pending_orders.pop(order_id, None)
                if removed is not None:
                    self._sync_bracket_tracking(removed.logical_trade_key)
                return True

            self.ib.cancelOrder(target_trade.order)

            for _ in range(20):
                await asyncio.sleep(0.1)
                self.ib.sleep(0)
                status = target_trade.orderStatus.status
                if status in (
                    OrderStatus.CANCELLED,
                    OrderStatus.API_CANCELLED,
                ):
                    logger.info("Ordem %d cancelada com sucesso", order_id)
                    removed = self._pending_orders.pop(order_id, None)
                    if removed is not None:
                        self._sync_bracket_tracking(removed.logical_trade_key)
                    return True

            raise TimeoutError(
                f"Timeout ao aguardar confirmacao de cancelamento da ordem {order_id}"
            )

        try:
            return await self._request_executor.run(
                "cancel_order",
                f"cancel:{order_id}",
                _cancel,
                category="order",
                request_cost=1,
                order_messages=1,
                max_retries=_MAX_RETRIES,
                base_delay=_RETRY_DELAY_BASE,
            )
        except Exception:
            logger.error(
                "Todas as %d tentativas de cancelamento da ordem %d falharam.",
                _MAX_RETRIES,
                order_id,
            )
            return False

    async def cancel_all_grid_orders(self, grid_id: str) -> int:
        """
        Cancela todas as ordens pendentes associadas a uma grid.

        Parametros
        ----------
        grid_id : str
            Identificador da grid cujas ordens devem ser canceladas.

        Retorna
        -------
        int
            Numero de ordens canceladas com sucesso.
        """
        # Recolher IDs unicos (evitar duplicados do bracket)
        order_ids_to_cancel: set[int] = set()
        for oid, info in self._pending_orders.items():
            if info.grid_id == grid_id and info.status not in (
                OrderStatus.FILLED,
                OrderStatus.CANCELLED,
                OrderStatus.API_CANCELLED,
                OrderStatus.INACTIVE,
            ):
                order_ids_to_cancel.add(oid)

        if not order_ids_to_cancel:
            logger.info(
                "Nenhuma ordem pendente encontrada para a grid %s",
                grid_id,
            )
            return 0

        logger.info(
            "A cancelar %d ordem(ns) da grid %s...",
            len(order_ids_to_cancel),
            grid_id,
        )

        cancelled_count = 0
        for order_id in order_ids_to_cancel:
            success = await self.cancel_order(order_id)
            if success:
                cancelled_count += 1

        logger.info(
            "Cancelamento da grid %s concluido: %d/%d ordens canceladas",
            grid_id,
            cancelled_count,
            len(order_ids_to_cancel),
        )
        return cancelled_count

    async def cancel_symbol_orders(self, symbol: str) -> int:
        """Cancela todas as ordens abertas do IB para um simbolo."""
        trades = [
            trade for trade in self.ib.openTrades()
            if trade.contract.symbol == symbol
        ]
        if not trades:
            logger.info("Sem ordens abertas para cancelar em %s.", symbol)
            return 0

        cancelled = 0
        for trade in trades:
            if await self.cancel_order(trade.order.orderId):
                cancelled += 1

        logger.info(
            "Cancelamento por simbolo concluido para %s: %d/%d",
            symbol,
            cancelled,
            len(trades),
        )
        return cancelled

    # ------------------------------------------------------------------
    # Fecho de posicoes
    # ------------------------------------------------------------------

    async def close_position(
        self,
        contract: Contract,
        quantity: int,
        action: str = "SELL",
        logical_close_key: str | None = None,
    ) -> bool:
        """
        Fecha uma posicao com ordem de mercado.

        Parametros
        ----------
        contract : Contract
            Contrato da posicao a fechar.
        quantity : int
            Quantidade a fechar.
        action : str
            'SELL' para fechar posicao longa, 'BUY' para fechar posicao curta.

        Retorna
        -------
        bool
            True se a ordem de mercado foi submetida e preenchida com sucesso.
        """
        if quantity <= 0:
            logger.error(
                "Quantidade invalida para fecho de posicao: %d", quantity
            )
            return False

        close_key = logical_close_key or f"close:{contract.symbol}:{action.upper()}:{quantity}"
        for trade in self.ib.openTrades():
            if self._normalize_order_ref(trade.order) != close_key:
                continue
            status = str(getattr(trade.orderStatus, "status", "") or "")
            if not self._is_terminal_status(status):
                logger.warning(
                    "Fecho duplicado bloqueado para %s: ordem de flatten já está aberta no broker.",
                    close_key,
                )
                return True

        async def _close() -> bool:
            order = MarketOrder(
                action=action.upper(),
                totalQuantity=quantity,
            )
            order.orderRef = close_key

            trade = self.ib.placeOrder(contract, order)

            for _ in range(100):
                await asyncio.sleep(0.1)
                self.ib.sleep(0)
                if trade.orderStatus.status == OrderStatus.FILLED:
                    fill_price = trade.orderStatus.avgFillPrice
                    logger.info(
                        "Posicao fechada com sucesso — contrato=%s, "
                        "accao=%s, qtd=%d, preco_preenchimento=%.4f",
                        contract,
                        action.upper(),
                        quantity,
                        fill_price,
                    )
                    return True

            raise TimeoutError(
                f"Timeout ao aguardar preenchimento da ordem de mercado para {contract}"
            )

        try:
            # Contenção de segurança: ordens de fecho não podem repetir cegamente
            # até existir idempotência broker-side/local.
            return await self._request_executor.run(
                "close_position",
                f"close:{contract.symbol}:{action.upper()}:{quantity}",
                _close,
                category="order",
                request_cost=1,
                order_messages=1,
                max_retries=1,
                base_delay=_RETRY_DELAY_BASE,
            )
        except Exception:
            logger.error(
                "Fecho de posição falhou sem retry automático — "
                "contrato=%s. ATENÇÃO: posição pode continuar aberta e requer validação explícita.",
                contract,
            )
            return False

    # ------------------------------------------------------------------
    # Modificacao de ordens
    # ------------------------------------------------------------------

    async def modify_order(self, order_id: int, new_price: float) -> bool:
        """
        Modifica o preco de uma ordem existente.

        Parametros
        ----------
        order_id : int
            ID da ordem a modificar.
        new_price : float
            Novo preco limite (para LimitOrder) ou novo preco stop
            (para StopOrder).

        Retorna
        -------
        bool
            True se a modificacao foi aplicada com sucesso.
        """
        if new_price <= 0:
            logger.error(
                "Preco invalido para modificacao da ordem %d: %.4f",
                order_id,
                new_price,
            )
            return False

        async def _modify() -> bool:
            target_trade: Trade | None = None
            for trade in self.ib.openTrades():
                if trade.order.orderId == order_id:
                    target_trade = trade
                    break

            if target_trade is None:
                logger.warning(
                    "Ordem %d nao encontrada para modificacao "
                    "(pode ja ter sido preenchida ou cancelada)",
                    order_id,
                )
                return False

            order = target_trade.order

            if isinstance(order, LimitOrder) or hasattr(order, "lmtPrice"):
                order.lmtPrice = new_price
            elif isinstance(order, StopOrder) or hasattr(order, "auxPrice"):
                order.auxPrice = new_price
            else:
                logger.error(
                    "Tipo de ordem nao suportado para modificacao: %s",
                    type(order).__name__,
                )
                return False

            self.ib.placeOrder(target_trade.contract, order)
            await asyncio.sleep(0.2)
            self.ib.sleep(0)

            if order_id in self._pending_orders:
                info = self._pending_orders[order_id]
                if hasattr(order, "lmtPrice"):
                    info.price = new_price
                else:
                    info.stop = new_price

            logger.info(
                "Ordem %d modificada com sucesso para preco %.4f",
                order_id,
                new_price,
            )
            return True

        try:
            return await self._request_executor.run(
                "modify_order",
                f"modify:{order_id}",
                _modify,
                category="order",
                request_cost=1,
                order_messages=1,
                max_retries=_MAX_RETRIES,
                base_delay=_RETRY_DELAY_BASE,
            )
        except Exception:
            logger.error(
                "Todas as %d tentativas de modificacao da ordem %d falharam.",
                _MAX_RETRIES,
                order_id,
            )
            return False

    # ------------------------------------------------------------------
    # Consulta de estado
    # ------------------------------------------------------------------

    def get_order_status(self, order_id: int) -> str | None:
        """
        Obtem o estado actual de uma ordem.

        Parametros
        ----------
        order_id : int
            ID da ordem a consultar.

        Retorna
        -------
        str | None
            Estado da ordem, ou None se nao encontrada no tracking.
        """
        # Primeiro, verificar o tracking interno
        if order_id in self._pending_orders:
            return self._pending_orders[order_id].status

        # Verificar nas trades abertas do IB
        for trade in self.ib.openTrades():
            if trade.order.orderId == order_id:
                return trade.orderStatus.status

        logger.debug("Ordem %d nao encontrada no tracking nem no IB", order_id)
        return None

    def get_order_info(self, order_id: int) -> OrderInfo | None:
        """
        Obtem a informacao completa de uma ordem.

        Parametros
        ----------
        order_id : int
            ID da ordem a consultar.

        Retorna
        -------
        OrderInfo | None
            Objecto com informacao completa, ou None se nao encontrada.
        """
        return self._pending_orders.get(order_id)

    async def get_positions(self) -> list[dict[str, Any]]:
        """
        Obtem todas as posicoes actuais do IB.

        Retorna
        -------
        list[dict]
            Lista de dicionarios com informacao de cada posicao:
            - contract: str (descricao do contrato)
            - symbol: str
            - quantity: float
            - avg_cost: float
            - market_value: float (se disponivel)
        """
        try:
            positions = await self._request_executor.run(
                "get_positions",
                "positions",
                self.ib.positions,
                request_cost=1,
                max_retries=_MAX_RETRIES,
                base_delay=_RETRY_DELAY_BASE,
            )

            result: list[dict[str, Any]] = []
            for pos in positions:
                result.append(
                    {
                        "account": pos.account,
                        "contract": str(pos.contract),
                        "symbol": pos.contract.symbol,
                        "quantity": float(pos.position),
                        "avg_cost": float(pos.avgCost),
                    }
                )

            logger.debug(
                "Obtidas %d posicao(oes) do IB",
                len(result),
            )
            return result

        except Exception as exc:
            logger.error("Erro ao obter posicoes: %s", exc)
            return []

    async def get_open_orders(self) -> list[dict[str, Any]]:
        """
        Obtem todas as ordens abertas do IB.

        Retorna
        -------
        list[dict]
            Lista de dicionarios com informacao de cada ordem aberta.
        """
        try:
            trades = await self._request_executor.run(
                "get_open_orders",
                "open_orders",
                self.ib.openTrades,
                request_cost=1,
                max_retries=_MAX_RETRIES,
                base_delay=_RETRY_DELAY_BASE,
            )

            result: list[dict[str, Any]] = []
            for trade in trades:
                order = trade.order
                order_status = trade.orderStatus

                order_dict: dict[str, Any] = {
                    "order_id": order.orderId,
                    "parent_id": int(getattr(order, "parentId", 0) or 0),
                    "order_ref": self._normalize_order_ref(order),
                    "contract": str(trade.contract),
                    "symbol": trade.contract.symbol,
                    "action": order.action,
                    "order_type": order.orderType,
                    "quantity": float(order.totalQuantity),
                    "status": order_status.status,
                    "filled": float(order_status.filled),
                    "remaining": float(order_status.remaining),
                    "avg_fill_price": float(order_status.avgFillPrice),
                }

                # Adicionar precos conforme o tipo de ordem
                if hasattr(order, "lmtPrice") and order.lmtPrice:
                    order_dict["limit_price"] = float(order.lmtPrice)
                if hasattr(order, "auxPrice") and order.auxPrice:
                    order_dict["stop_price"] = float(order.auxPrice)

                # Adicionar informacao da grid se disponivel
                if order.orderId in self._pending_orders:
                    info = self._pending_orders[order.orderId]
                    order_dict["grid_id"] = info.grid_id
                    order_dict["level"] = info.level
                    order_dict["logical_trade_key"] = info.logical_trade_key
                    order_dict["leg_type"] = info.leg_type

                result.append(order_dict)

            logger.debug(
                "Obtidas %d ordem(ns) aberta(s) do IB",
                len(result),
            )
            return result

        except Exception as exc:
            logger.error("Erro ao obter ordens abertas: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Utilitarios
    # ------------------------------------------------------------------

    def get_grid_orders(self, grid_id: str) -> list[OrderInfo]:
        """
        Obtem todas as ordens associadas a uma grid especifica.

        Parametros
        ----------
        grid_id : str
            Identificador da grid.

        Retorna
        -------
        list[OrderInfo]
            Lista de ordens pertencentes a grid indicada.
        """
        seen_ids: set[int] = set()
        result: list[OrderInfo] = []
        for info in self._pending_orders.values():
            if info.grid_id == grid_id and info.order_id not in seen_ids:
                result.append(info)
                seen_ids.add(info.order_id)
        return result

    def get_pending_count(self) -> int:
        """Retorna o numero de ordens-pai unicas no tracking."""
        unique_parents: set[int] = set()
        for info in self._pending_orders.values():
            if not self._is_terminal_status(info.status):
                unique_parents.add(info.parent_id or info.order_id)
        return len(unique_parents)

    def cleanup_completed(self) -> int:
        """
        Remove ordens preenchidas, canceladas ou inactivas do tracking.

        Retorna
        -------
        int
            Numero de entradas removidas.
        """
        to_remove = [
            oid
            for oid, info in self._pending_orders.items()
            if self._is_terminal_status(info.status)
        ]

        affected_keys: set[str] = set()
        for oid in to_remove:
            info = self._pending_orders.pop(oid)
            affected_keys.add(info.logical_trade_key)

        for trade_key in affected_keys:
            self._sync_bracket_tracking(trade_key)

        if to_remove:
            logger.info(
                "Limpeza do tracking: %d entrada(s) removida(s)",
                len(to_remove),
            )
        return len(to_remove)
