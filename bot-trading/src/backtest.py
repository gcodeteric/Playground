"""Motor de backtesting do bot de grid trading. """  # Backtest

from __future__ import annotations  # Backtest

import argparse  # Backtest
import csv  # Backtest
import logging  # Backtest
import math  # Backtest
import tempfile  # Backtest
from dataclasses import dataclass  # Backtest
from pathlib import Path  # Backtest

import pandas as pd  # Backtest

from src.grid_engine import Grid, GridEngine  # Backtest
from src.risk_manager import RiskManager  # Backtest
from src.signal_engine import (  # Backtest
    SignalResult,  # Backtest
    analyze,  # Backtest
    calculate_atr,  # Backtest
    calculate_bollinger_bands,  # Backtest
    calculate_rsi2,  # Backtest
    calculate_sma,  # Backtest
    calculate_volume_avg,  # Backtest
    kotegawa_signal,  # Backtest
)  # Backtest

logger = logging.getLogger(__name__)  # Backtest


@dataclass(slots=True)  # Backtest
class BacktestConfig:  # Backtest
    """Configuração do backtest. """  # Backtest

    symbol: str  # Backtest
    start_date: str  # Backtest
    end_date: str  # Backtest
    initial_capital: float  # Backtest
    data_csv_path: str  # Backtest
    commission_per_trade: float = 1.0  # Backtest
    slippage_pct: float = 0.05  # Backtest


@dataclass(slots=True)  # Backtest
class BacktestTrade:  # Backtest
    """Trade individual do backtest. """  # Backtest

    symbol: str  # Backtest
    entry_date: str  # Backtest
    exit_date: str | None  # Backtest
    entry_price: float  # Backtest
    exit_price: float | None  # Backtest
    quantity: int  # Backtest
    side: str  # Backtest
    pnl: float | None  # Backtest
    regime: str  # Backtest
    confidence: str  # Backtest
    grid_id: str  # Backtest
    level: int  # Backtest
    kairi_at_entry: float  # Backtest
    rsi2_at_entry: float | None  # Backtest
    atr_at_entry: float  # Backtest


@dataclass(slots=True)  # Backtest
class BacktestResult:  # Backtest
    """Resultado completo do backtest. """  # Backtest

    config: BacktestConfig  # Backtest
    trades: list[BacktestTrade]  # Backtest
    equity_curve: list[tuple[str, float]]  # Backtest
    total_return_pct: float  # Backtest
    annualized_return_pct: float  # Backtest
    max_drawdown_pct: float  # Backtest
    max_drawdown_duration_days: int  # Backtest
    sharpe_ratio: float  # Backtest
    sortino_ratio: float  # Backtest
    profit_factor: float  # Backtest
    total_trades: int  # Backtest
    win_rate: float  # Backtest
    avg_win: float  # Backtest
    avg_loss: float  # Backtest
    avg_rr_realized: float  # Backtest
    best_trade_pnl: float  # Backtest
    worst_trade_pnl: float  # Backtest
    total_signals: int  # Backtest
    signals_triggered_pct: float  # Backtest
    avg_kairi_at_entry: float  # Backtest
    avg_hold_bars: float  # Backtest
    regime_stats: dict[str, dict[str, float | int]]  # Backtest


class BacktestEngine:  # Backtest
    """  # Backtest
    Motor de backtesting para o bot de grid trading.  # Backtest
    Reutiliza signal_engine, grid_engine e risk_manager  # Backtest
    sem qualquer modificação. # Backtest  # Backtest
    """  # Backtest

    def __init__(self, config: BacktestConfig) -> None:  # Backtest
        self.config = config  # Backtest
        self.risk_manager = RiskManager(  # Backtest
            capital=config.initial_capital,  # Backtest
            risk_per_level=0.01,  # Backtest
            kelly_cap=0.05,  # Backtest
            stop_atr_mult=1.0,  # Backtest
            tp_atr_mult=2.5,  # Backtest
            daily_loss_limit=0.03,  # Backtest
            weekly_loss_limit=0.06,  # Backtest
            monthly_dd_limit=0.10,  # Backtest
            max_positions=10,  # Backtest
            max_grids=5,  # Backtest
            min_rr=2.5,  # Backtest
        )  # Backtest
        temp_data_dir = Path(tempfile.gettempdir()) / "backtest"  # Backtest
        temp_data_dir.mkdir(parents=True, exist_ok=True)  # Backtest
        self.grid_engine = GridEngine(data_dir=temp_data_dir)  # Backtest
        self.cash = config.initial_capital  # Backtest
        self.capital = config.initial_capital  # Backtest
        self.trades: list[BacktestTrade] = []  # Backtest
        self.equity_curve: list[tuple[str, float]] = []  # Backtest
        self._hold_bars: list[int] = []  # Backtest
        self._total_signals: int = 0  # Backtest
        self._triggered_signals: int = 0  # Backtest
        self._open_trade_meta: dict[tuple[str, int], tuple[int, int]] = {}  # Backtest

    def load_data(self) -> pd.DataFrame:  # Backtest
        """Carrega OHLCV de CSV. Colunas: date,open,high,low,close,volume."""  # Backtest
        csv_path = Path(self.config.data_csv_path)  # Backtest
        df = pd.read_csv(csv_path, parse_dates=["date"])  # Backtest
        df.columns = [str(column).lower() for column in df.columns]  # Backtest
        df = df.sort_values("date").reset_index(drop=True)  # Backtest
        required = ["date", "open", "high", "low", "close", "volume"]  # Backtest
        if not all(column in df.columns for column in required):  # Backtest
            raise AssertionError(f"CSV em falta colunas: {required}")  # Backtest
        for column in ["open", "high", "low", "close", "volume"]:  # Backtest
            df[column] = pd.to_numeric(df[column], errors="coerce")  # Backtest
        return df.dropna(subset=required).reset_index(drop=True)  # Backtest

    def _mark_to_market_equity(  # Backtest
        self,  # Backtest
        active_grids: list[Grid],  # Backtest
        current_price: float,  # Backtest
    ) -> float:  # Backtest
        equity = self.cash  # Backtest
        for grid in active_grids:  # Backtest
            for level in grid.levels:  # Backtest
                if level.status == "bought":  # Backtest
                    equity += current_price * level.quantity  # Backtest
        return equity  # Backtest

    def _record_trade_entry(  # Backtest
        self,  # Backtest
        *,  # Backtest
        date_str: str,  # Backtest
        grid: Grid,  # Backtest
        level: int,  # Backtest
        quantity: int,  # Backtest
        entry_price: float,  # Backtest
        kairi: float,  # Backtest
        rsi2_value: float | None,  # Backtest
        atr_value: float,  # Backtest
        bar_index: int,  # Backtest
    ) -> None:  # Backtest
        trade = BacktestTrade(  # Backtest
            symbol=self.config.symbol,  # Backtest
            entry_date=date_str,  # Backtest
            exit_date=None,  # Backtest
            entry_price=entry_price,  # Backtest
            exit_price=None,  # Backtest
            quantity=quantity,  # Backtest
            side="BUY",  # Backtest
            pnl=None,  # Backtest
            regime=grid.regime,  # Backtest
            confidence=grid.confidence,  # Backtest
            grid_id=grid.id,  # Backtest
            level=level,  # Backtest
            kairi_at_entry=kairi,  # Backtest
            rsi2_at_entry=rsi2_value,  # Backtest
            atr_at_entry=atr_value,  # Backtest
        )  # Backtest
        self.trades.append(trade)  # Backtest
        self._open_trade_meta[(grid.id, level)] = (len(self.trades) - 1, bar_index)  # Backtest

    def _close_trade(  # Backtest
        self,  # Backtest
        *,  # Backtest
        grid: Grid,  # Backtest
        level: int,  # Backtest
        date_str: str,  # Backtest
        fill_price: float,  # Backtest
        pnl: float,  # Backtest
        side: str,  # Backtest
        bar_index: int,  # Backtest
    ) -> None:  # Backtest
        trade_meta = self._open_trade_meta.pop((grid.id, level), None)  # Backtest
        if trade_meta is None:  # Backtest
            return  # Backtest
        trade_index, entry_bar_index = trade_meta  # Backtest
        trade = self.trades[trade_index]  # Backtest
        trade.exit_date = date_str  # Backtest
        trade.exit_price = fill_price  # Backtest
        trade.pnl = pnl  # Backtest
        trade.side = side  # Backtest
        self._hold_bars.append(max(1, bar_index - entry_bar_index))  # Backtest

    def run(self) -> BacktestResult:  # Backtest
        """Executa o backtest barra a barra. # Backtest"""  # Backtest
        df = self.load_data()  # Backtest
        start_ts = pd.Timestamp(self.config.start_date)  # Backtest
        end_ts = pd.Timestamp(self.config.end_date)  # Backtest
        mask = (df["date"] >= start_ts) & (df["date"] <= end_ts)  # Backtest
        df = df.loc[mask].reset_index(drop=True)  # Backtest

        if len(df) < 220:  # Backtest
            raise ValueError("Dados insuficientes para backtest (mínimo 220 barras)")  # Backtest

        active_grids: list[Grid] = []  # Backtest

        for i in range(200, len(df)):  # Backtest
            bar = df.iloc[i]  # Backtest
            date_str = pd.Timestamp(bar["date"]).strftime("%Y-%m-%d")  # Backtest
            hist = df.iloc[: i + 1]  # Backtest
            closes = hist["close"].astype(float).tolist()  # Backtest
            highs = hist["high"].astype(float).tolist()  # Backtest
            lows = hist["low"].astype(float).tolist()  # Backtest
            volumes = hist["volume"].astype(float).tolist()  # Backtest
            price = float(bar["close"])  # Backtest

            regime_info = None  # Backtest
            signal_result: SignalResult | None = None  # Backtest
            atr14_val = calculate_atr(highs, lows, closes, 14) or 0.0  # Backtest
            analysis = analyze(closes, highs, lows, volumes)  # Backtest
            if analysis is not None:  # Backtest
                regime_info, analysed_signal = analysis  # Backtest
                rsi2_val = calculate_rsi2(closes)  # Backtest
                sma25 = calculate_sma(closes, 25)  # Backtest
                bb = calculate_bollinger_bands(closes, 20, 2.0)  # Backtest
                vol_avg = calculate_volume_avg(volumes, 20)  # Backtest
                rsi14 = analysed_signal.rsi  # Backtest
                bb_lower = bb[2] if bb is not None else None  # Backtest
                volume = volumes[-1]  # Backtest
                if None not in (sma25, rsi14, bb_lower, vol_avg):  # Backtest
                    signal_result = kotegawa_signal(  # Backtest
                        price=price,  # Backtest
                        sma25=float(sma25),  # Backtest
                        rsi=float(rsi14),  # Backtest
                        bb_lower=float(bb_lower),  # Backtest
                        volume=volume,  # Backtest
                        vol_avg_20=float(vol_avg),  # Backtest
                        regime=regime_info.regime.value,  # Backtest
                        sma50=calculate_sma(closes, 50),  # Backtest
                        sma200=calculate_sma(closes, 200),  # Backtest
                        rsi2=rsi2_val,  # Backtest
                    )  # Backtest

            for grid in list(active_grids):  # Backtest
                for level in grid.levels:  # Backtest
                    if level.status == "pending" and float(bar["low"]) <= level.buy_price:  # Backtest
                        fill_price = level.buy_price * (1 + self.config.slippage_pct / 100.0)  # Backtest
                        commission = self.config.commission_per_trade  # Backtest
                        level.buy_price = fill_price  # Backtest
                        self.grid_engine.on_level_bought(grid, level.level, fill_price, date_str)  # Backtest
                        self.cash -= fill_price * level.quantity + commission  # Backtest
                        entry_kairi = signal_result.deviation if signal_result is not None else 0.0  # Backtest
                        entry_rsi2 = signal_result.rsi2 if signal_result is not None else None  # Backtest
                        self._record_trade_entry(  # Backtest
                            date_str=date_str,  # Backtest
                            grid=grid,  # Backtest
                            level=level.level,  # Backtest
                            quantity=level.quantity,  # Backtest
                            entry_price=fill_price,  # Backtest
                            kairi=entry_kairi,  # Backtest
                            rsi2_value=entry_rsi2,  # Backtest
                            atr_value=atr14_val,  # Backtest
                            bar_index=i,  # Backtest
                        )  # Backtest
                    elif level.status == "bought":  # Backtest
                        if float(bar["high"]) >= level.sell_price:  # Backtest
                            fill_price = level.sell_price * (1 - self.config.slippage_pct / 100.0)  # Backtest
                            pnl = (  # Backtest
                                (fill_price - level.buy_price) * level.quantity  # Backtest
                                - (2 * self.config.commission_per_trade)  # Backtest
                            )  # Backtest
                            self.grid_engine.on_level_sold(grid, level.level, fill_price, date_str)  # Backtest
                            self.cash += (fill_price * level.quantity) - self.config.commission_per_trade  # Backtest
                            self._close_trade(  # Backtest
                                grid=grid,  # Backtest
                                level=level.level,  # Backtest
                                date_str=date_str,  # Backtest
                                fill_price=fill_price,  # Backtest
                                pnl=pnl,  # Backtest
                                side="SELL_TP",  # Backtest
                                bar_index=i,  # Backtest
                            )  # Backtest
                        elif float(bar["low"]) <= level.stop_price:  # Backtest
                            fill_price = level.stop_price * (1 - self.config.slippage_pct / 100.0)  # Backtest
                            pnl = (  # Backtest
                                (fill_price - level.buy_price) * level.quantity  # Backtest
                                - (2 * self.config.commission_per_trade)  # Backtest
                            )  # Backtest
                            self.grid_engine.on_level_stopped(grid, level.level, fill_price, date_str)  # Backtest
                            self.cash += (fill_price * level.quantity) - self.config.commission_per_trade  # Backtest
                            self._close_trade(  # Backtest
                                grid=grid,  # Backtest
                                level=level.level,  # Backtest
                                date_str=date_str,  # Backtest
                                fill_price=fill_price,  # Backtest
                                pnl=pnl,  # Backtest
                                side="SELL_SL",  # Backtest
                                bar_index=i,  # Backtest
                            )  # Backtest

            active_grids = [  # Backtest
                grid for grid in active_grids  # Backtest
                if any(level.status in ("pending", "bought") for level in grid.levels)  # Backtest
            ]  # Backtest

            if signal_result is not None and signal_result.signal:  # Backtest
                self._total_signals += 1  # Backtest

            if (  # Backtest
                signal_result is not None  # Backtest
                and signal_result.signal  # Backtest
                and signal_result.size_multiplier > 0  # Backtest
                and regime_info is not None  # Backtest
                and atr14_val > 0  # Backtest
                and len(active_grids) < 5  # Backtest
            ):  # Backtest
                num_levels = self.grid_engine.get_num_levels_for_regime(regime_info.regime.value)  # Backtest
                base_qty = self.risk_manager.position_size_per_level(  # Backtest
                    capital=self.capital,  # Backtest
                    entry=price,  # Backtest
                    stop=self.risk_manager.calculate_stop_loss(price, atr14_val),  # Backtest
                    win_rate=0.50,  # Backtest
                    payoff_ratio=2.5,  # Backtest
                    num_levels=num_levels,  # Backtest
                )  # Backtest
                if base_qty > 0:  # Backtest
                    grid = self.grid_engine.create_grid(  # Backtest
                        symbol=self.config.symbol,  # Backtest
                        center_price=price,  # Backtest
                        atr=atr14_val,  # Backtest
                        regime=regime_info.regime.value,  # Backtest
                        num_levels=num_levels,  # Backtest
                        base_quantity=base_qty,  # Backtest
                        confidence=signal_result.confianca.value,  # Backtest
                        size_multiplier=signal_result.size_multiplier,  # Backtest
                    )  # Backtest
                    active_grids.append(grid)  # Backtest
                    self._triggered_signals += 1  # Backtest

            self.capital = self._mark_to_market_equity(active_grids, price)  # Backtest
            self.risk_manager.update_capital(self.capital)  # Backtest
            self.risk_manager.update_peak_equity(self.capital)  # Backtest
            self.equity_curve.append((date_str, self.capital))  # Backtest

        return self._compile_results()  # Backtest

    def _compile_results(self) -> BacktestResult:  # Backtest
        """Compila todas as métricas do backtest. # Backtest"""  # Backtest
        closed = [trade for trade in self.trades if trade.pnl is not None]  # Backtest
        wins = [trade for trade in closed if (trade.pnl or 0.0) > 0]  # Backtest
        losses = [trade for trade in closed if (trade.pnl or 0.0) <= 0]  # Backtest

        win_rate = len(wins) / len(closed) if closed else 0.0  # Backtest
        avg_win = sum((trade.pnl or 0.0) for trade in wins) / len(wins) if wins else 0.0  # Backtest
        avg_loss = sum((trade.pnl or 0.0) for trade in losses) / len(losses) if losses else 0.0  # Backtest
        gross_profit = sum((trade.pnl or 0.0) for trade in wins)  # Backtest
        gross_loss = abs(sum((trade.pnl or 0.0) for trade in losses))  # Backtest
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")  # Backtest

        equities = [equity for _, equity in self.equity_curve]  # Backtest
        peak = self.config.initial_capital  # Backtest
        max_drawdown = 0.0  # Backtest
        drawdown_duration = 0  # Backtest
        max_drawdown_duration = 0  # Backtest
        for equity in equities:  # Backtest
            if equity >= peak:  # Backtest
                peak = equity  # Backtest
                drawdown_duration = 0  # Backtest
            else:  # Backtest
                drawdown_duration += 1  # Backtest
            drawdown = (peak - equity) / peak if peak > 0 else 0.0  # Backtest
            max_drawdown = max(max_drawdown, drawdown)  # Backtest
            max_drawdown_duration = max(max_drawdown_duration, drawdown_duration)  # Backtest

        total_return = (self.capital - self.config.initial_capital) / self.config.initial_capital  # Backtest
        daily_returns: list[float] = []  # Backtest
        for idx in range(1, len(equities)):  # Backtest
            previous = equities[idx - 1]  # Backtest
            current = equities[idx]  # Backtest
            if previous > 0:  # Backtest
                daily_returns.append((current - previous) / previous)  # Backtest

        if daily_returns:  # Backtest
            mean_ret = sum(daily_returns) / len(daily_returns)  # Backtest
            variance = sum((ret - mean_ret) ** 2 for ret in daily_returns) / len(daily_returns)  # Backtest
            std_ret = math.sqrt(variance)  # Backtest
            sharpe = (mean_ret / std_ret) * math.sqrt(252) if std_ret > 0 else 0.0  # Backtest
            negative_returns = [ret for ret in daily_returns if ret < 0]  # Backtest
            downside_variance = (  # Backtest
                sum(ret ** 2 for ret in negative_returns) / len(negative_returns)  # Backtest
                if negative_returns else 0.0  # Backtest
            )  # Backtest
            downside_std = math.sqrt(downside_variance) if downside_variance > 0 else 0.0  # Backtest
            sortino = (mean_ret / downside_std) * math.sqrt(252) if downside_std > 0 else 0.0  # Backtest
        else:  # Backtest
            sharpe = 0.0  # Backtest
            sortino = 0.0  # Backtest

        regime_stats: dict[str, dict[str, float | int]] = {}  # Backtest
        for regime in ("BULL", "BEAR", "SIDEWAYS"):  # Backtest
            regime_trades = [trade for trade in closed if trade.regime == regime]  # Backtest
            regime_wins = [trade for trade in regime_trades if (trade.pnl or 0.0) > 0]  # Backtest
            regime_stats[regime] = {  # Backtest
                "trades": len(regime_trades),  # Backtest
                "win_rate": (len(regime_wins) / len(regime_trades)) if regime_trades else 0.0,  # Backtest
                "avg_pnl": (  # Backtest
                    sum((trade.pnl or 0.0) for trade in regime_trades) / len(regime_trades)  # Backtest
                    if regime_trades else 0.0  # Backtest
                ),  # Backtest
            }  # Backtest

        trading_days = len(self.equity_curve)  # Backtest
        years = trading_days / 252 if trading_days > 0 else 0.0  # Backtest
        annualized = ((1 + total_return) ** (1 / years) - 1) if years > 0 else 0.0  # Backtest
        avg_kairi = sum(trade.kairi_at_entry for trade in self.trades) / len(self.trades) if self.trades else 0.0  # Backtest
        avg_hold_bars = sum(self._hold_bars) / len(self._hold_bars) if self._hold_bars else 0.0  # Backtest
        triggered_pct = (self._triggered_signals / self._total_signals * 100.0) if self._total_signals else 0.0  # Backtest

        return BacktestResult(  # Backtest
            config=self.config,  # Backtest
            trades=self.trades,  # Backtest
            equity_curve=self.equity_curve,  # Backtest
            total_return_pct=total_return * 100.0,  # Backtest
            annualized_return_pct=annualized * 100.0,  # Backtest
            max_drawdown_pct=max_drawdown * 100.0,  # Backtest
            max_drawdown_duration_days=max_drawdown_duration,  # Backtest
            sharpe_ratio=sharpe,  # Backtest
            sortino_ratio=sortino,  # Backtest
            profit_factor=profit_factor,  # Backtest
            total_trades=len(closed),  # Backtest
            win_rate=win_rate,  # Backtest
            avg_win=avg_win,  # Backtest
            avg_loss=avg_loss,  # Backtest
            avg_rr_realized=abs(avg_win / avg_loss) if avg_loss != 0 else 0.0,  # Backtest
            best_trade_pnl=max(((trade.pnl or 0.0) for trade in closed), default=0.0),  # Backtest
            worst_trade_pnl=min(((trade.pnl or 0.0) for trade in closed), default=0.0),  # Backtest
            total_signals=self._total_signals,  # Backtest
            signals_triggered_pct=triggered_pct,  # Backtest
            avg_kairi_at_entry=avg_kairi,  # Backtest
            avg_hold_bars=avg_hold_bars,  # Backtest
            regime_stats=regime_stats,  # Backtest
        )  # Backtest

    def print_report(self, result: BacktestResult) -> None:  # Backtest
        """Escreve relatório completo do backtest no logger. # Backtest"""  # Backtest
        lines = [  # Backtest
            "",  # Backtest
            "=" * 60,  # Backtest
            f"RELATÓRIO DE BACKTEST — {result.config.symbol}",  # Backtest
            f"Período: {result.config.start_date} → {result.config.end_date}",  # Backtest
            "=" * 60,  # Backtest
            f"  Retorno Total:        {result.total_return_pct:+.2f}%",  # Backtest
            f"  Retorno Anualizado:   {result.annualized_return_pct:+.2f}%",  # Backtest
            f"  Max Drawdown:         {result.max_drawdown_pct:.2f}%",  # Backtest
            f"  DD Duration (dias):   {result.max_drawdown_duration_days}",  # Backtest
            f"  Sharpe Ratio:         {result.sharpe_ratio:.3f}",  # Backtest
            f"  Sortino Ratio:        {result.sortino_ratio:.3f}",  # Backtest
            f"  Profit Factor:        {result.profit_factor:.2f}",  # Backtest
            "-" * 60,  # Backtest
            f"  Total Trades:         {result.total_trades}",  # Backtest
            f"  Win Rate:             {result.win_rate * 100:.1f}%",  # Backtest
            f"  Avg Win:              ${result.avg_win:.2f}",  # Backtest
            f"  Avg Loss:             ${result.avg_loss:.2f}",  # Backtest
            f"  R:R Realizado:        {result.avg_rr_realized:.2f}",  # Backtest
            f"  Melhor Trade:         ${result.best_trade_pnl:.2f}",  # Backtest
            f"  Pior Trade:           ${result.worst_trade_pnl:.2f}",  # Backtest
            "-" * 60,  # Backtest
            "  Por Regime:",  # Backtest
        ]  # Backtest
        for regime, stats in result.regime_stats.items():  # Backtest
            lines.append(  # Backtest
                f"    {regime:10s}: {int(stats['trades']):3d} trades | "  # Backtest
                f"WR={float(stats['win_rate']) * 100:.0f}% | "  # Backtest
                f"avg PnL=${float(stats['avg_pnl']):.2f}"  # Backtest
            )  # Backtest
        lines.extend(["=" * 60, ""])  # Backtest
        logger.info("\n".join(lines))  # Backtest

    def export_trades_csv(  # Backtest
        self,  # Backtest
        result: BacktestResult,  # Backtest
        path: str = "backtest_trades.csv",  # Backtest
    ) -> None:  # Backtest
        """Exporta trades para CSV para análise externa. # Backtest"""  # Backtest
        csv_path = Path(path)  # Backtest
        fields = [  # Backtest
            "entry_date",  # Backtest
            "exit_date",  # Backtest
            "symbol",  # Backtest
            "regime",  # Backtest
            "confidence",  # Backtest
            "level",  # Backtest
            "entry_price",  # Backtest
            "exit_price",  # Backtest
            "quantity",  # Backtest
            "side",  # Backtest
            "pnl",  # Backtest
            "kairi_at_entry",  # Backtest
            "rsi2_at_entry",  # Backtest
            "atr_at_entry",  # Backtest
            "grid_id",  # Backtest
        ]  # Backtest
        with csv_path.open("w", newline="", encoding="utf-8") as handle:  # Backtest
            writer = csv.DictWriter(handle, fieldnames=fields)  # Backtest
            writer.writeheader()  # Backtest
            for trade in result.trades:  # Backtest
                writer.writerow({field: getattr(trade, field, "") for field in fields})  # Backtest
        logger.info("Trades exportados: %s", csv_path)  # Backtest


if __name__ == "__main__":  # Backtest
    logging.basicConfig(level=logging.INFO, format="%(message)s")  # Backtest
    parser = argparse.ArgumentParser(description="Backtest do bot")  # Backtest
    parser.add_argument("--symbol", default="SPY")  # Backtest
    parser.add_argument("--csv", required=True)  # Backtest
    parser.add_argument("--start", default="2020-01-01")  # Backtest
    parser.add_argument("--end", default="2025-12-31")  # Backtest
    parser.add_argument("--capital", type=float, default=100_000.0)  # Backtest
    parser.add_argument("--commission", type=float, default=1.0)  # Backtest
    parser.add_argument("--slippage", type=float, default=0.05)  # Backtest
    parser.add_argument("--export-csv", action="store_true")  # Backtest
    args = parser.parse_args()  # Backtest

    config = BacktestConfig(  # Backtest
        symbol=args.symbol,  # Backtest
        start_date=args.start,  # Backtest
        end_date=args.end,  # Backtest
        initial_capital=args.capital,  # Backtest
        data_csv_path=args.csv,  # Backtest
        commission_per_trade=args.commission,  # Backtest
        slippage_pct=args.slippage,  # Backtest
    )  # Backtest
    engine = BacktestEngine(config)  # Backtest
    result = engine.run()  # Backtest
    engine.print_report(result)  # Backtest
    if args.export_csv:  # Backtest
        engine.export_trades_csv(result, f"backtest_{args.symbol}.csv")  # Backtest
