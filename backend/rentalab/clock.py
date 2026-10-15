"""Business calendar independent of the host timezone and injectable in HTTP tests."""

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends

TodayProvider = Callable[[], date]


def utc_now() -> datetime:
    return datetime.now(UTC)


def madrid_today() -> date:
    return utc_now().astimezone(ZoneInfo("Europe/Madrid")).date()


def get_today_provider() -> TodayProvider:
    # Return a provider, not a captured date: writers call it after obtaining the lock.
    return madrid_today


BusinessDate = Annotated[TodayProvider, Depends(get_today_provider)]
