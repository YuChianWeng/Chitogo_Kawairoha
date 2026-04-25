from __future__ import annotations

from contextlib import nullcontext
import re
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.chat.itinerary_builder import ItineraryBuildResult, ItineraryBuilder
from app.chat.schemas import RoutingStatus
from app.llm.client import llm_client
from app.orchestration.slots import extract_stop_index
from app.orchestration.turn_frame import PlaceConstraint, extract_replan_turn_frame
from app.session.models import Itinerary, Leg, Preferences, Stop
from app.tools.models import ToolPlace

if TYPE_CHECKING:
    from app.chat.trace_recorder import TraceRecorder

_LAST_PATTERN = re.compile(r"(最後一站|last\s+stop)", re.IGNORECASE)


class ReplanRequest(BaseModel):
    operation: Literal["replace", "insert", "remove"]
    target_index: int | None = Field(default=None, ge=0)
    insert_index: int | None = Field(default=None, ge=0)
    replacement_constraint: PlaceConstraint | None = None
    stable_preference_delta: Preferences | None = None
    needs_clarification: bool = False
    missing_fields: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class ReplanResult(BaseModel):
    itinerary: Itinerary
    routing_status: RoutingStatus
    operation: Literal["replace", "insert", "remove"]
    target_index: int | None = None

    model_config = ConfigDict(extra="forbid")


class Replanner:
    """Bounded itinerary editing for replace, insert, and remove requests."""

    def __init__(self, *, itinerary_builder: ItineraryBuilder | None = None) -> None:
        self._builder = itinerary_builder or ItineraryBuilder()
        self._client = llm_client

    async def parse_request(self, message: str, itinerary: Itinerary) -> ReplanRequest:
        frame = await extract_replan_turn_frame(
            message,
            itinerary,
            client=self._client,
        )
        operation = frame.operation or "replace"
        target_index = (
            frame.target_reference.resolved_index
            if frame.target_reference is not None
            else None
        )

        if frame.needs_clarification:
            return ReplanRequest(
                operation=operation,
                replacement_constraint=frame.replacement_constraint,
                stable_preference_delta=frame.stable_preference_delta,
                needs_clarification=True,
                missing_fields=self._clarification_fields(frame.missing_fields),
            )

        if operation == "insert":
            insert_index = self._resolve_insert_index(message, itinerary)
            if insert_index is None:
                return ReplanRequest(
                    operation=operation,
                    replacement_constraint=frame.replacement_constraint,
                    stable_preference_delta=frame.stable_preference_delta,
                    needs_clarification=True,
                    missing_fields=["stop_index"],
                )
            return ReplanRequest(
                operation=operation,
                target_index=max(0, insert_index - 1) if insert_index > 0 else 0,
                insert_index=insert_index,
                replacement_constraint=frame.replacement_constraint,
                stable_preference_delta=frame.stable_preference_delta,
            )

        return ReplanRequest(
            operation=operation,
            target_index=target_index,
            replacement_constraint=frame.replacement_constraint,
            stable_preference_delta=frame.stable_preference_delta,
        )

    async def apply(
        self,
        *,
        current_itinerary: Itinerary,
        request: ReplanRequest,
        preferences: Preferences,
        replacement_place: ToolPlace | None = None,
        trace_recorder: TraceRecorder | None = None,
    ) -> ReplanResult:
        step_context = (
            trace_recorder.step("replan.apply") if trace_recorder is not None else nullcontext()
        )
        with step_context as trace_step:
            if request.needs_clarification:
                if trace_step is not None:
                    trace_step.error(summary="clarification_required")
                raise ValueError("replan request requires clarification")

            if request.operation == "remove":
                stop_sequence = self._sequence_for_remove(current_itinerary, request.target_index or 0)
            elif request.operation == "insert":
                if replacement_place is None or request.insert_index is None:
                    if trace_step is not None:
                        trace_step.error(summary="missing_insert_replacement")
                    raise ValueError("insert requires a replacement place")
                stop_sequence = self._sequence_for_insert(
                    current_itinerary,
                    request.insert_index,
                    replacement_place,
                )
            else:
                if replacement_place is None or request.target_index is None:
                    if trace_step is not None:
                        trace_step.error(summary="missing_replace_replacement")
                    raise ValueError("replace requires a replacement place")
                stop_sequence = self._sequence_for_replace(
                    current_itinerary,
                    request.target_index,
                    replacement_place,
                )

            itinerary_build = await self._rebuild_itinerary(
                current_itinerary=current_itinerary,
                stop_sequence=stop_sequence,
                preferences=preferences,
                trace_recorder=trace_recorder,
            )
            if trace_step is not None:
                trace_step.success(
                    summary=request.operation,
                    detail={
                        "stop_count": len(itinerary_build.itinerary.stops),
                        "routing_status": itinerary_build.routing_status,
                    },
                )
            return ReplanResult(
                itinerary=itinerary_build.itinerary,
                routing_status=itinerary_build.routing_status,
                operation=request.operation,
                target_index=request.target_index,
            )

    def _resolve_insert_index(self, message: str, itinerary: Itinerary) -> int | None:
        if _LAST_PATTERN.search(message):
            return len(itinerary.stops)
        stop_index = extract_stop_index(message)
        if stop_index is None:
            return None
        if "前面" in message or "before" in message.lower():
            return stop_index
        return min(len(itinerary.stops), stop_index + 1)

    @staticmethod
    def _clarification_fields(missing_fields: list[str]) -> list[str]:
        normalized: list[str] = []
        for field_name in missing_fields:
            mapped = "stop_index" if field_name == "target_reference" else field_name
            if mapped not in normalized:
                normalized.append(mapped)
        return normalized or ["stop_index"]

    def _sequence_for_replace(
        self,
        itinerary: Itinerary,
        target_index: int,
        replacement_place: ToolPlace,
    ) -> list[tuple[Stop, int | None]]:
        stop_sequence: list[tuple[Stop, int | None]] = []
        for stop in itinerary.stops:
            if stop.stop_index == target_index:
                stop_sequence.append(
                    (
                        self._replacement_stop(
                            replacement_place,
                            stop_index=target_index,
                            arrival_time=stop.arrival_time,
                        ),
                        None,
                    )
                )
            else:
                stop_sequence.append((stop.model_copy(deep=True), stop.stop_index))
        return stop_sequence

    def _sequence_for_remove(
        self,
        itinerary: Itinerary,
        target_index: int,
    ) -> list[tuple[Stop, int | None]]:
        stop_sequence: list[tuple[Stop, int | None]] = []
        next_index = 0
        for stop in itinerary.stops:
            if stop.stop_index == target_index:
                continue
            stop_copy = stop.model_copy(deep=True)
            stop_copy.stop_index = next_index
            stop_sequence.append((stop_copy, stop.stop_index))
            next_index += 1
        return stop_sequence

    def _sequence_for_insert(
        self,
        itinerary: Itinerary,
        insert_index: int,
        replacement_place: ToolPlace,
    ) -> list[tuple[Stop, int | None]]:
        stop_sequence: list[tuple[Stop, int | None]] = []
        next_index = 0
        inserted = False
        for stop in itinerary.stops:
            if next_index == insert_index and not inserted:
                stop_sequence.append(
                    (
                        self._replacement_stop(
                            replacement_place,
                            stop_index=next_index,
                        ),
                        None,
                    )
                )
                next_index += 1
                inserted = True
            stop_copy = stop.model_copy(deep=True)
            stop_copy.stop_index = next_index
            stop_sequence.append((stop_copy, stop.stop_index))
            next_index += 1
        if not inserted:
            stop_sequence.append(
                (
                    self._replacement_stop(replacement_place, stop_index=next_index),
                    None,
                )
            )
        return stop_sequence

    async def _rebuild_itinerary(
        self,
        *,
        current_itinerary: Itinerary,
        stop_sequence: list[tuple[Stop, int | None]],
        preferences: Preferences,
        trace_recorder: TraceRecorder | None = None,
    ) -> ItineraryBuildResult:
        step_context = (
            trace_recorder.step("replan.rebuild_itinerary")
            if trace_recorder is not None
            else nullcontext()
        )
        with step_context as trace_step:
            new_stops = [stop for stop, _ in stop_sequence]
            rebuilt_legs: list[Leg] = []
            route_states: list[Literal["ok", "fallback", "failed"]] = []
            preserved_leg_count = 0

            for new_index in range(len(new_stops) - 1):
                left_stop, left_old_index = stop_sequence[new_index]
                right_stop, right_old_index = stop_sequence[new_index + 1]
                if (
                    left_old_index is not None
                    and right_old_index is not None
                    and right_old_index == left_old_index + 1
                ):
                    original_leg = current_itinerary.legs[left_old_index].model_copy(deep=True)
                    original_leg.from_stop = new_index
                    original_leg.to_stop = new_index + 1
                    rebuilt_legs.append(original_leg)
                    route_states.append("fallback" if original_leg.estimated else "ok")
                    preserved_leg_count += 1
                    continue

                estimated_leg = await self._builder.estimate_leg(
                    from_stop=left_stop,
                    to_stop=right_stop,
                    preferences=preferences,
                    trace_recorder=trace_recorder,
                )
                rebuilt_legs.append(estimated_leg.leg)
                route_states.append(estimated_leg.route_status)

            timed_stops = self._builder.assign_arrival_times(
                stops=new_stops,
                legs=rebuilt_legs,
                preferences=preferences,
                default_start_time=self._builder.settings.default_start_time,
            )
            itinerary = Itinerary(
                summary="",
                total_duration_min=sum(stop.visit_duration_min or 0 for stop in timed_stops)
                + sum(leg.duration_min for leg in rebuilt_legs),
                stops=timed_stops,
                legs=rebuilt_legs,
            )
            itinerary.summary = self._builder.summarize(
                itinerary=itinerary,
                preferences=preferences,
            )
            routing_status = self._builder.routing_status_for(route_states)
            if trace_step is not None:
                step_status = "success" if routing_status == "full" else "fallback"
                detail = {
                    "stop_count": len(timed_stops),
                    "preserved_leg_count": preserved_leg_count,
                    "rebuilt_leg_count": len(rebuilt_legs) - preserved_leg_count,
                    "routing_status": routing_status,
                }
                if step_status == "success":
                    trace_step.success(summary="replanned", detail=detail)
                else:
                    trace_step.fallback(summary="replanned", detail=detail)
            return ItineraryBuildResult(
                itinerary=itinerary,
                routing_status=routing_status,
            )

    @staticmethod
    def _replacement_stop(
        place: ToolPlace,
        *,
        stop_index: int,
        arrival_time: str | None = None,
    ) -> Stop:
        category = place.category or "other"
        duration = {
            "attraction": 60,
            "food": 75,
            "shopping": 60,
            "lodging": 30,
            "transport": 15,
            "nightlife": 90,
            "other": 45,
        }.get(category, 45)
        return Stop(
            stop_index=stop_index,
            venue_id=place.venue_id,
            venue_name=place.name,
            category=category,
            arrival_time=arrival_time,
            visit_duration_min=duration,
            lat=place.lat,
            lng=place.lng,
        )


__all__ = ["ReplanRequest", "ReplanResult", "Replanner"]
