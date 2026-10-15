from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from rentalab.autenticacion.dependencias import exigir_administrador
from rentalab.importaciones.carga import lectura_csv_carga
from rentalab.importaciones.esquemas import ImportacionInforme
from rentalab.importaciones.lector_csv import ImportacionArchivoError
from rentalab.importaciones.servicio import ImportacionServicio
from rentalab.respuestas_http import RespuestaError

enrutador = APIRouter(
    prefix="/api/imports", tags=["Importaciones"], dependencies=[Depends(exigir_administrador)]
)


@enrutador.get(
    "/example",
    response_class=FileResponse,
    summary="Descargar un CSV ficticio de ejemplo",
    responses={200: {"content": {"text/csv": {"schema": {"type": "string", "format": "binary"}}}}},
)
def descargar_ejemplo() -> FileResponse:
    return FileResponse(
        Path(__file__).with_name("example.csv"),
        media_type="text/csv",
        filename="rentalab-pedidos-ejemplo.csv",
    )


@enrutador.post(
    "",
    response_model=ImportacionInforme,
    summary="Importar solicitudes de reserva desde CSV",
    description=(
        "UTF-8 con o sin BOM, comas, hasta 1 MiB y 500 filas. Transacción independiente por fila."
    ),
    responses={
        413: {
            "model": RespuestaError,
            "description": "Tamaño o cantidad de filas excedidos; sin inserciones",
        },
        422: {
            "model": RespuestaError,
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
async def importacion_reservas(solicitud: Request) -> ImportacionInforme:
    try:
        contenido = await lectura_csv_carga(solicitud)
        servicio = ImportacionServicio(solicitud.app.state.fabrica_sesiones)
        return await run_in_threadpool(servicio.ejecutar, contenido)
    except ImportacionArchivoError as error:
        raise HTTPException(status_code=error.estado_codigo, detail=str(error)) from error
