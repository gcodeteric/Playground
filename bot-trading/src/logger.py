"""
Modulo de logging e notificacoes do bot de trading autonomo.

TradeLogger — registo append-only de operacoes e calculo de metricas.
TelegramNotifier — notificacoes assincronas via Telegram Bot API (aiohttp).

Todas as mensagens estao em Portugues (PT-PT).
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TradeLogger
# ---------------------------------------------------------------------------

class TradeLogger:
    """
    Registo append-only de trades e calculo de metricas de performance.

    Os trades sao guardados em ``data/trades_log.json`` e as metricas
    agregadas em ``data/metrics.json``.  Nunca se apagam ou modificam
    entradas existentes — apenas se acrescentam novas.
    """

    # Campos obrigatorios num registo de trade
    TRADE_FIELDS: list[str] = [
        "timestamp",
        "symbol",
        "side",
        "price",
        "quantity",
        "order_id",
        "grid_id",
        "level",
        "pnl",
        "regime",
        "signal_confidence",
        "logical_trade_key",
        "order_ref",
        "order_leg",
    ]

    def __init__(self, data_dir: str = "data") -> None:
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)

        self._trades_path: Path = self._data_dir / "trades_log.json"
        self._metrics_path: Path = self._data_dir / "metrics.json"

        # Garantir que os ficheiros existem com estrutura valida
        if not self._trades_path.exists():
            self._trades_path.write_text(
                json.dumps({"trades": []}, indent=2), encoding="utf-8"
            )

        if not self._metrics_path.exists():
            self._metrics_path.write_text(
                json.dumps({"equity_curve": [], "metrics": {}}, indent=2),
                encoding="utf-8",
            )

    # ------------------------------------------------------------------
    # Leitura / escrita atomica do ficheiro de trades
    # ------------------------------------------------------------------

    def _read_trades_file(self) -> dict[str, Any]:
        """Le o ficheiro de trades e devolve o dicionario raiz."""
        try:
            with self._trades_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if "trades" not in data:
                data["trades"] = []
            return data
        except json.JSONDecodeError:
            backup_path = self._trades_path.with_suffix(".json.corrupted")
            try:
                import shutil
                shutil.copy2(self._trades_path, backup_path)
                logger.error(
                    "Ficheiro de trades corrompido — backup criado em %s. "
                    "Historico preservado no backup.",
                    backup_path,
                )
            except Exception as backup_exc:  # noqa: BLE001
                logger.error(
                    "Ficheiro de trades corrompido e backup falhou: %s",
                    backup_exc,
                )
            return {"trades": []}
        except FileNotFoundError:
            return {"trades": []}

    def _write_trades_file(self, data: dict[str, Any]) -> None:
        """Escreve o dicionario raiz no ficheiro de trades (atomico via tmp)."""
        tmp_path = self._trades_path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False, default=str)
        tmp_path.replace(self._trades_path)

    # ------------------------------------------------------------------
    # log_trade — append-only
    # ------------------------------------------------------------------

    def log_trade(self, trade: dict[str, Any]) -> None:
        """
        Regista um trade no ficheiro de log (append-only).

        Campos esperados: timestamp, symbol, side, price, quantity,
        order_id, grid_id, level, pnl, regime, signal_confidence,
        logical_trade_key, order_ref, order_leg.
        Campos em falta ficam com valor ``None``.
        Entradas existentes NUNCA sao apagadas ou modificadas.
        """
        # Garantir que todos os campos existem
        record: dict[str, Any] = {}
        for field in self.TRADE_FIELDS:
            record[field] = trade.get(field)

        # Garantir timestamp
        if record["timestamp"] is None:
            record["timestamp"] = datetime.now(timezone.utc).isoformat()

        data = self._read_trades_file()
        data["trades"].append(record)
        self._write_trades_file(data)

        logger.info(
            "Trade registado: %s %s %s @ %.4f  pnl=%.2f key=%s leg=%s",
            record.get("side", "?"),
            record.get("quantity", 0),
            record.get("symbol", "?"),
            record.get("price", 0) or 0,
            record.get("pnl", 0) or 0,
            record.get("logical_trade_key", "-"),
            record.get("order_leg", "-"),
        )

    # ------------------------------------------------------------------
    # get_trades — consulta com filtros
    # ------------------------------------------------------------------

    def get_trades(
        self,
        symbol: str | None = None,
        grid_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Devolve os trades registados, com filtro opcional por simbolo e/ou grid.
        """
        trades = self._read_trades_file()["trades"]

        if symbol is not None:
            trades = [t for t in trades if t.get("symbol") == symbol]

        if grid_id is not None:
            trades = [t for t in trades if t.get("grid_id") == grid_id]

        return trades

    # ------------------------------------------------------------------
    # calculate_metrics
    # ------------------------------------------------------------------

    def calculate_metrics(self) -> dict[str, Any]:
        """
        Calcula metricas completas de performance:

        - win_rate:      fraccao de trades com pnl > 0
        - payoff_ratio:  media dos ganhos / media das perdas (abs)
        - expectancy:    (prob_win * avg_win) - (prob_loss * avg_loss)
        - max_drawdown:  maior queda pico-vale na equity cumulativa
        - sharpe_ratio:  Sharpe rolling 30 dias (annualizado, rf=0)
        - profit_factor: gross_profit / gross_loss
        - num_trades:    total de trades com pnl preenchido
        - pnl_by_grid:   soma de pnl por grid_id
        - pnl_by_symbol: soma de pnl por simbolo
        - pnl_by_regime: soma de pnl por regime
        - total_pnl:     soma de todos os pnl
        """
        trades = self._read_trades_file()["trades"]

        # Filtrar trades com pnl numerico (sells tipicamente)
        pnl_trades: list[dict[str, Any]] = []
        for t in trades:
            pnl = t.get("pnl")
            if pnl is not None:
                try:
                    pnl_val = float(pnl)
                    pnl_trades.append({**t, "pnl": pnl_val})
                except (TypeError, ValueError):
                    continue

        num_trades = len(pnl_trades)

        if num_trades == 0:
            return {
                "win_rate": 0.0,
                "payoff_ratio": 0.0,
                "expectancy": 0.0,
                "max_drawdown": 0.0,
                "sharpe_ratio": 0.0,
                "profit_factor": 0.0,
                "num_trades": 0,
                "total_pnl": 0.0,
                "pnl_by_grid": {},
                "pnl_by_symbol": {},
                "pnl_by_regime": {},
            }

        # --- Classificacao ganho / perda ---
        wins = [t for t in pnl_trades if t["pnl"] > 0]
        losses = [t for t in pnl_trades if t["pnl"] < 0]
        breakevens = [t for t in pnl_trades if t["pnl"] == 0]

        num_wins = len(wins)
        num_losses = len(losses)
        win_rate = num_wins / num_trades if num_trades > 0 else 0.0

        avg_win = sum(t["pnl"] for t in wins) / num_wins if num_wins > 0 else 0.0
        avg_loss_abs = (
            abs(sum(t["pnl"] for t in losses)) / num_losses
            if num_losses > 0
            else 0.0
        )

        # Payoff ratio (avg_win / avg_loss)
        payoff_ratio = avg_win / avg_loss_abs if avg_loss_abs > 0 else float("inf")

        # Expectancy
        prob_win = num_wins / num_trades if num_trades > 0 else 0.0
        prob_loss = num_losses / num_trades if num_trades > 0 else 0.0
        expectancy = (prob_win * avg_win) - (prob_loss * avg_loss_abs)

        # Profit factor
        gross_profit = sum(t["pnl"] for t in wins)
        gross_loss = abs(sum(t["pnl"] for t in losses))
        profit_factor = (
            gross_profit / gross_loss if gross_loss > 0 else float("inf")
        )

        # Total P&L
        total_pnl = sum(t["pnl"] for t in pnl_trades)

        # --- Max Drawdown (sobre equity cumulativa) ---
        equity_curve: list[float] = []
        cumulative = 0.0
        for t in pnl_trades:
            cumulative += t["pnl"]
            equity_curve.append(cumulative)

        max_drawdown = self._compute_max_drawdown(equity_curve)

        # --- Sharpe Ratio (rolling 30 dias, annualizado) ---
        sharpe_ratio = self._compute_sharpe(pnl_trades, window_days=30)

        # --- P&L por grid / simbolo / regime ---
        pnl_by_grid: dict[str, float] = {}
        pnl_by_symbol: dict[str, float] = {}
        pnl_by_regime: dict[str, float] = {}

        for t in pnl_trades:
            gid = t.get("grid_id") or "unknown"
            sym = t.get("symbol") or "unknown"
            reg = t.get("regime") or "unknown"

            pnl_by_grid[gid] = pnl_by_grid.get(gid, 0.0) + t["pnl"]
            pnl_by_symbol[sym] = pnl_by_symbol.get(sym, 0.0) + t["pnl"]
            pnl_by_regime[reg] = pnl_by_regime.get(reg, 0.0) + t["pnl"]

        return {
            "win_rate": round(win_rate, 4),
            "payoff_ratio": round(payoff_ratio, 4) if payoff_ratio != float("inf") else None,
            "expectancy": round(expectancy, 4),
            "max_drawdown": round(max_drawdown, 4),
            "sharpe_ratio": round(sharpe_ratio, 4),
            "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else None,
            "num_trades": num_trades,
            "total_pnl": round(total_pnl, 4),
            "pnl_by_grid": {k: round(v, 4) for k, v in pnl_by_grid.items()},
            "pnl_by_symbol": {k: round(v, 4) for k, v in pnl_by_symbol.items()},
            "pnl_by_regime": {k: round(v, 4) for k, v in pnl_by_regime.items()},
        }

    # ------------------------------------------------------------------
    # Auxiliares de calculo
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_max_drawdown(equity_curve: list[float]) -> float:
        """
        Calcula o max drawdown absoluto sobre uma curva de equity cumulativa.
        Devolve um valor positivo (ex: 150.0 significa queda maxima de 150).
        """
        if not equity_curve:
            return 0.0

        peak = equity_curve[0]
        max_dd = 0.0

        for value in equity_curve:
            if value > peak:
                peak = value
            dd = peak - value
            if dd > max_dd:
                max_dd = dd

        return max_dd

    @staticmethod
    def _compute_sharpe(
        pnl_trades: list[dict[str, Any]],
        window_days: int = 30,
        risk_free_rate: float = 0.0,
    ) -> float:
        """
        Calcula o Sharpe ratio annualizado sobre os retornos diarios
        dos ultimos ``window_days`` dias.

        Agrupa os trades por dia, soma o pnl diario e calcula
        mean / std dos retornos diarios.  Annualiza por sqrt(252).
        """
        if not pnl_trades:
            return 0.0

        # Determinar a data-limite
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=window_days)

        # Agrupar pnl por dia (dentro da janela)
        daily_pnl: dict[str, float] = {}
        for t in pnl_trades:
            ts_raw = t.get("timestamp")
            if ts_raw is None:
                continue
            try:
                if isinstance(ts_raw, str):
                    # Suporta ISO com e sem timezone
                    ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                else:
                    ts = ts_raw
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue

            if ts < cutoff:
                continue

            day_key = ts.strftime("%Y-%m-%d")
            daily_pnl[day_key] = daily_pnl.get(day_key, 0.0) + t["pnl"]

        if len(daily_pnl) < 2:
            return 0.0

        returns = list(daily_pnl.values())
        mean_ret = sum(returns) / len(returns)
        variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
        std_ret = math.sqrt(variance) if variance > 0 else 0.0

        if std_ret == 0.0:
            return 0.0

        daily_sharpe = (mean_ret - risk_free_rate) / std_ret
        annualized_sharpe = daily_sharpe * math.sqrt(252)
        return annualized_sharpe

    # ------------------------------------------------------------------
    # save_metrics
    # ------------------------------------------------------------------

    def save_metrics(self, metrics: dict[str, Any]) -> None:
        """
        Guarda as metricas em ``data/metrics.json``.

        Preserva a equity_curve existente e actualiza apenas o bloco
        ``metrics`` e o ``last_updated``.
        """
        try:
            with self._metrics_path.open("r", encoding="utf-8") as fh:
                existing = json.load(fh)
        except (json.JSONDecodeError, FileNotFoundError):
            existing = {"equity_curve": [], "metrics": {}}

        existing["metrics"] = metrics
        existing["last_updated"] = datetime.now(timezone.utc).isoformat()

        tmp_path = self._metrics_path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as fh:
            json.dump(existing, fh, indent=2, ensure_ascii=False, default=str)
        tmp_path.replace(self._metrics_path)

        logger.info("Metricas guardadas em %s", self._metrics_path)

    # ------------------------------------------------------------------
    # get_daily_summary
    # ------------------------------------------------------------------

    def get_daily_summary(self, date: str | None = None) -> dict[str, Any]:
        """
        Resumo diario: contagem de trades, win rate, P&L, drawdown,
        grids activas.

        :param date: Data no formato ``YYYY-MM-DD``.  Se None, usa hoje.
        """
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        trades = self._read_trades_file()["trades"]

        # Filtrar trades do dia
        day_trades: list[dict[str, Any]] = []
        for t in trades:
            ts_raw = t.get("timestamp")
            if ts_raw is None:
                continue
            try:
                ts_str = str(ts_raw)[:10]  # YYYY-MM-DD
            except Exception:
                continue
            if ts_str == date:
                day_trades.append(t)

        # Trades com pnl numerico
        pnl_trades: list[dict[str, Any]] = []
        for t in day_trades:
            pnl = t.get("pnl")
            if pnl is not None:
                try:
                    pnl_trades.append({**t, "pnl": float(pnl)})
                except (TypeError, ValueError):
                    continue

        num_trades = len(day_trades)
        num_pnl = len(pnl_trades)

        wins = [t for t in pnl_trades if t["pnl"] > 0]
        win_rate = len(wins) / num_pnl if num_pnl > 0 else 0.0
        total_pnl = sum(t["pnl"] for t in pnl_trades)

        # Drawdown do dia
        equity: list[float] = []
        cumulative = 0.0
        for t in pnl_trades:
            cumulative += t["pnl"]
            equity.append(cumulative)
        drawdown = self._compute_max_drawdown(equity)

        # Grids activas (grid_ids distintos com compras)
        active_grids: set[str] = set()
        for t in day_trades:
            gid = t.get("grid_id")
            if gid:
                active_grids.add(str(gid))

        return {
            "date": date,
            "trades_count": num_trades,
            "win_rate": round(win_rate, 4),
            "total_pnl": round(total_pnl, 4),
            "drawdown": round(drawdown, 4),
            "active_grids": sorted(active_grids),
            "num_active_grids": len(active_grids),
        }


# ---------------------------------------------------------------------------
# TelegramNotifier
# ---------------------------------------------------------------------------

class TelegramNotifier:
    """
    Notificacoes assincronas via Telegram Bot API usando aiohttp.

    Todas as chamadas HTTP tem timeout de 10 segundos para nao bloquear
    o loop principal do bot.
    """

    BASE_URL = "https://api.telegram.org/bot{token}/sendMessage"
    TIMEOUT_SECONDS = 10

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self._logger = logging.getLogger(__name__)
        self._bot_token: str = bot_token
        self._chat_id: str = chat_id
        self._token: str = bot_token
        self._url: str = self.BASE_URL.format(token=self._bot_token)
        self.enabled: bool = bool(bot_token and chat_id)

    # ------------------------------------------------------------------
    # send_message — metodo base
    # ------------------------------------------------------------------

    async def _send(self, text: str) -> bool:
        """Envia mensagem Telegram de forma assíncrona e silenciosa."""
        if not self.enabled:
            return False
        try:
            url = f"https://api.telegram.org/bot{self._token}/sendMessage"
            payload = {"chat_id": self._chat_id, "text": text, "parse_mode": "HTML"}
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status != 200:
                        self._logger.warning("Telegram: resposta %d", resp.status)
                        return False
                    return True
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("Telegram send falhou: %s", exc)
            return False

    async def send_message(self, message: str) -> bool:
        """
        Envia uma mensagem de texto via Telegram Bot API.

        Utiliza ``aiohttp`` com timeout de 10 s.  Devolve ``True`` se
        a mensagem foi enviada com sucesso, ``False`` caso contrario
        (sem levantar excepcoes — o bot deve continuar a funcionar).
        """
        return await self._send(message)

    # ------------------------------------------------------------------
    # Notificacoes formatadas
    # ------------------------------------------------------------------

    async def notify_grid_opened(
        self,
        symbol: str,
        regime: str,
        levels: int,
        spacing: float,
        center: float,
        confidence: str,
    ) -> None:
        """Notificacao de abertura de nova grid."""
        msg = (
            "\U0001F4CA <b>NOVA GRID ABERTA</b>\n"
            "\n"
            f"\U0001F4B9 Simbolo: <code>{symbol}</code>\n"
            f"\U0001F30D Regime: <code>{regime}</code>\n"
            f"\U0001F4C9 Niveis: <code>{levels}</code>\n"
            f"\U0001F4CF Espacamento: <code>{spacing:.4f}</code>\n"
            f"\U0001F3AF Centro: <code>{center:.4f}</code>\n"
            f"\U0001F50D Confianca: <code>{confidence}</code>\n"
        )
        await self.send_message(msg)

    async def notify_buy_executed(
        self,
        symbol: str,
        level: int,
        price: float,
        qty: int,
        stop: float,
        target: float,
        grid_id: str,
    ) -> None:
        """Notificacao de compra executada."""
        msg = (
            "\U0001F7E2 <b>COMPRA EXECUTADA</b>\n"
            "\n"
            f"\U0001F4B9 Simbolo: <code>{symbol}</code>\n"
            f"\U0001F522 Nivel: <code>{level}</code>\n"
            f"\U0001F4B0 Preco: <code>{price:.4f}</code>\n"
            f"\U0001F4E6 Quantidade: <code>{qty}</code>\n"
            f"\U0001F6D1 Stop-loss: <code>{stop:.4f}</code>\n"
            f"\U0001F3AF Take-profit: <code>{target:.4f}</code>\n"
            f"\U0001F5C2 Grid: <code>{grid_id}</code>\n"
        )
        await self.send_message(msg)

    async def notify_sell_executed(
        self,
        symbol: str,
        level: int,
        price: float,
        pnl: float,
        grid_pnl: float,
    ) -> None:
        """Notificacao de venda executada."""
        pnl_emoji = "\U0001F4B0" if pnl >= 0 else "\U0001F4B8"
        msg = (
            "\U0001F534 <b>VENDA EXECUTADA</b>\n"
            "\n"
            f"\U0001F4B9 Simbolo: <code>{symbol}</code>\n"
            f"\U0001F522 Nivel: <code>{level}</code>\n"
            f"\U0001F4B0 Preco: <code>{price:.4f}</code>\n"
            f"{pnl_emoji} P&L operacao: <code>{pnl:+.2f}</code>\n"
            f"\U0001F4CA P&L grid: <code>{grid_pnl:+.2f}</code>\n"
        )
        await self.send_message(msg)

    async def notify_stop_hit(
        self,
        symbol: str,
        level: int,
        loss: float,
        daily_pnl_pct: float,
        kill_switch: bool,
    ) -> None:
        """Notificacao de stop-loss atingido."""
        status = (
            "\U0001F6D1 <b>KILL SWITCH ACTIVADO</b>"
            if kill_switch
            else "\U00002705 Bot continua activo"
        )
        msg = (
            "\U000026A0\U0000FE0F <b>STOP-LOSS ATINGIDO</b>\n"
            "\n"
            f"\U0001F4B9 Simbolo: <code>{symbol}</code>\n"
            f"\U0001F522 Nivel: <code>{level}</code>\n"
            f"\U0001F4B8 Perda: <code>{loss:+.2f}</code>\n"
            f"\U0001F4C9 P&L diario: <code>{daily_pnl_pct:+.2f}%</code>\n"
            f"\U0001F6A6 Estado: {status}\n"
        )
        await self.send_message(msg)

    async def notify_kill_switch(self, monthly_dd: float) -> None:
        """Notificacao de activacao do kill switch."""
        msg = (
            "\U0001F6D1 <b>KILL SWITCH ATIVADO</b>\n"
            "\n"
            f"\U0001F4C9 Drawdown mensal: <code>{monthly_dd:+.2f}%</code>\n"
            f"\U000026A0\U0000FE0F Todas as posicoes estao a ser encerradas.\n"
            "\U0001F512 Bot pausado — requer reinicio manual.\n"
        )
        await self.send_message(msg)

    async def notify_regime_change(
        self,
        symbol: str,
        old_regime: str,
        new_regime: str,
    ) -> None:
        """Notificacao de mudanca de regime de mercado."""
        msg = (
            "\U0001F504 <b>REGIME CHANGED</b>\n"
            "\n"
            f"\U0001F4B9 Simbolo: <code>{symbol}</code>\n"
            f"\U0001F519 Anterior: <code>{old_regime}</code>\n"
            f"\U000027A1\U0000FE0F Novo: <code>{new_regime}</code>\n"
            "\U0001F50D Reavaliando grids activas...\n"
        )
        await self.send_message(msg)

    async def notify_daily_summary(self, summary: dict[str, Any]) -> None:
        """Notificacao com o resumo diario."""
        date = summary.get("date", "—")
        trades_count = summary.get("trades_count", 0)
        win_rate = summary.get("win_rate", 0.0)
        total_pnl = summary.get("total_pnl", 0.0)
        drawdown = summary.get("drawdown", 0.0)
        num_grids = summary.get("num_active_grids", 0)

        pnl_emoji = "\U0001F4B0" if total_pnl >= 0 else "\U0001F4B8"

        msg = (
            "\U0001F4C8 <b>RESUMO DIARIO</b>\n"
            "\n"
            f"\U0001F4C5 Data: <code>{date}</code>\n"
            f"\U0001F4CA Trades: <code>{trades_count}</code>\n"
            f"\U0001F3AF Win rate: <code>{win_rate:.1%}</code>\n"
            f"{pnl_emoji} P&L: <code>{total_pnl:+.2f}</code>\n"
            f"\U0001F4C9 Drawdown: <code>{drawdown:.2f}</code>\n"
            f"\U0001F5C2 Grids activas: <code>{num_grids}</code>\n"
        )
        await self.send_message(msg)

    async def notify_error(self, error_msg: str) -> None:
        """Notificacao de erro critico."""
        msg = (
            "\U0000274C <b>ERRO</b>\n"
            "\n"
            f"\U0001F4AC <code>{error_msg}</code>\n"
        )
        await self.send_message(msg)

    async def notify_operational_alert(self, message: str) -> None:
        """Alerta operacional generico."""
        msg = (
            "\U0001F6A8 <b>ALERTA OPERACIONAL</b>\n"
            "\n"
            f"\U0001F4AC <code>{message}</code>\n"
        )
        await self.send_message(msg)

    async def notify_warmup_waiting(self, symbol: str, missing_rules: list[str]) -> None:
        """Notificacao de warm-up insuficiente."""
        joined = ", ".join(missing_rules)
        msg = (
            "\U000023F3 <b>WARM-UP INSUFICIENTE</b>\n"
            "\n"
            f"\U0001F4B9 Simbolo: <code>{symbol}</code>\n"
            f"\U0001F4DA Em falta: <code>{joined}</code>\n"
            "\U0001F6D1 Trading pausado ate existirem barras suficientes.\n"
        )
        await self.send_message(msg)

    async def notify_reconciliation(self, message: str) -> None:
        """Notificacao do resultado de reconciliacao de arranque."""
        msg = (
            "\U0001F9FE <b>RECONCILIACAO DE ARRANQUE</b>\n"
            "\n"
            f"\U0001F4AC <code>{message}</code>\n"
        )
        await self.send_message(msg)

    async def notify_session_status(
        self,
        symbol: str,
        status: str,
        opens_at: str | None = None,
        closes_at: str | None = None,
    ) -> None:
        """Notificacao de transicao de sessao de mercado."""
        open_line = f"\U0001F513 Abre: <code>{opens_at}</code>\n" if opens_at else ""
        close_line = f"\U0001F512 Fecha: <code>{closes_at}</code>\n" if closes_at else ""
        msg = (
            "\U0001F551 <b>SESSAO DE MERCADO</b>\n"
            "\n"
            f"\U0001F4B9 Simbolo: <code>{symbol}</code>\n"
            f"\U0001F6A6 Estado: <code>{status}</code>\n"
            f"{open_line}"
            f"{close_line}"
        )
        await self.send_message(msg)

    async def notify_connection_status(self, connected: bool) -> None:
        """Notificacao de estado da ligacao (IB Gateway, etc.)."""
        if connected:
            msg = (
                "\U00002705 <b>LIGACAO ESTABELECIDA</b>\n"
                "\n"
                "\U0001F4E1 Bot ligado ao gateway com sucesso.\n"
            )
        else:
            msg = (
                "\U0001F534 <b>LIGACAO PERDIDA</b>\n"
                "\n"
                "\U000026A0\U0000FE0F Ligacao ao gateway interrompida.\n"
                "\U0001F504 A tentar reconectar...\n"
            )
        await self.send_message(msg)

    async def notify_startup(
        self,
        *,
        mode: str,
        watchlist: list[str],
        capital: float,
        port: int,
        version: str,
        timestamp_utc: str,
    ) -> None:
        """Mensagem de arranque do bot."""
        msg = (
            "\U0001F916 <b>Bot iniciado</b>\n"
            f"Modo: <code>{mode}</code>\n"
            f"Watchlist: <code>{', '.join(watchlist)}</code>\n"
            f"Capital: <code>${capital:.2f}</code>\n"
            f"Porta IB: <code>{port}</code>\n"
            f"Versao: <code>{version}</code>\n"
            f"Hora: <code>{timestamp_utc}</code>\n"
        )
        await self.send_message(msg)

    async def notify_shutdown(self, timestamp_utc: str) -> None:
        """Mensagem de encerramento gracioso."""
        msg = (
            "\U0001F6D1 <b>Bot encerrado</b>\n"
            f"Hora: <code>{timestamp_utc}</code>\n"
        )
        await self.send_message(msg)

    async def notify_reconnect_resumed(self, timestamp_utc: str) -> None:
        """Mensagem apos reconexao bem-sucedida."""
        msg = (
            "\u2705 <b>IB reconectado. Operacao retomada.</b>\n"
            f"Hora: <code>{timestamp_utc}</code>\n"
        )
        await self.send_message(msg)

    async def trade_opened(
        self,
        symbol: str,
        action: str,
        entry: float,
        stop: float,
        tp: float,
        confidence: int,
        module: str,
        regime: str,
        paper: bool = True,
    ) -> None:
        """Notifica a abertura de um trade."""
        emoji = "🟢" if action == "BUY" else "🔴"
        await self._send(
            f"{emoji} <b>Trade Aberto</b> {'📄 PAPER' if paper else '💰 LIVE'}\n"
            f"──────────────────\n"
            f"📌 <b>{symbol}</b> | {action}\n"
            f"📦 Módulo: {module} | 📊 Regime: {regime}\n"
            f"──────────────────\n"
            f"🎯 Entry: <code>{entry:.4f}</code>\n"
            f"🛑 Stop:  <code>{stop:.4f}</code>\n"
            f"✅ TP:    <code>{tp:.4f}</code>\n"
            f"⭐ Confidence: {confidence}/3"
        )

    async def trade_closed(
        self,
        symbol: str,
        action: str,
        entry: float,
        exit_price: float,
        pnl: float,
        module: str,
        paper: bool = True,
    ) -> None:
        """Notifica o fecho de um trade."""
        emoji = "💰" if pnl >= 0 else "💸"
        result = "WIN ✅" if pnl >= 0 else "LOSS ❌"
        await self._send(
            f"{emoji} <b>Trade Fechado</b> {'📄 PAPER' if paper else '💰 LIVE'}\n"
            f"──────────────────\n"
            f"📌 <b>{symbol}</b> | {action} | {result}\n"
            f"📦 Módulo: {module}\n"
            f"──────────────────\n"
            f"🎯 Entry: <code>{entry:.4f}</code>\n"
            f"🏁 Exit:  <code>{exit_price:.4f}</code>\n"
            f"📈 P&L:   <code>€{pnl:+.2f}</code>"
        )

    async def kill_switch_warning(
        self,
        level: str,
        current_pct: float,
        limit_pct: float,
        paper: bool = True,
    ) -> None:
        """Notifica aproximação a um kill switch."""
        ratio = current_pct / limit_pct if limit_pct > 0 else 0.0
        emoji = "🚨" if ratio >= 0.90 else "⚠️"
        await self._send(
            f"{emoji} <b>Kill Switch {level.upper()}</b> {'📄 PAPER' if paper else '💰 LIVE'}\n"
            f"──────────────────\n"
            f"📉 Actual: <code>{current_pct * 100:.2f}%</code>\n"
            f"🛑 Limite: <code>{limit_pct * 100:.1f}%</code>\n"
            f"📊 Usado:  <code>{ratio * 100:.0f}%</code> do limite\n"
            f"{'🚨 <b>PRÓXIMO DO LIMITE</b>' if ratio >= 0.90 else '⚠️ Monitorizar'}"
        )

    async def kill_switch_triggered(
        self,
        level: str,
        current_pct: float,
        paper: bool = True,
    ) -> None:
        """Notifica activação de kill switch."""
        await self._send(
            f"🚨🚨 <b>KILL SWITCH ACTIVADO</b> 🚨🚨\n"
            f"──────────────────\n"
            f"🛑 Nível: <b>{level.upper()}</b> {'📄 PAPER' if paper else '💰 LIVE'}\n"
            f"📉 Perda: <code>{current_pct * 100:.2f}%</code>\n"
            f"──────────────────\n"
            f"⛔ Bot pausado. Usa /status para verificar."
        )

    async def grid_exhausted(
        self,
        symbol: str,
        regime: str,
        levels_used: int,
        module: str,
        paper: bool = True,
    ) -> None:
        """Notifica quando uma grid fica exausta."""
        await self._send(
            f"🔲 <b>Grid Exausto</b> {'📄 PAPER' if paper else '💰 LIVE'}\n"
            f"──────────────────\n"
            f"📌 <b>{symbol}</b> | 📦 {module} | 📊 {regime}\n"
            f"📐 Níveis usados: {levels_used}\n"
            f"ℹ️ Níveis stopped não reabrem (zero averaging down)."
        )

    async def bot_started(
        self,
        version: str = "v2.0",
        paper: bool = True,
        symbols: list[str] | None = None,
    ) -> None:
        """Notifica o arranque do bot."""
        syms = ", ".join((symbols or [])[:5])
        if symbols and len(symbols) > 5:
            syms += "..."
        await self._send(
            f"🤖 <b>Bot Trading Arrancou</b>\n"
            f"──────────────────\n"
            f"🏷️ Versão: {version} | ⚙️ {'📄 PAPER' if paper else '💰 LIVE'}\n"
            f"📋 Símbolos: {syms or '—'}\n"
            f"✅ Todos os sistemas operacionais."
        )

    async def bot_stopped(
        self,
        reason: str = "shutdown normal",
        paper: bool = True,
    ) -> None:
        """Notifica o encerramento do bot."""
        await self._send(
            f"🔌 <b>Bot Parado</b> {'📄 PAPER' if paper else '💰 LIVE'}\n"
            f"──────────────────\n"
            f"📝 Motivo: {reason}"
        )

    async def ib_reconnect(self, attempt: int, paper: bool = True) -> None:
        """Notifica tentativa de reconnect ao IB."""
        await self._send(
            f"🔌 <b>IB Reconnect #{attempt}</b> {'📄 PAPER' if paper else '💰 LIVE'}\n"
            f"⏳ A aguardar ligação..."
        )

    async def critical_error(
        self,
        error: str,
        location: str = "main loop",
        paper: bool = True,
    ) -> None:
        """Notifica erro crítico do bot."""
        short = error[:300] + "..." if len(error) > 300 else error
        await self._send(
            f"❌ <b>Erro Crítico</b> {'📄 PAPER' if paper else '💰 LIVE'}\n"
            f"──────────────────\n"
            f"📍 Local: {location}\n"
            f"🔎 <code>{short}</code>\n"
            f"⚠️ Verificar logs imediatamente."
        )

    async def daily_report(
        self,
        capital: float,
        daily_pnl: float,
        n_trades: int,
        win_rate: float,
        open_grids: int,
        kill_switch_pct: dict[str, float],
        paper: bool = True,
    ) -> None:
        """Envia um report diário resumido."""
        trend = "📈" if daily_pnl >= 0 else "📉"
        await self._send(
            f"📊 <b>Report Diário</b> {'📄 PAPER' if paper else '💰 LIVE'}\n"
            f"──────────────────\n"
            f"💶 Capital:   <code>€{capital:,.2f}</code>\n"
            f"{trend} P&L hoje: <code>€{daily_pnl:+.2f}</code>\n"
            f"🔢 Trades:   {n_trades} | 🏆 Win Rate: {win_rate:.1f}%\n"
            f"🔲 Grids:    {open_grids} abertos\n"
            f"──────────────────\n"
            f"🛡️ Kill Switches:\n"
            f"  D:{kill_switch_pct.get('daily', 0) * 100:.2f}%/3% "
            f"  W:{kill_switch_pct.get('weekly', 0) * 100:.2f}%/6% "
            f"  M:{kill_switch_pct.get('monthly', 0) * 100:.2f}%/10%"
        )

    async def poll_commands(self, status_callback: Any) -> None:
        """Polling a cada 10 segundos para /status e /help."""
        if not self.enabled:
            return

        last_update_id = 0
        while True:
            try:
                await asyncio.sleep(10)
                url = (
                    f"https://api.telegram.org/bot{self._token}"
                    f"/getUpdates?offset={last_update_id + 1}&timeout=5"
                )
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url,
                        timeout=aiohttp.ClientTimeout(total=8),
                    ) as resp:
                        if resp.status != 200:
                            continue
                        data = await resp.json()

                for update in data.get("result", []):
                    last_update_id = update.get("update_id", last_update_id)
                    message = update.get("message", {})
                    text = str(message.get("text", "")).strip().lower()
                    chat = str(message.get("chat", {}).get("id", ""))
                    if chat != str(self._chat_id):
                        continue
                    if text == "/status":
                        await self._send(await status_callback())
                    elif text == "/help":
                        await self._send(
                            "🤖 <b>Comandos disponíveis</b>\n"
                            "──────────────────\n"
                            "/status → Estado actual do bot\n"
                            "/help   → Esta mensagem\n"
                            "──────────────────\n"
                            "Notificações automáticas:\n"
                            "🟢 Trades abertos\n"
                            "🔴 Trades fechados\n"
                            "⚠️ Kill switches\n"
                            "📊 Report diário\n"
                            "❌ Erros críticos"
                        )
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                self._logger.debug("Telegram polling (silencioso): %s", exc)
