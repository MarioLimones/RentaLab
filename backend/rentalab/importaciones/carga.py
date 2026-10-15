from fastapi import Request
from python_multipart import MultipartParser
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import parse_options_header

from rentalab.importaciones.lector_csv import MAXIMO_ARCHIVO_BYTES, ImportacionArchivoError

MAXIMO_MULTIPART_SOBRECARGA = 65_536


class CsvCarga:
    """Recibe un archivo en memoria sin crear temporales ni confiar en su nombre."""

    def __init__(instancia) -> None:
        instancia.contenido = bytearray()
        instancia.partes = 0
        instancia.completada = False
        instancia.parte_terminado = False
        instancia.cabecera_campo = bytearray()
        instancia.cabecera_valor = bytearray()
        instancia.cabecera_bytes = 0
        instancia.contenido_disposicion: bytes | None = None

    def on_part_begin(instancia) -> None:
        instancia.partes += 1
        if instancia.partes != 1:
            raise ImportacionArchivoError("Envía únicamente un archivo en el campo file")

    def on_header_field(instancia, datos: bytes, arranque: int, fin: int) -> None:
        instancia._contar_cabecera(fin - arranque)
        instancia.cabecera_campo.extend(datos[arranque:fin])

    def on_header_value(instancia, datos: bytes, arranque: int, fin: int) -> None:
        instancia._contar_cabecera(fin - arranque)
        instancia.cabecera_valor.extend(datos[arranque:fin])

    def _contar_cabecera(instancia, tamano: int) -> None:
        instancia.cabecera_bytes += tamano
        if instancia.cabecera_bytes > MAXIMO_MULTIPART_SOBRECARGA:
            raise ImportacionArchivoError(
                "Las cabeceras multipart superan el límite permitido", 413
            )

    def on_header_end(instancia) -> None:
        if instancia.cabecera_campo.lower() == b"content-disposition":
            if instancia.contenido_disposicion is not None:
                raise ImportacionArchivoError("La cabecera multipart está duplicada")
            instancia.contenido_disposicion = bytes(instancia.cabecera_valor)
        instancia.cabecera_campo.clear()
        instancia.cabecera_valor.clear()

    def on_headers_finished(instancia) -> None:
        disposicion, opciones = parse_options_header(instancia.contenido_disposicion)
        if (
            disposicion.lower() != b"form-data"
            or opciones.get(b"name") != b"file"
            or b"filename" not in opciones
        ):
            raise ImportacionArchivoError("Envía un archivo en el campo multipart file")

    def on_part_data(instancia, datos: bytes, arranque: int, fin: int) -> None:
        if len(instancia.contenido) + fin - arranque > MAXIMO_ARCHIVO_BYTES:
            raise ImportacionArchivoError("El archivo supera el límite de 1 MiB", 413)
        instancia.contenido.extend(datos[arranque:fin])

    def on_part_end(instancia) -> None:
        instancia.parte_terminado = True

    def on_end(instancia) -> None:
        instancia.completada = True


async def lectura_csv_carga(solicitud: Request) -> bytes:
    contenido_tipo, opciones = parse_options_header(solicitud.headers.get("content-type"))
    limite = opciones.get(b"boundary")
    if contenido_tipo.lower() != b"multipart/form-data" or not limite or len(limite) > 70:
        raise ImportacionArchivoError(
            "Envía un multipart válido con un único archivo en el campo file"
        )
    maximo_cuerpo = MAXIMO_ARCHIVO_BYTES + MAXIMO_MULTIPART_SOBRECARGA
    contenido_longitud = solicitud.headers.get("content-length")
    if contenido_longitud is not None:
        try:
            longitud = int(contenido_longitud)
        except ValueError as error:
            raise ImportacionArchivoError("El tamaño de la petición no es válido") from error
        if longitud < 0:
            raise ImportacionArchivoError("El tamaño de la petición no es válido")
        if longitud > maximo_cuerpo:
            raise ImportacionArchivoError("La petición supera el límite permitido", 413)
    carga = CsvCarga()
    analizador = MultipartParser(
        limite,
        {
            nombre: getattr(carga, nombre)
            for nombre in (
                "on_part_begin",
                "on_header_field",
                "on_header_value",
                "on_header_end",
                "on_headers_finished",
                "on_part_data",
                "on_part_end",
                "on_end",
            )
        },
    )
    recibido = 0
    try:
        async for fragmento in solicitud.stream():
            recibido += len(fragmento)
            if recibido > maximo_cuerpo:
                raise ImportacionArchivoError("La petición supera el límite permitido", 413)
            analizador.write(fragmento)
        analizador.finalize()
    except MultipartParseError as error:
        raise ImportacionArchivoError("El contenido multipart no es válido") from error
    if not carga.completada or not carga.parte_terminado or carga.partes != 1:
        raise ImportacionArchivoError(
            "El contenido multipart está incompleto o no contiene el archivo"
        )
    return bytes(carga.contenido)
