"""
Motor de grid trading para o bot autonomo.

Gere a criacao, monitorizacao e persistencia de grids de trading.
Cada grid contem niveis de compra escalonados com take-profit e stop-loss
individuais, calculados a partir do ATR do instrumento.

Principios:
- Sem averaging down: niveis parados (stopped) NAO sao reabertos.
- Escrita atomica: estado gravado via ficheiro temporario + Path.replace().
- Backup automatico antes de cada escrita.
- Validacao de esquema ao carregar estado.
"""

from __future__ import annotations

import json
import logging
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_VALID_GRID_STATUSES = {"staging", "active", "paused", "closed", "failed"}
_VALID_LEVEL_STATUSES = {"pending", "bought", "sold", "stopped", "cancelled"}

_REGIME_NUM_LEVELS: dict[str, int] = {
    "BULL": 5,
    "BEAR": 4,       # Finding 3a — BEAR: 8→4 anti cluster-stop
    "SIDEWAYS": 8,   # Finding 3a — SIDEWAYS: 7→8
}

_STATE_FILENAME = "grids_state.json"
_BACKUP_SUFFIX = ".bak"

# Finding 3c — limiar de recentragem por regime
_RECENTER_THRESHOLDS: dict[str, float] = {  # Finding 3c
    "BULL": 0.80,  # Finding 3c
    "BEAR": 0.60,  # Finding 3c
    "SIDEWAYS": 0.70,  # Finding 3c
}  # Finding 3c
_MIN_SPACING_PCT = 1.0
_MAX_SPACING_PCT = 4.0
_CHANGE_THRESHOLD_PCT = 0.3
_RESPACING_COOLDOWN_SECONDS = 3600


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class GridLevel:
    """Representa um nivel individual dentro de uma grid de trading."""

    level: int
    buy_price: float
    sell_price: float          # take-profit
    stop_price: float          # stop-loss
    status: str                # 'pending', 'bought', 'sold', 'stopped', 'cancelled'
    quantity: int
    buy_order_id: int | None = None
    sell_order_id: int | None = None
    stop_order_id: int | None = None
    bought_at: str | None = None
    sold_at: str | None = None
    pnl: float | None = None

    def __post_init__(self) -> None:
        if self.status not in _VALID_LEVEL_STATUSES:
            raise ValueError(
                f"Estado de nivel invalido: '{self.status}'. "
                f"Valores aceites: {_VALID_LEVEL_STATUSES}"
            )


@dataclass
class Grid:
    """Representa uma grid completa de trading para um simbolo."""

    id: str                    # grid_{symbol}_{date}_{seq}
    symbol: str
    status: str                # 'staging', 'active', 'paused', 'closed', 'failed'
    regime: str
    created_at: str
    center_price: float
    atr: float
    spacing: float
    spacing_pct: float = 0.0
    levels: list[GridLevel] = field(default_factory=list)
    total_pnl: float = 0.0
    confidence: str = ""
    size_multiplier: float = 1.0
    last_respaced_at: str | None = None
    reconciliation_state: str = "unknown"
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in _VALID_GRID_STATUSES:
            raise ValueError(
                f"Estado de grid invalido: '{self.status}'. "
                f"Valores aceites: {_VALID_GRID_STATUSES}"
            )


# ---------------------------------------------------------------------------
# Motor de Grid
# ---------------------------------------------------------------------------

class GridEngine:
    """
    Motor principal de grid trading.

    Responsavel por criar, monitorizar, recentrar e persistir grids
    de trading com niveis de compra escalonados.
    """

    def __init__(self, data_dir: str | Path = "data") -> None:
        self.grids: list[Grid] = []
        self._data_dir = Path(data_dir)
        self._seq_counter: int = 0
        logger.info("Motor de grid inicializado (directoria de dados: %s)", data_dir)

    @staticmethod
    def calculate_geometric_levels(  # Finding 5
        center_price: float,  # Finding 5
        spacing_pct: float,  # Finding 5
        num_levels: int,  # Finding 5
    ) -> list[float]:  # Finding 5
        """
        Níveis com espaçamento geométrico — percentagem constante  # Finding 5
        entre níveis. Superior ao aritmético em mercados voláteis.  # Finding 5
        Finding 5.  # Finding 5
        """
        if num_levels <= 1:  # Finding 5
            return [center_price * (1.0 - spacing_pct / 100.0)]  # Finding 5
        lower_bound = center_price * (  # Finding 5
            1.0 - (spacing_pct / 100.0) * num_levels  # Finding 5
        )  # Finding 5
        lower_bound = max(lower_bound, center_price * 0.50)  # Finding 5
        ratio = (center_price / lower_bound) ** (  # Finding 5
            1.0 / max(1, num_levels - 1)  # Finding 5
        )  # Finding 5
        levels = [lower_bound * (ratio ** i) for i in range(num_levels)]  # Finding 5
        return sorted(levels, reverse=True)  # Finding 5

    # ------------------------------------------------------------------
    # Criacao de grid
    # ------------------------------------------------------------------

    def create_grid(
        self,
        symbol: str,
        center_price: float,
        atr: float,
        regime: str,
        num_levels: int,
        base_quantity: int,
        confidence: str,
        size_multiplier: float,
        stop_atr_mult: float = 1.0,
        tp_atr_mult: float = 2.5,
        status: str = "active",
    ) -> Grid:
        """
        Cria uma nova grid com *num_levels* niveis abaixo do preco central.

        Parametros de calculo:
        - Espacamento entre niveis: clamp(ATR% x 0.6, 1.0%, 4.0%)
        - Preco de compra do nivel n: center_price - n * spacing
        - Take-profit de cada nivel: buy_price + 2.5 * ATR
        - Stop-loss de cada nivel: buy_price - 1.0 * ATR
        - Quantidade ajustada pelo size_multiplier
        """
        spacing_pct = self.calculate_spacing_pct(center_price, atr)
        spacing = round(center_price * spacing_pct / 100.0, 6)
        adjusted_qty = max(1, int(round(base_quantity * size_multiplier)))
        grid_id = self.generate_grid_id(symbol)
        now = datetime.now(tz=timezone.utc).isoformat()

        levels: list[GridLevel] = []
        geo_levels = self.calculate_geometric_levels(  # Finding 5
            center_price, spacing_pct, num_levels  # Finding 5
        )  # Finding 5
        for n, buy_price_raw in enumerate(geo_levels, start=1):  # Finding 5
            buy_price = round(buy_price_raw, 6)  # Finding 5
            # Kotegawa TP — NÃO ALTERAR
            sell_price = round(buy_price + tp_atr_mult * atr, 6)
            # Kotegawa SL — NÃO ALTERAR
            stop_price = round(buy_price - stop_atr_mult * atr, 6)
            levels.append(
                GridLevel(
                    level=n,
                    buy_price=buy_price,
                    sell_price=sell_price,
                    stop_price=stop_price,
                    status="pending",
                    quantity=adjusted_qty,
                )
            )

        grid = Grid(
            id=grid_id,
            symbol=symbol,
            status=status,
            regime=regime,
            created_at=now,
            center_price=center_price,
            atr=atr,
            spacing=spacing,
            spacing_pct=spacing_pct,
            levels=levels,
            total_pnl=0.0,
            confidence=confidence,
            size_multiplier=size_multiplier,
            last_respaced_at=now,
            reconciliation_state="synced",
        )

        self.grids.append(grid)
        logger.info(
            "Grid criada: %s | simbolo=%s | regime=%s | niveis=%d | "
            "centro=%.4f | ATR=%.4f | confianca=%s | multiplicador=%.2f",
            grid_id, symbol, regime, num_levels, center_price, atr,
            confidence, size_multiplier,
        )
        return grid

    def activate_grid(self, grid: Grid) -> Grid:
        """Promove uma grid staged para active após submissão inicial completa."""
        grid.status = "active"
        grid.failure_reason = None
        logger.info("Grid %s activada.", grid.id)
        return grid

    def fail_grid(self, grid: Grid, reason: str) -> Grid:
        """Marca uma grid como falhada sem fingir fecho limpo."""
        grid.status = "failed"
        grid.failure_reason = reason
        logger.error("Grid %s marcada como failed: %s", grid.id, reason)
        return grid

    # ------------------------------------------------------------------
    # Niveis por regime
    # ------------------------------------------------------------------

    @staticmethod
    def get_num_levels_for_regime(regime: str) -> int:
        """
        Devolve o numero de niveis recomendado para o regime de mercado.

        BULL: 5 | BEAR: 8 (intervalo 7-10) | SIDEWAYS: 7 (intervalo 6-8)
        """
        regime_upper = regime.upper()
        num = _REGIME_NUM_LEVELS.get(regime_upper)
        if num is None:
            logger.warning(
                "Regime desconhecido '%s' — a usar valor por defeito de 5 niveis.",
                regime,
            )
            return 5
        return num

    # ------------------------------------------------------------------
    # Recentragem
    # ------------------------------------------------------------------

    def should_recenter(self, grid: Grid, current_price: float) -> bool:
        """
        Verifica se o preco actual ultrapassou 70 %% da extensao da grid,
        indicando que e necessario recentrar.

        A extensao da grid e definida como a distancia entre o centro
        e o nivel mais afastado (ultimo nivel de compra).
        """
        if not grid.levels:
            return False

        # Extensao total: do centro ate ao ultimo nivel de compra
        lowest_buy = min(lv.buy_price for lv in grid.levels)
        highest_buy = max(lv.buy_price for lv in grid.levels)

        # Distancia total da grid em ambas as direccoes a partir do centro
        extension_down = grid.center_price - lowest_buy
        extension_up = grid.center_price - highest_buy  # negativo (acima do centro nao ha niveis)

        # O preco pode mover-se para baixo (abaixo do centro) ou para cima
        # Recentrar se o preco se afastou mais de 70 % da extensao total
        # em qualquer direccao
        if extension_down > 0:
            # Finding 3c — threshold de recentragem por regime
            recenter_threshold = _RECENTER_THRESHOLDS.get(grid.regime, 0.70)  # Finding 3c
            threshold_down = grid.center_price - recenter_threshold * extension_down  # Finding 3c
            if current_price < threshold_down:
                logger.info(
                    "Grid %s: preco actual (%.4f) ultrapassou %.0f%% da extensao "
                    "inferior (limiar=%.4f). Recentragem recomendada. # Finding 3c",
                    grid.id, current_price, recenter_threshold * 100, threshold_down,
                )
                return True

        # Preco moveu-se para cima alem do limiar por regime
        if extension_down > 0:
            recenter_threshold = _RECENTER_THRESHOLDS.get(grid.regime, 0.70)  # Finding 3c
            threshold_up = grid.center_price + recenter_threshold * extension_down  # Finding 3c
            if current_price > threshold_up:
                logger.info(
                    "Grid %s: preco actual (%.4f) ultrapassou %.0f%% da extensao "
                    "superior (limiar=%.4f). Recentragem recomendada. # Finding 3c",
                    grid.id, current_price, recenter_threshold * 100, threshold_up,
                )
                return True

        return False

    def recenter_grid(
        self,
        grid: Grid,
        new_center: float,
        atr: float,
        *,
        stop_atr_mult: float = 1.0,
        tp_atr_mult: float = 2.5,
        respaced_at: str | None = None,
    ) -> Grid:
        """
        Recentra a grid num novo preco central.

        - Niveis pendentes sao cancelados e recalculados.
        - Niveis ja comprados (status='bought') sao mantidos inalterados.
        - Niveis vendidos ou parados permanecem como estao (historico).
        """
        spacing_pct = self.calculate_spacing_pct(new_center, atr)
        spacing = round(new_center * spacing_pct / 100.0, 6)
        kept_levels: list[GridLevel] = []
        cancelled_count = 0

        for lv in grid.levels:
            if lv.status == "bought":
                # Manter niveis comprados — posicao aberta
                kept_levels.append(lv)
            elif lv.status in ("sold", "stopped"):
                # Manter historico de niveis concluidos
                kept_levels.append(lv)
            else:
                # Cancelar niveis pendentes
                lv.status = "cancelled"
                kept_levels.append(lv)
                cancelled_count += 1

        # Recalcular novos niveis pendentes para substituir os cancelados
        num_new = cancelled_count
        # Determinar o proximo numero de nivel
        existing_level_nums = {lv.level for lv in kept_levels}
        next_level = max(existing_level_nums, default=0) + 1
        adjusted_qty = max(1, int(round(grid.levels[0].quantity if grid.levels else 1)))

        new_levels: list[GridLevel] = []
        geo_levels = self.calculate_geometric_levels(  # Finding 5
            new_center, spacing_pct, num_new  # Finding 5
        )  # Finding 5
        for i, buy_price_raw in enumerate(geo_levels):  # Finding 5
            buy_price = round(buy_price_raw, 6)  # Finding 5
            # Kotegawa TP — NÃO ALTERAR
            sell_price = round(buy_price + tp_atr_mult * atr, 6)
            # Kotegawa SL — NÃO ALTERAR
            stop_price = round(buy_price - stop_atr_mult * atr, 6)
            new_levels.append(
                GridLevel(
                    level=next_level + i,
                    buy_price=buy_price,
                    sell_price=sell_price,
                    stop_price=stop_price,
                    status="pending",
                    quantity=adjusted_qty,
                )
            )

        grid.levels = kept_levels + new_levels
        grid.center_price = new_center
        grid.atr = atr
        grid.spacing = spacing
        grid.spacing_pct = spacing_pct
        grid.last_respaced_at = respaced_at or datetime.now(tz=timezone.utc).isoformat()

        logger.info(
            "Grid %s recentrada: novo_centro=%.4f | ATR=%.4f | spacing=%.4f (%.2f%%) | "
            "niveis_cancelados=%d | novos_niveis=%d | niveis_mantidos=%d",
            grid.id, new_center, atr, spacing, spacing_pct, cancelled_count, len(new_levels),
            len(kept_levels) - cancelled_count,
        )
        return grid

    # ------------------------------------------------------------------
    # Fecho de grid
    # ------------------------------------------------------------------

    def close_grid(self, grid: Grid) -> Grid:
        """
        Fecha a grid: define status='closed' e calcula o P&L total.

        Niveis pendentes sao cancelados. O P&L total e a soma dos P&L
        individuais de todos os niveis que foram executados.
        """
        total_pnl = 0.0
        for lv in grid.levels:
            if lv.status == "pending":
                lv.status = "cancelled"
            if lv.pnl is not None:
                total_pnl += lv.pnl

        grid.total_pnl = round(total_pnl, 6)
        grid.status = "closed"

        logger.info(
            "Grid %s fechada | P&L total: %.4f | niveis executados: %d",
            grid.id, grid.total_pnl,
            sum(1 for lv in grid.levels if lv.status in ("sold", "stopped")),
        )
        return grid

    # ------------------------------------------------------------------
    # Eventos de nivel
    # ------------------------------------------------------------------

    def on_level_bought(
        self, grid: Grid, level: int, price: float, timestamp: str
    ) -> None:
        """
        Marca um nivel como comprado apos execucao da ordem de compra.
        """
        lv = self._find_level(grid, level)
        if lv is None:
            logger.error(
                "Grid %s: nivel %d nao encontrado para marcar como comprado.",
                grid.id, level,
            )
            return

        lv.status = "bought"
        lv.bought_at = timestamp
        logger.info(
            "Grid %s: nivel %d comprado a %.4f em %s",
            grid.id, level, price, timestamp,
        )

    def on_level_sold(
        self, grid: Grid, level: int, price: float, timestamp: str
    ) -> None:
        """
        Marca um nivel como vendido (take-profit atingido) e calcula o P&L.
        """
        lv = self._find_level(grid, level)
        if lv is None:
            logger.error(
                "Grid %s: nivel %d nao encontrado para marcar como vendido.",
                grid.id, level,
            )
            return

        lv.status = "sold"
        lv.sold_at = timestamp
        lv.pnl = round((price - lv.buy_price) * lv.quantity, 6)
        grid.total_pnl = round(
            grid.total_pnl + lv.pnl, 6
        )

        logger.info(
            "Grid %s: nivel %d vendido a %.4f | P&L do nivel: %.4f | "
            "P&L total da grid: %.4f",
            grid.id, level, price, lv.pnl, grid.total_pnl,
        )

    def on_level_stopped(
        self, grid: Grid, level: int, price: float, timestamp: str
    ) -> None:
        """
        Marca um nivel como parado (stop-loss atingido) e calcula o P&L.

        IMPORTANTE: O nivel NAO e reaberto (principio de zero averaging down).
        """
        lv = self._find_level(grid, level)
        if lv is None:
            logger.error(
                "Grid %s: nivel %d nao encontrado para marcar como parado.",
                grid.id, level,
            )
            return

        lv.status = "stopped"
        lv.sold_at = timestamp
        lv.pnl = round((price - lv.buy_price) * lv.quantity, 6)
        grid.total_pnl = round(
            grid.total_pnl + lv.pnl, 6
        )

        logger.warning(
            "Grid %s: nivel %d parado (stop-loss) a %.4f | Perda do nivel: %.4f | "
            "P&L total da grid: %.4f | Nivel NAO sera reaberto (sem averaging down).",
            grid.id, level, price, lv.pnl, grid.total_pnl,
        )

    # ------------------------------------------------------------------
    # Persistencia de estado
    # ------------------------------------------------------------------

    def save_state(self) -> None:
        """
        Grava o estado de todas as grids em disco de forma atomica.

        Procedimento:
        1. Cria backup do ficheiro actual (se existir).
        2. Escreve num ficheiro temporario na mesma directoria.
        3. Faz Path.replace() do temporario para o definitivo (operacao atomica
           em sistemas de ficheiros POSIX).
        """
        dir_path = self._data_dir
        dir_path.mkdir(parents=True, exist_ok=True)

        state_path = dir_path / _STATE_FILENAME
        backup_path = dir_path / (_STATE_FILENAME + _BACKUP_SUFFIX)

        # Serializar estado
        state_data: dict[str, Any] = {
            "version": 1,
            "saved_at": datetime.now(tz=timezone.utc).isoformat(),
            "grids": [self._grid_to_dict(g) for g in self.grids],
        }
        payload = json.dumps(state_data, indent=2, ensure_ascii=False)

        # Backup do ficheiro actual
        if state_path.exists():
            try:
                shutil.copy2(str(state_path), str(backup_path))
                logger.debug(
                    "Backup do estado criado: %s", backup_path,
                )
            except OSError as exc:
                logger.warning(
                    "Nao foi possivel criar backup do estado: %s", exc,
                )

        # Escrita atomica: temporario + rename
        tmp_path_obj: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=dir_path,
                prefix=".grids_state_",
                suffix=".tmp",
                delete=False,
            ) as handle:
                handle.write(payload)
                tmp_path_obj = Path(handle.name)
            assert tmp_path_obj is not None
            tmp_path_obj.replace(state_path)
            logger.info(
                "Estado gravado com sucesso: %d grid(s) em %s",
                len(self.grids), state_path,
            )
        except BaseException:
            # Limpar ficheiro temporario em caso de erro
            try:
                if tmp_path_obj is not None and tmp_path_obj.exists():
                    tmp_path_obj.unlink()
            except OSError:
                pass
            raise

    def load_state(self) -> None:
        """
        Carrega o estado das grids a partir do ficheiro JSON.

        Valida a estrutura (esquema) do ficheiro antes de aceitar os dados.
        Se o ficheiro nao existir, inicia com lista vazia.
        """
        state_path = self._data_dir / _STATE_FILENAME

        if not state_path.exists():
            logger.info(
                "Ficheiro de estado nao encontrado em %s — a iniciar sem grids.",
                state_path,
            )
            self.grids = []
            return

        try:
            with state_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error(
                "Erro ao ler ficheiro de estado %s: %s", state_path, exc,
            )
            raise

        # Validacao de esquema
        self._validate_state_schema(data)

        # Desserializar grids
        grids: list[Grid] = []
        for g_data in data.get("grids", []):
            grid = self._dict_to_grid(g_data)
            grids.append(grid)

        self.grids = grids

        # Recalcular o contador de sequencia a partir das grids existentes
        self._recalculate_seq_counter()

        logger.info(
            "Estado carregado com sucesso: %d grid(s) de %s",
            len(self.grids), state_path,
        )

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def get_active_grids(self) -> list[Grid]:
        """Devolve todas as grids com status 'active'."""
        return [g for g in self.grids if g.status == "active"]

    def get_grid_by_id(self, grid_id: str) -> Grid | None:
        """Devolve a grid com o ID especificado, ou None se nao existir."""
        for g in self.grids:
            if g.id == grid_id:
                return g
        return None

    # ------------------------------------------------------------------
    # Geracao de ID
    # ------------------------------------------------------------------

    def generate_grid_id(self, symbol: str) -> str:
        """
        Gera um ID unico para a grid no formato:
            grid_{symbol}_{YYYYMMDD}_{sequence}

        O numero de sequencia e incrementado por cada grid criada na sessao.
        """
        self._seq_counter += 1
        date_str = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
        clean_symbol = symbol.replace(" ", "").replace("/", "").upper()
        grid_id = f"grid_{clean_symbol}_{date_str}_{self._seq_counter:04d}"
        return grid_id

    # ------------------------------------------------------------------
    # Metodos auxiliares privados
    # ------------------------------------------------------------------

    @staticmethod
    def _find_level(grid: Grid, level: int) -> GridLevel | None:
        """Encontra um nivel pelo numero dentro de uma grid."""
        for lv in grid.levels:
            if lv.level == level:
                return lv
        return None

    @staticmethod
    def _grid_to_dict(grid: Grid) -> dict[str, Any]:
        """Converte uma Grid (com os seus GridLevel) para dicionario."""
        return asdict(grid)

    @staticmethod
    def _dict_to_grid(data: dict[str, Any]) -> Grid:
        """Reconstroi uma Grid a partir de um dicionario."""
        grid_data = dict(data)
        levels_data = grid_data.pop("levels", [])
        levels = [GridLevel(**lv) for lv in levels_data]
        if "spacing_pct" not in grid_data:
            center = float(grid_data.get("center_price", 0.0) or 0.0)
            spacing = float(grid_data.get("spacing", 0.0) or 0.0)
            grid_data["spacing_pct"] = round((spacing / center) * 100.0, 6) if center > 0 else 0.0
        grid_data.setdefault("last_respaced_at", grid_data.get("created_at"))
        grid_data.setdefault("reconciliation_state", "unknown")
        grid_data.setdefault("failure_reason", None)
        return Grid(**grid_data, levels=levels)

    @staticmethod
    def calculate_spacing_pct(reference_price: float, atr: float) -> float:
        """Calcula o espaçamento percentual com clamp da auditoria."""
        if reference_price <= 0:
            raise ValueError(f"Preco de referencia invalido: {reference_price}")
        if atr <= 0:
            raise ValueError(f"ATR invalido: {atr}")

        atr_pct = (atr / reference_price) * 100.0
        spacing_pct = atr_pct * 0.6
        spacing_pct = max(_MIN_SPACING_PCT, min(_MAX_SPACING_PCT, spacing_pct))
        return round(spacing_pct, 6)

    def should_respace(
        self,
        grid: Grid,
        reference_price: float,
        atr: float,
        now: datetime | None = None,
    ) -> bool:
        """Verifica se a grid deve ser re-espacada pelo ATR actual."""
        current_time = now or datetime.now(tz=timezone.utc)
        new_spacing_pct = self.calculate_spacing_pct(reference_price, atr)
        current_spacing_pct = (
            grid.spacing_pct
            if grid.spacing_pct > 0
            else self.calculate_spacing_pct(grid.center_price, grid.atr)
        )
        change_pct = abs(new_spacing_pct - current_spacing_pct)

        if change_pct < _CHANGE_THRESHOLD_PCT:
            return False

        if grid.last_respaced_at:
            try:
                last_respaced = datetime.fromisoformat(grid.last_respaced_at)
                if last_respaced.tzinfo is None:
                    last_respaced = last_respaced.replace(tzinfo=timezone.utc)
                if (current_time - last_respaced).total_seconds() < _RESPACING_COOLDOWN_SECONDS:
                    logger.info(
                        "Grid %s: re-espacamento adiado por cooldown de 1 hora.",
                        grid.id,
                    )
                    return False
            except ValueError:
                logger.warning(
                    "Grid %s com last_respaced_at invalido (%s).",
                    grid.id,
                    grid.last_respaced_at,
                )

        logger.info(
            "Grid %s: re-espacamento recomendado (%.2f%% -> %.2f%%).",
            grid.id,
            current_spacing_pct,
            new_spacing_pct,
        )
        return True

    def _recalculate_seq_counter(self) -> None:
        """
        Recalcula o contador de sequencia a partir dos IDs das grids
        carregadas para evitar colisoes.
        """
        max_seq = 0
        today_str = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
        for g in self.grids:
            parts = g.id.split("_")
            # Formato: grid_{symbol}_{date}_{seq}
            if len(parts) >= 4:
                date_part = parts[-2]
                seq_part = parts[-1]
                if date_part == today_str:
                    try:
                        seq = int(seq_part)
                        if seq > max_seq:
                            max_seq = seq
                    except ValueError:
                        pass
        self._seq_counter = max_seq

    @staticmethod
    def _validate_state_schema(data: Any) -> None:
        """
        Valida a estrutura basica do ficheiro de estado.

        Verifica:
        - Tipo raiz e dicionario
        - Campo 'version' existe e e inteiro
        - Campo 'grids' existe e e lista
        - Cada grid tem os campos obrigatorios
        - Cada nivel tem os campos obrigatorios
        """
        if not isinstance(data, dict):
            raise ValueError(
                "Esquema invalido: raiz do ficheiro de estado deve ser "
                "um dicionario JSON."
            )

        # Verificar versao
        version = data.get("version")
        if not isinstance(version, int):
            raise ValueError(
                "Esquema invalido: campo 'version' ausente ou nao e inteiro."
            )

        # Verificar lista de grids
        grids = data.get("grids")
        if not isinstance(grids, list):
            raise ValueError(
                "Esquema invalido: campo 'grids' ausente ou nao e uma lista."
            )

        required_grid_fields = {
            "id", "symbol", "status", "regime", "created_at",
            "center_price", "atr", "spacing", "levels",
        }
        required_level_fields = {
            "level", "buy_price", "sell_price", "stop_price",
            "status", "quantity",
        }

        for i, g in enumerate(grids):
            if not isinstance(g, dict):
                raise ValueError(
                    f"Esquema invalido: grid no indice {i} nao e um dicionario."
                )
            missing_grid = required_grid_fields - set(g.keys())
            if missing_grid:
                raise ValueError(
                    f"Esquema invalido: grid no indice {i} — campos em falta: "
                    f"{missing_grid}"
                )

            if g.get("status") not in _VALID_GRID_STATUSES:
                raise ValueError(
                    f"Esquema invalido: grid no indice {i} — status "
                    f"'{g.get('status')}' invalido. "
                    f"Valores aceites: {_VALID_GRID_STATUSES}"
                )

            levels = g.get("levels")
            if not isinstance(levels, list):
                raise ValueError(
                    f"Esquema invalido: grid no indice {i} — 'levels' "
                    f"nao e uma lista."
                )
            for j, lv in enumerate(levels):
                if not isinstance(lv, dict):
                    raise ValueError(
                        f"Esquema invalido: grid {i}, nivel {j} — "
                        f"nao e um dicionario."
                    )
                missing_level = required_level_fields - set(lv.keys())
                if missing_level:
                    raise ValueError(
                        f"Esquema invalido: grid {i}, nivel {j} — "
                        f"campos em falta: {missing_level}"
                    )
                if lv.get("status") not in _VALID_LEVEL_STATUSES:
                    raise ValueError(
                        f"Esquema invalido: grid {i}, nivel {j} — "
                        f"status '{lv.get('status')}' invalido. "
                        f"Valores aceites: {_VALID_LEVEL_STATUSES}"
                    )
