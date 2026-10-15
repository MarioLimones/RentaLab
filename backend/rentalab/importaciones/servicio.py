from pydantic import ValidationError
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from rentalab.base_datos import es_sqlite_ocupado
from rentalab.compatibilidad import alias_json, nombre_interno
from rentalab.equipo.servicio import EquipoNoEncontrado
from rentalab.importaciones.esquemas import (
    ImportacionFilaResultado,
    ImportacionInforme,
    ImportacionTotales,
)
from rentalab.importaciones.lector_csv import CsvFila, analizar_csv
from rentalab.reservas.esquemas import LecturaReserva, ReservaPorCodigo
from rentalab.reservas.repositorio import RepositorioReservas
from rentalab.reservas.servicio import ConflictoReserva, ServicioReservas

CAMPO_MENSAJES = {
    "external_reference": "La referencia externa es obligatoria: hasta 120 caracteres válidos",
    "customer_name": "El nombre del cliente debe tener entre 1 y 120 caracteres válidos",
    "customer_email": "El correo del cliente no es válido",
    "equipment_code": "El código del equipo no es válido",
    "start_date": "starts_on debe ser una fecha ISO YYYY-MM-DD válida",
    "end_date": "ends_on debe ser una fecha ISO YYYY-MM-DD válida",
}


class ImportacionServicio:
    def __init__(instancia, fabrica_sesiones: sessionmaker[Session]) -> None:
        instancia.fabrica_sesiones = fabrica_sesiones

    def ejecutar(instancia, contenido: bytes) -> ImportacionInforme:
        filas = analizar_csv(
            contenido
        )  # Completa la validación previa antes de la primera escritura en la base.
        resultados = [instancia._procesar(fila) for fila in filas]
        totales = ImportacionTotales(total=len(resultados))
        for resultado in resultados:
            campo = nombre_interno(resultado.estado)
            setattr(totales, campo, getattr(totales, campo) + 1)
        return ImportacionInforme(totales=totales, filas=resultados)

    def _procesar(instancia, fila: CsvFila) -> ImportacionFilaResultado:
        referencia = (fila.valores[0].strip() or None) if fila.valores else None
        resultado = ImportacionFilaResultado(
            linea=fila.linea,
            referencia_externa=referencia,
            estado="rejected",
            reserva=None,
            mensaje="La fila debe contener exactamente seis columnas",
        )
        if len(fila.valores) != 6:
            return resultado
        try:
            datos = ReservaPorCodigo(
                referencia_externa=fila.valores[0],
                nombre_cliente=fila.valores[1],
                correo_cliente=fila.valores[2],
                codigo_equipo=fila.valores[3],
                fecha_inicio=fila.valores[4],
                fecha_fin=fila.valores[5],
            )
        except ValidationError as error:
            mensajes = [
                CAMPO_MENSAJES.get(
                    alias_json(str(elemento["loc"][0])) if elemento["loc"] else "",
                    "ends_on debe ser posterior a starts_on",
                )
                for elemento in error.errors(include_input=False, include_url=False)
            ]
            resultado.mensaje = ". ".join(dict.fromkeys(mensajes)) + "."
            return resultado
        try:
            with instancia.fabrica_sesiones() as sesion:
                desenlace = ServicioReservas(RepositorioReservas(sesion)).crear_desde_codigo(datos)
                resultado.reserva = LecturaReserva.model_validate(desenlace.reserva)
                resultado.estado = "accepted" if desenlace.creados else "already_imported"
                resultado.referencia_externa = datos.referencia_externa
                resultado.mensaje = (
                    "Reserva creada."
                    if desenlace.creados
                    else "La reserva ya estaba importada; se conserva sin cambios."
                )
        except EquipoNoEncontrado:
            resultado.mensaje = "El equipo indicado no existe."
        except ConflictoReserva as error:
            resultado.mensaje = str(error)
        except OperationalError as error:
            resultado.mensaje = (
                "La base de datos está ocupada; vuelve a importar esta fila."
                if es_sqlite_ocupado(error)
                else "No se pudo procesar esta fila; inténtalo de nuevo."
            )
        except SQLAlchemyError:
            resultado.mensaje = "No se pudo procesar esta fila; inténtalo de nuevo."
        return resultado
