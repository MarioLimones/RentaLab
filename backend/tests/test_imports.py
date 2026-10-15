import csv
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from conftest import authenticate
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event

from rentalab.config import Settings
from rentalab.main import create_app

HEADER = [
    "external_reference",
    "customer_name",
    "customer_email",
    "equipment_code",
    "starts_on",
    "ends_on",
]
FIXTURES = Path(__file__).parent / "fixtures" / "imports"
MAX_FILE_BYTES = 1_048_576


@pytest.fixture
def import_equipment(
    client: TestClient, equipment_payload: dict[str, object]
) -> list[dict[str, Any]]:
    equipment = []
    for code in ("CAM-001", "CAM-002"):
        response = client.post("/api/equipment", json={**equipment_payload, "code": code})
        assert response.status_code == 201
        equipment.append(response.json())
    return equipment


def make_csv(rows: list[list[str]], header: list[str] = HEADER) -> bytes:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def order_row(reference: str = "ORDER-001", **changes: str) -> list[str]:
    values = {
        "external_reference": reference,
        "customer_name": "Cliente ficticio",
        "customer_email": "cliente@example.test",
        "equipment_code": "CAM-001",
        "starts_on": "2026-11-10",
        "ends_on": "2026-11-12",
        **changes,
    }
    return [values[key] for key in HEADER]


def import_csv(client: TestClient, content: bytes) -> dict[str, Any]:
    response = client.post("/api/imports", files={"file": ("orders.csv", content, "text/csv")})
    assert response.status_code == 200, response.text
    report = response.json()
    assert set(report) == {"totals", "rows"}
    assert set(report["totals"]) == {"total", "accepted", "already_imported", "rejected"}
    assert report["totals"]["total"] == len(report["rows"])
    assert (
        sum(report["totals"][status] for status in ("accepted", "already_imported", "rejected"))
        == report["totals"]["total"]
    )
    for row in report["rows"]:
        assert set(row) == {"line", "external_reference", "status", "reservation", "message"}
        assert isinstance(row["message"], str) and row["message"].strip()
        assert "Traceback" not in row["message"]
        assert "INSERT INTO" not in row["message"]
        assert row["status"] in {"accepted", "already_imported", "rejected"}
        assert (row["reservation"] is None) is (row["status"] == "rejected")
    return report


def test_import_valid_csv_creates_normalized_reservations_in_file_order(
    client: TestClient, import_equipment: list[dict[str, Any]]
) -> None:
    report = import_csv(client, (FIXTURES / "valid.csv").read_bytes())
    assert report["totals"] == {"total": 3, "accepted": 3, "already_imported": 0, "rejected": 0}
    assert [row["line"] for row in report["rows"]] == [2, 3, 4]
    first = report["rows"][0]
    assert first["external_reference"] == "ORDER-001"
    assert first["reservation"] == {
        "id": first["reservation"]["id"],
        "equipment_id": import_equipment[0]["id"],
        "customer_name": "Luz, Norte",
        "customer_email": "luz@example.test",
        "start_date": "2026-11-10",
        "end_date": "2026-11-12",
        "status": "confirmed",
        "external_reference": "ORDER-001",
        "customer_user_id": None,
        "origin": "csv",
    }
    for row in report["rows"]:
        reservation = row["reservation"]
        assert client.get(f"/api/reservations/{reservation['id']}").json() == reservation
    assert len(client.get("/api/reservations").json()) == 3


def test_mixed_csv_commits_valid_rows_and_rejects_other_rows_individually(
    client: TestClient, import_equipment: list[dict[str, Any]]
) -> None:
    report = import_csv(client, (FIXTURES / "mixed.csv").read_bytes())
    assert report["totals"] == {"total": 5, "accepted": 2, "already_imported": 0, "rejected": 3}
    assert [row["status"] for row in report["rows"]] == [
        "accepted",
        "rejected",
        "rejected",
        "rejected",
        "accepted",
    ]
    assert [row["line"] for row in report["rows"]] == [2, 3, 4, 5, 6]
    assert [row["external_reference"] for row in report["rows"]] == [
        "ORDER-A",
        "ORDER-B",
        "ORDER-C",
        "ORDER-D",
        "ORDER-E",
    ]
    assert len(client.get("/api/reservations").json()) == 2


def test_reimport_returns_original_reservations_without_duplicates(
    client: TestClient, import_equipment: list[dict[str, Any]]
) -> None:
    content = (FIXTURES / "valid.csv").read_bytes()
    first = import_csv(client, content)
    original = client.get("/api/reservations").json()
    second = import_csv(client, content)
    assert second["totals"] == {"total": 3, "accepted": 0, "already_imported": 3, "rejected": 0}
    assert [row["reservation"] for row in second["rows"]] == [
        row["reservation"] for row in first["rows"]
    ]
    assert client.get("/api/reservations").json() == original


def test_normalized_duplicate_references_in_a_file_are_idempotent(
    client: TestClient, import_equipment: list[dict[str, Any]]
) -> None:
    report = import_csv(
        client,
        make_csv(
            [
                order_row(
                    " ORDER-001 ",
                    customer_name="  Cliente ficticio  ",
                    customer_email="cliente@EXAMPLE.TEST",
                    equipment_code=" cam-001 ",
                ),
                order_row(),
                order_row(customer_name="Otro cliente"),
            ]
        ),
    )
    assert report["totals"] == {"total": 3, "accepted": 1, "already_imported": 1, "rejected": 1}
    assert [row["status"] for row in report["rows"]] == ["accepted", "already_imported", "rejected"]
    assert report["rows"][0]["reservation"] == report["rows"][1]["reservation"]
    assert len(client.get("/api/reservations").json()) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"customer_name": "Otro cliente"},
        {"customer_email": "otro@example.test"},
        {"equipment_code": "CAM-002"},
        {"starts_on": "2026-11-09"},
        {"ends_on": "2026-11-13"},
    ],
)
def test_a_reference_with_changed_data_is_rejected_without_overwriting_history(
    client: TestClient, import_equipment: list[dict[str, Any]], changes: dict[str, str]
) -> None:
    import_csv(client, make_csv([order_row()]))
    before = client.get("/api/reservations").json()
    report = import_csv(client, make_csv([order_row(**changes)]))
    assert report["totals"]["rejected"] == 1
    assert report["rows"][0]["external_reference"] == "ORDER-001"
    assert client.get("/api/reservations").json() == before


@pytest.mark.parametrize("obstacle", ["inactive", "incident", "later_booking"])
def test_cancelled_identical_import_stays_idempotent_despite_current_unavailability(
    client: TestClient, import_equipment: list[dict[str, Any]], obstacle: str
) -> None:
    equipment_id = import_equipment[0]["id"]
    imported = import_csv(client, make_csv([order_row()]))["rows"][0]["reservation"]
    cancelled = client.post(f"/api/reservations/{imported['id']}/cancel").json()
    if obstacle == "inactive":
        assert (
            client.patch(f"/api/equipment/{equipment_id}", json={"active": False}).status_code
            == 200
        )
    elif obstacle == "incident":
        assert (
            client.post(
                "/api/incidents",
                json={
                    "equipment_id": equipment_id,
                    "title": "Incidencia ficticia",
                    "blocking": True,
                },
            ).status_code
            == 201
        )
    else:
        assert (
            client.post(
                "/api/reservations",
                json={
                    **{
                        key: value
                        for key, value in imported.items()
                        if key not in {"id", "status", "customer_user_id", "origin"}
                    },
                    "external_reference": "LATER-BOOKING",
                },
            ).status_code
            == 201
        )
    before = client.get("/api/reservations").json()
    report = import_csv(client, make_csv([order_row()]))
    assert report["totals"] == {"total": 1, "accepted": 0, "already_imported": 1, "rejected": 0}
    assert report["rows"][0]["reservation"] == cancelled
    assert client.get("/api/reservations").json() == before


def test_reference_comparison_is_case_sensitive(
    client: TestClient, import_equipment: list[dict[str, Any]]
) -> None:
    report = import_csv(
        client,
        make_csv(
            [
                order_row("ORDER-001"),
                order_row("order-001", starts_on="2026-11-12", ends_on="2026-11-13"),
            ]
        ),
    )
    assert report["totals"]["accepted"] == 2


@pytest.mark.parametrize("obstacle", ["inactive", "incident", "overlap"])
def test_import_uses_the_existing_reservation_policy_and_continues_after_rejection(
    client: TestClient, import_equipment: list[dict[str, Any]], obstacle: str
) -> None:
    equipment_id = import_equipment[0]["id"]
    if obstacle == "inactive":
        client.patch(f"/api/equipment/{equipment_id}", json={"active": False})
    elif obstacle == "incident":
        client.post(
            "/api/incidents",
            json={"equipment_id": equipment_id, "title": "Incidencia ficticia", "blocking": True},
        )
    else:
        import_csv(client, make_csv([order_row("EXISTING")]))
    before = client.get("/api/reservations").json()
    report = import_csv(
        client, make_csv([order_row("BLOCKED"), order_row("FREE", equipment_code="CAM-002")])
    )
    assert report["totals"] == {"total": 2, "accepted": 1, "already_imported": 0, "rejected": 1}
    assert [row["status"] for row in report["rows"]] == ["rejected", "accepted"]
    after = client.get("/api/reservations").json()
    assert len(after) == len(before) + 1
    for original in before:
        assert client.get(f"/api/reservations/{original['id']}").json() == original


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("external_reference", ""),
        ("external_reference", "   "),
        ("external_reference", "X" * 121),
        ("external_reference", "REF\x00bad"),
        ("customer_name", ""),
        ("customer_name", "  "),
        ("customer_name", "X" * 121),
        ("customer_name", "Bad\x00name"),
        ("customer_email", "invalid-email"),
        ("customer_email", ""),
        ("equipment_code", ""),
        ("equipment_code", "UNKNOWN"),
        ("equipment_code", "CAM\x00bad"),
        ("starts_on", "2026-11-12"),
        ("starts_on", "2026-11-13"),
        ("starts_on", "2026-02-30"),
        ("starts_on", "2026-1-10"),
        ("starts_on", "2026-11-10T00:00:00"),
        ("starts_on", " 2026-11-10 "),
        ("ends_on", "2026-11-10"),
        ("ends_on", ""),
        ("ends_on", "2026-11-12T00:00:00Z"),
    ],
)
def test_invalid_row_fields_are_rejected_without_losing_the_next_valid_row(
    client: TestClient, import_equipment: list[dict[str, Any]], field: str, value: str
) -> None:
    report = import_csv(client, make_csv([order_row(**{field: value}), order_row("VALID-SECOND")]))
    assert report["totals"] == {"total": 2, "accepted": 1, "already_imported": 0, "rejected": 1}
    assert [row["status"] for row in report["rows"]] == ["rejected", "accepted"]
    assert report["rows"][1]["line"] == 3
    assert len(client.get("/api/reservations").json()) == 1


@pytest.mark.parametrize("bad_row", [[], ["ONLY-REF"], order_row() + ["extra"]])
def test_blank_and_wrong_cell_counts_are_rejected_and_processing_continues(
    client: TestClient, import_equipment: list[dict[str, Any]], bad_row: list[str]
) -> None:
    report = import_csv(client, make_csv([bad_row, order_row("VALID-SECOND")]))
    assert report["totals"]["rejected"] == 1
    assert report["totals"]["accepted"] == 1
    assert [row["line"] for row in report["rows"]] == [2, 3]


def test_quoted_commas_multiline_records_and_physical_start_line_numbers(
    client: TestClient, import_equipment: list[dict[str, Any]]
) -> None:
    report = import_csv(
        client,
        make_csv(
            [
                order_row(customer_name='Estudio "Norte",\nProducción'),
                order_row("SECOND", equipment_code="CAM-002"),
            ]
        ),
    )
    assert report["totals"]["accepted"] == 2
    assert [row["line"] for row in report["rows"]] == [2, 4]
    assert report["rows"][0]["reservation"]["customer_name"] == 'Estudio "Norte",\nProducción'


@pytest.mark.parametrize("bom", [False, True])
@pytest.mark.parametrize("crlf", [False, True])
def test_utf8_with_optional_bom_and_windows_newlines_is_supported(
    client: TestClient, import_equipment: list[dict[str, Any]], bom: bool, crlf: bool
) -> None:
    content = make_csv([order_row(customer_name="Producción Ñandú")])
    if crlf:
        content = content.replace(b"\n", b"\r\n")
    if bom:
        content = b"\xef\xbb\xbf" + content
    report = import_csv(client, content)
    assert report["totals"]["accepted"] == 1
    assert report["rows"][0]["reservation"]["customer_name"] == "Producción Ñandú"


def test_header_only_is_an_empty_successful_import(client: TestClient) -> None:
    assert import_csv(client, make_csv([])) == {
        "totals": {"total": 0, "accepted": 0, "already_imported": 0, "rejected": 0},
        "rows": [],
    }


@pytest.mark.parametrize(
    "header",
    [
        HEADER[:-1],
        HEADER + ["extra"],
        [HEADER[1], HEADER[0], *HEADER[2:]],
        ["EXTERNAL_REFERENCE", *HEADER[1:]],
        [" external_reference", *HEADER[1:]],
        ["external_reference ", *HEADER[1:]],
        [*HEADER[:-1], "starts_on"],
    ],
)
def test_header_is_exact_ordered_and_case_sensitive(
    client: TestClient, import_equipment: list[dict[str, Any]], header: list[str]
) -> None:
    response = client.post(
        "/api/imports",
        files={"file": ("orders.csv", make_csv([order_row()], header=header), "text/csv")},
    )
    assert response.status_code == 422
    assert client.get("/api/reservations").json() == []


def test_invalid_header_fixture_is_rejected_without_creating_reservations(
    client: TestClient, import_equipment: list[dict[str, Any]]
) -> None:
    response = client.post(
        "/api/imports",
        files={"file": ("orders.csv", (FIXTURES / "invalid_header.csv").read_bytes(), "text/csv")},
    )
    assert response.status_code == 422
    assert client.get("/api/reservations").json() == []


@pytest.mark.parametrize("content", [b"", b"\xef\xbb\xbf", b"\xff\xfeinvalid-utf8"])
def test_empty_or_non_utf8_files_are_422(client: TestClient, content: bytes) -> None:
    response = client.post("/api/imports", files={"file": ("orders.csv", content, "text/csv")})
    assert response.status_code == 422


@pytest.mark.parametrize("suffix", [b'"unclosed\n', b'"bad"unexpected,value\n'])
def test_structurally_broken_csv_is_rejected_before_any_insert(
    app: FastAPI,
    client: TestClient,
    import_equipment: list[dict[str, Any]],
    suffix: bytes,
) -> None:
    statements: list[str] = []

    def observe_sql(_connection: object, _cursor: object, statement: str, *_args: object) -> None:
        statements.append(statement)

    event.listen(app.state.engine, "before_cursor_execute", observe_sql)
    try:
        response = client.post(
            "/api/imports",
            files={"file": ("orders.csv", make_csv([order_row()]) + suffix, "text/csv")},
        )
    finally:
        event.remove(app.state.engine, "before_cursor_execute", observe_sql)
    assert response.status_code == 422
    assert not any(statement.lstrip().upper().startswith("INSERT") for statement in statements)
    assert client.get("/api/reservations").json() == []


@pytest.mark.parametrize("too_large", ["bytes", "rows"])
def test_limits_are_checked_for_the_entire_file_before_any_insert(
    app: FastAPI,
    client: TestClient,
    import_equipment: list[dict[str, Any]],
    too_large: str,
) -> None:
    if too_large == "bytes":
        content = make_csv([order_row()]) + b"X" * MAX_FILE_BYTES
    else:
        content = make_csv([order_row(str(index)) for index in range(501)])
    statements: list[str] = []

    def observe_sql(_connection: object, _cursor: object, statement: str, *_args: object) -> None:
        statements.append(statement)

    event.listen(app.state.engine, "before_cursor_execute", observe_sql)
    try:
        response = client.post("/api/imports", files={"file": ("orders.csv", content, "text/csv")})
    finally:
        event.remove(app.state.engine, "before_cursor_execute", observe_sql)
    assert response.status_code == 413
    assert not any(statement.lstrip().upper().startswith("INSERT") for statement in statements)
    assert client.get("/api/reservations").json() == []


def test_exactly_500_rows_are_allowed(
    client: TestClient, import_equipment: list[dict[str, Any]]
) -> None:
    start = date(2027, 1, 1)
    rows = [
        order_row(
            f"ORDER-{index}",
            starts_on=(start + timedelta(days=index)).isoformat(),
            ends_on=(start + timedelta(days=index + 1)).isoformat(),
        )
        for index in range(500)
    ]
    report = import_csv(client, make_csv(rows))
    assert report["totals"] == {"total": 500, "accepted": 500, "already_imported": 0, "rejected": 0}
    assert len(client.get("/api/reservations").json()) == 500


def test_exact_byte_limit_is_allowed_and_large_fields_are_row_errors(
    client: TestClient, import_equipment: list[dict[str, Any]]
) -> None:
    base = make_csv([order_row(customer_name="")])
    content = make_csv([order_row(customer_name="X" * (MAX_FILE_BYTES - len(base)))])
    assert len(content) == MAX_FILE_BYTES
    report = import_csv(client, content)
    assert report["totals"] == {"total": 1, "accepted": 0, "already_imported": 0, "rejected": 1}


def test_fields_above_csv_default_size_limit_do_not_abort_other_rows(
    client: TestClient, import_equipment: list[dict[str, Any]]
) -> None:
    report = import_csv(
        client,
        make_csv([order_row("HUGE", customer_name="X" * 150_000), order_row("VALID-SECOND")]),
    )
    assert report["totals"] == {"total": 2, "accepted": 1, "already_imported": 0, "rejected": 1}


@pytest.mark.parametrize("kind", ["missing", "wrong_field", "json", "duplicate_file", "extra"])
def test_invalid_multipart_contract_is_422(client: TestClient, kind: str) -> None:
    file = ("orders.csv", make_csv([]), "text/csv")
    if kind == "missing":
        response = client.post("/api/imports")
    elif kind == "wrong_field":
        response = client.post("/api/imports", files={"upload": file})
    elif kind == "json":
        response = client.post("/api/imports", json={"file": "orders.csv"})
    elif kind == "duplicate_file":
        response = client.post("/api/imports", files=[("file", file), ("file", file)])
    else:
        response = client.post("/api/imports", files={"file": file}, data={"extra": "unexpected"})
    assert response.status_code == 422


def test_example_download_is_csv_with_the_exact_contract_and_fictitious_data(
    client: TestClient,
) -> None:
    response = client.get("/api/imports/example")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert ".csv" in response.headers["content-disposition"]
    rows = list(csv.reader(StringIO(response.content.decode("utf-8-sig"))))
    assert rows[0] == HEADER
    assert len(rows) > 1
    assert all(len(row) == len(HEADER) for row in rows)
    assert all(row[2].endswith(".test") for row in rows[1:])
    assert all(row[3] in {"CAM-001", "CAM-002", "AUD-001", "LGT-001"} for row in rows[1:])


def test_imported_reservations_persist_and_reimport_after_application_recreation(
    client: TestClient, import_equipment: list[dict[str, Any]], settings: Settings
) -> None:
    content = make_csv([order_row()])
    original = import_csv(client, content)["rows"][0]["reservation"]
    application = create_app(settings)
    try:
        with TestClient(application) as recreated:
            authenticate(recreated)
            report = import_csv(recreated, content)
            assert report["totals"]["already_imported"] == 1
            assert report["rows"][0]["reservation"] == original
            assert recreated.get("/api/reservations").json() == [original]
    finally:
        application.state.engine.dispose()


def test_truncated_multipart_is_rejected_before_any_reservation_is_created(
    client: TestClient, import_equipment: list[dict[str, Any]]
) -> None:
    content = (
        b'--test-boundary\r\nContent-Disposition: form-data; name="file"; filename="orders.csv"\r\n'
        b"Content-Type: text/csv\r\n\r\n" + make_csv([order_row()])
    )
    response = client.post(
        "/api/imports",
        content=content,
        headers={"Content-Type": "multipart/form-data; boundary=test-boundary"},
    )
    assert response.status_code == 422
    assert client.get("/api/reservations").json() == []


def test_file_size_is_enforced_without_a_content_length_header(
    client: TestClient, import_equipment: list[dict[str, Any]]
) -> None:
    content = (
        b'--test-boundary\r\nContent-Disposition: form-data; name="file"; filename="orders.csv"\r\n'
        b"Content-Type: text/csv\r\n\r\n"
        + make_csv([order_row()])
        + b"X" * MAX_FILE_BYTES
        + b"\r\n--test-boundary--\r\n"
    )
    request = client.build_request(
        "POST",
        "/api/imports",
        content=iter([content]),
        headers={"Content-Type": "multipart/form-data; boundary=test-boundary"},
    )
    assert "content-length" not in request.headers
    assert client.send(request).status_code == 413
    assert client.get("/api/reservations").json() == []
