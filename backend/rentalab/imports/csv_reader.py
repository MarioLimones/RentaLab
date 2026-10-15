import csv
from dataclasses import dataclass
from io import StringIO

MAX_FILE_BYTES = 1_048_576
MAX_DATA_ROWS = 500
CSV_HEADER = (
    "external_reference",
    "customer_name",
    "customer_email",
    "equipment_code",
    "starts_on",
    "ends_on",
)
# Set once: a long field within the file limit is a row error, not a parser failure.
csv.field_size_limit(MAX_FILE_BYTES)


class ImportFileError(Exception):
    def __init__(self, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class CsvRow:
    line: int
    values: list[str]


def parse_csv(content: bytes) -> list[CsvRow]:
    if len(content) > MAX_FILE_BYTES:
        raise ImportFileError("El archivo supera el límite de 1 MiB", 413)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ImportFileError("El archivo debe estar codificado en UTF-8") from error
    reader = csv.reader(StringIO(text, newline=""), delimiter=",", strict=True)
    try:
        if tuple(next(reader, [])) != CSV_HEADER:
            raise ImportFileError("La cabecera debe ser exactamente: " + ",".join(CSV_HEADER))
        rows: list[CsvRow] = []
        while True:
            line = reader.line_num + 1
            values = next(reader, None)
            if values is None:
                break
            rows.append(CsvRow(line=line, values=values))
            if len(rows) > MAX_DATA_ROWS:
                raise ImportFileError("El archivo supera el límite de 500 filas de datos", 413)
        return rows
    except csv.Error as error:
        raise ImportFileError("El CSV contiene comillas o estructura incorrectas") from error
