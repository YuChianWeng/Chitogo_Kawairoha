from __future__ import annotations

import asyncio
import logging
import re
from uuid import uuid4

from app.chat.itinerary_builder import ItineraryBuilder
from app.chat.loop import AgentLoop
from app.chat.replanner import Replanner
from app.chat.response_composer import ResponseComposer
from app.chat.schemas import (
    ChatCandidate,
    ChatMessageRequest,
    ChatMessageResponse,
    LoopResult,
    TraceFinalStatus,
    ToolResultsSummary,
)
from app.chat.trace_recorder import TraceRecorder
from app.chat.trace_store import TraceStore
from app.core.config import Settings, get_settings
from app.core.logging import log_event
from app.orchestration.classifier import IntentClassifier, detect_missing_generate_fields
from app.orchestration.intents import Intent
from app.orchestration.language import detect_language_hint
from app.orchestration.preferences import PreferenceExtractor
from app.orchestration.slots import (
    ChatGeneralSlots,
    CheckLodgingLegalSlots,
    ClassifierResult,
)
from app.orchestration.turn_frame import (
    CandidateMatchDecision,
    extract_category_mix,
    PlaceConstraint,
    candidate_matches_constraint,
)
from app.session.manager import (
    SessionManager,
    session_manager,
    stable_preference_delta,
)
from app.session.models import Itinerary, Place, Preferences, Session, Turn
from app.tools.models import ToolPlace

logger = logging.getLogger(__name__)

_ITINERARY_LANGUAGE_PATTERN = re.compile(
    r"(行程|安排|排(?:一個|一下)?|schedule|itinerary|trip\s+plan)",
    re.IGNORECASE,
)


class MessageHandler:
    """Single-turn application service for the chat endpoint."""

    def __init__(
        self,
        *,
        session_manager_instance: SessionManager | None = None,
        classifier: IntentClassifier | None = None,
        preference_extractor: PreferenceExtractor | None = None,
        agent_loop: AgentLoop | None = None,
        composer: ResponseComposer | None = None,
        itinerary_builder: ItineraryBuilder | None = None,
        replanner: Replanner | None = None,
        settings: Settings | None = None,
        trace_store: TraceStore | None = None,
    ) -> None:
        self._session_manager = session_manager_instance or session_manager
        self._classifier = classifier or IntentClassifier()
        self._preference_extractor = preference_extractor or PreferenceExtractor()
        self._agent_loop = agent_loop or AgentLoop()
        self._composer = composer or ResponseComposer()
        self._settings = settings
        self._trace_store = trace_store or TraceStore(
            max_items=self.settings.trace_store_max_items,
        )
        self._session_lock_guard = asyncio.Lock()
        self._session_locks: dict[str, asyncio.Lock] = {}
        shared_registry = getattr(self._agent_loop, "_registry", None)
        self._itinerary_builder = itinerary_builder or ItineraryBuilder(
            registry=shared_registry,
        )
        self._replanner = replanner or Replanner(itinerary_builder=self._itinerary_builder)

    @property
    def settings(self) -> Settings:
        if self._settings is None:
            self._settings = get_settings()
        return self._settings

    @property
    def trace_store(self) -> TraceStore:
        return self._trace_store

    async def handle(self, request: ChatMessageRequest) -> ChatMessageResponse:
        session_id = request.session_id or str(uuid4())
        user_turn_id = str(uuid4())
        assistant_turn_id = str(uuid4())
        recorder = TraceRecorder(session_id=session_id)
        trace = None
        lock = await self._session_lock_for(session_id)

        async with lock:
            try:
                with recorder.step("session.get_or_create") as step:
                    session = await self._session_manager.get_or_create(session_id)
                    step.success(
                        detail={
                            "has_itinerary": session.latest_itinerary is not None,
                            "cached_candidate_count": len(session.cached_candidates),
                        }
                    )
                with recorder.step("session.append_user_turn") as step:
                    await self._session_manager.append_turn(
                        session_id,
                        Turn(turn_id=user_turn_id, role="user", content=request.message),
                    )
                    step.success()

                classifier_result, preference_delta = await asyncio.gather(
                    self._classify_request(
                        request=request,
                        session=session,
                        recorder=recorder,
                    ),
                    self._extract_preferences(
                        request=request,
                        session=session,
                        recorder=recorder,
                    ),
                )
                session = await self._merge_preferences(
                    session_id=session_id,
                    session=session,
                    preference_delta=preference_delta,
                    recorder=recorder,
                )
                preferences = self._preferences_for_current_turn(
                    base_preferences=session.preferences,
                    preference_delta=preference_delta,
                    intent=classifier_result.intent,
                )
                discovery_request = self._should_use_discovery_flow(
                    message=request.message,
                    classifier_result=classifier_result,
                    preferences=preferences,
                )
                if (
                    classifier_result.intent == Intent.GENERATE_ITINERARY
                    and discovery_request
                    and self._should_override_generate_to_discovery(
                        message=request.message,
                        preferences=preferences,
                    )
                ):
                    classifier_result = classifier_result.model_copy(
                        update={
                            "intent": Intent.CHAT_GENERAL,
                            "needs_clarification": False,
                            "missing_fields": [],
                        }
                    )

                if classifier_result.intent == Intent.GENERATE_ITINERARY:
                    with recorder.step("generate.detect_missing_fields") as step:
                        missing_fields = detect_missing_generate_fields(
                            request.message,
                            preferences,
                        )
                        classifier_result.missing_fields = missing_fields
                        classifier_result.needs_clarification = bool(missing_fields)
                        step.success(detail={"missing_fields": missing_fields})

                recorder.set_intent(classifier_result.intent.value)
                recorder.set_needs_clarification(classifier_result.needs_clarification)

                if classifier_result.intent == Intent.CHECK_LODGING_LEGAL:
                    response = await self._handle_check_lodging_legal(
                        session_id=session_id,
                        turn_id=assistant_turn_id,
                        request=request,
                        preferences=preferences,
                        classifier_result=classifier_result,
                        source=classifier_result.source,
                        trace_recorder=recorder,
                    )
                elif classifier_result.intent == Intent.REPLAN:
                    response = await self._handle_replan(
                        session=session,
                        session_id=session_id,
                        turn_id=assistant_turn_id,
                        request=request,
                        preferences=preferences,
                        source=classifier_result.source,
                        trace_recorder=recorder,
                    )
                elif classifier_result.needs_clarification:
                    self._record_turn_frame_validation(
                        trace_recorder=recorder,
                        message=request.message,
                        intent=classifier_result.intent,
                        preferences=preferences,
                        route="clarification",
                        needs_clarification=True,
                        missing_fields=classifier_result.missing_fields,
                    )
                    recorder.record_step(
                        name="orchestration.tools",
                        status="skipped",
                        summary="clarification_required",
                    )
                    with recorder.step("response.compose_clarification") as step:
                        reply_text = self._composer.compose_clarification(
                            missing_fields=classifier_result.missing_fields,
                            preferences=preferences,
                        )
                        step.success(detail={"missing_fields": classifier_result.missing_fields})
                    response = ChatMessageResponse(
                        session_id=session_id,
                        turn_id=assistant_turn_id,
                        intent=classifier_result.intent,
                        needs_clarification=True,
                        message=reply_text,
                        preferences=preferences,
                        source=classifier_result.source,
                    )
                elif classifier_result.intent == Intent.EXPLAIN:
                    self._record_turn_frame_validation(
                        trace_recorder=recorder,
                        message=request.message,
                        intent=classifier_result.intent,
                        preferences=preferences,
                        route="explain",
                        needs_clarification=False,
                        missing_fields=[],
                    )
                    recorder.record_step(
                        name="orchestration.tools",
                        status="skipped",
                        summary="explain_uses_cached_candidates",
                    )
                    with recorder.step("response.compose_explain") as step:
                        reply_text = self._composer.compose_explain(
                            preferences=preferences,
                            candidate_names=[
                                candidate.name for candidate in session.cached_candidates
                            ],
                        )
                        step.success(
                            detail={"candidate_count": len(session.cached_candidates)}
                        )
                    response = ChatMessageResponse(
                        session_id=session_id,
                        turn_id=assistant_turn_id,
                        intent=classifier_result.intent,
                        needs_clarification=False,
                        message=reply_text,
                        preferences=preferences,
                        source=classifier_result.source,
                    )
                elif classifier_result.intent == Intent.GENERATE_ITINERARY:
                    response = await self._handle_generate_itinerary(
                        session_id=session_id,
                        turn_id=assistant_turn_id,
                        request=request,
                        preferences=preferences,
                        source=classifier_result.source,
                        trace_recorder=recorder,
                    )
                elif discovery_request:
                    response = await self._handle_discovery(
                        session_id=session_id,
                        turn_id=assistant_turn_id,
                        request=request,
                        preferences=preferences,
                        source=classifier_result.source,
                        trace_recorder=recorder,
                    )
                else:
                    self._record_turn_frame_validation(
                        trace_recorder=recorder,
                        message=request.message,
                        intent=classifier_result.intent,
                        preferences=preferences,
                        route="chat_general",
                        needs_clarification=False,
                        missing_fields=[],
                    )
                    recorder.record_step(
                        name="orchestration.tools",
                        status="skipped",
                        summary="general_chat_no_tools",
                    )
                    with recorder.step("response.compose_general_chat") as step:
                        reply_text = self._composer.compose_general_chat(
                            preferences=preferences,
                        )
                        step.success()
                    response = ChatMessageResponse(
                        session_id=session_id,
                        turn_id=assistant_turn_id,
                        intent=classifier_result.intent,
                        needs_clarification=False,
                        message=reply_text,
                        preferences=preferences,
                        source=classifier_result.source,
                    )

                with recorder.step("session.append_assistant_turn") as step:
                    await self._session_manager.append_turn(
                        session_id,
                        Turn(
                            turn_id=assistant_turn_id,
                            role="assistant",
                            content=response.message,
                        ),
                    )
                    step.success()

                trace = recorder.finalize(
                    final_status=self._final_status_for_response(response),
                    outcome=self._outcome_for_response(response),
                    intent=response.intent.value,
                    needs_clarification=response.needs_clarification,
                )
                return response
            except Exception as exc:
                trace = recorder.finalize(
                    final_status="error",
                    outcome="internal_error",
                    error_summary=exc.__class__.__name__,
                )
                raise
            finally:
                if trace is None:
                    trace = recorder.finalize(
                        final_status="error",
                        outcome="internal_error",
                        error_summary="unfinalized_trace",
                    )
                await self._trace_store.add(trace)
                self._log_trace(trace)

    async def _classify_request(
        self,
        *,
        request: ChatMessageRequest,
        session: Session,
        recorder: TraceRecorder,
    ) -> ClassifierResult:
        with recorder.step("classification") as step:
            try:
                classifier_result = await self._classifier.classify(
                    request.message,
                    has_itinerary=session.latest_itinerary is not None,
                )
            except Exception as exc:
                classifier_result = ClassifierResult(
                    intent=Intent.CHAT_GENERAL,
                    confidence=0.0,
                    extracted_slots=ChatGeneralSlots(topic="classifier_fallback"),
                    source="rules",
                )
                step.fallback(
                    summary="classifier_fallback",
                    error=exc.__class__.__name__,
                )
                return classifier_result
            step.success(
                summary=classifier_result.intent.value,
                detail={
                    "source": classifier_result.source,
                    "needs_clarification": classifier_result.needs_clarification,
                },
            )
            return classifier_result

    async def _extract_preferences(
        self,
        *,
        request: ChatMessageRequest,
        session: Session,
        recorder: TraceRecorder,
    ) -> Preferences:
        with recorder.step("preferences.extract") as step:
            try:
                preference_delta = await self._preference_extractor.extract(
                    request.message,
                    current_preferences=session.preferences,
                )
            except Exception as exc:
                preference_delta = Preferences(language=detect_language_hint(request.message))
                step.fallback(
                    summary="language_only_preferences",
                    error=exc.__class__.__name__,
                    detail={"fields": sorted(preference_delta.model_fields_set)},
                )
                return preference_delta
            step.success(detail={"fields": sorted(preference_delta.model_fields_set)})
            return preference_delta

    async def _merge_preferences(
        self,
        *,
        session_id: str,
        session: Session,
        preference_delta: Preferences,
        recorder: TraceRecorder,
    ) -> Session:
        with recorder.step("preferences.merge") as step:
            persisted_delta = stable_preference_delta(preference_delta)
            persisted_fields = (
                sorted(persisted_delta.model_fields_set)
                if persisted_delta is not None
                else []
            )
            try:
                if persisted_delta is None:
                    step.success(
                        detail={
                            "persisted_fields": [],
                            "turn_fields": sorted(preference_delta.model_fields_set),
                        }
                    )
                    return session
                merged_session = await self._session_manager.update_preferences(session_id, persisted_delta)
            except Exception as exc:
                step.fallback(
                    summary="preferences_preserved",
                    error=exc.__class__.__name__,
                )
                return session
            step.success(
                detail={
                    "persisted_fields": persisted_fields,
                    "turn_fields": sorted(preference_delta.model_fields_set),
                }
            )
            return merged_session

    async def _handle_check_lodging_legal(
        self,
        *,
        session_id: str,
        turn_id: str,
        request: ChatMessageRequest,
        preferences: Preferences,
        classifier_result: ClassifierResult,
        source: str,
        trace_recorder: TraceRecorder,
    ) -> ChatMessageResponse:
        self._record_turn_frame_validation(
            trace_recorder=trace_recorder,
            message=request.message,
            intent=Intent.CHECK_LODGING_LEGAL,
            preferences=preferences,
            route="check_lodging_legal",
            needs_clarification=False,
            missing_fields=[],
        )

        slots = classifier_result.extracted_slots
        lodging_name = (
            slots.lodging_name
            if isinstance(slots, CheckLodgingLegalSlots) and slots.lodging_name
            else request.message.strip()
        )
        phone = slots.phone if isinstance(slots, CheckLodgingLegalSlots) else None
        district = slots.district if isinstance(slots, CheckLodgingLegalSlots) else None

        with trace_recorder.step("orchestration.lodging_legal_check") as step:
            legal_tool = self._agent_loop._registry.get_tool("lodging_legal_check")
            if legal_tool is None:
                step.fallback(summary="tool_not_found", error="lodging_legal_check")
                reply = self._composer.compose_tool_error(preferences=preferences)
                return ChatMessageResponse(
                    session_id=session_id,
                    turn_id=turn_id,
                    intent=Intent.CHECK_LODGING_LEGAL,
                    needs_clarification=False,
                    message=reply,
                    preferences=preferences,
                    source=source,
                )
            try:
                legal_result = await legal_tool.handler(
                    name=lodging_name,
                    phone=phone,
                    district=district,
                )
            except Exception as exc:
                step.fallback(summary="tool_error", error=exc.__class__.__name__)
                reply = self._composer.compose_tool_error(preferences=preferences)
                return ChatMessageResponse(
                    session_id=session_id,
                    turn_id=turn_id,
                    intent=Intent.CHECK_LODGING_LEGAL,
                    needs_clarification=False,
                    message=reply,
                    preferences=preferences,
                    source=source,
                )
            step.success(
                detail={
                    "is_legal": legal_result.is_legal,
                    "match_type": legal_result.match_type,
                    "confidence": legal_result.confidence,
                }
            )

        # High confidence or phone match → direct answer
        if legal_result.is_legal and (
            legal_result.match_type == "phone"
            or legal_result.confidence is None
            or legal_result.confidence >= 0.90
        ):
            reply = self._composer.compose_lodging_legal_status(
                preferences=preferences,
                lodging_name=lodging_name,
                lodging=legal_result.lodging,
                match_type=legal_result.match_type,
                confidence=legal_result.confidence,
                high_confidence=True,
            )
            return ChatMessageResponse(
                session_id=session_id,
                turn_id=turn_id,
                intent=Intent.CHECK_LODGING_LEGAL,
                needs_clarification=False,
                message=reply,
                preferences=preferences,
                source=source,
            )

        # Medium confidence → answer with caveat
        if legal_result.is_legal:
            reply = self._composer.compose_lodging_legal_status(
                preferences=preferences,
                lodging_name=lodging_name,
                lodging=legal_result.lodging,
                match_type=legal_result.match_type,
                confidence=legal_result.confidence,
                high_confidence=False,
            )
            return ChatMessageResponse(
                session_id=session_id,
                turn_id=turn_id,
                intent=Intent.CHECK_LODGING_LEGAL,
                needs_clarification=False,
                message=reply,
                preferences=preferences,
                source=source,
            )

        # No match → try to find candidates for disambiguation
        with trace_recorder.step("orchestration.lodging_candidates") as step:
            candidates_tool = self._agent_loop._registry.get_tool("lodging_candidates")
            candidates_result = None
            if candidates_tool is not None:
                try:
                    candidates_result = await candidates_tool.handler(
                        name=lodging_name, limit=3
                    )
                except Exception as exc:
                    step.fallback(summary="candidates_error", error=exc.__class__.__name__)
            if candidates_result is not None and candidates_result.status == "ok" and candidates_result.items:
                step.success(detail={"candidate_count": len(candidates_result.items)})
                reply = self._composer.compose_lodging_candidates(
                    preferences=preferences,
                    query_name=lodging_name,
                    candidates=candidates_result.items,
                )
                return ChatMessageResponse(
                    session_id=session_id,
                    turn_id=turn_id,
                    intent=Intent.CHECK_LODGING_LEGAL,
                    needs_clarification=True,
                    message=reply,
                    preferences=preferences,
                    source=source,
                )
            step.success(detail={"candidate_count": 0})

        reply = self._composer.compose_lodging_not_found(
            preferences=preferences,
            query_name=lodging_name,
        )
        return ChatMessageResponse(
            session_id=session_id,
            turn_id=turn_id,
            intent=Intent.CHECK_LODGING_LEGAL,
            needs_clarification=False,
            message=reply,
            preferences=preferences,
            source=source,
        )

    async def _handle_discovery(
        self,
        *,
        session_id: str,
        turn_id: str,
        request: ChatMessageRequest,
        preferences: Preferences,
        source: str,
        trace_recorder: TraceRecorder,
    ) -> ChatMessageResponse:
        self._record_turn_frame_validation(
            trace_recorder=trace_recorder,
            message=request.message,
            intent=Intent.CHAT_GENERAL,
            preferences=preferences,
            route="discovery",
            needs_clarification=False,
            missing_fields=[],
        )
        loop_result = await self._run_loop(
            intent=Intent.CHAT_GENERAL,
            message=request.message,
            preferences=preferences,
            replacement_constraint=None,
            category_mix=None,
            user_context=request.user_context,
            trace_recorder=trace_recorder,
            step_name="agent_loop.chat_general",
        )
        summary = self._tool_summary(loop_result)
        if loop_result.status == "ok":
            reply_text, candidates = self._compose_place_recommendation_reply(
                loop_result=loop_result,
                preferences=preferences,
                trace_recorder=trace_recorder,
            )
            with trace_recorder.step("session.cache_candidates") as step:
                await self._session_manager.cache_candidates(
                    session_id,
                    [self._to_cached_place(place) for place in loop_result.places],
                )
                step.success(detail={"candidate_count": len(loop_result.places)})
            return ChatMessageResponse(
                session_id=session_id,
                turn_id=turn_id,
                intent=Intent.CHAT_GENERAL,
                needs_clarification=False,
                message=reply_text,
                preferences=preferences,
                candidates=candidates,
                tool_results_summary=summary,
                source=source,
            )

        if loop_result.status == "empty":
            reply_text, candidates = self._compose_relaxed_or_no_results_reply(
                loop_result=loop_result,
                preferences=preferences,
                trace_recorder=trace_recorder,
            )
            if candidates:
                with trace_recorder.step("session.cache_candidates") as step:
                    await self._session_manager.cache_candidates(
                        session_id,
                        [self._to_cached_place(place) for place in loop_result.places],
                    )
                    step.success(detail={"candidate_count": len(loop_result.places)})
            return ChatMessageResponse(
                session_id=session_id,
                turn_id=turn_id,
                intent=Intent.CHAT_GENERAL,
                needs_clarification=False,
                message=reply_text,
                preferences=preferences,
                candidates=candidates,
                tool_results_summary=summary,
                source=source,
            )

        with trace_recorder.step("response.compose_tool_error") as step:
            reply_text = self._composer.compose_tool_error(preferences=preferences)
            step.success()
        return ChatMessageResponse(
            session_id=session_id,
            turn_id=turn_id,
            intent=Intent.CHAT_GENERAL,
            needs_clarification=False,
            message=reply_text,
            preferences=preferences,
            candidates=[],
            tool_results_summary=summary,
            source=source,
        )

    async def _handle_generate_itinerary(
        self,
        *,
        session_id: str,
        turn_id: str,
        request: ChatMessageRequest,
        preferences: Preferences,
        source: str,
        trace_recorder: TraceRecorder,
    ) -> ChatMessageResponse:
        category_mix = await self._extract_category_mix(
            message=request.message,
            trace_recorder=trace_recorder,
        )
        self._record_turn_frame_validation(
            trace_recorder=trace_recorder,
            message=request.message,
            intent=Intent.GENERATE_ITINERARY,
            preferences=preferences,
            route="generate",
            needs_clarification=False,
            missing_fields=[],
            category_mix=category_mix,
        )
        loop_result = await self._run_loop(
            intent=Intent.GENERATE_ITINERARY,
            message=request.message,
            preferences=preferences,
            replacement_constraint=None,
            category_mix=category_mix,
            user_context=request.user_context,
            trace_recorder=trace_recorder,
            step_name="agent_loop.generate_itinerary",
        )
        summary = self._tool_summary(loop_result)
        if loop_result.status == "empty":
            reply_text, candidates = self._compose_relaxed_or_no_results_reply(
                loop_result=loop_result,
                preferences=preferences,
                trace_recorder=trace_recorder,
            )
            if candidates:
                with trace_recorder.step("session.cache_candidates") as step:
                    await self._session_manager.cache_candidates(
                        session_id,
                        [self._to_cached_place(place) for place in loop_result.places],
                    )
                    step.success(detail={"candidate_count": len(loop_result.places)})
            return ChatMessageResponse(
                session_id=session_id,
                turn_id=turn_id,
                intent=Intent.GENERATE_ITINERARY,
                needs_clarification=False,
                message=reply_text,
                preferences=preferences,
                candidates=candidates,
                tool_results_summary=summary,
                source=source,
            )
        if loop_result.status == "error":
            with trace_recorder.step("response.compose_tool_error") as step:
                reply_text = self._composer.compose_tool_error(preferences=preferences)
                step.success()
            return ChatMessageResponse(
                session_id=session_id,
                turn_id=turn_id,
                intent=Intent.GENERATE_ITINERARY,
                needs_clarification=False,
                message=reply_text,
                preferences=preferences,
                tool_results_summary=summary,
                source=source,
            )

        try:
            itinerary_build = await self._itinerary_builder.build(
                places=loop_result.places,
                preferences=preferences,
                category_mix=category_mix,
                trace_recorder=trace_recorder,
            )
        except Exception as exc:
            trace_recorder.add_warning("itinerary_build_failed")
            recorder_step = trace_recorder.step("response.compose_tool_error")
            with recorder_step as step:
                reply_text = self._composer.compose_tool_error(preferences=preferences)
                step.success()
            return ChatMessageResponse(
                session_id=session_id,
                turn_id=turn_id,
                intent=Intent.GENERATE_ITINERARY,
                needs_clarification=False,
                message=reply_text,
                preferences=preferences,
                tool_results_summary=summary,
                source=source,
            )

        with trace_recorder.step("session.cache_candidates") as step:
            await self._session_manager.cache_candidates(
                session_id,
                [self._to_cached_place(place) for place in loop_result.places],
            )
            step.success(detail={"candidate_count": len(loop_result.places)})
        with trace_recorder.step("session.set_itinerary") as step:
            await self._session_manager.set_itinerary(session_id, itinerary_build.itinerary)
            step.success(detail={"stop_count": len(itinerary_build.itinerary.stops)})
        with trace_recorder.step("response.compose_itinerary") as step:
            reply_text = self._composer.compose_itinerary(
                itinerary=itinerary_build.itinerary,
                routing_status=itinerary_build.routing_status,
                preferences=preferences,
            )
            if loop_result.missing_categories:
                with trace_recorder.step("category_mix.relaxation") as relaxation_step:
                    reply_text += self._composer.compose_category_mix_relaxation(
                        preferences=preferences,
                        missing_categories=loop_result.missing_categories,
                    )
                    relaxation_step.fallback(
                        summary="missing_categories",
                        detail={
                            "requested_categories": loop_result.requested_categories,
                            "missing_categories": loop_result.missing_categories,
                        },
                    )
            step.success(
                detail={
                    "stop_count": len(itinerary_build.itinerary.stops),
                    "routing_status": itinerary_build.routing_status,
                    "missing_categories": loop_result.missing_categories,
                }
            )
        return ChatMessageResponse(
            session_id=session_id,
            turn_id=turn_id,
            intent=Intent.GENERATE_ITINERARY,
            needs_clarification=False,
            message=reply_text,
            preferences=preferences,
            itinerary=itinerary_build.itinerary,
            routing_status=itinerary_build.routing_status,
            candidates=self._to_chat_candidates(loop_result.places, preferences),
            tool_results_summary=summary,
            source=source,
        )

    async def _handle_replan(
        self,
        *,
        session: Session,
        session_id: str,
        turn_id: str,
        request: ChatMessageRequest,
        preferences: Preferences,
        source: str,
        trace_recorder: TraceRecorder,
    ) -> ChatMessageResponse:
        if session.latest_itinerary is None:
            trace_recorder.record_step(
                name="replan.parse_request",
                status="skipped",
                summary="missing_itinerary",
            )
            with trace_recorder.step("response.compose_replan_clarification") as step:
                reply_text = self._composer.compose_replan_clarification(
                    preferences=preferences,
                    has_itinerary=False,
                )
                step.success()
            return ChatMessageResponse(
                session_id=session_id,
                turn_id=turn_id,
                intent=Intent.REPLAN,
                needs_clarification=True,
                message=reply_text,
                preferences=preferences,
                source=source,
            )

        with trace_recorder.step("replan.parse_request") as step:
            replan_request = await self._replanner.parse_request(
                request.message,
                session.latest_itinerary,
            )
            if replan_request.needs_clarification:
                step.fallback(
                    summary="clarification_required",
                    detail={"missing_fields": replan_request.missing_fields},
                )
            else:
                step.success(
                    summary=replan_request.operation,
                    detail={"target_index": replan_request.target_index},
                )
        self._record_turn_frame_validation(
            trace_recorder=trace_recorder,
            message=request.message,
            intent=Intent.REPLAN,
            preferences=preferences,
            route="replan",
            needs_clarification=replan_request.needs_clarification,
            missing_fields=replan_request.missing_fields,
            replan_request=replan_request,
        )

        if replan_request.stable_preference_delta is not None:
            with trace_recorder.step("preferences.merge_replan_frame") as step:
                try:
                    persisted_delta = stable_preference_delta(replan_request.stable_preference_delta)
                    if persisted_delta is None:
                        step.success(detail={"fields": []})
                    else:
                        session = await self._session_manager.update_preferences(
                            session_id,
                            persisted_delta,
                        )
                        preferences = session.preferences
                        step.success(detail={"fields": sorted(persisted_delta.model_fields_set)})
                except Exception as exc:
                    step.fallback(summary="preferences_preserved", error=exc.__class__.__name__)

        if replan_request.needs_clarification:
            trace_recorder.record_step(
                name="replan.apply",
                status="skipped",
                summary="clarification_required",
            )
            with trace_recorder.step("response.compose_replan_clarification") as step:
                reply_text = self._composer.compose_replan_clarification(
                    preferences=preferences,
                    has_itinerary=True,
                    missing_fields=replan_request.missing_fields,
                )
                step.success(
                    detail={"missing_fields": replan_request.missing_fields}
                )
            return ChatMessageResponse(
                session_id=session_id,
                turn_id=turn_id,
                intent=Intent.REPLAN,
                needs_clarification=True,
                message=reply_text,
                preferences=preferences,
                source=source,
            )

        loop_result = None
        summary = None
        replacement_place = None
        if replan_request.operation in {"replace", "insert"}:
            replacement_place, cache_decisions = self._pick_cached_replan_candidate(
                session=session,
                target_index=replan_request.target_index,
                replacement_constraint=replan_request.replacement_constraint,
            )
            trace_recorder.record_step(
                name="replan.cache_candidate_filter",
                status="success" if replacement_place is not None else "fallback",
                summary=(
                    "cached_candidate_matched"
                    if replacement_place is not None
                    else "no_matching_cached_candidate"
                ),
                detail={
                    "evaluated_count": len(cache_decisions),
                    "failed_fields": sorted(
                        {
                            field_name
                            for decision in cache_decisions
                            for field_name in decision.failed_fields
                        }
                    ),
                    "matched_candidate_id": (
                        replacement_place.venue_id if replacement_place is not None else None
                    ),
                },
            )
            if replacement_place is not None:
                trace_recorder.record_step(
                    name="replan.pick_cached_candidate",
                    status="success",
                    summary="cached_candidate_reused",
                    detail={
                        "target_index": replan_request.target_index,
                        "candidate_id": replacement_place.venue_id,
                    },
                )
            if replacement_place is None:
                loop_result = await self._run_loop(
                    intent=Intent.REPLAN,
                    message=request.message,
                    preferences=preferences,
                    replacement_constraint=replan_request.replacement_constraint,
                    category_mix=None,
                    user_context=request.user_context,
                    trace_recorder=trace_recorder,
                    step_name="agent_loop.replan",
                )
                summary = self._tool_summary(loop_result)
                if loop_result.status == "error":
                    with trace_recorder.step("response.compose_tool_error") as step:
                        reply_text = self._composer.compose_tool_error(
                            preferences=preferences,
                        )
                        step.success()
                    return ChatMessageResponse(
                        session_id=session_id,
                        turn_id=turn_id,
                        intent=Intent.REPLAN,
                        needs_clarification=False,
                        message=reply_text,
                        preferences=preferences,
                        tool_results_summary=summary,
                        source=source,
                    )
                if loop_result.status == "empty":
                    reply_text, candidates = self._compose_relaxed_or_no_results_reply(
                        loop_result=loop_result,
                        preferences=preferences,
                        trace_recorder=trace_recorder,
                    )
                    if candidates:
                        with trace_recorder.step("session.cache_candidates") as step:
                            await self._session_manager.cache_candidates(
                                session_id,
                                [self._to_cached_place(place) for place in loop_result.places],
                            )
                            step.success(detail={"candidate_count": len(loop_result.places)})
                    return ChatMessageResponse(
                        session_id=session_id,
                        turn_id=turn_id,
                        intent=Intent.REPLAN,
                        needs_clarification=False,
                        message=reply_text,
                        preferences=preferences,
                        candidates=candidates,
                        tool_results_summary=summary,
                        source=source,
                    )
                replacement_place = self._pick_tool_replan_candidate(
                    current_itinerary=session.latest_itinerary,
                    places=loop_result.places,
                    target_index=replan_request.target_index,
                    replacement_constraint=replan_request.replacement_constraint,
                )
                trace_recorder.record_step(
                    name="replan.pick_tool_candidate",
                    status="success" if replacement_place is not None else "fallback",
                    summary=(
                        "tool_candidate_selected"
                        if replacement_place is not None
                        else "no_replacement_candidate"
                    ),
                    detail={
                        "candidate_id": (
                            replacement_place.venue_id if replacement_place is not None else None
                        )
                    },
                )
                with trace_recorder.step("session.cache_candidates") as step:
                    await self._session_manager.cache_candidates(
                        session_id,
                        [self._to_cached_place(place) for place in loop_result.places],
                    )
                    step.success(detail={"candidate_count": len(loop_result.places)})

            if replacement_place is None:
                trace_recorder.record_step(
                    name="replan.pick_tool_candidate",
                    status="fallback",
                    summary="no_replacement_candidate",
                )
                with trace_recorder.step("response.compose_no_results") as step:
                    reply_text = self._composer.compose_no_results(preferences=preferences)
                    step.success()
                return ChatMessageResponse(
                    session_id=session_id,
                    turn_id=turn_id,
                    intent=Intent.REPLAN,
                    needs_clarification=False,
                    message=reply_text,
                    preferences=preferences,
                    tool_results_summary=summary,
                    source=source,
                )

        try:
            replan_result = await self._replanner.apply(
                current_itinerary=session.latest_itinerary,
                request=replan_request,
                preferences=preferences,
                replacement_place=replacement_place,
                trace_recorder=trace_recorder,
            )
        except Exception:
            with trace_recorder.step("response.compose_replan_error") as step:
                reply_text = self._composer.compose_replan_error(preferences=preferences)
                step.success()
            return ChatMessageResponse(
                session_id=session_id,
                turn_id=turn_id,
                intent=Intent.REPLAN,
                needs_clarification=False,
                message=reply_text,
                preferences=preferences,
                tool_results_summary=summary,
                source=source,
            )

        with trace_recorder.step("session.set_itinerary") as step:
            await self._session_manager.set_itinerary(session_id, replan_result.itinerary)
            step.success(detail={"stop_count": len(replan_result.itinerary.stops)})
        with trace_recorder.step("response.compose_replan") as step:
            reply_text = self._composer.compose_replan(
                itinerary=replan_result.itinerary,
                routing_status=replan_result.routing_status,
                preferences=preferences,
                operation=replan_result.operation,
                target_index=replan_result.target_index,
            )
            step.success(
                detail={
                    "operation": replan_result.operation,
                    "routing_status": replan_result.routing_status,
                }
            )
        return ChatMessageResponse(
            session_id=session_id,
            turn_id=turn_id,
            intent=Intent.REPLAN,
            needs_clarification=False,
            message=reply_text,
            preferences=preferences,
            itinerary=replan_result.itinerary,
            routing_status=replan_result.routing_status,
            candidates=(
                self._to_chat_candidates(loop_result.places, preferences)
                if loop_result and loop_result.status == "ok"
                else []
            ),
            tool_results_summary=summary,
            source=source,
        )

    async def _run_loop(
        self,
        *,
        intent: Intent,
        message: str,
        preferences: Preferences,
        replacement_constraint: PlaceConstraint | None,
        category_mix,
        user_context,
        trace_recorder: TraceRecorder,
        step_name: str,
    ):
        with trace_recorder.step(step_name) as step:
            try:
                loop_result = await self._agent_loop.run(
                    intent=intent,
                    message=message,
                    preferences=preferences,
                    replacement_constraint=replacement_constraint,
                    category_mix=category_mix,
                    user_context=user_context,
                    trace_recorder=trace_recorder,
                )
            except Exception as exc:
                step.error(summary="agent_loop_exception", error=exc.__class__.__name__)
                return LoopResult(
                    status="error",
                    tools_used=[],
                    places=[],
                    error=exc.__class__.__name__,
                )
            if loop_result.status == "ok":
                step.success(
                    summary="ok",
                    detail={
                        "candidate_count": len(loop_result.places),
                        "tools_used": loop_result.tools_used,
                    },
                )
            elif loop_result.status == "empty":
                step.success(
                    summary="empty",
                    detail={"tools_used": loop_result.tools_used},
                )
            else:
                step.fallback(
                    summary=loop_result.error or "error",
                    detail={"tools_used": loop_result.tools_used},
                )
            return loop_result

    def _compose_place_recommendation_reply(
        self,
        *,
        loop_result: LoopResult,
        preferences: Preferences,
        trace_recorder: TraceRecorder,
    ) -> tuple[str, list[ChatCandidate]]:
        if loop_result.relaxations_applied:
            with trace_recorder.step("response.compose_recommendation_with_relaxation") as step:
                reply_text, candidates = self._composer.compose_recommendation_with_relaxation(
                    places=loop_result.places,
                    preferences=preferences,
                    relaxations=loop_result.relaxations_applied,
                    original_filters=loop_result.original_filters,
                )
                step.success(
                    detail={
                        "candidate_count": len(candidates),
                        "relaxations": loop_result.relaxations_applied,
                    }
                )
                return reply_text, candidates

        with trace_recorder.step("response.compose_recommendation") as step:
            reply_text, candidates = self._composer.compose_recommendation(
                places=loop_result.places,
                preferences=preferences,
            )
            step.success(detail={"candidate_count": len(candidates)})
            return reply_text, candidates

    def _compose_relaxed_or_no_results_reply(
        self,
        *,
        loop_result: LoopResult,
        preferences: Preferences,
        trace_recorder: TraceRecorder,
    ) -> tuple[str, list[ChatCandidate]]:
        if loop_result.places:
            return self._compose_place_recommendation_reply(
                loop_result=loop_result,
                preferences=preferences,
                trace_recorder=trace_recorder,
            )

        with trace_recorder.step("response.compose_no_results") as step:
            reply_text = self._composer.compose_no_results(preferences=preferences)
            step.success()
        return reply_text, []

    @staticmethod
    def _tool_summary(loop_result) -> ToolResultsSummary:
        return ToolResultsSummary(
            tools_used=list(getattr(loop_result, "tools_used", [])),
            result_status=getattr(loop_result, "status", "error"),
            candidate_count=len(getattr(loop_result, "places", [])),
        )

    async def _extract_category_mix(
        self,
        *,
        message: str,
        trace_recorder: TraceRecorder,
    ):
        with trace_recorder.step("category_mix.extract") as step:
            category_mix = await extract_category_mix(
                message,
                client=self._agent_loop._client,
            )
            step.success(
                detail={
                    "categories": [item.internal_category for item in category_mix],
                }
            )
            return category_mix

    def _should_use_discovery_flow(
        self,
        *,
        message: str,
        classifier_result: ClassifierResult,
        preferences: Preferences,
    ) -> bool:
        if classifier_result.intent in {Intent.REPLAN, Intent.EXPLAIN}:
            return False
        if self._agent_loop.is_discovery_message(message):
            return True
        return (
            classifier_result.intent in {Intent.CHAT_GENERAL, Intent.GENERATE_ITINERARY}
            and self._is_specific_place_request(message, preferences)
        )

    def _should_override_generate_to_discovery(
        self,
        *,
        message: str,
        preferences: Preferences,
    ) -> bool:
        if _ITINERARY_LANGUAGE_PATTERN.search(message):
            return False
        return preferences.origin is None and preferences.time_window is None

    def _is_specific_place_request(
        self,
        message: str,
        preferences: Preferences,
    ) -> bool:
        if self._agent_loop.infer_primary_type(message, preferences) is not None:
            return True
        return (
            self._agent_loop.infer_internal_category(message, preferences) is not None
            and self._agent_loop._preferred_tag_keyword(preferences) is not None
        )

    def _record_turn_frame_validation(
        self,
        *,
        trace_recorder: TraceRecorder,
        message: str,
        intent: Intent,
        preferences: Preferences,
        route: str,
        needs_clarification: bool,
        missing_fields: list[str],
        category_mix: list | None = None,
        replan_request=None,
    ) -> None:
        inferred_primary_type = self._agent_loop.infer_primary_type(message, preferences)
        inferred_category = self._agent_loop.infer_internal_category(message, preferences)
        selected_vibe_tags: list[str] = []
        operation = None
        target_index = None
        replacement_internal_category = None
        replacement_primary_type = None

        if replan_request is not None:
            operation = replan_request.operation
            target_index = replan_request.target_index
            if replan_request.replacement_constraint is not None:
                replacement_internal_category = replan_request.replacement_constraint.internal_category
                replacement_primary_type = replan_request.replacement_constraint.primary_type
                selected_vibe_tags = list(replan_request.replacement_constraint.vibe_tags)

        trace_recorder.record_step(
            name="turn_frame.validate",
            status="fallback" if needs_clarification else "success",
            summary=route,
            detail={
                "intent": intent.value,
                "route": route,
                "operation": operation,
                "target_index": target_index,
                "origin": preferences.origin,
                "district": preferences.district,
                "time_window_start": (
                    preferences.time_window.start_time if preferences.time_window else None
                ),
                "time_window_end": (
                    preferences.time_window.end_time if preferences.time_window else None
                ),
                "search_internal_category": inferred_category,
                "search_primary_type": inferred_primary_type,
                "replacement_internal_category": replacement_internal_category,
                "replacement_primary_type": replacement_primary_type,
                "selected_vibe_tags": selected_vibe_tags,
                "category_mix": [
                    item.internal_category for item in (category_mix or [])
                ],
                "missing_fields": missing_fields,
            },
        )

    @staticmethod
    def _final_status_for_response(response: ChatMessageResponse) -> TraceFinalStatus:
        if response.needs_clarification:
            return "clarification"
        return "success"

    @staticmethod
    def _outcome_for_response(response: ChatMessageResponse) -> str:
        if response.needs_clarification:
            return "clarification"
        if response.intent == Intent.GENERATE_ITINERARY and response.itinerary is not None:
            return "itinerary_generated"
        if response.intent == Intent.REPLAN and response.itinerary is not None:
            return "replan_applied"
        if response.tool_results_summary and response.tool_results_summary.result_status == "error":
            return "tool_error_degraded"
        if response.tool_results_summary and response.tool_results_summary.result_status == "empty":
            return "no_results"
        if response.candidates:
            return "recommendations_returned"
        return "chat_replied"

    async def _session_lock_for(self, session_id: str) -> asyncio.Lock:
        async with self._session_lock_guard:
            lock = self._session_locks.get(session_id)
            if lock is None:
                lock = asyncio.Lock()
                # TODO: prune idle session locks if unique-session growth becomes relevant
                # outside the current demo/dev scope.
                self._session_locks[session_id] = lock
            return lock

    @staticmethod
    def _log_trace(trace) -> None:
        level = logging.ERROR if trace.final_status == "error" else logging.INFO
        log_event(
            logger,
            level,
            "chat.trace.recorded",
            trace_id=trace.trace_id,
            session_id=trace.session_id,
            intent=trace.intent,
            outcome=trace.outcome,
            final_status=trace.final_status,
            duration_ms=trace.duration_ms,
            step_count=len(trace.steps),
            warning_count=len(trace.warnings),
            error_summary=trace.error_summary,
        )

    @staticmethod
    def _to_cached_place(place: Place | object) -> Place:
        if isinstance(place, Place):
            return place
        tool_place = place
        return Place(
            place_id=getattr(tool_place, "venue_id", None),
            venue_id=getattr(tool_place, "venue_id", None),
            name=getattr(tool_place, "name"),
            category=getattr(tool_place, "category", None),
            district=getattr(tool_place, "district", None),
            primary_type=getattr(tool_place, "primary_type", None),
            budget_level=getattr(tool_place, "budget_level", None),
            indoor=getattr(tool_place, "indoor", None),
            vibe_tags=list(getattr(tool_place, "vibe_tags", None) or []),
            lat=getattr(tool_place, "lat", None),
            lng=getattr(tool_place, "lng", None),
            raw_payload=getattr(tool_place, "raw_payload", {}) or {},
        )

    def _to_chat_candidates(
        self,
        places: list[ToolPlace],
        preferences: Preferences,
    ) -> list[ChatCandidate]:
        _, candidates = self._composer.compose_recommendation(
            places=places,
            preferences=preferences,
        )
        return candidates

    @staticmethod
    def _pick_cached_replan_candidate(
        *,
        session: Session,
        target_index: int | None,
        replacement_constraint: PlaceConstraint | None,
    ) -> tuple[ToolPlace | None, list[CandidateMatchDecision]]:
        used_ids = (
            {stop.venue_id for stop in session.latest_itinerary.stops}
            if session.latest_itinerary
            else set()
        )
        decisions = []
        for candidate in session.cached_candidates:
            candidate_id = candidate.venue_id or candidate.place_id
            if candidate_id is None or candidate_id in used_ids:
                continue
            decision = candidate_matches_constraint(candidate, replacement_constraint)
            decisions.append(decision)
            if not decision.matched:
                continue
            return ToolPlace(
                venue_id=candidate_id,
                name=candidate.name,
                category=candidate.category,
                district=candidate.district,
                primary_type=candidate.primary_type,
                budget_level=candidate.budget_level,
                indoor=candidate.indoor,
                vibe_tags=list(candidate.vibe_tags),
                lat=candidate.lat,
                lng=candidate.lng,
                raw_payload=candidate.raw_payload,
            ), decisions
        return None, decisions

    @staticmethod
    def _pick_tool_replan_candidate(
        *,
        current_itinerary: Itinerary,
        places: list[ToolPlace],
        target_index: int | None,
        replacement_constraint: PlaceConstraint | None,
    ) -> ToolPlace | None:
        used_ids = {stop.venue_id for stop in current_itinerary.stops}
        target_venue_id = None
        if target_index is not None and 0 <= target_index < len(current_itinerary.stops):
            target_venue_id = current_itinerary.stops[target_index].venue_id
        for place in places:
            if place.venue_id not in used_ids and candidate_matches_constraint(
                place,
                replacement_constraint,
            ).matched:
                return place
        for place in places:
            if (
                (target_venue_id is None or place.venue_id != target_venue_id)
                and candidate_matches_constraint(place, replacement_constraint).matched
            ):
                return place
        return None

    @staticmethod
    def _preferences_for_current_turn(
        *,
        base_preferences: Preferences,
        preference_delta: Preferences,
        intent: Intent,
    ) -> Preferences:
        if intent == Intent.REPLAN:
            return base_preferences.model_copy(deep=True)

        payload = base_preferences.model_dump()
        for field_name in preference_delta.model_fields_set:
            value = getattr(preference_delta, field_name)
            if field_name in {"interest_tags", "avoid_tags"}:
                payload[field_name] = list(value or [])
                continue
            if field_name == "time_window" and value is not None:
                current_time_window = base_preferences.time_window or {}
                current_time_window_data = (
                    current_time_window.model_dump(exclude_none=True)
                    if hasattr(current_time_window, "model_dump")
                    else {}
                )
                payload[field_name] = {
                    "start_time": value.start_time or current_time_window_data.get("start_time"),
                    "end_time": value.end_time or current_time_window_data.get("end_time"),
                }
                continue
            if value is None:
                continue
            payload[field_name] = value
        return Preferences.model_validate(payload)
