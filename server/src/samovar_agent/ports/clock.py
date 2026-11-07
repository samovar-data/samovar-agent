"""Port: the wall clock."""

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Timezone-aware current time."""
        ...
