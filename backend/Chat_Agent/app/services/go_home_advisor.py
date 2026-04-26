from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.session.models import Session

TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def _now_taipei(override: datetime | None = None) -> datetime:
    """Return current Taipei time, or the provided override for demo/testing."""
    if override is not None:
        if override.tzinfo is None:
            return override.replace(tzinfo=TAIPEI_TZ)
        return override.astimezone(TAIPEI_TZ)
    return datetime.now(TAIPEI_TZ)


def parse_sim_time(sim_time_str: str | None) -> datetime | None:
    """Parse a HH:MM sim_time string into a tz-aware Taipei datetime for today.
    Returns None if the string is missing or malformed.
    """
    if not sim_time_str:
        return None
    try:
        hh, mm = map(int, sim_time_str.split(":"))
        now = datetime.now(TAIPEI_TZ)
        return now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    except (ValueError, AttributeError):
        return None


def calculate_trigger_time(
    return_time_str: str,
    snooze_mins: int = 0,
    now_override: datetime | None = None,
) -> datetime:
    """Parse HH:MM return time and subtract 30 min buffer + snooze.
    Assumes return_time_str is in Asia/Taipei time.
    """
    hh, mm = map(int, return_time_str.split(":"))
    now_taipei = _now_taipei(now_override)
    return_dt = now_taipei.replace(hour=hh, minute=mm, second=0, microsecond=0)

    # Trigger is 30 mins before return_time. Snooze pushes it back.
    # If snooze_mins is 10, trigger moves from T-30 to T-20.
    return return_dt - timedelta(minutes=30 - snooze_mins)


def time_urgency(session: Session, now_override: datetime | None = None) -> float:
    """0..1 urgency toward return time for destination-homing; 0 if no return_time or >90m left."""
    if not session.return_time:
        return 0.0
    now = _now_taipei(now_override)
    try:
        hh, mm = map(int, session.return_time.split(":"))
    except (ValueError, TypeError, AttributeError):
        return 0.0
    ret = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    m = (ret - now).total_seconds() / 60.0
    if m < 0:
        m = 0.0
    if m >= 90:
        return 0.0
    if m > 60:
        return 0.2
    if m > 30:
        return 0.5
    if m > 15:
        return 0.8
    return 1.0


def urgency_level(urgency: float) -> str:
    if urgency <= 0:
        return "none"
    if urgency <= 0.2:
        return "low"
    if urgency <= 0.5:
        return "medium"
    if urgency <= 0.8:
        return "high"
    return "critical"


def is_in_window(session: Session, now_override: datetime | None = None) -> bool:
    """Return True if current time is within (30 - snooze) mins of return_time.
    Used for both the recommendation card and proactive reminders.
    Pass now_override (Taipei-aware datetime) to simulate a different time for demos.
    """
    if not session.return_time:
        return False
    try:
        trigger = calculate_trigger_time(
            session.return_time, session.go_home_snooze_mins, now_override
        )
    except (ValueError, TypeError):
        return False

    return _now_taipei(now_override) >= trigger


def should_remind(
    session: Session,
    current_transit_min: int,
    now_override: datetime | None = None,
) -> bool:
    """Return True if now >= trigger_time and cooldown has passed.
    Used for proactive notifications (banners/messages).
    Pass now_override (Taipei-aware datetime) to simulate a different time for demos.
    """
    if not is_in_window(session, now_override):
        return False

    if session.go_home_reminded_at is not None:
        # Use 10 min cooldown for the notification bubble/banner
        last_reminded = session.go_home_reminded_at
        if last_reminded.tzinfo is None or last_reminded.tzinfo.utcoffset(last_reminded) is None:
            from datetime import UTC
            last_reminded = last_reminded.replace(tzinfo=UTC)

        if _now_taipei(now_override) < last_reminded.astimezone(TAIPEI_TZ) + timedelta(minutes=10):
            return False

    return True


def record_reminded(session: Session) -> None:
    from datetime import UTC
    session.go_home_reminded_at = datetime.now(UTC)


def snooze(session: Session) -> None:
    """Increment snooze by 10 minutes, up to the 30-minute limit."""
    session.go_home_snooze_mins = min(30, session.go_home_snooze_mins + 10)
    # Also record reminded time to trigger the banner cooldown
    record_reminded(session)
