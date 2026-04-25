from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services import go_home_advisor
from app.session.models import FlowState, Session

TPE = ZoneInfo("Asia/Taipei")


class GoHomeUrgencyTests(unittest.TestCase):
    def test_time_urgency_zero_without_return_time(self) -> None:
        s = Session(session_id="x", flow_state=FlowState.RECOMMENDING, return_time=None)
        self.assertEqual(go_home_advisor.time_urgency(s, None), 0.0)

    def test_time_urgency_bands(self) -> None:
        s = Session(session_id="x", flow_state=FlowState.RECOMMENDING, return_time="18:00")
        base = datetime(2025, 6, 1, 12, 0, tzinfo=TPE)
        self.assertEqual(go_home_advisor.time_urgency(s, base.replace(hour=16, minute=0)), 0.0)  # 120m
        self.assertEqual(go_home_advisor.time_urgency(s, base.replace(hour=16, minute=30)), 0.0)  # 90m
        self.assertEqual(go_home_advisor.time_urgency(s, base.replace(hour=16, minute=31)), 0.2)  # 89m
        self.assertEqual(go_home_advisor.time_urgency(s, base.replace(hour=17, minute=0)), 0.5)  # 60m
        self.assertEqual(go_home_advisor.time_urgency(s, base.replace(hour=17, minute=1)), 0.5)  # 59m
        self.assertEqual(go_home_advisor.time_urgency(s, base.replace(hour=17, minute=30)), 0.8)  # 30m
        self.assertEqual(go_home_advisor.time_urgency(s, base.replace(hour=17, minute=31)), 0.8)  # 29m
        self.assertEqual(go_home_advisor.time_urgency(s, base.replace(hour=17, minute=45)), 1.0)  # 15m
        self.assertEqual(go_home_advisor.time_urgency(s, base.replace(hour=17, minute=46)), 1.0)  # 14m

    def test_urgency_level_strings(self) -> None:
        self.assertEqual(go_home_advisor.urgency_level(0.0), "none")
        self.assertEqual(go_home_advisor.urgency_level(0.2), "low")
        self.assertEqual(go_home_advisor.urgency_level(0.5), "medium")
        self.assertEqual(go_home_advisor.urgency_level(0.8), "high")
        self.assertEqual(go_home_advisor.urgency_level(1.0), "critical")
