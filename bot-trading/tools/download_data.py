"""Ferramenta para descarregar OHLCV histórico para backtesting. """  # Backtest

from __future__ import annotations  # Backtest

import argparse  # Backtest
import logging  # Backtest
import sys  # Backtest
from pathlib import Path  # Backtest

import pandas as pd  # Backtest

logger = logging.getLogger(__name__)  # Backtest

try:  # Backtest
    import yfinance as yf  # Backtest
except ImportError:  # Backtest
    logging.basicConfig(level=logging.INFO, format="%(message)s")  # Backtest
    logger.error("Instalar: pip install yfinance")  # Backtest
    sys.exit(1)  # Backtest


def main() -> None:  # Backtest
    """Descarrega dados OHLCV históricos via yfinance para backtesting. """  # Backtest
    logging.basicConfig(level=logging.INFO, format="%(message)s")  # Backtest
    parser = argparse.ArgumentParser()  # Backtest
    parser.add_argument(  # Backtest
        "--symbols",  # Backtest
        nargs="+",  # Backtest
        default=["SPY", "QQQ", "AAPL", "XLU", "GDXJ"],  # Backtest
    )  # Backtest
    parser.add_argument("--start", default="2018-01-01")  # Backtest
    parser.add_argument("--end", default="2025-12-31")  # Backtest
    parser.add_argument("--outdir", default="data/historical")  # Backtest
    args = parser.parse_args()  # Backtest

    outdir = Path(args.outdir)  # Backtest
    outdir.mkdir(parents=True, exist_ok=True)  # Backtest

    for symbol in args.symbols:  # Backtest
        logger.info("A descarregar %s...", symbol)  # Backtest
        df = yf.download(  # Backtest
            symbol,  # Backtest
            start=args.start,  # Backtest
            end=args.end,  # Backtest
            auto_adjust=True,  # Backtest
            progress=False,  # Backtest
        )  # Backtest
        df = df.reset_index()  # Backtest
        df.columns = [str(column).lower() for column in df.columns]  # Backtest
        df = df[["date", "open", "high", "low", "close", "volume"]]  # Backtest
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")  # Backtest
        output_path = outdir / f"{symbol}_daily.csv"  # Backtest
        df.to_csv(output_path, index=False)  # Backtest
        logger.info("  Guardado: %s (%d barras)", output_path, len(df))  # Backtest


if __name__ == "__main__":  # Backtest
    main()  # Backtest
