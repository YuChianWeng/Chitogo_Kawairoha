from __future__ import annotations

import unittest

from app.orchestration.intents import Intent
from app.tools.registry import ToolRegistry


class StubPlaceAdapter:
    async def search_places(self, **_: object) -> object:
        return None

    async def recommend_places(self, **_: object) -> object:
        return None

    async def batch_get_places(self, **_: object) -> object:
        return None

    async def nearby_places(self, **_: object) -> object:
        return None

    async def get_categories(self) -> object:
        return None

    async def get_vibe_tags(self, **_: object) -> object:
        return None

    async def get_stats(self) -> object:
        return None


class StubRouteAdapter:
    async def estimate_route(self, **_: object) -> object:
        return None


class ToolRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ToolRegistry(
            place_adapter=StubPlaceAdapter(),
            route_adapter=StubRouteAdapter(),
        )

    def test_registers_tools_and_resolves_by_name(self) -> None:
        tool_names = [tool.name for tool in self.registry.list_tools()]

        self.assertIn("place_search", tool_names)
        self.assertIn("place_vibe_tags", tool_names)
        self.assertIn("route_estimate", tool_names)
        self.assertIsNotNone(self.registry.get_tool("place_search"))
        self.assertIsNotNone(self.registry.get_tool("place_vibe_tags"))
        self.assertIsNone(self.registry.get_tool("missing_tool"))

    def test_returns_allowed_tools_for_intent(self) -> None:
        explain_names = [tool.name for tool in self.registry.list_tools_for_intent(Intent.EXPLAIN)]
        chat_names = [tool.name for tool in self.registry.list_tools_for_intent(Intent.CHAT_GENERAL)]
        generate_names = [tool.name for tool in self.registry.list_tools_for_intent(Intent.GENERATE_ITINERARY)]

        self.assertEqual(explain_names, [])
        self.assertEqual(chat_names, ["place_search", "place_vibe_tags"])
        self.assertIn("place_recommend", generate_names)
        self.assertIn("place_vibe_tags", generate_names)
        self.assertIn("route_estimate", generate_names)
