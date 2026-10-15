from datetime import date, datetime

import pytest

from rentalab import reloj


@pytest.mark.parametrize(
    "instante,esperado",
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
def test_negocio_fecha_usa_madrid_incluyendo_verano_y_invierno(
    monkeypatch: pytest.MonkeyPatch, instante: str, esperado: date
) -> None:
    monkeypatch.setattr(reloj, "utc_ahora", lambda: datetime.fromisoformat(instante))
    assert reloj.madrid_hoy() == esperado


def test_proveedor_hace_no_capturar_a_fecha_antes_la_escritura_transaccion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instantes = iter(
        [
            datetime.fromisoformat("2026-01-14T22:59:59+00:00"),
            datetime.fromisoformat("2026-01-14T23:00:00+00:00"),
        ]
    )
    monkeypatch.setattr(reloj, "utc_ahora", lambda: next(instantes))
    hoy = reloj.obtener_hoy_proveedor()
    assert hoy() == date(2026, 1, 14)
    assert hoy() == date(2026, 1, 15)
