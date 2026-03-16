"""
Configuracao central do bot de trading autonomo.

Carrega todos os parametros a partir de variaveis de ambiente (.env),
com valores por defeito seguros (paper trading activado por defeito).
Utiliza pydantic para validacao rigorosa dos tipos e limites.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator, model_validator

# Caminho base do projecto
BASE_DIR: Path = Path(__file__).resolve().parent

# Carregar variaveis de ambiente do ficheiro .env (se existir)
load_dotenv(BASE_DIR / ".env")


def _env(key: str, default: str | None = None) -> str | None:
    """Auxiliar para ler variaveis de ambiente com fallback."""
    return os.getenv(key, default)


def _env_bool(key: str, default: bool = False) -> bool:
    """Converte variavel de ambiente para booleano (aceita true/1/yes)."""
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("true", "1", "yes", "sim")


def _env_int(key: str, default: int) -> int:
    """Converte variavel de ambiente para inteiro."""
    val = os.getenv(key)
    if val is None or not val.strip():
        return default
    return int(val)


def _env_float(key: str, default: float) -> float:
    """Converte variavel de ambiente para float."""
    val = os.getenv(key)
    if val is None or not val.strip():
        return default
    return float(val)


class IBConfig(BaseModel):
    """Configuracao da ligacao ao Interactive Brokers (via ib_insync)."""

    paper_trading: bool = Field(
        default=True,
        description="Se True, opera em paper trading.",
    )
    use_gateway: bool = Field(
        default=False,
        description="Se True, usa IB Gateway; caso contrario usa TWS.",
    )
    host: str = Field(
        default="127.0.0.1",
        description="Endereco do IB Gateway / TWS",
    )
    port: int = Field(
        default=0,
        description=(
            "Porta do IB Gateway/TWS "
            "(0 = auto: paper+tws=7497, paper+gateway=4002, "
            "live+tws=7496, live+gateway=4001)"
        ),
    )
    client_id: int = Field(
        default=1,
        description="ID do cliente para a ligacao IB",
    )

    @model_validator(mode="after")
    def _auto_port(self) -> "IBConfig":
        """Se a porta nao foi definida, escolhe automaticamente com base no modo."""
        if self.port == 0:
            if self.paper_trading and self.use_gateway:
                self.port = 4002
            elif self.paper_trading and not self.use_gateway:
                self.port = 7497
            elif not self.paper_trading and self.use_gateway:
                self.port = 4001
            else:
                self.port = 7496
        return self


class TelegramConfig(BaseModel):
    """Configuracao das notificacoes via Telegram."""

    bot_token: Optional[str] = Field(
        default=None,
        description="Token do bot Telegram (obtido via @BotFather)",
    )
    chat_id: Optional[str] = Field(
        default=None,
        description="ID do chat/grupo para enviar alertas",
    )

    @property
    def is_configured(self) -> bool:
        """Verifica se as credenciais do Telegram estao preenchidas."""
        invalid_tokens = {None, "", "your_token_here"}
        invalid_chats = {None, "", "your_chat_id_here"}
        return self.bot_token not in invalid_tokens and self.chat_id not in invalid_chats


class RiskConfig(BaseModel):
    """
    Parametros de gestao de risco.

    Limites diarios, semanais e mensais para proteccao do capital.
    Inclui dimensionamento de posicoes via fraccao de Kelly limitada.
    """

    # --- Dimensionamento de posicoes ---
    risk_per_level: float = Field(
        default=0.01,
        ge=0.001,
        le=0.10,
        description="Fraccao do capital arriscada por nivel de entrada (1%)",
    )
    min_rr: float = Field(
        default=2.5,
        ge=1.0,
        description="Racio minimo recompensa/risco para aceitar operacao",
    )
    stop_atr_mult: float = Field(
        default=1.0,
        gt=0.0,
        description="Multiplicador do ATR para colocacao do stop-loss",
    )
    tp_atr_mult: float = Field(
        default=2.5,
        gt=0.0,
        description="Multiplicador do ATR para colocacao do take-profit",
    )

    # --- Limites de perda ---
    daily_loss_limit: float = Field(
        default=0.03,
        ge=0.0,
        le=1.0,
        description="Limite maximo de perda diaria (3% do capital)",
    )
    weekly_loss_limit: float = Field(
        default=0.06,
        ge=0.0,
        le=1.0,
        description="Limite maximo de perda semanal (6% do capital)",
    )
    monthly_dd_limit: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
        description="Drawdown maximo mensal permitido (10%)",
    )

    # --- Limites de posicoes ---
    max_positions: int = Field(
        default=8,
        ge=1,
        le=50,
        description="Numero maximo de posicoes simultaneas",
    )
    max_grids: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Numero maximo de grids activas em simultaneo",
    )

    # --- Kelly ---
    kelly_cap: float = Field(
        default=0.05,
        ge=0.01,
        le=0.25,
        description="Fraccao maxima de Kelly permitida (cap de seguranca)",
    )

    # --- Grid ---
    grid_recenter_pct: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Percentagem de niveis preenchidos para recentrar grid",
    )

    @field_validator("min_rr")
    @classmethod
    def _rr_must_be_positive(cls, v: float) -> float:
        """O racio recompensa/risco tem de ser pelo menos 1.0."""
        if v < 1.0:
            raise ValueError("min_rr deve ser >= 1.0")
        return v


class AppConfig(BaseModel):
    """Configuracao global da aplicacao — agrega todas as sub-configuracoes."""

    # --- Sub-configuracoes ---
    ib: IBConfig = Field(default_factory=IBConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)

    # --- Ciclo principal ---
    cycle_interval_seconds: int = Field(
        default=300,
        ge=5,
        le=3600,
        description="Intervalo em segundos entre ciclos do loop principal",
    )

    # --- Caminhos ---
    data_dir: Path = Field(
        default=BASE_DIR / "data",
        description="Directoria para ficheiros de estado e registos",
    )

    # --- Logging ---
    log_level: str = Field(
        default="INFO",
        description="Nivel de logging (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        """Garante que o nivel de logging e valido."""
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level deve ser um de {allowed}, recebido: {v}")
        return upper


def load_config() -> AppConfig:
    """
    Carrega a configuracao completa a partir das variaveis de ambiente.

    Retorna uma instancia imutavel de AppConfig com todos os parametros
    validados. Se alguma variavel estiver fora dos limites, levanta
    ValidationError do pydantic.
    """
    ib = IBConfig(
        paper_trading=_env_bool("PAPER_TRADING", default=True),
        use_gateway=_env_bool("USE_GATEWAY", default=False),
        host=_env("IB_HOST", "127.0.0.1"),  # type: ignore[arg-type]
        port=_env_int("IB_PORT", 0),
        client_id=_env_int("IB_CLIENT_ID", 1),
    )

    telegram = TelegramConfig(
        bot_token=_env("TELEGRAM_BOT_TOKEN"),
        chat_id=_env("TELEGRAM_CHAT_ID"),
    )

    risk = RiskConfig(
        risk_per_level=_env_float("RISK_PER_LEVEL", 0.01),
        min_rr=_env_float("MIN_RR", 2.5),
        stop_atr_mult=_env_float("STOP_ATR_MULT", 1.0),
        tp_atr_mult=_env_float("TP_ATR_MULT", 2.5),
        daily_loss_limit=_env_float("DAILY_LOSS_LIMIT", 0.03),
        weekly_loss_limit=_env_float("WEEKLY_LOSS_LIMIT", 0.06),
        monthly_dd_limit=_env_float("MONTHLY_DD_LIMIT", 0.10),
        max_positions=_env_int("MAX_POSITIONS", 8),
        max_grids=_env_int("MAX_GRIDS", 3),
        kelly_cap=_env_float("KELLY_CAP", 0.05),
        grid_recenter_pct=_env_float("GRID_RECENTER_PCT", 0.70),
    )

    data_dir_str = _env("DATA_DIR")
    data_dir = Path(data_dir_str) if data_dir_str else BASE_DIR / "data"

    config = AppConfig(
        ib=ib,
        telegram=telegram,
        risk=risk,
        cycle_interval_seconds=_env_int("CYCLE_INTERVAL_SECONDS", 300),
        data_dir=data_dir,
        log_level=_env("LOG_LEVEL", "INFO"),  # type: ignore[arg-type]
    )

    return config


# Instancia global — importavel directamente: from config import settings
settings: AppConfig = load_config()
