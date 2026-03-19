"""
Utilitarios partilhados para pacing rules e retries do Interactive Brokers.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import inspect
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any


AlertCallback = Callable[[str], Awaitable[None]]

_DEFAULT_REQUEST_WINDOW_SECONDS = 600.0
_DEFAULT_MAX_REQUESTS = 60
_DEFAULT_IDENTICAL_COOLDOWN_SECONDS = 15.0
_DEFAULT_MAX_ORDER_MESSAGES_PER_SECOND = 45
_IB_PACING_ERROR_CODE = 162


@dataclass(frozen=True, slots=True)
class IBErrorPolicyDecision:
    """Decisão operacional derivada de um código de erro do IB."""

    error_code: int
    message: str
    action: str
    scope: str
    severity: str
    halt_reason: str | None = None


def classify_ib_error(error_code: int, error_string: str) -> IBErrorPolicyDecision | None:
    """Mapeia códigos IB relevantes para acções operacionais determinísticas."""
    policy = {
        1100: IBErrorPolicyDecision(
            error_code=1100,
            message=error_string,
            action="entry_halt",
            scope="connection",
            severity="critical",
            halt_reason="ib_connection_lost",
        ),
        1101: IBErrorPolicyDecision(
            error_code=1101,
            message=error_string,
            action="entry_halt",
            scope="connection",
            severity="critical",
            halt_reason="ib_connection_lost",
        ),
        1102: IBErrorPolicyDecision(
            error_code=1102,
            message=error_string,
            action="clear_connection_halt",
            scope="connection",
            severity="info",
            halt_reason="ib_connection_lost",
        ),
        354: IBErrorPolicyDecision(
            error_code=354,
            message=error_string,
            action="symbol_skip",
            scope="request",
            severity="warning",
        ),
        10197: IBErrorPolicyDecision(
            error_code=10197,
            message=error_string,
            action="symbol_skip",
            scope="request",
            severity="warning",
        ),
        _IB_PACING_ERROR_CODE: IBErrorPolicyDecision(
            error_code=_IB_PACING_ERROR_CODE,
            message=error_string,
            action="symbol_skip",
            scope="request",
            severity="warning",
        ),
        201: IBErrorPolicyDecision(
            error_code=201,
            message=error_string,
            action="order_reject_sync",
            scope="order",
            severity="error",
        ),
        202: IBErrorPolicyDecision(
            error_code=202,
            message=error_string,
            action="order_cancel_sync",
            scope="order",
            severity="warning",
        ),
    }
    return policy.get(error_code)


class IBRateLimiter:
    """Rate limiter multi-regra para a API do IB."""

    def __init__(
        self,
        max_requests: int = _DEFAULT_MAX_REQUESTS,
        request_window_seconds: float = _DEFAULT_REQUEST_WINDOW_SECONDS,
        identical_cooldown_seconds: float = _DEFAULT_IDENTICAL_COOLDOWN_SECONDS,
        max_order_messages_per_second: int = _DEFAULT_MAX_ORDER_MESSAGES_PER_SECOND,
    ) -> None:
        self._max_requests = max_requests
        self._request_window_seconds = request_window_seconds
        self._identical_cooldown_seconds = identical_cooldown_seconds
        self._max_order_messages_per_second = max_order_messages_per_second
        self._request_timestamps: deque[float] = deque()
        self._order_timestamps: deque[float] = deque()
        self._last_identical_requests: dict[str, float] = {}
        self._last_wait_reasons: list[tuple[str, float]] = []
        self._lock = asyncio.Lock()

    async def acquire(
        self,
        request_key: str,
        *,
        request_cost: int = 1,
        category: str = "request",
        order_messages: int = 0,
    ) -> float:
        """
        Aguarda ate ser seguro enviar a operacao.

        Retorna o tempo total aguardado.
        """
        total_wait = 0.0
        self._last_wait_reasons = []

        while True:
            async with self._lock:
                now = time.monotonic()
                self._prune(now)

                wait_candidates = [
                    ("historical_window", self._request_wait(now, request_cost)),
                    ("identical_request", self._identical_wait(request_key, now)),
                    ("order_messages", self._order_wait(now, category, order_messages)),
                ]
                wait_reason, wait_time = max(wait_candidates, key=lambda item: item[1])

                if wait_time <= 0:
                    self._reserve(request_key, now, request_cost, category, order_messages)
                    return total_wait

                self._last_wait_reasons.append((wait_reason, wait_time))
            total_wait += wait_time
            await asyncio.sleep(wait_time)

    def _prune(self, now: float) -> None:
        while self._request_timestamps and (now - self._request_timestamps[0]) >= self._request_window_seconds:
            self._request_timestamps.popleft()

        while self._order_timestamps and (now - self._order_timestamps[0]) >= 1.0:
            self._order_timestamps.popleft()

    def _request_wait(self, now: float, request_cost: int) -> float:
        if len(self._request_timestamps) + request_cost <= self._max_requests:
            return 0.0

        to_expire = (len(self._request_timestamps) + request_cost) - self._max_requests
        boundary_ts = self._request_timestamps[to_expire - 1]
        return max(0.0, self._request_window_seconds - (now - boundary_ts))

    def _identical_wait(self, request_key: str, now: float) -> float:
        last = self._last_identical_requests.get(request_key)
        if last is None:
            return 0.0
        return max(0.0, self._identical_cooldown_seconds - (now - last))

    def _order_wait(self, now: float, category: str, order_messages: int) -> float:
        if category != "order" or order_messages <= 0:
            return 0.0
        if len(self._order_timestamps) + order_messages <= self._max_order_messages_per_second:
            return 0.0

        to_expire = (
            len(self._order_timestamps) + order_messages
        ) - self._max_order_messages_per_second
        boundary_ts = self._order_timestamps[to_expire - 1]
        return max(0.0, 1.0 - (now - boundary_ts))

    def _reserve(
        self,
        request_key: str,
        now: float,
        request_cost: int,
        category: str,
        order_messages: int,
    ) -> None:
        for _ in range(max(request_cost, 0)):
            self._request_timestamps.append(now)

        self._last_identical_requests[request_key] = now

        if category == "order":
            for _ in range(max(order_messages, 0)):
                self._order_timestamps.append(now)

    @property
    def current_usage(self) -> int:
        """Numero de mensagens de ordem na janela actual de 1 segundo."""
        now = time.monotonic()
        return sum(1 for ts in self._order_timestamps if (now - ts) < 1.0)

    @property
    def last_wait_reasons(self) -> list[tuple[str, float]]:
        """Historico dos motivos de espera da ultima aquisicao."""
        return list(self._last_wait_reasons)


class IBRequestExecutor:
    """Executor com retries, logs operacionais e alertas Telegram."""

    def __init__(
        self,
        rate_limiter: IBRateLimiter,
        logger: logging.Logger,
        *,
        alert_callback: AlertCallback | None = None,
    ) -> None:
        self._rate_limiter = rate_limiter
        self._logger = logger
        self._alert_callback = alert_callback

    def set_alert_callback(self, alert_callback: AlertCallback | None) -> None:
        """Actualiza o callback de alertas operacionais."""
        self._alert_callback = alert_callback

    async def run(
        self,
        operation_name: str,
        request_key: str,
        func: Callable[[], Any],
        *,
        category: str = "request",
        request_cost: int = 1,
        order_messages: int = 0,
        max_retries: int = 3,
        base_delay: float = 0.5,
    ) -> Any:
        """Executa uma operacao IB com pacing rules e retry automatico."""
        for attempt in range(1, max_retries + 1):
            try:
                waited = await self._rate_limiter.acquire(
                    request_key,
                    request_cost=request_cost,
                    category=category,
                    order_messages=order_messages,
                )
                if waited > 0:
                    wait_details = ", ".join(
                        f"{reason}={duration:.2f}s"
                        for reason, duration in self._rate_limiter.last_wait_reasons
                    ) or "motivo_indefinido"
                    self._logger.warning(
                        "Pacing rule aplicada em %s: espera %.2f s para %s (%s)",
                        operation_name,
                        waited,
                        request_key,
                        wait_details,
                    )

                result = func()
                if inspect.isawaitable(result):
                    result = await result
                return result

            except Exception as exc:  # noqa: BLE001
                delay = base_delay * (2 ** (attempt - 1))
                if self._is_pacing_violation(exc):
                    delay = 60.0
                    self._logger.warning(
                        "Violacao de pacing do IB detectada em %s. Espera forcada de 60 s antes do retry.",
                        operation_name,
                    )
                message = (
                    f"{operation_name} falhou [{attempt}/{max_retries}] "
                    f"para {request_key}: {exc}"
                )
                self._logger.error(message)

                if attempt == 1:
                    await self._send_alert(
                        f"Retry IB iniciado em {operation_name}: {request_key} | erro={exc}"
                    )

                if attempt >= max_retries:
                    await self._send_alert(
                        f"Falha terminal IB em {operation_name}: {request_key} | erro={exc}"
                    )
                    raise

                self._logger.warning(
                    "Novo retry de %s em %.1f s (tentativa %d/%d).",
                    operation_name,
                    delay,
                    attempt + 1,
                    max_retries,
                )
                await asyncio.sleep(delay)

        raise RuntimeError(f"Fluxo invalido no executor IB para {operation_name}.")

    async def _send_alert(self, message: str) -> None:
        if self._alert_callback is None:
            return
        try:
            await self._alert_callback(message)
        except Exception as exc:  # noqa: BLE001
            self._logger.error("Falha ao enviar alerta operacional IB: %s", exc)

    @staticmethod
    def _is_pacing_violation(exc: Exception) -> bool:
        text = str(exc)
        return str(_IB_PACING_ERROR_CODE) in text or "pacing" in text.lower()
