"""
Módulo 4: Gestão de Risco Autónoma

Implementa toda a lógica de gestão de risco do bot de trading:
- Position sizing via Half-Kelly Criterion com cap de segurança
- Kill switches automáticos (diário, semanal, mensal)
- Validação de cada ordem antes de submissão
- Cálculo de Risk of Ruin
- Aplicação de regras de ferro: stop-loss obrigatório, zero averaging down
- Cálculo de stop-loss e take-profit baseados em ATR

Todas as constantes vêm dos parâmetros extraídos da investigação (EXTRACTED_PARAMS.md).

Comentários em português (PT-PT), nomes de variáveis e funções em inglês.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

# ──────────────────────────────────────────────────────────────────────
# Logger do módulo — mensagens em português
# ──────────────────────────────────────────────────────────────────────
logger = logging.getLogger("risk_manager")


# ──────────────────────────────────────────────────────────────────────
# Enums auxiliares
# ──────────────────────────────────────────────────────────────────────
class RiskStatus(str, Enum):
    """Estado do resultado de uma verificação de risco."""
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    WARNING = "WARNING"


class KillSwitchLevel(str, Enum):
    """Nível do kill switch ativado."""
    NONE = "NONE"
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"


# ──────────────────────────────────────────────────────────────────────
# Dataclasses de resultados
# ──────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class RiskCheckResult:
    """
    Resultado de uma verificação de risco individual.

    Utilizado internamente por cada método check_* para comunicar
    o estado da verificação ao chamador.
    """
    passed: bool
    status: RiskStatus
    metric_name: str
    current_value: float
    limit_value: float
    message: str
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __str__(self) -> str:
        icon = "OK" if self.passed else "FALHOU"
        return (
            f"[{icon}] {self.metric_name}: "
            f"{self.current_value:.4f} / limite {self.limit_value:.4f} — {self.message}"
        )


@dataclass(frozen=True)
class OrderValidation:
    """
    Resultado da validação completa de uma ordem antes de submissão.

    Contém a decisão final (aprovada/rejeitada), o motivo de rejeição
    (se aplicável) e a lista detalhada de todas as verificações realizadas.
    """
    approved: bool
    rejection_reason: str
    checks: list[RiskCheckResult]
    position_size: int = 0
    risk_amount: float = 0.0
    risk_percent: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __str__(self) -> str:
        estado = "APROVADA" if self.approved else f"REJEITADA — {self.rejection_reason}"
        return (
            f"Validação de ordem: {estado} | "
            f"Tamanho: {self.position_size} | "
            f"Risco: {self.risk_amount:.2f} ({self.risk_percent:.2%})"
        )


def check_correlation_limit(
    new_symbol: str,
    open_positions: list[str],
    returns_map: dict[str, list[float]],
    max_correlation: float = 0.70,
    lookback: int = 60,
) -> bool:
    """Verifica se um novo instrumento tem correlação excessiva com posições abertas.

    Bloqueia a abertura se a correlação de Pearson com qualquer posição
    aberta for superior a max_correlation (70% por defeito).

    Integrar em validate_order() como verificação adicional para módulos
    multi-instrumento (ETFs internacionais, commodities, sector rotation).

    Args:
        new_symbol: Símbolo do novo instrumento a avaliar.
        open_positions: Lista de símbolos com posição aberta.
        returns_map: Dicionário {symbol: [retornos diários]} com pelo menos
                     lookback dias de dados para cada símbolo.
        max_correlation: Correlação máxima permitida (0.70 = 70%).
        lookback: Número de dias para o cálculo (60 = trimestral).

    Returns:
        True se permitido (correlação OK), False se bloqueado.
    """
    if not open_positions:
        return True

    if new_symbol not in returns_map:
        logger.warning(
            "Sem dados de retornos para %s — a bloquear por precaução.",
            new_symbol,
        )
        return False

    new_returns = returns_map[new_symbol][-lookback:]

    for pos_symbol in open_positions:
        if pos_symbol not in returns_map:
            continue

        pos_returns = returns_map[pos_symbol][-lookback:]
        min_len = min(len(new_returns), len(pos_returns))

        if min_len < lookback * 0.5:
            continue

        nr = new_returns[-min_len:]
        pr = pos_returns[-min_len:]
        n = len(nr)

        mean_nr = sum(nr) / n
        mean_pr = sum(pr) / n

        cov = sum((a - mean_nr) * (b - mean_pr) for a, b in zip(nr, pr)) / n
        std_nr = math.sqrt(sum((a - mean_nr) ** 2 for a in nr) / n)
        std_pr = math.sqrt(sum((b - mean_pr) ** 2 for b in pr) / n)

        if std_nr == 0 or std_pr == 0:
            continue

        corr = cov / (std_nr * std_pr)

        if corr > max_correlation:
            logger.info(
                "Correlacao %s<->%s = %.2f > %.2f -- BLOQUEADO.",
                new_symbol, pos_symbol, corr, max_correlation,
            )
            return False

    return True


# ──────────────────────────────────────────────────────────────────────
# Classe principal: RiskManager
# ──────────────────────────────────────────────────────────────────────
class RiskManager:
    """
    Gestão de risco autónoma para o bot de trading.

    Implementa as regras de ferro extraídas da investigação:
    1. Stop-loss em CADA ordem — sem exceção
    2. ZERO averaging down — NUNCA comprar mais num nível em perda
    3. Risco por nível: máximo 1% do capital (cap absoluto 5% via Half-Kelly)
    4. Kill switch: 10% drawdown mensal para TUDO
    5. Risk of ruin calculado deve ser < 0.1%
    6. PAPER_TRADING=true por defeito

    Parâmetros por defeito baseados na investigação:
    - risk_per_level: 1% do capital por nível de grid
    - kelly_cap: 5% — limite máximo independentemente do Kelly
    - daily_loss_limit: 3% — pausa automática
    - weekly_loss_limit: 6% — pausa automática
    - monthly_dd_limit: 10% — kill switch total
    - max_positions: 8 — posições simultâneas
    - max_grids: 3 — grids ativas simultâneas
    - min_rr: 2.5 — rácio risco/recompensa mínimo (R:R 2.5:1)
    """

    def __init__(
        self,
        capital: float,
        risk_per_level: float = 0.01,
        kelly_cap: float = 0.05,
        stop_atr_mult: float = 1.0,
        tp_atr_mult: float = 2.5,
        daily_loss_limit: float = 0.03,
        weekly_loss_limit: float = 0.06,
        monthly_dd_limit: float = 0.10,
        max_positions: int = 8,
        max_grids: int = 3,
        min_rr: float = 2.5,
    ) -> None:
        """
        Inicializa o gestor de risco com os parâmetros da investigação.

        Args:
            capital: Capital total disponível na conta.
            risk_per_level: Fracção máxima do capital em risco por nível de grid (1%).
            kelly_cap: Fracção máxima absoluta do capital por nível via Kelly (5%).
            stop_atr_mult: Multiplicador de ATR para o stop-loss.
            tp_atr_mult: Multiplicador de ATR para o take-profit.
            daily_loss_limit: Perda diária máxima em fracção do capital (3%).
            weekly_loss_limit: Perda semanal máxima em fracção do capital (6%).
            monthly_dd_limit: Drawdown mensal máximo — kill switch (10%).
            max_positions: Número máximo de posições simultâneas abertas.
            max_grids: Número máximo de grids ativas em simultâneo.
            min_rr: Rácio risco/recompensa mínimo exigido (2.5 = alvo >= 2.5x risco).
        """
        # Validação de parâmetros de entrada
        if capital <= 0:
            raise ValueError("Capital deve ser positivo.")
        if not (0 < risk_per_level <= 1):
            raise ValueError("risk_per_level deve estar entre 0 e 1 (exclusivo/inclusivo).")
        if not (0 < kelly_cap <= 1):
            raise ValueError("kelly_cap deve estar entre 0 e 1.")
        if not (0 < daily_loss_limit <= 1):
            raise ValueError("daily_loss_limit deve estar entre 0 e 1.")
        if not (0 < weekly_loss_limit <= 1):
            raise ValueError("weekly_loss_limit deve estar entre 0 e 1.")
        if not (0 < monthly_dd_limit <= 1):
            raise ValueError("monthly_dd_limit deve estar entre 0 e 1.")
        if max_positions < 1:
            raise ValueError("max_positions deve ser >= 1.")
        if max_grids < 1:
            raise ValueError("max_grids deve ser >= 1.")
        if min_rr <= 0:
            raise ValueError("min_rr deve ser positivo.")

        self._capital: float = capital
        self._initial_capital: float = capital
        self.peak_equity: float = capital  # Finding 8
        self.risk_per_level: float = risk_per_level
        self.kelly_cap: float = kelly_cap
        self.stop_atr_mult: float = stop_atr_mult
        self.tp_atr_mult: float = tp_atr_mult
        self.daily_loss_limit: float = daily_loss_limit
        self.weekly_loss_limit: float = weekly_loss_limit
        self.monthly_dd_limit: float = monthly_dd_limit
        self.max_positions: int = max_positions
        self.max_grids: int = max_grids
        self.min_rr: float = min_rr

        # Registo de níveis em perda — para aplicar zero averaging down
        # Chave: (símbolo, nível) → True se nível está em perda
        self._losing_levels: dict[tuple[str, int], bool] = {}

        logger.info(
            "Gestor de risco inicializado — Capital: %.2f | "
            "Risco/nível: %.1f%% | Kelly cap: %.1f%% | "
            "Stop ATR: %.2f | TP ATR: %.2f | "
            "Kill switch mensal: %.1f%% | "
            "Max posições: %d | Max grids: %d | R:R mínimo: %.1f",
            capital,
            risk_per_level * 100,
            kelly_cap * 100,
            stop_atr_mult,
            tp_atr_mult,
            monthly_dd_limit * 100,
            max_positions,
            max_grids,
            min_rr,
        )

    # ──────────────────────────────────────────────────────────────────
    # Propriedades
    # ──────────────────────────────────────────────────────────────────
    @property
    def capital(self) -> float:
        """Capital actual da conta."""
        return self._capital

    @property
    def initial_capital(self) -> float:
        """Capital inicial registado no arranque."""
        return self._initial_capital

    def update_peak_equity(self, current_equity: float) -> None:  # Finding 8
        """Actualiza o máximo histórico do capital."""  # Finding 8
        if current_equity > self.peak_equity:  # Finding 8
            self.peak_equity = current_equity  # Finding 8

    def apply_drawdown_scaling(self, base_size: int) -> int:  # Finding 8
        """  # Finding 8
        Reduz posição 50% quando DD ≥ metade do limite mensal.  # Finding 8
        Finding 8 — Half-Kelly drawdown recovery.  # Finding 8
        """  # Finding 8
        if self.peak_equity <= 0:  # Finding 8
            return base_size  # Finding 8
        drawdown = (self.peak_equity - self.capital) / self.peak_equity  # Finding 8
        trigger = self.monthly_dd_limit / 2.0  # Finding 8
        if drawdown >= trigger:  # Finding 8
            scaled = max(1, int(base_size * 0.5))  # Finding 8
            logger.warning(  # Finding 8
                "Half-Kelly activado: DD=%.2f%% ≥ %.2f%%. "  # Finding 8
                "Posição %d → %d. # Finding 8",  # Finding 8
                drawdown * 100, trigger * 100, base_size, scaled,  # Finding 8
            )  # Finding 8
            return scaled  # Finding 8
        return base_size  # Finding 8

    def dynamic_risk_per_level(self, num_levels: int) -> float:  # Finding 4d
        """  # Finding 4d
        Risco por nível = kelly_cap / num_níveis.  # Finding 4d
        Garante que risco total da grid ≤ Kelly cap. Finding 4d.  # Finding 4d
        """  # Finding 4d
        return min(self.risk_per_level, self.kelly_cap / max(1, num_levels))  # Finding 4d

    def calculate_dynamic_win_rate(  # WinRate
        self,  # WinRate
        trades_log_path: Any,  # WinRate
        lookback: int = 100,  # WinRate
        min_trades: int = 20,  # WinRate
    ) -> float:  # WinRate
        """  # WinRate
        Win rate real dos últimos N trades fechados.  # WinRate
        Substitui o valor estático de 50% assumido no Kelly.  # WinRate
        Requer mínimo de 20 trades para activar.  # WinRate
        Retorna 0.50 se dados insuficientes. # WinRate  # WinRate
        """  # WinRate
        try:  # WinRate
            import json  # WinRate
            from pathlib import Path  # WinRate

            path = Path(trades_log_path)  # WinRate
            if not path.exists():  # WinRate
                return 0.50  # WinRate
            data = json.loads(path.read_text(encoding="utf-8"))  # WinRate
            trades = data.get("trades", [])  # WinRate
            closed = [  # WinRate
                t for t in trades  # WinRate
                if t.get("pnl") is not None and t.get("side") == "SELL"  # WinRate
            ]  # WinRate
            if len(closed) < min_trades:  # WinRate
                logger.debug(  # WinRate
                    "Win rate dinâmico: %d trades (mínimo %d). "  # WinRate
                    "A usar 0.50. # WinRate",  # WinRate
                    len(closed), min_trades,  # WinRate
                )  # WinRate
                return 0.50  # WinRate
            recent = closed[-lookback:]  # WinRate
            wins = sum(1 for t in recent if float(t.get("pnl", 0)) > 0)  # WinRate
            rate = wins / len(recent)  # WinRate
            rate = max(0.35, min(0.80, rate))  # WinRate
            logger.info(  # WinRate
                "Win rate dinâmico: %.1f%% (%d/%d trades). # WinRate",  # WinRate
                rate * 100, wins, len(recent),  # WinRate
            )  # WinRate
            return rate  # WinRate
        except Exception as exc:  # noqa: BLE001  # WinRate
            logger.warning(  # WinRate
                "Erro no win rate dinâmico: %s. A usar 0.50. # WinRate",  # WinRate
                exc,  # WinRate
            )  # WinRate
            return 0.50  # WinRate

    # ──────────────────────────────────────────────────────────────────
    # Position Sizing — Half-Kelly Criterion
    # ──────────────────────────────────────────────────────────────────
    def position_size_per_level(
        self,
        capital: float,
        entry: float,
        stop: float,
        win_rate: float = 0.5,
        payoff_ratio: float = 2.5,
        num_levels: int = 1,  # Finding 4d
    ) -> int:
        """
        Calcula o tamanho da posição por nível de grid usando Half-Kelly.

        Algoritmo (da investigação):
        1. Kelly: K = win_rate - (1 - win_rate) / payoff_ratio
        2. Half-Kelly: K / 2  (captura ~75% do crescimento com ~50% da volatilidade)
        3. Cap por Kelly: min(K/2, kelly_cap)  — nunca mais de 5% do capital
        4. Cap por risco/nível: min(capped_kelly, risk_per_level)  — nunca mais de 1%
        5. risk_amount = capital * fracção_final
        6. quantity = risk_amount / |entry - stop|
        7. Retorna int (floor) — arredondamento conservador

        Args:
            capital: Capital disponível para o cálculo.
            entry: Preço de entrada previsto.
            stop: Preço do stop-loss.
            win_rate: Taxa de acerto histórica (0 a 1). Defeito: 0.50.
            payoff_ratio: Rácio ganho médio / perda média. Defeito: 2.5.

        Returns:
            Quantidade inteira de unidades a comprar (floor). Retorna 0 se
            os parâmetros resultarem em risco inválido.
        """
        # Validações de segurança
        if capital <= 0:
            logger.warning("Capital inválido (%.2f) — retorna tamanho 0.", capital)
            return 0

        if entry <= 0 or stop <= 0:
            logger.warning(
                "Preço de entrada (%.4f) ou stop (%.4f) inválido — retorna tamanho 0.",
                entry, stop,
            )
            return 0

        risk_per_unit = abs(entry - stop)
        if risk_per_unit == 0:
            logger.warning("Entry e stop são iguais — impossível calcular posição.")
            return 0

        if not (0 < win_rate < 1):
            logger.warning("Win rate (%.4f) fora do intervalo ]0, 1[ — retorna tamanho 0.", win_rate)
            return 0

        if payoff_ratio <= 0:
            logger.warning("Payoff ratio (%.4f) deve ser positivo — retorna tamanho 0.", payoff_ratio)
            return 0

        # 1. Fórmula de Kelly: K = W - (1 - W) / R
        kelly = win_rate - (1.0 - win_rate) / payoff_ratio

        # Se Kelly é negativo ou zero, a estratégia não tem edge — não operar
        if kelly <= 0:
            logger.info(
                "Kelly negativo ou zero (%.4f) — estratégia sem edge. "
                "Win rate: %.2f, Payoff: %.2f. Tamanho = 0.",
                kelly, win_rate, payoff_ratio,
            )
            return 0

        # 2. Half-Kelly: captura ~75% do crescimento com ~50% da volatilidade
        half_kelly = kelly / 2.0

        # 3. Cap pelo kelly_cap (5% — limite absoluto da investigação)
        capped_kelly = min(half_kelly, self.kelly_cap)

        # 4. Cap pelo risk_per_level (1% — risco máximo por nível de grid)
        final_fraction = min(capped_kelly, self.dynamic_risk_per_level(num_levels))  # Finding 4d

        # 5. Montante de risco em unidades monetárias
        risk_amount = capital * final_fraction

        # 6. Quantidade = risco_total / risco_por_unidade
        quantity = risk_amount / risk_per_unit

        # 7. Floor — arredondamento conservador (nunca arriscar mais do que calculado)
        size = int(math.floor(quantity))

        logger.debug(
            "Position sizing — Kelly: %.4f | Half-Kelly: %.4f | "
            "Cap: %.4f | Fracção final: %.4f | "
            "Risco: %.2f | Qty: %d | Entry: %.4f | Stop: %.4f",
            kelly, half_kelly, capped_kelly, final_fraction,
            risk_amount, size, entry, stop,
        )

        size = self.apply_drawdown_scaling(size)  # Finding 8
        return max(size, 0)  # Finding 8

    # ──────────────────────────────────────────────────────────────────
    # Verificações de limites de perda (Kill Switches)
    # ──────────────────────────────────────────────────────────────────
    def check_daily_limit(self, daily_pnl: float, capital: float) -> bool:
        """
        Verifica se a perda diária excede o limite de 3%.

        Args:
            daily_pnl: P&L acumulado do dia (negativo = perda).
            capital: Capital de referência para o cálculo da percentagem.

        Returns:
            True se está dentro do limite (pode continuar a operar).
            False se excedeu — deve pausar todas as operações.
        """
        if capital <= 0:
            logger.error("Capital inválido (%.2f) na verificação de limite diário.", capital)
            return False

        # Perda diária em percentagem do capital (valor absoluto)
        loss_pct = abs(min(daily_pnl, 0)) / capital

        within_limit = loss_pct < self.daily_loss_limit

        if not within_limit:
            logger.warning(
                "LIMITE DIARIO EXCEDIDO — Perda: %.2f (%.2f%%) | "
                "Limite: %.2f%% do capital (%.2f). Operações devem ser pausadas.",
                daily_pnl, loss_pct * 100,
                self.daily_loss_limit * 100, capital,
            )
        else:
            logger.debug(
                "Limite diário OK — P&L: %.2f (%.2f%%) | Limite: %.2f%%.",
                daily_pnl, loss_pct * 100, self.daily_loss_limit * 100,
            )

        return within_limit

    def check_weekly_limit(self, weekly_pnl: float, capital: float) -> bool:
        """
        Verifica se a perda semanal excede o limite de 6%.

        Args:
            weekly_pnl: P&L acumulado da semana (negativo = perda).
            capital: Capital de referência.

        Returns:
            True se está dentro do limite (pode continuar).
            False se excedeu — deve pausar operações.
        """
        if capital <= 0:
            logger.error("Capital inválido (%.2f) na verificação de limite semanal.", capital)
            return False

        loss_pct = abs(min(weekly_pnl, 0)) / capital

        within_limit = loss_pct < self.weekly_loss_limit

        if not within_limit:
            logger.warning(
                "LIMITE SEMANAL EXCEDIDO — Perda: %.2f (%.2f%%) | "
                "Limite: %.2f%% do capital (%.2f). Operações devem ser pausadas.",
                weekly_pnl, loss_pct * 100,
                self.weekly_loss_limit * 100, capital,
            )
        else:
            logger.debug(
                "Limite semanal OK — P&L: %.2f (%.2f%%) | Limite: %.2f%%.",
                weekly_pnl, loss_pct * 100, self.weekly_loss_limit * 100,
            )

        return within_limit

    def check_kill_switch(self, monthly_pnl: float, capital: float) -> bool:
        """
        Verifica o kill switch mensal — drawdown de 10% para TUDO.

        Esta é a protecção de último recurso. Se activada, o bot deve:
        - Fechar TODAS as posições abertas
        - Cancelar TODAS as ordens pendentes
        - Enviar alerta Telegram imediato
        - NÃO reiniciar automaticamente (requer confirmação manual)

        Args:
            monthly_pnl: P&L acumulado do mês (negativo = perda).
            capital: Capital de referência.

        Returns:
            True se está dentro do limite (pode continuar).
            False se o kill switch deve ser activado.
        """
        if capital <= 0:
            logger.error("Capital inválido (%.2f) na verificação do kill switch.", capital)
            return False

        loss_pct = abs(min(monthly_pnl, 0)) / capital

        within_limit = loss_pct < self.monthly_dd_limit

        if not within_limit:
            logger.critical(
                "KILL SWITCH ACTIVADO — Drawdown mensal: %.2f (%.2f%%) | "
                "Limite: %.2f%% do capital (%.2f). "
                "TODAS as operações devem ser encerradas IMEDIATAMENTE. "
                "Requer confirmação manual para reiniciar.",
                monthly_pnl, loss_pct * 100,
                self.monthly_dd_limit * 100, capital,
            )
        else:
            logger.debug(
                "Kill switch OK — P&L mensal: %.2f (%.2f%%) | Limite: %.2f%%.",
                monthly_pnl, loss_pct * 100, self.monthly_dd_limit * 100,
            )

        return within_limit

    # ──────────────────────────────────────────────────────────────────
    # Verificações de exposição
    # ──────────────────────────────────────────────────────────────────
    def check_max_positions(self, current_positions: int) -> bool:
        """
        Verifica se o número de posições simultâneas está dentro do limite.

        Args:
            current_positions: Número actual de posições abertas.

        Returns:
            True se pode abrir mais posições.
            False se atingiu o limite máximo.
        """
        within_limit = current_positions < self.max_positions

        if not within_limit:
            logger.warning(
                "LIMITE DE POSICOES ATINGIDO — Abertas: %d | Máximo: %d. "
                "Não é possível abrir novas posições.",
                current_positions, self.max_positions,
            )
        else:
            logger.debug(
                "Posições OK — Abertas: %d / %d.",
                current_positions, self.max_positions,
            )

        return within_limit

    def check_max_grids(self, current_grids: int) -> bool:
        """
        Verifica se o número de grids activas está dentro do limite.

        Args:
            current_grids: Número actual de grids activas.

        Returns:
            True se pode criar mais grids.
            False se atingiu o limite máximo.
        """
        within_limit = current_grids < self.max_grids

        if not within_limit:
            logger.warning(
                "LIMITE DE GRIDS ATINGIDO — Activas: %d | Máximo: %d. "
                "Não é possível criar novas grids.",
                current_grids, self.max_grids,
            )
        else:
            logger.debug(
                "Grids OK — Activas: %d / %d.",
                current_grids, self.max_grids,
            )

        return within_limit

    # ──────────────────────────────────────────────────────────────────
    # Risk of Ruin — Cálculo matemático
    # ──────────────────────────────────────────────────────────────────
    def calculate_risk_of_ruin(
        self,
        win_rate: float,
        payoff_ratio: float,
        risk_per_trade: float,
    ) -> float:
        """
        Calcula a probabilidade de ruína usando a fórmula clássica.

        A fórmula utilizada é a aproximação de Perry Kaufman adaptada para
        trading com diferentes payoff ratios:

            Se edge > 0:
                RoR = ((1 - edge) / (1 + edge)) ^ unidades_de_capital

            Onde:
                edge = (win_rate * payoff_ratio) - (1 - win_rate)
                        → expectância por unidade de risco
                unidades_de_capital = 1 / risk_per_trade
                        → número de perdas consecutivas até ruína

        Se o edge é zero ou negativo (sem vantagem estatística), o risco
        de ruína é 1.0 (100%) — ruína certa a longo prazo.

        Meta da investigação: Risk of Ruin < 0.1% (essencialmente zero).

        Exemplos da investigação:
        - 1% risco/trade, 50% WR, 2:1 R:R → RoR aprox. 0%
        - 5% risco/trade, 50% WR, 2:1 R:R → RoR aprox. 13% (INACEITÁVEL)
        - 10% risco/trade, 50% WR, 2:1 R:R → RoR > 50% (CATASTRÓFICO)

        Args:
            win_rate: Taxa de acerto (0 a 1).
            payoff_ratio: Rácio ganho médio / perda média (> 0).
            risk_per_trade: Fracção do capital arriscada por trade (0 a 1).

        Returns:
            Probabilidade de ruína entre 0.0 e 1.0.
        """
        # Validações
        if not (0 < win_rate < 1):
            logger.error("Win rate (%.4f) fora do intervalo ]0, 1[.", win_rate)
            return 1.0

        if payoff_ratio <= 0:
            logger.error("Payoff ratio (%.4f) deve ser positivo.", payoff_ratio)
            return 1.0

        if not (0 < risk_per_trade < 1):
            logger.error("Risco por trade (%.4f) fora do intervalo ]0, 1[.", risk_per_trade)
            return 1.0

        # Probabilidade de perda
        loss_rate = 1.0 - win_rate

        # Edge (expectância por unidade de risco)
        # edge = ganho_esperado - perda_esperada (por unidade arriscada)
        edge = (win_rate * payoff_ratio) - loss_rate

        if edge <= 0:
            # Sem vantagem estatística — ruína é certa
            logger.warning(
                "Edge negativo ou zero (%.4f) — sem vantagem estatística. "
                "Risk of Ruin = 100%%. Win rate: %.2f, Payoff: %.2f.",
                edge, win_rate, payoff_ratio,
            )
            return 1.0

        # Número de unidades de capital (quantas perdas consecutivas até ruína)
        capital_units = 1.0 / risk_per_trade

        # Probabilidade de perda ajustada pelo payoff
        # Usamos a fórmula de risco de ruína baseada na vantagem:
        #   p = probabilidade de ganhar uma "unidade de jogo"
        #   q = probabilidade de perder uma "unidade de jogo"
        #
        # Com payoff ratio != 1, convertemos para probabilidades equivalentes:
        #   p_adj = win_rate * payoff_ratio / (win_rate * payoff_ratio + loss_rate)
        #   q_adj = loss_rate / (win_rate * payoff_ratio + loss_rate)
        #
        #   RoR = (q_adj / p_adj) ^ capital_units
        p_adj = (win_rate * payoff_ratio) / (win_rate * payoff_ratio + loss_rate)
        q_adj = loss_rate / (win_rate * payoff_ratio + loss_rate)

        if p_adj <= 0 or p_adj <= q_adj:
            # Cenário sem vantagem após ajuste
            logger.warning(
                "Probabilidade ajustada sem vantagem — p_adj: %.4f, q_adj: %.4f. "
                "Risk of Ruin = 100%%.",
                p_adj, q_adj,
            )
            return 1.0

        # Fórmula de ruína: (q/p) ^ n
        ratio = q_adj / p_adj
        risk_of_ruin = ratio ** capital_units

        # Limitar ao intervalo [0, 1] por segurança numérica
        risk_of_ruin = max(0.0, min(1.0, risk_of_ruin))

        logger.info(
            "Risk of Ruin calculado: %.6f%% | "
            "Edge: %.4f | Unidades capital: %.0f | "
            "Win rate: %.2f | Payoff: %.2f | Risco/trade: %.2f%%",
            risk_of_ruin * 100,
            edge, capital_units,
            win_rate, payoff_ratio, risk_per_trade * 100,
        )

        # Aviso se o risco de ruína excede 1%
        if risk_of_ruin > 0.01:
            logger.warning(
                "ATENCAO: Risk of Ruin (%.4f%%) excede 1%%. "
                "A investigação define < 0.1%% como meta. "
                "O bot DEVE RECUSAR arrancar com este nível de risco.",
                risk_of_ruin * 100,
            )

        return risk_of_ruin

    # ──────────────────────────────────────────────────────────────────
    # Zero Averaging Down — Gestão de níveis em perda
    # ──────────────────────────────────────────────────────────────────
    def mark_level_losing(self, symbol: str, level: int) -> None:
        """
        Marca um nível de grid como estando em perda.

        Após esta marcação, qualquer tentativa de comprar mais neste nível
        será bloqueada pela regra de zero averaging down.

        Args:
            symbol: Símbolo do ativo (ex: "AAPL").
            level: Número do nível na grid.
        """
        key = (symbol, level)
        self._losing_levels[key] = True
        logger.info(
            "Nível marcado como em perda — %s nível %d. "
            "Zero averaging down: compras adicionais bloqueadas.",
            symbol, level,
        )

    def clear_level_losing(self, symbol: str, level: int) -> None:
        """
        Remove a marcação de perda de um nível (após fecho ou stop-loss).

        Args:
            symbol: Símbolo do ativo.
            level: Número do nível na grid.
        """
        key = (symbol, level)
        self._losing_levels.pop(key, None)
        logger.debug(
            "Marcação de perda removida — %s nível %d.",
            symbol, level,
        )

    def is_level_losing(self, symbol: str, level: int) -> bool:
        """
        Verifica se um nível está marcado como em perda.

        Args:
            symbol: Símbolo do ativo.
            level: Número do nível na grid.

        Returns:
            True se o nível está em perda (compras bloqueadas).
        """
        return self._losing_levels.get((symbol, level), False)

    def check_averaging_down(self, symbol: str, level: int) -> bool:
        """
        Verifica se é seguro comprar num nível (regra de zero averaging down).

        Regra absoluta da investigação (Kotegawa): NUNCA comprar mais
        num nível que está em perda. Averaging down é proibido.

        Args:
            symbol: Símbolo do ativo.
            level: Número do nível na grid.

        Returns:
            True se pode comprar (nível NÃO está em perda).
            False se averaging down seria violado.
        """
        if self.is_level_losing(symbol, level):
            logger.warning(
                "ZERO AVERAGING DOWN — Compra bloqueada em %s nível %d. "
                "O nível está em perda. Averaging down é PROIBIDO.",
                symbol, level,
            )
            return False
        return True

    # ──────────────────────────────────────────────────────────────────
    # Validação completa de ordens
    # ──────────────────────────────────────────────────────────────────
    def _build_order_validation(self, order_params: dict[str, Any]) -> OrderValidation:
        """Constroi o resultado detalhado da validacao de risco de uma ordem."""
        checks: list[RiskCheckResult] = []
        rejection_reasons: list[str] = []

        # ── Extracção de parâmetros com defaults seguros ──
        symbol: str = order_params.get("symbol", "UNKNOWN")
        entry_price: float = order_params.get("entry_price", 0.0)
        stop_price: float | None = order_params.get("stop_price", None)
        take_profit_price: float | None = order_params.get("take_profit_price", None)
        capital: float = order_params.get("capital", self._capital)
        daily_pnl: float = order_params.get("daily_pnl", 0.0)
        weekly_pnl: float = order_params.get("weekly_pnl", 0.0)
        monthly_pnl: float = order_params.get("monthly_pnl", 0.0)
        current_positions: int = order_params.get("current_positions", 0)
        current_grids: int = order_params.get("current_grids", 0)
        level: int | None = order_params.get("level", None)
        win_rate: float = order_params.get("win_rate", 0.5)
        payoff_ratio: float = order_params.get("payoff_ratio", 2.5)
        num_levels: int = order_params.get("num_levels", 1)  # Finding 4d
        open_positions: list[str] = list(order_params.get("open_positions", []) or [])
        returns_map: dict[str, list[float]] = dict(order_params.get("returns_map", {}) or {})
        max_correlation: float = float(order_params.get("max_correlation", 0.70))
        position_size = 0
        risk_amount = 0.0
        risk_percent = 0.0

        sizing_inputs_valid = (
            stop_price is not None
            and stop_price > 0
            and entry_price > 0
            and capital > 0
        )
        if sizing_inputs_valid:
            position_size = self.position_size_per_level(
                capital,
                entry_price,
                stop_price,
                win_rate,
                payoff_ratio,
                num_levels,
            )
            risk_per_unit = abs(entry_price - stop_price)
            risk_amount = position_size * risk_per_unit
            risk_percent = risk_amount / capital if capital > 0 else 0.0

        # ── 1. Stop-loss obrigatório (regra de ferro #1) ──
        if stop_price is None or stop_price <= 0:
            msg = "Stop-loss OBRIGATORIO em cada ordem — sem excepção."
            checks.append(RiskCheckResult(
                passed=False,
                status=RiskStatus.REJECTED,
                metric_name="stop_loss_presente",
                current_value=0.0,
                limit_value=1.0,
                message=msg,
            ))
            rejection_reasons.append(msg)
            logger.error("Ordem rejeitada para %s — %s", symbol, msg)
        else:
            checks.append(RiskCheckResult(
                passed=True,
                status=RiskStatus.APPROVED,
                metric_name="stop_loss_presente",
                current_value=stop_price,
                limit_value=stop_price,
                message="Stop-loss presente.",
            ))

        # ── 2. Preço de entrada válido ──
        if entry_price <= 0:
            msg = "Preço de entrada inválido (deve ser positivo)."
            checks.append(RiskCheckResult(
                passed=False,
                status=RiskStatus.REJECTED,
                metric_name="entry_price_valido",
                current_value=entry_price,
                limit_value=0.0,
                message=msg,
            ))
            rejection_reasons.append(msg)
            logger.error("Ordem rejeitada para %s — %s", symbol, msg)
        else:
            checks.append(RiskCheckResult(
                passed=True,
                status=RiskStatus.APPROVED,
                metric_name="entry_price_valido",
                current_value=entry_price,
                limit_value=0.0,
                message="Preço de entrada válido.",
            ))

        # ── 3. Rácio risco/recompensa mínimo (R:R >= min_rr) ──
        if stop_price and stop_price > 0 and entry_price > 0 and take_profit_price and take_profit_price > 0:
            risk = abs(entry_price - stop_price)
            reward = abs(take_profit_price - entry_price)
            rr_ratio = reward / risk if risk > 0 else 0.0

            rr_ok = rr_ratio >= self.min_rr
            if not rr_ok:
                msg = (
                    f"Rácio R:R insuficiente: {rr_ratio:.2f} (mínimo: {self.min_rr:.1f}). "
                    f"Alvo deve ser >= {self.min_rr:.1f}x o risco."
                )
                rejection_reasons.append(msg)
                logger.warning("Ordem para %s — %s", symbol, msg)

            checks.append(RiskCheckResult(
                passed=rr_ok,
                status=RiskStatus.APPROVED if rr_ok else RiskStatus.REJECTED,
                metric_name="rr_ratio",
                current_value=rr_ratio,
                limit_value=self.min_rr,
                message=f"R:R = {rr_ratio:.2f}" if rr_ok else msg,
            ))

        # ── 4. Risco por nível dentro dos limites ──
        if sizing_inputs_valid:
            max_risk_pct = min(self.kelly_cap, self.dynamic_risk_per_level(num_levels))  # Finding 4d

            risk_ok = risk_percent <= max_risk_pct + 1e-9  # Tolerância numérica
            if not risk_ok:
                msg = (
                    f"Risco por nível excede limite: {risk_percent:.4%} "
                    f"(máximo: {max_risk_pct:.4%})."
                )
                rejection_reasons.append(msg)

            checks.append(RiskCheckResult(
                passed=risk_ok,
                status=RiskStatus.APPROVED if risk_ok else RiskStatus.REJECTED,
                metric_name="risco_por_nivel",
                current_value=risk_percent,
                limit_value=max_risk_pct,
                message=f"Risco: {risk_percent:.4%}" if risk_ok else msg,
            ))

        # ── 5. Limite diário ──
        daily_ok = self.check_daily_limit(daily_pnl, capital)
        if not daily_ok:
            msg = f"Limite de perda diária excedido: {daily_pnl:.2f}."
            rejection_reasons.append(msg)

        checks.append(RiskCheckResult(
            passed=daily_ok,
            status=RiskStatus.APPROVED if daily_ok else RiskStatus.REJECTED,
            metric_name="limite_diario",
            current_value=abs(min(daily_pnl, 0)) / capital if capital > 0 else 0.0,
            limit_value=self.daily_loss_limit,
            message="Limite diário OK." if daily_ok else msg,
        ))

        # ── 6. Limite semanal ──
        weekly_ok = self.check_weekly_limit(weekly_pnl, capital)
        if not weekly_ok:
            msg = f"Limite de perda semanal excedido: {weekly_pnl:.2f}."
            rejection_reasons.append(msg)

        checks.append(RiskCheckResult(
            passed=weekly_ok,
            status=RiskStatus.APPROVED if weekly_ok else RiskStatus.REJECTED,
            metric_name="limite_semanal",
            current_value=abs(min(weekly_pnl, 0)) / capital if capital > 0 else 0.0,
            limit_value=self.weekly_loss_limit,
            message="Limite semanal OK." if weekly_ok else msg,
        ))

        # ── 7. Kill switch mensal ──
        monthly_ok = self.check_kill_switch(monthly_pnl, capital)
        if not monthly_ok:
            msg = f"KILL SWITCH — Drawdown mensal excedido: {monthly_pnl:.2f}."
            rejection_reasons.append(msg)

        checks.append(RiskCheckResult(
            passed=monthly_ok,
            status=RiskStatus.APPROVED if monthly_ok else RiskStatus.REJECTED,
            metric_name="kill_switch_mensal",
            current_value=abs(min(monthly_pnl, 0)) / capital if capital > 0 else 0.0,
            limit_value=self.monthly_dd_limit,
            message="Kill switch OK." if monthly_ok else msg,
        ))

        # ── 8. Máximo de posições ──
        positions_ok = self.check_max_positions(current_positions)
        if not positions_ok:
            msg = f"Limite de posições atingido: {current_positions}/{self.max_positions}."
            rejection_reasons.append(msg)

        checks.append(RiskCheckResult(
            passed=positions_ok,
            status=RiskStatus.APPROVED if positions_ok else RiskStatus.REJECTED,
            metric_name="max_posicoes",
            current_value=float(current_positions),
            limit_value=float(self.max_positions),
            message="Posições OK." if positions_ok else msg,
        ))

        # ── 9. Máximo de grids ──
        grids_ok = self.check_max_grids(current_grids)
        if not grids_ok:
            msg = f"Limite de grids atingido: {current_grids}/{self.max_grids}."
            rejection_reasons.append(msg)

        checks.append(RiskCheckResult(
            passed=grids_ok,
            status=RiskStatus.APPROVED if grids_ok else RiskStatus.REJECTED,
            metric_name="max_grids",
            current_value=float(current_grids),
            limit_value=float(self.max_grids),
            message="Grids OK." if grids_ok else msg,
        ))

        # ── 10. Correlação agregada do portefólio ──
        if open_positions:
            corr_ok = check_correlation_limit(
                new_symbol=symbol,
                open_positions=open_positions,
                returns_map=returns_map,
                max_correlation=max_correlation,
            )
            if not corr_ok:
                msg = (
                    f"Correlação excessiva ou contexto insuficiente para {symbol}. "
                    "Nova exposição bloqueada."
                )
                rejection_reasons.append(msg)

            checks.append(RiskCheckResult(
                passed=corr_ok,
                status=RiskStatus.APPROVED if corr_ok else RiskStatus.REJECTED,
                metric_name="correlacao_portefolio",
                current_value=float(len(open_positions)),
                limit_value=max_correlation,
                message="Correlação agregada OK." if corr_ok else msg,
            ))

        # ── 11. Zero averaging down (se nível especificado) ──
        if level is not None:
            avg_ok = self.check_averaging_down(symbol, level)
            if not avg_ok:
                msg = (
                    f"ZERO AVERAGING DOWN — Nível {level} de {symbol} "
                    f"está em perda. Compra bloqueada."
                )
                rejection_reasons.append(msg)

            checks.append(RiskCheckResult(
                passed=avg_ok,
                status=RiskStatus.APPROVED if avg_ok else RiskStatus.REJECTED,
                metric_name="zero_averaging_down",
                current_value=float(level),
                limit_value=0.0,
                message="Averaging down OK." if avg_ok else msg,
            ))

        # ── Decisão final ──
        approved = len(rejection_reasons) == 0
        rejection_reason = "; ".join(rejection_reasons) if rejection_reasons else ""
        return OrderValidation(
            approved=approved,
            rejection_reason=rejection_reason,
            checks=checks,
            position_size=position_size,
            risk_amount=risk_amount,
            risk_percent=risk_percent,
        )

    def validate_order(self, order_params: dict[str, Any]) -> tuple[bool, str]:
        """
        Validação completa de uma ordem antes de submissão ao broker.

        Verifica TODAS as condições de risco antes de aprovar uma ordem.
        Qualquer falha resulta em rejeição com motivo explícito.

        Parâmetros esperados em order_params:
            - symbol (str): Símbolo do ativo.
            - entry_price (float): Preço de entrada.
            - stop_price (float): Preço do stop-loss (OBRIGATÓRIO).
            - take_profit_price (float): Preço do take-profit.
            - capital (float): Capital actual disponível.
            - daily_pnl (float): P&L acumulado do dia.
            - weekly_pnl (float): P&L acumulado da semana.
            - monthly_pnl (float): P&L acumulado do mês.
            - current_positions (int): Número actual de posições.
            - current_grids (int): Número actual de grids activas.
            - level (int, opcional): Nível da grid (para verificar averaging down).
            - win_rate (float, opcional): Win rate actual. Defeito: 0.5.
            - payoff_ratio (float, opcional): Payoff ratio actual. Defeito: 2.5.
            - num_levels (int, opcional): Número de níveis planeados na grid. # Finding 4d

        Args:
            order_params: Dicionário com os parâmetros da ordem.

        Returns:
            Tupla (aprovado, motivo_rejeicao).
            Se aprovado=True, motivo_rejeicao é string vazia.
        """
        validation = self._build_order_validation(order_params)
        symbol = order_params.get("symbol", "UNKNOWN")

        if validation.approved:
            logger.info(
                "Ordem APROVADA para %s — Tamanho: %d | Risco: %.2f (%.4f%%).",
                symbol,
                validation.position_size,
                validation.risk_amount,
                validation.risk_percent * 100,
            )
        else:
            logger.warning(
                "Ordem REJEITADA para %s — Motivo(s): %s",
                symbol,
                validation.rejection_reason,
            )

        return (validation.approved, validation.rejection_reason)

    def validate_order_full(self, order_params: dict[str, Any]) -> OrderValidation:
        """
        Validação completa de uma ordem com resultado detalhado.

        Funciona como validate_order mas retorna o objecto OrderValidation
        completo em vez de apenas o tuplo (aprovado, motivo).

        Args:
            order_params: Dicionário com os parâmetros da ordem.

        Returns:
            Objecto OrderValidation com todos os detalhes.
        """
        return self._build_order_validation(order_params)

    # ──────────────────────────────────────────────────────────────────
    # Stop-Loss e Take-Profit baseados em ATR
    # ──────────────────────────────────────────────────────────────────
    def calculate_stop_loss(
        self,
        entry_price: float,
        atr: float,
        multiplier: float | None = None,
    ) -> float:
        """
        Calcula o preço do stop-loss baseado no ATR.

        Fórmula (da investigação):
            stop_loss = entry_price - (multiplier * ATR(14))

        O multiplicador por defeito é 1.0 conforme a auditoria:
        "Stop-loss por nível: 1x ATR(14) abaixo do preço de entrada"

        Args:
            entry_price: Preço de entrada.
            atr: Valor actual do ATR(14).
            multiplier: Multiplicador do ATR para o stop. Defeito: configuração activa.

        Returns:
            Preço do stop-loss. Nunca inferior a 0.

        Raises:
            ValueError: Se entry_price ou atr forem inválidos.
        """
        if entry_price <= 0:
            raise ValueError(f"Preço de entrada inválido: {entry_price}")
        if atr <= 0:
            raise ValueError(f"ATR inválido: {atr}")
        if multiplier is None:
            multiplier = self.stop_atr_mult
        if multiplier <= 0:
            raise ValueError(f"Multiplicador inválido: {multiplier}")

        stop = entry_price - (multiplier * atr)

        # O stop nunca pode ser negativo
        stop = max(stop, 0.01)

        logger.debug(
            "Stop-loss calculado — Entry: %.4f | ATR: %.4f | "
            "Multiplicador: %.2f | Stop: %.4f",
            entry_price, atr, multiplier, stop,
        )

        return round(stop, 6)

    def calculate_take_profit(
        self,
        entry_price: float,
        atr: float,
        multiplier: float | None = None,
    ) -> float:
        """
        Calcula o preço do take-profit baseado no ATR.

        Fórmula (da investigação):
            take_profit = entry_price + (multiplier * ATR(14))

        O multiplicador por defeito é 2.5 conforme a auditoria:
        "Take-profit por nível: 2.5x ATR(14) acima do preço de entrada"

        Isto garante um R:R de 2.5:1 quando combinado com o stop-loss
        de 1x ATR.

        Args:
            entry_price: Preço de entrada.
            atr: Valor actual do ATR(14).
            multiplier: Multiplicador do ATR para o take-profit. Defeito: configuração activa.

        Returns:
            Preço do take-profit.

        Raises:
            ValueError: Se entry_price ou atr forem inválidos.
        """
        if entry_price <= 0:
            raise ValueError(f"Preço de entrada inválido: {entry_price}")
        if atr <= 0:
            raise ValueError(f"ATR inválido: {atr}")
        if multiplier is None:
            multiplier = self.tp_atr_mult
        if multiplier <= 0:
            raise ValueError(f"Multiplicador inválido: {multiplier}")

        tp = entry_price + (multiplier * atr)

        logger.debug(
            "Take-profit calculado — Entry: %.4f | ATR: %.4f | "
            "Multiplicador: %.2f | TP: %.4f",
            entry_price, atr, multiplier, tp,
        )

        return round(tp, 6)

    # ──────────────────────────────────────────────────────────────────
    # Actualização de capital
    # ──────────────────────────────────────────────────────────────────
    def update_capital(self, new_capital: float) -> None:
        """
        Actualiza o capital actual da conta.

        Chamado após cada trade fechado ou quando a conta é reconciliada
        com o broker. O capital inicial mantém-se inalterado para cálculos
        de drawdown.

        Args:
            new_capital: Novo valor do capital da conta.

        Raises:
            ValueError: Se new_capital for negativo.
        """
        if new_capital < 0:
            raise ValueError(
                f"Capital não pode ser negativo: {new_capital}. "
                "Se a conta atingiu zero, o kill switch já deveria ter actuado."
            )

        old_capital = self._capital
        self._capital = new_capital
        self.update_peak_equity(new_capital)  # Finding 8

        # Calcular variação para logging
        change = new_capital - old_capital
        change_pct = (change / old_capital * 100) if old_capital > 0 else 0.0

        # Calcular drawdown desde o início
        dd_from_initial = (
            (new_capital - self._initial_capital) / self._initial_capital * 100
            if self._initial_capital > 0
            else 0.0
        )

        logger.info(
            "Capital actualizado — Anterior: %.2f | Novo: %.2f | "
            "Variação: %+.2f (%+.2f%%) | Desde início: %+.2f%%",
            old_capital, new_capital, change, change_pct, dd_from_initial,
        )

    # ──────────────────────────────────────────────────────────────────
    # Validação de arranque — Risk of Ruin
    # ──────────────────────────────────────────────────────────────────
    def validate_startup(
        self,
        win_rate: float = 0.5,
        payoff_ratio: float = 2.5,
    ) -> RiskCheckResult:
        """
        Validação de risco no arranque do bot.

        Calcula o Risk of Ruin com os parâmetros actuais e verifica
        se está abaixo do limiar de 0.1% definido na investigação.

        Se Risk of Ruin > 1%, o bot DEVE RECUSAR arrancar.

        Args:
            win_rate: Taxa de acerto esperada.
            payoff_ratio: Payoff ratio esperado.

        Returns:
            RiskCheckResult com o resultado da validação.
        """
        ror = self.calculate_risk_of_ruin(
            win_rate=win_rate,
            payoff_ratio=payoff_ratio,
            risk_per_trade=self.risk_per_level,
        )

        # Meta: < 0.1% (0.001)
        # Limite absoluto: 1% (0.01) — acima disto o bot recusa arrancar
        passed = ror < 0.01
        target_met = ror < 0.001

        if not passed:
            message = (
                f"Risk of Ruin ({ror:.4%}) excede o limite absoluto de 1%. "
                f"O bot RECUSA arrancar. Ajustar parâmetros de risco."
            )
            logger.critical(message)
        elif not target_met:
            message = (
                f"Risk of Ruin ({ror:.4%}) está acima da meta de 0.1% "
                f"mas abaixo do limite absoluto de 1%. "
                f"Recomenda-se reduzir o risco por trade."
            )
            logger.warning(message)
        else:
            message = (
                f"Risk of Ruin ({ror:.6%}) está abaixo da meta de 0.1%. "
                f"Parâmetros de risco validados com sucesso."
            )
            logger.info(message)

        return RiskCheckResult(
            passed=passed,
            status=RiskStatus.APPROVED if passed else RiskStatus.REJECTED,
            metric_name="risk_of_ruin_arranque",
            current_value=ror,
            limit_value=0.01,
            message=message,
        )

    # ──────────────────────────────────────────────────────────────────
    # Utilitários
    # ──────────────────────────────────────────────────────────────────
    def get_risk_summary(
        self,
        daily_pnl: float = 0.0,
        weekly_pnl: float = 0.0,
        monthly_pnl: float = 0.0,
        current_positions: int = 0,
        current_grids: int = 0,
        win_rate: float = 0.5,
        payoff_ratio: float = 2.5,
    ) -> dict[str, Any]:
        """
        Gera um resumo completo do estado de risco actual.

        Útil para dashboards, logging periódico e alertas Telegram.

        Returns:
            Dicionário com o estado completo de risco.
        """
        capital = self._capital
        ror = self.calculate_risk_of_ruin(win_rate, payoff_ratio, self.risk_per_level)

        daily_loss_pct = abs(min(daily_pnl, 0)) / capital if capital > 0 else 0.0
        weekly_loss_pct = abs(min(weekly_pnl, 0)) / capital if capital > 0 else 0.0
        monthly_loss_pct = abs(min(monthly_pnl, 0)) / capital if capital > 0 else 0.0

        return {
            "capital_actual": capital,
            "capital_inicial": self._initial_capital,
            "variacao_total_pct": (
                (capital - self._initial_capital) / self._initial_capital * 100
                if self._initial_capital > 0 else 0.0
            ),
            "risk_per_level_pct": self.risk_per_level * 100,
            "kelly_cap_pct": self.kelly_cap * 100,
            "limites": {
                "diario": {
                    "pnl": daily_pnl,
                    "perda_pct": daily_loss_pct * 100,
                    "limite_pct": self.daily_loss_limit * 100,
                    "ok": self.check_daily_limit(daily_pnl, capital),
                },
                "semanal": {
                    "pnl": weekly_pnl,
                    "perda_pct": weekly_loss_pct * 100,
                    "limite_pct": self.weekly_loss_limit * 100,
                    "ok": self.check_weekly_limit(weekly_pnl, capital),
                },
                "mensal": {
                    "pnl": monthly_pnl,
                    "perda_pct": monthly_loss_pct * 100,
                    "limite_pct": self.monthly_dd_limit * 100,
                    "ok": self.check_kill_switch(monthly_pnl, capital),
                },
            },
            "exposicao": {
                "posicoes": current_positions,
                "max_posicoes": self.max_positions,
                "grids": current_grids,
                "max_grids": self.max_grids,
            },
            "risk_of_ruin": {
                "valor": ror,
                "valor_pct": ror * 100,
                "meta_pct": 0.1,
                "abaixo_meta": ror < 0.001,
                "abaixo_limite": ror < 0.01,
            },
            "niveis_em_perda": len(self._losing_levels),
            "min_rr": self.min_rr,
        }

    def __repr__(self) -> str:
        return (
            f"RiskManager("
            f"capital={self._capital:.2f}, "
            f"risk_per_level={self.risk_per_level:.2%}, "
            f"kelly_cap={self.kelly_cap:.2%}, "
            f"daily_limit={self.daily_loss_limit:.2%}, "
            f"weekly_limit={self.weekly_loss_limit:.2%}, "
            f"monthly_limit={self.monthly_dd_limit:.2%}, "
            f"max_positions={self.max_positions}, "
            f"max_grids={self.max_grids}, "
            f"min_rr={self.min_rr:.1f})"
        )
