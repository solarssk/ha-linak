"""Host-side reminder edit policy, not firmware or medical limits."""

MIN_SITTING_MINUTES = 1
MAX_SITTING_MINUTES = 60
STANDARD_SITTING_MINUTES = 55


class InvalidReminderInterval(ValueError):
    """A requested duration is outside the integration's input policy."""


class ReminderProfileActive(ValueError):
    """Only inactive-profile interval editing has hardware evidence."""


def sitting_minutes(value: float) -> int:
    """Accept whole minutes only; HA number services pass floats."""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not MIN_SITTING_MINUTES <= value <= MAX_SITTING_MINUTES
        or int(value) != value
    ):
        raise InvalidReminderInterval("Enter whole minutes from 1 to 60")
    return int(value)
