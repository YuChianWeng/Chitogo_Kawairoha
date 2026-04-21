from __future__ import annotations

from time import perf_counter
from typing import Any
from uuid import uuid4

from app.chat.schemas import (
    ChatTraceDetail,
    TraceFinalStatus,
    TraceStepRecord,
    TraceStepStatus,
)
from app.session.models import utc_now


class TraceRecorder:
    """Collect lightweight per-request execution traces."""

    def __init__(self, *, session_id: str | None = None) -> None:
        self.trace_id = str(uuid4())
        self.session_id = session_id
        self.requested_at = utc_now()
        self._started_at = perf_counter()
        self._steps: list[TraceStepRecord] = []
        self._warnings: list[str] = []
        self._intent: str | None = None
        self._needs_clarification: bool | None = None
        self._final_trace: ChatTraceDetail | None = None

    def step(self, name: str) -> _TraceStepContext:
        return _TraceStepContext(self, name=name)

    def record_step(
        self,
        *,
        name: str,
        status: TraceStepStatus,
        duration_ms: int = 0,
        summary: str | None = None,
        detail: dict[str, Any] | None = None,
        warning: str | None = None,
        error: str | None = None,
    ) -> None:
        self._append_step(
            TraceStepRecord(
                name=name,
                status=status,
                duration_ms=max(0, duration_ms),
                summary=summary,
                detail=_sanitize_detail(detail),
                warning=warning,
                error=error,
            )
        )

    def set_intent(self, intent: str | None) -> None:
        self._intent = intent

    def set_needs_clarification(self, needs_clarification: bool | None) -> None:
        self._needs_clarification = needs_clarification

    def add_warning(self, warning: str) -> None:
        if warning:
            self._warnings.append(warning[:200])

    def finalize(
        self,
        *,
        final_status: TraceFinalStatus,
        outcome: str | None,
        error_summary: str | None = None,
        intent: str | None = None,
        needs_clarification: bool | None = None,
    ) -> ChatTraceDetail:
        if self._final_trace is None:
            self._final_trace = ChatTraceDetail(
                trace_id=self.trace_id,
                session_id=self.session_id,
                requested_at=self.requested_at,
                intent=intent if intent is not None else self._intent,
                needs_clarification=(
                    needs_clarification
                    if needs_clarification is not None
                    else self._needs_clarification
                ),
                final_status=final_status,
                outcome=outcome,
                duration_ms=max(0, int(round((perf_counter() - self._started_at) * 1000))),
                steps=[step.model_copy(deep=True) for step in self._steps],
                warnings=list(self._warnings),
                error_summary=error_summary,
            )
        return self._final_trace.model_copy(deep=True)

    def _append_step(self, step: TraceStepRecord) -> None:
        self._steps.append(step)
        if step.warning:
            self._warnings.append(step.warning[:200])


class _TraceStepContext:
    def __init__(self, recorder: TraceRecorder, *, name: str) -> None:
        self._recorder = recorder
        self._name = name
        self._started_at = 0.0
        self._status: TraceStepStatus | None = None
        self._summary: str | None = None
        self._detail: dict[str, Any] = {}
        self._warning: str | None = None
        self._error: str | None = None

    def __enter__(self) -> _TraceStepContext:
        self._started_at = perf_counter()
        return self

    def __exit__(self, exc_type, exc, _tb) -> bool:
        if exc is not None and self._status is None:
            self._status = "error"
            self._summary = self._summary or "exception"
            self._error = self._error or exc.__class__.__name__
        self._recorder.record_step(
            name=self._name,
            status=self._status or "success",
            duration_ms=max(0, int(round((perf_counter() - self._started_at) * 1000))),
            summary=self._summary,
            detail=self._detail,
            warning=self._warning,
            error=self._error,
        )
        return False

    def success(
        self,
        *,
        summary: str | None = None,
        detail: dict[str, Any] | None = None,
        warning: str | None = None,
    ) -> None:
        self._status = "success"
        self._summary = summary
        self._warning = warning
        if detail:
            self._detail.update(detail)

    def fallback(
        self,
        *,
        summary: str | None = None,
        detail: dict[str, Any] | None = None,
        warning: str | None = None,
        error: str | None = None,
    ) -> None:
        self._status = "fallback"
        self._summary = summary
        self._warning = warning
        self._error = error
        if detail:
            self._detail.update(detail)

    def skip(
        self,
        *,
        summary: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        self._status = "skipped"
        self._summary = summary
        if detail:
            self._detail.update(detail)

    def error(
        self,
        *,
        summary: str | None = None,
        detail: dict[str, Any] | None = None,
        warning: str | None = None,
        error: str | None = None,
    ) -> None:
        self._status = "error"
        self._summary = summary
        self._warning = warning
        self._error = error
        if detail:
            self._detail.update(detail)


def _sanitize_detail(detail: dict[str, Any] | None) -> dict[str, Any]:
    if detail is None:
        return {}
    sanitized: dict[str, Any] = {}
    for key, value in detail.items():
        if value is None or isinstance(value, (bool, int, float)):
            sanitized[key] = value
            continue
        if isinstance(value, str):
            sanitized[key] = value[:200]
            continue
        if isinstance(value, list):
            sanitized[key] = [str(item)[:100] for item in value[:20]]
            continue
        sanitized[key] = str(value)[:200]
    return sanitized


__all__ = ["TraceRecorder"]
