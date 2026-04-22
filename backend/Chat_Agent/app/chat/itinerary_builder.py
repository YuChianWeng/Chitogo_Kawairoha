from __future__ import annotations

import asyncio
from contextlib import nullcontext
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.chat.schemas import RoutingStatus
from app.core.config import Settings, get_settings
from app.session.models import Itinerary, Leg, Preferences, Stop
from app.tools.models import RouteResult, ToolPlace
from app.tools.registry import ToolRegistry, tool_registry

if TYPE_CHECKING:
    from app.chat.trace_recorder import TraceRecorder

_DEFAULT_STOP_COUNTS = (
    (180, 2),
    (300, 3),
)
_DEFAULT_VISIT_DURATIONS = {
    "attraction": 60,
    "food": 75,
    "shopping": 60,
    "lodging": 30,
    "transport": 15,
    "nightlife": 90,
    "other": 45,
}


class EstimatedLeg(BaseModel):
    leg: Leg
    route_status: Literal["ok", "fallback", "failed"]

    model_config = ConfigDict(extra="forbid")


class RoutingOutcome(BaseModel):
    legs: list[Leg] = Field(default_factory=list)
    routing_status: RoutingStatus = "full"

    model_config = ConfigDict(extra="forbid")


class ItineraryBuildResult(BaseModel):
    itinerary: Itinerary
    routing_status: RoutingStatus

    model_config = ConfigDict(extra="forbid")


class ItineraryBuilder:
    """Deterministic itinerary assembly and leg enrichment for Phase 6."""

    def __init__(
        self,
        *,
        registry: ToolRegistry | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._registry = registry or tool_registry
        self._settings = settings

    @property
    def settings(self) -> Settings:
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    async def build(
        self,
        *,
        places: list[ToolPlace],
        preferences: Preferences,
        trace_recorder: TraceRecorder | None = None,
    ) -> ItineraryBuildResult:
        step_context = (
            trace_recorder.step("itinerary.build") if trace_recorder is not None else nullcontext()
        )
        with step_context as trace_step:
            selected_places = self._select_places(places, preferences)
            if not selected_places:
                if trace_step is not None:
                    trace_step.error(summary="no_places")
                raise ValueError("at least one place is required to build an itinerary")

            stops = [
                self._build_stop(place, stop_index=index)
                for index, place in enumerate(selected_places)
            ]
            routing_outcome = await self.enrich_legs(
                stops=stops,
                preferences=preferences,
                trace_recorder=trace_recorder,
            )
            timed_stops = self._assign_arrival_times(
                stops=stops,
                legs=routing_outcome.legs,
                preferences=preferences,
                default_start_time="10:00",
            )
            itinerary = Itinerary(
                summary="",
                total_duration_min=self._compute_total_duration(timed_stops, routing_outcome.legs),
                stops=timed_stops,
                legs=routing_outcome.legs,
            )
            itinerary.summary = self.summarize(itinerary=itinerary, preferences=preferences)
            if trace_step is not None:
                trace_step.success(
                    summary="itinerary_built",
                    detail={
                        "stop_count": len(timed_stops),
                        "leg_count": len(routing_outcome.legs),
                        "routing_status": routing_outcome.routing_status,
                    },
                )
            return ItineraryBuildResult(
                itinerary=itinerary,
                routing_status=routing_outcome.routing_status,
            )

    def assign_arrival_times(
        self,
        *,
        stops: list[Stop],
        legs: list[Leg],
        preferences: Preferences,
        default_start_time: str,
    ) -> list[Stop]:
        return self._assign_arrival_times(
            stops=stops,
            legs=legs,
            preferences=preferences,
            default_start_time=default_start_time,
        )

    async def enrich_legs(
        self,
        *,
        stops: list[Stop],
        preferences: Preferences,
        trace_recorder: TraceRecorder | None = None,
    ) -> RoutingOutcome:
        step_context = (
            trace_recorder.step("itinerary.route_enrichment")
            if trace_recorder is not None
            else nullcontext()
        )
        with step_context as trace_step:
            semaphore = asyncio.Semaphore(5)

            async def _bounded_leg(from_stop: Stop, to_stop: Stop) -> EstimatedLeg:
                async with semaphore:
                    return await self.estimate_leg(
                        from_stop=from_stop,
                        to_stop=to_stop,
                        preferences=preferences,
                        trace_recorder=trace_recorder,
                    )

            estimated_legs: list[EstimatedLeg] = list(
                await asyncio.gather(
                    *[
                        _bounded_leg(stops[i], stops[i + 1])
                        for i in range(len(stops) - 1)
                    ]
                )
            )
            routing_status = self.routing_status_for(
                [item.route_status for item in estimated_legs]
            )
            if trace_step is not None:
                step_status = "success" if routing_status == "full" else "fallback"
                if step_status == "success":
                    trace_step.success(
                        summary=routing_status,
                        detail={"leg_count": len(estimated_legs)},
                    )
                else:
                    trace_step.fallback(
                        summary=routing_status,
                        detail={"leg_count": len(estimated_legs)},
                    )
            return RoutingOutcome(
                legs=[item.leg for item in estimated_legs],
                routing_status=routing_status,
            )

    async def estimate_leg(
        self,
        *,
        from_stop: Stop,
        to_stop: Stop,
        preferences: Preferences,
        trace_recorder: TraceRecorder | None = None,
    ) -> EstimatedLeg:
        step_context = (
            trace_recorder.step("tool.route_estimate")
            if trace_recorder is not None
            else nullcontext()
        )
        with step_context as trace_step:
            transport_mode = preferences.transport_mode or "transit"
            route_tool = self._registry.get_tool("route_estimate")
            if route_tool is None:
                if trace_step is not None:
                    trace_step.skip(summary="tool_unavailable")
                return self._failed_leg(from_stop=from_stop, to_stop=to_stop)

            if (
                from_stop.lat is None
                or from_stop.lng is None
                or to_stop.lat is None
                or to_stop.lng is None
            ):
                if trace_step is not None:
                    trace_step.skip(summary="missing_coordinates")
                return self._failed_leg(from_stop=from_stop, to_stop=to_stop)

            try:
                route_result = await route_tool.handler(
                    origin_lat=from_stop.lat,
                    origin_lng=from_stop.lng,
                    destination_lat=to_stop.lat,
                    destination_lng=to_stop.lng,
                    transport_mode=transport_mode,
                )
            except Exception as exc:
                if trace_step is not None:
                    trace_step.error(summary="tool_exception", error=exc.__class__.__name__)
                return self._failed_leg(from_stop=from_stop, to_stop=to_stop)

            if not isinstance(route_result, RouteResult):
                if trace_step is not None:
                    trace_step.error(summary="malformed_tool_result")
                return self._failed_leg(from_stop=from_stop, to_stop=to_stop)

            if route_result.status == "ok":
                if trace_step is not None:
                    trace_step.success(
                        summary="ok",
                        detail={
                            "duration_min": route_result.duration_min,
                            "provider": route_result.provider,
                        },
                    )
                return EstimatedLeg(
                    leg=Leg(
                        from_stop=from_stop.stop_index,
                        to_stop=to_stop.stop_index,
                        transit_method=self._transit_method_for(route_result),
                        duration_min=route_result.duration_min,
                        estimated=False,
                    ),
                    route_status="ok",
                )

            if route_result.status == "fallback":
                if trace_step is not None:
                    trace_step.fallback(
                        summary=route_result.fallback_reason or "fallback",
                        detail={
                            "duration_min": route_result.duration_min,
                            "provider": route_result.provider,
                        },
                        warning=route_result.warning,
                    )
                return EstimatedLeg(
                    leg=Leg(
                        from_stop=from_stop.stop_index,
                        to_stop=to_stop.stop_index,
                        transit_method="estimated",
                        duration_min=route_result.duration_min,
                        estimated=True,
                    ),
                    route_status="fallback",
                )

            if trace_step is not None:
                trace_step.error(summary=route_result.status)
            return self._failed_leg(from_stop=from_stop, to_stop=to_stop)

    def summarize(self, *, itinerary: Itinerary, preferences: Preferences) -> str:
        district = preferences.district or preferences.origin or "Taipei"
        language = preferences.language or "en"
        stop_count = len(itinerary.stops)
        if language == "zh-TW":
            return f"{district} {stop_count} 站行程"
        return f"{stop_count}-stop itinerary around {district}"

    def _select_places(
        self,
        places: list[ToolPlace],
        preferences: Preferences,
    ) -> list[ToolPlace]:
        seen_ids: set[int | str] = set()
        unique_places: list[ToolPlace] = []
        for place in places:
            if place.venue_id in seen_ids:
                continue
            seen_ids.add(place.venue_id)
            unique_places.append(place)

        stop_count = min(len(unique_places), self._target_stop_count(preferences))
        return unique_places[:stop_count]

    def _target_stop_count(self, preferences: Preferences) -> int:
        duration_min = self._time_window_duration(preferences)
        if duration_min is None:
            return 3
        for threshold, stop_count in _DEFAULT_STOP_COUNTS:
            if duration_min <= threshold:
                return stop_count
        return 4

    @staticmethod
    def _time_window_duration(preferences: Preferences) -> int | None:
        if preferences.time_window is None:
            return None
        if not preferences.time_window.start_time or not preferences.time_window.end_time:
            return None
        start = datetime.strptime(preferences.time_window.start_time, "%H:%M")
        end = datetime.strptime(preferences.time_window.end_time, "%H:%M")
        duration = int((end - start).total_seconds() // 60)
        return duration if duration > 0 else None

    @staticmethod
    def _build_stop(place: ToolPlace, *, stop_index: int) -> Stop:
        category = place.category or "other"
        return Stop(
            stop_index=stop_index,
            venue_id=place.venue_id,
            venue_name=place.name,
            category=category,
            visit_duration_min=_DEFAULT_VISIT_DURATIONS.get(category, 45),
            lat=place.lat,
            lng=place.lng,
        )

    @staticmethod
    def _assign_arrival_times(
        *,
        stops: list[Stop],
        legs: list[Leg],
        preferences: Preferences,
        default_start_time: str,
    ) -> list[Stop]:
        start_time = preferences.time_window.start_time if preferences.time_window else None
        current_time = datetime.strptime(
            start_time or default_start_time,
            "%H:%M",
        )
        timed_stops: list[Stop] = []
        for index, stop in enumerate(stops):
            timed_stop = stop.model_copy(deep=True)
            timed_stop.arrival_time = current_time.strftime("%H:%M")
            timed_stops.append(timed_stop)
            current_time += timedelta(minutes=timed_stop.visit_duration_min or 0)
            if index < len(legs):
                current_time += timedelta(minutes=legs[index].duration_min)
        return timed_stops

    @staticmethod
    def _compute_total_duration(stops: list[Stop], legs: list[Leg]) -> int:
        return sum(stop.visit_duration_min or 0 for stop in stops) + sum(
            leg.duration_min for leg in legs
        )

    @staticmethod
    def routing_status_for(statuses: list[Literal["ok", "fallback", "failed"]]) -> RoutingStatus:
        if not statuses or all(status == "ok" for status in statuses):
            return "full"
        if all(status == "failed" for status in statuses):
            return "failed"
        return "partial_fallback"

    @staticmethod
    def _transit_method_for(route_result: RouteResult) -> str:
        if route_result.transport_mode == "walk":
            return "walking"
        if route_result.transport_mode == "drive":
            return "drive"
        return "transit"

    @staticmethod
    def _failed_leg(*, from_stop: Stop, to_stop: Stop) -> EstimatedLeg:
        return EstimatedLeg(
            leg=Leg(
                from_stop=from_stop.stop_index,
                to_stop=to_stop.stop_index,
                transit_method="estimated",
                duration_min=0,
                estimated=True,
            ),
            route_status="failed",
        )


__all__ = [
    "EstimatedLeg",
    "ItineraryBuildResult",
    "ItineraryBuilder",
    "RoutingOutcome",
]
