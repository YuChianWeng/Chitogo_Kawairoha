from __future__ import annotations

import math
from dataclasses import dataclass

from app.models.schemas import ScoredVenue


@dataclass
class RouteStop:
    venue: ScoredVenue
    order: int
    suggested_start: str   # "HH:MM"
    suggested_end: str     # "HH:MM"
    duration_minutes: int
    travel_minutes_from_prev: int


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in kilometres."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _travel_minutes(km: float) -> int:
    """Estimate travel time: walking/MRT mix, minimum 5 min."""
    return max(5, int(km * 12))


def _mins_to_hhmm(total_minutes: int) -> str:
    h = (total_minutes // 60) % 24
    m = total_minutes % 60
    return f"{h:02d}:{m:02d}"


def _hhmm_to_mins(hhmm: str) -> int:
    h, m = map(int, hhmm.split(":"))
    return h * 60 + m


class RouteOptimizer:
    MAX_STOPS = 5
    MIN_STOPS = 3

    def build_route(
        self,
        scored_venues: list[ScoredVenue],
        start_time: str,
        end_time: str,
    ) -> list[RouteStop]:
        if not scored_venues:
            return []

        budget_mins = _hhmm_to_mins(end_time) - _hhmm_to_mins(start_time)
        current_time = _hhmm_to_mins(start_time)
        remaining = list(scored_venues)

        # Anchor: highest-scored venue
        anchor = remaining.pop(0)
        stops: list[RouteStop] = []
        stops.append(
            RouteStop(
                venue=anchor,
                order=1,
                suggested_start=_mins_to_hhmm(current_time),
                suggested_end=_mins_to_hhmm(current_time + anchor.avg_duration_minutes),
                duration_minutes=anchor.avg_duration_minutes,
                travel_minutes_from_prev=0,
            )
        )
        current_time += anchor.avg_duration_minutes
        current_lat, current_lng = anchor.lat, anchor.lng

        while remaining and len(stops) < self.MAX_STOPS:
            time_left = _hhmm_to_mins(end_time) - current_time
            if time_left <= 0:
                break

            # Score = venue_score / (1 + distance_km)
            def _combined(v: ScoredVenue) -> float:
                km = _haversine_km(current_lat, current_lng, v.lat, v.lng)
                travel = _travel_minutes(km)
                if travel + v.avg_duration_minutes > time_left:
                    return -1.0  # won't fit
                return v.score / (1 + km)

            best = max(remaining, key=_combined)
            if _combined(best) < 0:
                break  # nothing fits in remaining time

            remaining.remove(best)
            km = _haversine_km(current_lat, current_lng, best.lat, best.lng)
            travel = _travel_minutes(km)
            current_time += travel

            stops.append(
                RouteStop(
                    venue=best,
                    order=len(stops) + 1,
                    suggested_start=_mins_to_hhmm(current_time),
                    suggested_end=_mins_to_hhmm(current_time + best.avg_duration_minutes),
                    duration_minutes=best.avg_duration_minutes,
                    travel_minutes_from_prev=travel,
                )
            )
            current_time += best.avg_duration_minutes
            current_lat, current_lng = best.lat, best.lng

        return stops
