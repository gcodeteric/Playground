"""
Parsing de instrumentos da watchlist e construcao de contratos IB.

Formato suportado:
  - Simbolo simples: ``AAPL`` -> accao/ETF US por defeito
  - Formato tipado: ``SAP:STK:XETRA:EUR``
  - Forex: ``EURUSD:FX:IDEALPRO``
  - Futuros: ``MES:FUT:CME:USD``
"""

from __future__ import annotations

import asyncio
import datetime
import sys
from dataclasses import dataclass
from enum import Enum

# Garante event loop activo antes de importar ib_insync em Python 3.14+
if sys.version_info >= (3, 10):
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

from ib_insync import CFD, Contract, Forex, Future, Index, Stock


class AssetType(str, Enum):
    """Tipos de activos suportados na watchlist."""

    STOCK = "STK"
    ETF = "ETF"
    FOREX = "FX"
    FUTURE = "FUT"
    CFD = "CFD"


_US_EXCHANGES = {
    "SMART",
    "NYSE",
    "NASDAQ",
    "ARCA",
    "AMEX",
    "BATS",
    "IEX",
}
_EU_EXCHANGES = {
    "XETRA",
    "IBIS",
    "FWB",
    "GETTEX",
    "AEB",
    "SBF",
    "BVME",
    "MCE",
    "SWB",
    "SMART_EU",
}

_INDEX_CONTRACTS: dict[str, Index] = {
    "VIX": Index(symbol="VIX", exchange="CBOE", currency="USD"),
    "^VIX": Index(symbol="VIX", exchange="CBOE", currency="USD"),
    "SPX": Index(symbol="SPX", exchange="CBOE", currency="USD"),
    "NDX": Index(symbol="NDX", exchange="NASDAQ", currency="USD"),
    "DJI": Index(symbol="DJI", exchange="NYSE", currency="USD"),
    "RUT": Index(symbol="RUT", exchange="RUSSELL", currency="USD"),
}

_FOREX_CONTRACTS: dict[str, Forex] = {
    "EUR": Forex("EURUSD"),
    "GBP": Forex("GBPUSD"),
    "JPY": Forex("USDJPY"),
    "CHF": Forex("USDCHF"),
    "AUD": Forex("AUDUSD"),
    "NZD": Forex("NZDUSD"),
    "CAD": Forex("USDCAD"),
    "EURUSD": Forex("EURUSD"),
    "GBPUSD": Forex("GBPUSD"),
    "USDJPY": Forex("USDJPY"),
}

_FUTURES_SPECS: dict[str, dict[str, str]] = {
    "ES": {"symbol": "ES", "exchange": "CME", "currency": "USD"},
    "MES": {"symbol": "MES", "exchange": "CME", "currency": "USD"},
    "NQ": {"symbol": "NQ", "exchange": "CME", "currency": "USD"},
    "MNQ": {"symbol": "MNQ", "exchange": "CME", "currency": "USD"},
    "CL": {"symbol": "CL", "exchange": "NYMEX", "currency": "USD"},
    "GC": {"symbol": "GC", "exchange": "COMEX", "currency": "USD"},
    "MGC": {"symbol": "MGC", "exchange": "COMEX", "currency": "USD"},
    "ZN": {"symbol": "ZN", "exchange": "CBOT", "currency": "USD"},
    "ZB": {"symbol": "ZB", "exchange": "CBOT", "currency": "USD"},
    "SI": {"symbol": "SI", "exchange": "COMEX", "currency": "USD"},
}


@dataclass(frozen=True, slots=True)
class InstrumentSpec:
    """Descricao canonical de um instrumento da watchlist."""

    symbol: str
    asset_type: AssetType
    exchange: str
    currency: str
    region: str
    raw: str

    @property
    def display(self) -> str:
        """Identificador curto para logs e alertas."""
        return self.raw or self.symbol


def parse_watchlist_entry(raw_entry: str) -> InstrumentSpec:
    """
    Converte uma entrada textual da watchlist num InstrumentSpec.

    Regras:
      - Simbolos simples continuam a significar accoes/ETFs US.
      - Entradas tipadas seguem ``SYMBOL:ASSET:EXCHANGE[:CURRENCY[:REGION]]``.
    """
    raw = raw_entry.strip()
    if not raw:
        raise ValueError("Entrada de watchlist vazia.")

    parts = [part.strip().upper() for part in raw.split(":") if part.strip()]
    if len(parts) == 1:
        return InstrumentSpec(
            symbol=parts[0],
            asset_type=AssetType.STOCK,
            exchange="SMART",
            currency="USD",
            region="US",
            raw=raw,
        )

    symbol = parts[0]
    try:
        asset_type = AssetType(parts[1])
    except ValueError as exc:
        raise ValueError(
            f"Tipo de activo invalido em '{raw}'. Use STK, ETF, FX, FUT ou CFD."
        ) from exc

    exchange = parts[2] if len(parts) >= 3 else _default_exchange(asset_type)
    currency = parts[3] if len(parts) >= 4 else _default_currency(asset_type, symbol)
    region = parts[4] if len(parts) >= 5 else infer_region(asset_type, exchange, currency)

    return InstrumentSpec(
        symbol=symbol,
        asset_type=asset_type,
        exchange=exchange,
        currency=currency,
        region=region,
        raw=raw,
    )


def build_contract(spec: InstrumentSpec | str) -> Contract:
    """Constroi o contrato ib_insync correspondente ao instrumento."""
    if isinstance(spec, str):
        symbol = spec.strip().upper()
        if symbol in _INDEX_CONTRACTS:
            return _copy_index_contract(_INDEX_CONTRACTS[symbol])
        if symbol in _FOREX_CONTRACTS:
            return _copy_forex_contract(_FOREX_CONTRACTS[symbol])
        if symbol in _FUTURES_SPECS:
            return _build_future_contract(symbol)
        spec = parse_watchlist_entry(symbol)

    symbol = spec.symbol.upper()
    if symbol in _INDEX_CONTRACTS:
        return _copy_index_contract(_INDEX_CONTRACTS[symbol])
    if symbol in _FOREX_CONTRACTS:
        return _copy_forex_contract(_FOREX_CONTRACTS[symbol])
    if spec.asset_type == AssetType.FOREX:
        pair = symbol if len(symbol) == 6 else f"{symbol}{spec.currency.upper()}"
        if pair in _FOREX_CONTRACTS:
            return _copy_forex_contract(_FOREX_CONTRACTS[pair])
        return Forex(pair, exchange=spec.exchange)
    if symbol in _FUTURES_SPECS:
        return _build_future_contract(symbol)
    if spec.asset_type == AssetType.FUTURE:
        return Future(
            symbol=spec.symbol,
            lastTradeDateOrContractMonth=_next_futures_expiry(spec.symbol),
            exchange=spec.exchange,
            currency=spec.currency,
        )
    if spec.asset_type in (AssetType.STOCK, AssetType.ETF):
        return Stock(spec.symbol, spec.exchange, spec.currency)
    if spec.asset_type == AssetType.CFD:
        return CFD(spec.symbol, spec.exchange, spec.currency)
    raise ValueError(f"Tipo de activo nao suportado: {spec.asset_type}")


def infer_region(asset_type: AssetType, exchange: str, currency: str) -> str:
    """Infere a regiao predominante do activo para regras de sessao."""
    exchange_upper = exchange.upper()
    currency_upper = currency.upper()

    if asset_type == AssetType.FOREX:
        return "GLOBAL"
    if asset_type == AssetType.FUTURE:
        return "US"
    if exchange_upper in _US_EXCHANGES:
        return "US"
    if exchange_upper in _EU_EXCHANGES or currency_upper == "EUR":
        return "EU"
    return "US"


def _default_exchange(asset_type: AssetType) -> str:
    """Exchange por defeito por tipo de activo."""
    if asset_type in (AssetType.STOCK, AssetType.ETF):
        return "SMART"
    if asset_type == AssetType.FOREX:
        return "IDEALPRO"
    if asset_type == AssetType.FUTURE:
        return "CME"
    if asset_type == AssetType.CFD:
        return "SMART"
    raise ValueError(f"Sem exchange por defeito para {asset_type}")


def _default_currency(asset_type: AssetType, symbol: str) -> str:
    """Moeda por defeito por tipo de activo."""
    if asset_type == AssetType.FOREX and len(symbol) >= 6:
        return symbol[-3:]
    if asset_type == AssetType.FOREX:
        return "USD"
    if asset_type in (AssetType.STOCK, AssetType.ETF, AssetType.FUTURE, AssetType.CFD):
        return "USD"
    raise ValueError(f"Sem moeda por defeito para {asset_type}")


def _copy_index_contract(contract: Index) -> Index:
    """Cria uma cópia de um contrato de índice para evitar estado partilhado."""
    return Index(
        symbol=contract.symbol,
        exchange=contract.exchange,
        currency=contract.currency,
    )


def _copy_forex_contract(contract: Forex) -> Forex:
    """Cria uma cópia de um contrato Forex a partir do par original."""
    return Forex(
        f"{contract.symbol}{contract.currency}",
        exchange=contract.exchange,
    )


def _next_futures_expiry(symbol: str) -> str:
    """Retorna `YYYYMM` do contrato front-month activo."""
    today = datetime.date.today()
    sym = symbol.upper()

    if sym in ("ES", "MES", "NQ", "MNQ", "ZN", "ZB"):
        months = [3, 6, 9, 12]
    elif sym in ("GC", "MGC", "SI"):
        months = [2, 4, 6, 8, 10, 12]
    else:
        months = list(range(1, 13))

    year = today.year
    for month in months:
        expiry = datetime.date(year, month, 15)
        if expiry > today + datetime.timedelta(days=10):
            return f"{year}{month:02d}"
    return f"{year + 1}01"


def _build_future_contract(symbol: str) -> Future:
    """Cria um contrato de futuros com expiry front-month automático."""
    specs = _FUTURES_SPECS[symbol.upper()]
    expiry = _next_futures_expiry(symbol)
    return Future(
        symbol=specs["symbol"],
        lastTradeDateOrContractMonth=expiry,
        exchange=specs["exchange"],
        currency=specs["currency"],
    )
