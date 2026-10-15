from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from rentalab.auth.dependencies import require_admin
from rentalab.http import ErrorResponse
from rentalab.imports.csv_reader import ImportFileError
from rentalab.imports.schemas import ImportReport
from rentalab.imports.service import ImportService
from rentalab.imports.upload import read_csv_upload

router = APIRouter(
    prefix="/api/imports", tags=["Importaciones"], dependencies=[Depends(require_admin)]
)


@router.get(
    "/example",
    response_class=FileResponse,
    summary="Descargar un CSV ficticio de ejemplo",
    responses={200: {"content": {"text/csv": {"schema": {"type": "string", "format": "binary"}}}}},
)
def download_example() -> FileResponse:
    return FileResponse(
        Path(__file__).with_name("example.csv"),
        media_type="text/csv",
        filename="rentalab-pedidos-ejemplo.csv",
    )


@router.post(
    "",
    response_model=ImportReport,
    summary="Importar solicitudes de reserva desde CSV",
    description=(
        "UTF-8 con o sin BOM, comas, hasta 1 MiB y 500 filas. Transacción independiente por fila."
    ),
    responses={
        413: {
            "model": ErrorResponse,
            "description": "Tamaño o cantidad de filas excedidos; sin inserciones",
        },
        422: {
            "model": ErrorResponse,
            "description": "Multipart, UTF-8, cabecera o estructura CSV inválidos",
        },
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["file"],
                        "additionalProperties": False,
                        "properties": {
                            "file": {
                                "type": "string",
                                "format": "binary",
                                "description": "CSV UTF-8, máximo 1048576 bytes",
                            }
                        },
                    }
                }
            },
        }
    },
)
async def import_reservations(request: Request) -> ImportReport:
    try:
        content = await read_csv_upload(request)
        service = ImportService(request.app.state.session_factory)
        return await run_in_threadpool(service.run, content)
    except ImportFileError as error:
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error
