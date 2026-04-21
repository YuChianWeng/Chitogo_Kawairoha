from __future__ import annotations

from uuid import uuid4

from app.chat.loop import AgentLoop
from app.chat.response_composer import ResponseComposer
from app.chat.schemas import ChatMessageRequest, ChatMessageResponse, ToolResultsSummary
from app.orchestration.classifier import IntentClassifier, detect_missing_generate_fields
from app.orchestration.intents import Intent
from app.orchestration.preferences import PreferenceExtractor
from app.session.manager import SessionManager, session_manager
from app.session.models import Place, Turn


class MessageHandler:
    """Single-turn application service for the Phase 5 chat endpoint."""

    def __init__(
        self,
        *,
        session_manager_instance: SessionManager | None = None,
        classifier: IntentClassifier | None = None,
        preference_extractor: PreferenceExtractor | None = None,
        agent_loop: AgentLoop | None = None,
        composer: ResponseComposer | None = None,
    ) -> None:
        self._session_manager = session_manager_instance or session_manager
        self._classifier = classifier or IntentClassifier()
        self._preference_extractor = preference_extractor or PreferenceExtractor()
        self._agent_loop = agent_loop or AgentLoop()
        self._composer = composer or ResponseComposer()

    async def handle(self, request: ChatMessageRequest) -> ChatMessageResponse:
        session_id = request.session_id or str(uuid4())
        user_turn_id = str(uuid4())
        assistant_turn_id = str(uuid4())
        session = await self._session_manager.get_or_create(session_id)
        await self._session_manager.append_turn(
            session_id,
            Turn(turn_id=user_turn_id, role="user", content=request.message.strip()),
        )

        classifier_result = await self._classifier.classify(
            request.message,
            has_itinerary=session.latest_itinerary is not None,
        )
        preference_delta = await self._preference_extractor.extract(
            request.message,
            current_preferences=session.preferences,
        )
        session = await self._session_manager.update_preferences(session_id, preference_delta)
        preferences = session.preferences

        if classifier_result.intent == Intent.GENERATE_ITINERARY:
            missing_fields = detect_missing_generate_fields(request.message, preferences)
            classifier_result.missing_fields = missing_fields
            classifier_result.needs_clarification = bool(missing_fields)

        if classifier_result.needs_clarification:
            reply_text = self._composer.compose_clarification(
                missing_fields=classifier_result.missing_fields,
                preferences=preferences,
            )
            response = ChatMessageResponse(
                session_id=session_id,
                turn_id=assistant_turn_id,
                intent=classifier_result.intent,
                needs_clarification=True,
                message=reply_text,
                preferences=preferences,
                source=classifier_result.source,
            )
        elif classifier_result.intent == Intent.REPLAN:
            stop_index = getattr(classifier_result.extracted_slots, "stop_index", None)
            response = ChatMessageResponse(
                session_id=session_id,
                turn_id=assistant_turn_id,
                intent=classifier_result.intent,
                needs_clarification=False,
                message=self._composer.compose_replan_placeholder(
                    stop_index=stop_index,
                    preferences=preferences,
                ),
                preferences=preferences,
                source=classifier_result.source,
            )
        elif classifier_result.intent == Intent.EXPLAIN:
            response = ChatMessageResponse(
                session_id=session_id,
                turn_id=assistant_turn_id,
                intent=classifier_result.intent,
                needs_clarification=False,
                message=self._composer.compose_explain(
                    preferences=preferences,
                    candidate_names=[candidate.name for candidate in session.cached_candidates],
                ),
                preferences=preferences,
                source=classifier_result.source,
            )
        elif classifier_result.intent == Intent.GENERATE_ITINERARY or self._agent_loop.is_discovery_message(request.message):
            loop_result = await self._agent_loop.run(
                intent=Intent.GENERATE_ITINERARY if classifier_result.intent == Intent.GENERATE_ITINERARY else Intent.CHAT_GENERAL,
                message=request.message,
                preferences=preferences,
                user_context=request.user_context,
            )
            summary = ToolResultsSummary(
                tools_used=loop_result.tools_used,
                result_status=loop_result.status,
                candidate_count=len(loop_result.places),
            )
            if loop_result.status == "ok":
                reply_text, candidates = self._composer.compose_recommendation(
                    places=loop_result.places,
                    preferences=preferences,
                )
                await self._session_manager.cache_candidates(
                    session_id,
                    [self._to_cached_place(place) for place in loop_result.places],
                )
            elif loop_result.status == "empty":
                reply_text = self._composer.compose_no_results(preferences=preferences)
                candidates = []
            else:
                reply_text = self._composer.compose_tool_error(preferences=preferences)
                candidates = []

            response = ChatMessageResponse(
                session_id=session_id,
                turn_id=assistant_turn_id,
                intent=classifier_result.intent,
                needs_clarification=False,
                message=reply_text,
                preferences=preferences,
                candidates=candidates,
                tool_results_summary=summary,
                source=classifier_result.source,
            )
        else:
            response = ChatMessageResponse(
                session_id=session_id,
                turn_id=assistant_turn_id,
                intent=classifier_result.intent,
                needs_clarification=False,
                message=self._composer.compose_general_chat(preferences=preferences),
                preferences=preferences,
                source=classifier_result.source,
            )

        await self._session_manager.append_turn(
            session_id,
            Turn(turn_id=assistant_turn_id, role="assistant", content=response.message),
        )
        return response

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
            lat=getattr(tool_place, "lat", None),
            lng=getattr(tool_place, "lng", None),
            raw_payload=getattr(tool_place, "raw_payload", {}) or {},
        )
