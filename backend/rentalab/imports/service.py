from pydantic import ValidationError
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from rentalab.database import is_sqlite_busy
from rentalab.equipment.service import EquipmentNotFound
from rentalab.imports.csv_reader import CsvRow, parse_csv
from rentalab.imports.schemas import ImportReport, ImportRowResult, ImportTotals
from rentalab.reservations.repository import ReservationRepository
from rentalab.reservations.schemas import ReservationByCode, ReservationRead
from rentalab.reservations.service import ReservationConflict, ReservationService

FIELD_MESSAGES = {
    "external_reference": "La referencia externa es obligatoria: hasta 120 caracteres válidos",
    "customer_name": "El nombre del cliente debe tener entre 1 y 120 caracteres válidos",
    "customer_email": "El correo del cliente no es válido",
    "equipment_code": "El código del equipo no es válido",
    "start_date": "starts_on debe ser una fecha ISO YYYY-MM-DD válida",
    "end_date": "ends_on debe ser una fecha ISO YYYY-MM-DD válida",
}


class ImportService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def run(self, content: bytes) -> ImportReport:
        rows = parse_csv(content)  # Complete preflight before the first database write.
        results = [self._process(row) for row in rows]
        totals = ImportTotals(total=len(results))
        for result in results:
            setattr(totals, result.status, getattr(totals, result.status) + 1)
        return ImportReport(totals=totals, rows=results)

    def _process(self, row: CsvRow) -> ImportRowResult:
        reference = (row.values[0].strip() or None) if row.values else None
        result = ImportRowResult(
            line=row.line,
            external_reference=reference,
            status="rejected",
            reservation=None,
            message="La fila debe contener exactamente seis columnas",
        )
        if len(row.values) != 6:
            return result
        try:
            data = ReservationByCode(
                external_reference=row.values[0],
                customer_name=row.values[1],
                customer_email=row.values[2],
                equipment_code=row.values[3],
                start_date=row.values[4],
                end_date=row.values[5],
            )
        except ValidationError as error:
            messages = [
                FIELD_MESSAGES.get(
                    str(item["loc"][0]) if item["loc"] else "",
                    "ends_on debe ser posterior a starts_on",
                )
                for item in error.errors(include_input=False, include_url=False)
            ]
            result.message = ". ".join(dict.fromkeys(messages)) + "."
            return result
        try:
            with self.session_factory() as session:
                outcome = ReservationService(ReservationRepository(session)).create_from_code(data)
                result.reservation = ReservationRead.model_validate(outcome.reservation)
                result.status = "accepted" if outcome.created else "already_imported"
                result.external_reference = data.external_reference
                result.message = (
                    "Reserva creada."
                    if outcome.created
                    else "La reserva ya estaba importada; se conserva sin cambios."
                )
        except EquipmentNotFound:
            result.message = "El equipo indicado no existe."
        except ReservationConflict as error:
            result.message = str(error)
        except OperationalError as error:
            result.message = (
                "La base de datos está ocupada; vuelve a importar esta fila."
                if is_sqlite_busy(error)
                else "No se pudo procesar esta fila; inténtalo de nuevo."
            )
        except SQLAlchemyError:
            result.message = "No se pudo procesar esta fila; inténtalo de nuevo."
        return result
