from __future__ import annotations

from app.orchestration.intents import Intent
from app.tools.models import ToolDefinition
from app.tools.place_adapter import PlaceToolAdapter, place_tool_adapter
from app.tools.route_adapter import RouteToolAdapter, route_tool_adapter


class ToolRegistry:
    """Declarative registry for future tool-use phases."""

    def __init__(
        self,
        *,
        place_adapter: PlaceToolAdapter | None = None,
        route_adapter: RouteToolAdapter | None = None,
    ) -> None:
        self._place_adapter = place_adapter or place_tool_adapter
        self._route_adapter = route_adapter or route_tool_adapter
        self._tools = {
            tool.name: tool
            for tool in [
                ToolDefinition(
                    name="place_search",
                    description="Search Taipei venues with structured filters.",
                    handler=self._place_adapter.search_places,
                    intents=frozenset(
                        {
                            Intent.GENERATE_ITINERARY,
                            Intent.REPLAN,
                            Intent.CHAT_GENERAL,
                        }
                    ),
                ),
                ToolDefinition(
                    name="place_recommend",
                    description="Get scored Taipei venue recommendations.",
                    handler=self._place_adapter.recommend_places,
                    intents=frozenset({Intent.GENERATE_ITINERARY}),
                ),
                ToolDefinition(
                    name="place_nearby",
                    description="Find venues near a coordinate.",
                    handler=self._place_adapter.nearby_places,
                    intents=frozenset({Intent.GENERATE_ITINERARY, Intent.REPLAN}),
                ),
                ToolDefinition(
                    name="place_batch",
                    description="Fetch detailed venue records by id.",
                    handler=self._place_adapter.batch_get_places,
                    intents=frozenset({Intent.GENERATE_ITINERARY, Intent.REPLAN}),
                ),
                ToolDefinition(
                    name="place_categories",
                    description="List the supported internal categories.",
                    handler=self._place_adapter.get_categories,
                    intents=frozenset({Intent.GENERATE_ITINERARY}),
                ),
                ToolDefinition(
                    name="place_vibe_tags",
                    description="List known normalized vibe tags with optional place scope.",
                    handler=self._place_adapter.get_vibe_tags,
                    intents=frozenset(
                        {
                            Intent.GENERATE_ITINERARY,
                            Intent.REPLAN,
                            Intent.CHAT_GENERAL,
                        }
                    ),
                ),
                ToolDefinition(
                    name="place_stats",
                    description="Get aggregate place counts by district and category.",
                    handler=self._place_adapter.get_stats,
                    intents=frozenset({Intent.GENERATE_ITINERARY}),
                ),
                ToolDefinition(
                    name="route_estimate",
                    description="Estimate travel time between two coordinates.",
                    handler=self._route_adapter.estimate_route,
                    intents=frozenset({Intent.GENERATE_ITINERARY, Intent.REPLAN}),
                ),
            ]
        }

    def get_tool(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def list_tools_for_intent(self, intent: Intent) -> list[ToolDefinition]:
        return [tool for tool in self._tools.values() if intent in tool.intents]


tool_registry = ToolRegistry()

__all__ = ["ToolRegistry", "tool_registry"]
