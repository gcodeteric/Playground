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
    """Informacao detalhada de uma ordem individual ou bracket."""

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


from src.ib_requests import IBRateLimiter, IBRequestExecutor


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
    - Retries automaticos com backoff exponencial
    """

    def __init__(self, ib_connection: IBConnection) -> None:
        self.ib: IB = ib_connection.ib
        self._pending_orders: dict[int, OrderInfo] = {}
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
                    "Ordem %d (grid=%s, nivel=%d) PREENCHIDA a %.4f — "
                    "quantidade: %d",
                    order_id,
                    info.grid_id,
                    info.level,
                    info.fill_price,
                    info.filled_quantity,
                )
            elif new_status == OrderStatus.CANCELLED:
                logger.info(
                    "Ordem %d (grid=%s, nivel=%d) CANCELADA",
                    order_id,
                    info.grid_id,
                    info.level,
                )
            else:
                logger.debug(
                    "Ordem %d: estado alterado de %s para %s",
                    order_id,
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

            stop_order = StopOrder(
                action=reverse_action,
                totalQuantity=quantity,
                stopPrice=stop_price,
                transmit=False,
                parentId=parent.orderId,
            )
            stop_order.orderId = self.ib.client.getReqId()

            tp_order = LimitOrder(
                action=reverse_action,
                totalQuantity=quantity,
                lmtPrice=take_profit_price,
                transmit=True,
                parentId=parent.orderId,
            )
            tp_order.orderId = self.ib.client.getReqId()

            parent_trade = self.ib.placeOrder(contract, parent)
            self.ib.placeOrder(contract, stop_order)
            self.ib.placeOrder(contract, tp_order)

            await asyncio.sleep(0.1)
            self.ib.sleep(0)

            order_info = OrderInfo(
                order_id=parent.orderId,
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

            self._pending_orders[parent.orderId] = order_info
            self._pending_orders[stop_order.orderId] = order_info
            self._pending_orders[tp_order.orderId] = order_info

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

            return order_info.to_dict()

        try:
            return await self._request_executor.run(
                "submit_bracket_order",
                f"order:{grid_id}:{level}:{action.upper()}",
                _submit,
                category="order",
                request_cost=3,
                order_messages=3,
                max_retries=_MAX_RETRIES,
                base_delay=_RETRY_DELAY_BASE,
            )
        except Exception:
            logger.error(
                "Todas as %d tentativas falharam para ordem bracket — "
                "grid=%s, nivel=%d. Ordem NAO submetida.",
                _MAX_RETRIES,
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
                self._pending_orders.pop(order_id, None)
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
                    self._pending_orders.pop(order_id, None)
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

        async def _close() -> bool:
            order = MarketOrder(
                action=action.upper(),
                totalQuantity=quantity,
            )

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
            return await self._request_executor.run(
                "close_position",
                f"close:{contract.symbol}:{action.upper()}:{quantity}",
                _close,
                category="order",
                request_cost=1,
                order_messages=1,
                max_retries=_MAX_RETRIES,
                base_delay=_RETRY_DELAY_BASE,
            )
        except Exception:
            logger.error(
                "Todas as %d tentativas de fecho de posicao falharam — "
                "contrato=%s. ATENCAO: posicao pode continuar aberta!",
                _MAX_RETRIES,
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
            if info.status not in (
                OrderStatus.FILLED,
                OrderStatus.CANCELLED,
                OrderStatus.API_CANCELLED,
                OrderStatus.INACTIVE,
            ):
                unique_parents.add(info.parent_id)
        return len(unique_parents)

    def cleanup_completed(self) -> int:
        """
        Remove ordens preenchidas, canceladas ou inactivas do tracking.

        Retorna
        -------
        int
            Numero de entradas removidas.
        """
        terminal_states = {
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.API_CANCELLED,
            OrderStatus.INACTIVE,
        }
        to_remove = [
            oid
            for oid, info in self._pending_orders.items()
            if info.status in terminal_states
        ]

        for oid in to_remove:
            del self._pending_orders[oid]

        if to_remove:
            logger.info(
                "Limpeza do tracking: %d entrada(s) removida(s)",
                len(to_remove),
            )
        return len(to_remove)
