import csv
from dataclasses import dataclass
from io import StringIO

MAXIMO_ARCHIVO_BYTES = 1_048_576
MAXIMO_DATOS_FILAS = 500
CSV_CABECERA = (
    "external_reference",
    "customer_name",
    "customer_email",
    "equipment_code",
    "starts_on",
    "ends_on",
)
# Se configura una vez: un campo largo es un error de fila, no del analizador completo.
csv.field_size_limit(MAXIMO_ARCHIVO_BYTES)


class ImportacionArchivoError(Exception):
    def __init__(instancia, mensaje: str, estado_codigo: int = 422) -> None:
        super().__init__(mensaje)
        instancia.estado_codigo = estado_codigo


@dataclass(frozen=True)
class CsvFila:
    linea: int
    valores: list[str]


def analizar_csv(contenido: bytes) -> list[CsvFila]:
    if len(contenido) > MAXIMO_ARCHIVO_BYTES:
        raise ImportacionArchivoError("El archivo supera el límite de 1 MiB", 413)
    try:
        texto = contenido.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ImportacionArchivoError("El archivo debe estar codificado en UTF-8") from error
    lector = csv.reader(StringIO(texto, newline=""), delimiter=",", strict=True)
    try:
        if tuple(next(lector, [])) != CSV_CABECERA:
            raise ImportacionArchivoError(
                "La cabecera debe ser exactamente: " + ",".join(CSV_CABECERA)
            )
        filas: list[CsvFila] = []
        while True:
            linea = lector.line_num + 1
            valores = next(lector, None)
            if valores is None:
                break
            filas.append(CsvFila(linea=linea, valores=valores))
            if len(filas) > MAXIMO_DATOS_FILAS:
                raise ImportacionArchivoError(
                    "El archivo supera el límite de 500 filas de datos", 413
                )
        return filas
    except csv.Error as error:
        raise ImportacionArchivoError(
            "El CSV contiene comillas o estructura incorrectas"
        ) from error
