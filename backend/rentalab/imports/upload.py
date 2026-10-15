from fastapi import Request
from python_multipart import MultipartParser
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import parse_options_header

from rentalab.imports.csv_reader import MAX_FILE_BYTES, ImportFileError

MAX_MULTIPART_OVERHEAD = 65_536


class CsvUpload:
    """Receive one file in memory; never create a spooled file or trust its filename."""

    def __init__(self) -> None:
        self.content = bytearray()
        self.parts = 0
        self.completed = False
        self.part_finished = False
        self.header_field = bytearray()
        self.header_value = bytearray()
        self.header_bytes = 0
        self.content_disposition: bytes | None = None

    def on_part_begin(self) -> None:
        self.parts += 1
        if self.parts != 1:
            raise ImportFileError("Envía únicamente un archivo en el campo file")

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._count_header(end - start)
        self.header_field.extend(data[start:end])

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._count_header(end - start)
        self.header_value.extend(data[start:end])

    def _count_header(self, size: int) -> None:
        self.header_bytes += size
        if self.header_bytes > MAX_MULTIPART_OVERHEAD:
            raise ImportFileError("Las cabeceras multipart superan el límite permitido", 413)

    def on_header_end(self) -> None:
        if self.header_field.lower() == b"content-disposition":
            if self.content_disposition is not None:
                raise ImportFileError("La cabecera multipart está duplicada")
            self.content_disposition = bytes(self.header_value)
        self.header_field.clear()
        self.header_value.clear()

    def on_headers_finished(self) -> None:
        disposition, options = parse_options_header(self.content_disposition)
        if (
            disposition.lower() != b"form-data"
            or options.get(b"name") != b"file"
            or b"filename" not in options
        ):
            raise ImportFileError("Envía un archivo en el campo multipart file")

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if len(self.content) + end - start > MAX_FILE_BYTES:
            raise ImportFileError("El archivo supera el límite de 1 MiB", 413)
        self.content.extend(data[start:end])

    def on_part_end(self) -> None:
        self.part_finished = True

    def on_end(self) -> None:
        self.completed = True


async def read_csv_upload(request: Request) -> bytes:
    content_type, options = parse_options_header(request.headers.get("content-type"))
    boundary = options.get(b"boundary")
    if content_type.lower() != b"multipart/form-data" or not boundary or len(boundary) > 70:
        raise ImportFileError("Envía un multipart válido con un único archivo en el campo file")
    max_body = MAX_FILE_BYTES + MAX_MULTIPART_OVERHEAD
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            length = int(content_length)
        except ValueError as error:
            raise ImportFileError("El tamaño de la petición no es válido") from error
        if length < 0:
            raise ImportFileError("El tamaño de la petición no es válido")
        if length > max_body:
            raise ImportFileError("La petición supera el límite permitido", 413)
    upload = CsvUpload()
    parser = MultipartParser(
        boundary,
        {
            name: getattr(upload, name)
            for name in (
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
    received = 0
    try:
        async for chunk in request.stream():
            received += len(chunk)
            if received > max_body:
                raise ImportFileError("La petición supera el límite permitido", 413)
            parser.write(chunk)
        parser.finalize()
    except MultipartParseError as error:
        raise ImportFileError("El contenido multipart no es válido") from error
    if not upload.completed or not upload.part_finished or upload.parts != 1:
        raise ImportFileError("El contenido multipart está incompleto o no contiene el archivo")
    return bytes(upload.content)
