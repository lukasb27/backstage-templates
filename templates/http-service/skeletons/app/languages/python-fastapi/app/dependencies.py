"""
The one worked example of the env-driven, dev/prod-swappable dependency pattern:
an abstract interface, a real implementation, a dev stub, and a factory that
picks between them off ENVIRONMENT. Not wired into any route by default —
delete it, or follow the pattern for your first real dependency (a database
client, a queue, an external API).
"""

import os
from abc import ABC, abstractmethod
from datetime import UTC, datetime


class Clock(ABC):
    @abstractmethod
    def now(self) -> datetime: ...


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock(Clock):
    def now(self) -> datetime:
        return datetime(2020, 1, 1, tzinfo=UTC)


def get_clock() -> Clock:
    if os.getenv("ENVIRONMENT", "dev") == "prod":
        return SystemClock()

    return FixedClock()
