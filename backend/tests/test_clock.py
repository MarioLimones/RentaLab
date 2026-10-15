from datetime import date, datetime

import pytest

from rentalab import clock


@pytest.mark.parametrize(
    "instant,expected",
    [
        ("2026-01-14T22:59:59+00:00", date(2026, 1, 14)),
        ("2026-01-14T23:00:00+00:00", date(2026, 1, 15)),
        ("2026-07-14T21:59:59+00:00", date(2026, 7, 14)),
        ("2026-07-14T22:00:00+00:00", date(2026, 7, 15)),
        ("2026-03-29T22:30:00+00:00", date(2026, 3, 30)),
        ("2026-10-25T22:30:00+00:00", date(2026, 10, 25)),
        ("2026-10-25T23:00:00+00:00", date(2026, 10, 26)),
    ],
)
def test_business_date_uses_madrid_including_summer_and_winter(
    monkeypatch: pytest.MonkeyPatch, instant: str, expected: date
) -> None:
    monkeypatch.setattr(clock, "utc_now", lambda: datetime.fromisoformat(instant))
    assert clock.madrid_today() == expected


def test_provider_does_not_capture_a_date_before_the_write_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instants = iter(
        [
            datetime.fromisoformat("2026-01-14T22:59:59+00:00"),
            datetime.fromisoformat("2026-01-14T23:00:00+00:00"),
        ]
    )
    monkeypatch.setattr(clock, "utc_now", lambda: next(instants))
    today = clock.get_today_provider()
    assert today() == date(2026, 1, 14)
    assert today() == date(2026, 1, 15)
