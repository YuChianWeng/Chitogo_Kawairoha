from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.session.models import Session


def calculate_trigger_time(return_time_str: str, transit_min: int) -> datetime:
    """Parse HH:MM return time and subtract transit + 30 min buffer."""
    hh, mm = map(int, return_time_str.split(":"))
    today = datetime.now(UTC).date()
    return_dt = datetime(today.year, today.month, today.day, hh, mm, tzinfo=UTC)
    return return_dt - timedelta(minutes=transit_min + 30)


def should_remind(session: Session, current_transit_min: int) -> bool:
    """Return True if now >= trigger_time and cooldown has passed."""
    if not session.return_time:
        return False
    try:
        trigger = calculate_trigger_time(session.return_time, current_transit_min)
    except (ValueError, TypeError):
        return False

    now = datetime.now(UTC)
    if now < trigger:
        return False

    if session.go_home_reminded_at is not None:
        cooldown_end = session.go_home_reminded_at + timedelta(minutes=10)
        if now < cooldown_end:
            return False

    return True


def record_reminded(session: Session) -> None:
    session.go_home_reminded_at = datetime.now(UTC)
