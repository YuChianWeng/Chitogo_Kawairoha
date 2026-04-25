from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.session.models import Session

TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def calculate_trigger_time(return_time_str: str, snooze_mins: int = 0) -> datetime:
    """Parse HH:MM return time and subtract 30 min buffer + snooze.
    Assumes return_time_str is in Asia/Taipei time.
    """
    hh, mm = map(int, return_time_str.split(":"))
    now_taipei = datetime.now(TAIPEI_TZ)
    return_dt = now_taipei.replace(hour=hh, minute=mm, second=0, microsecond=0)
    
    # Trigger is 30 mins before return_time. Snooze pushes it back.
    # If snooze_mins is 10, trigger moves from T-30 to T-20.
    return return_dt - timedelta(minutes=30 - snooze_mins)


def is_in_window(session: Session) -> bool:
    """Return True if current time is within (30 - snooze) mins of return_time.
    Used for both the recommendation card and proactive reminders.
    """
    if not session.return_time:
        return False
    try:
        trigger = calculate_trigger_time(session.return_time, session.go_home_snooze_mins)
    except (ValueError, TypeError):
        return False

    return datetime.now(TAIPEI_TZ) >= trigger


def should_remind(session: Session, current_transit_min: int) -> bool:
    """Return True if now >= trigger_time and cooldown has passed.
    Used for proactive notifications (banners/messages).
    """
    if not is_in_window(session):
        return False

    if session.go_home_reminded_at is not None:
        # Use 10 min cooldown for the notification bubble/banner
        last_reminded = session.go_home_reminded_at
        if last_reminded.tzinfo is None or last_reminded.tzinfo.utcoffset(last_reminded) is None:
             from datetime import UTC
             last_reminded = last_reminded.replace(tzinfo=UTC)
        
        if datetime.now(TAIPEI_TZ) < last_reminded.astimezone(TAIPEI_TZ) + timedelta(minutes=10):
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
