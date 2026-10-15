# Reservas y disponibilidad: contrato de la API

Contrato de gestión administrativa. Para operaciones propias del cliente utiliza [la API `/api/me` de fase C](OPERACIONES_CLIENTE.md), con identidad de sesión y plazos Madrid; sus esquemas y permisos son distintos de las rutas descritas aquí.

La fase 2 añade reservas de unidades físicas y la fase 3 conecta las [incidencias](INCIDENCIAS.md) con su disponibilidad. La fase 5 incorpora la [interfaz React](INTERFAZ.md) de filtros, disponibilidad, creación, detalle y cancelación. Desde la fase 6, estas rutas requieren [sesión y CSRF](ACCESO.md). Todas las reglas y la validación definitiva se ejecutan en Python.

Para los ejemplos PowerShell, inicia primero una sesión y define `Invoke-RentaLab` según [ACCESO.md](ACCESO.md#api-desde-powershell); conserva la cookie y el token CSRF en esa terminal.
## Recursos y errores

| Método | Ruta | Resultado |
| --- | --- | --- |
| POST | `/api/reservations` | 201, reserva confirmada y cabecera `Location` |
| GET | `/api/reservations` | 200, lista ordenada por `start_date` y después `id` |
| GET | `/api/reservations/{reservation_id}` | 200, reserva actual, también si está cancelada |
| POST | `/api/reservations/{reservation_id}/cancel` | 200, reserva cancelada; repetir conserva la misma respuesta |
| GET | `/api/equipment/{equipment_id}/availability` | 200, disponibilidad calculada para un intervalo |

La cancelación no requiere cuerpo y sólo cambia `status`. No existe borrado, reactivación ni edición de fechas en esta fase. Se permite cancelar una reserva de un equipo que se haya desactivado después de confirmarla.

| HTTP | Significado |
| --- | --- |
| 404 | Equipo o reserva inexistente; también al filtrar por un equipo inexistente |
| 409 | Equipo inactivo, incidencia bloqueante sin resolver, solapamiento confirmado o referencia externa repetida |
| 422 | Campos inválidos, desconocidos, identificador fuera de rango, intervalo incompleto o fechas inválidas |
| 503 | Espera de un bloqueo temporal de SQLite agotada; se puede reintentar |

Los errores 404/409/503 tienen forma `{"detail":"Descripción del error"}`. Los 422 siguen el formato de validación FastAPI, con un array `detail`. Un bloqueo SQLite agotado devuelve 503 y `Retry-After: 1`, distinguiéndolo de fechas ocupadas. El cliente puede ofrecer un reintento; no se reenvían altas automáticamente. Un conflicto de negocio devuelve 409 sin esa cabecera.

## Crear y leer una reserva

```json
{
  "equipment_id": 1,
  "customer_name": "Cliente de ejemplo",
  "customer_email": "cliente@example.test",
  "start_date": "2026-11-10",
  "end_date": "2026-11-12",
  "external_reference": "DEMO-ORDER-001"
}
```

| Campo de entrada | Contrato |
| --- | --- |
| `equipment_id` | Entero JSON entre 1 y 9223372036854775807; equipo existente y activo |
| `customer_name` | Texto obligatorio, 1–120 caracteres después de recortar espacios; sin NUL |
| `customer_email` | Texto obligatorio, hasta 254 caracteres; validación sintáctica y normalización de correo |
| `start_date` | Fecha ISO exacta `YYYY-MM-DD`, incluida |
| `end_date` | Fecha ISO exacta `YYYY-MM-DD`, excluida y posterior a `start_date` |
| `external_reference` | Opcional, `null` por defecto; texto de 1–120 caracteres recortado y sin NUL |

El correo se valida sin consultas DNS ni envío de mensajes. Se admite el dominio ficticio `.test`. No se aceptan números de época, fechas con hora, formatos locales ni espacios alrededor de las fechas. No se impone una regla de fecha futura: esta demostración también admite ejemplos históricos.

La referencia externa es única en SQLite, distingue mayúsculas y minúsculas y sigue ocupada después de cancelar. Se permiten varias reservas con referencia `null`. Una referencia vacía no equivale a `null`: devuelve 422. El alta manual rechaza referencias repetidas con 409. Desde la fase 4, la [importación CSV](IMPORTACIONES.md) reconoce una referencia con datos normalizados idénticos sin crear otra reserva.

El servidor añade `id` y `status`. Crear siempre confirma; enviar `id` o `status` en el cuerpo devuelve 422. Ejemplo de respuesta 201 con `Location: /api/reservations/1`:

```json
{
  "start_date": "2026-11-10",
  "end_date": "2026-11-12",
  "equipment_id": 1,
  "customer_name": "Cliente de ejemplo",
  "customer_email": "cliente@example.test",
  "external_reference": "DEMO-ORDER-001",
  "id": 1,
  "status": "confirmed"
}
```

Los únicos estados son `confirmed` y `cancelled`. Cancelar conserva identificador, equipo, cliente, fechas y referencia; no libera la referencia externa. Una cancelada ya no bloquea el intervalo.

## Filtros de listado

`GET /api/reservations` devuelve todas las reservas, incluidas las canceladas. Los filtros opcionales se combinan:

- `equipment_id`: unidad física concreta.
- `status`: `confirmed` o `cancelled`.
- `start_date` y `end_date`: se envían juntos; seleccionan las reservas que **solapan** ese intervalo, con independencia del estado si no se filtra también por él.

Por ejemplo, `GET /api/reservations?equipment_id=1&status=confirmed&start_date=2026-11-11&end_date=2026-11-20` incluye una reserva del 10 al 12. Una reserva que empieza exactamente el 20 no coincide con ese filtro. No hay paginación en esta fase.

## Disponibilidad e intervalos

La consulta exige ambas fechas:

```text
GET /api/equipment/1/availability?start_date=2026-11-10&end_date=2026-11-12
```

Respuesta si la reserva anterior está confirmada:

```json
{
  "start_date": "2026-11-10",
  "end_date": "2026-11-12",
  "equipment_id": 1,
  "available": false,
  "reason": "reservation_overlap",
  "conflicting_reservation_ids": [1]
}
```

`available` es un resultado calculado; no existe una columna que lo guarde. Si está libre, vale `true`, `reason` es `null` y los identificadores son `[]`. La prioridad de los motivos es `equipment_inactive`, después `blocking_incident` y después `reservation_overlap`. Los dos primeros devuelven identificadores de reservas `[]`; sólo el último incluye las reservas solapadas. La consulta no expone nombres ni correos de clientes. Un equipo inexistente devuelve 404, no una disponibilidad negativa.

La consulta y la creación llaman a `ReservationService.availability`, que delega en el servicio compartido `AvailabilityService.check` de `rentalab/availability.py`. La primera es informativa: `available=true` no retiene material. Crear vuelve a comprobar las reglas dentro de una transacción. La importación CSV utiliza `ReservationService.create_from_code` y el mismo método de creación comprobada que el alta manual, respetando esa política y su transacción.

Para una reserva existente y otra solicitada del mismo equipo hay solapamiento si:

```text
existing.start_date < requested.end_date
AND existing.end_date > requested.start_date
```

Sólo se consideran reservas `confirmed`. `[10,12)` ocupa los días 10 y 11: `[12,14)` es adyacente y se permite; `[11,13)` ocupa también el 11 y se rechaza. Dos equipos distintos pueden reservarse en las mismas fechas.

## Atomicidad y bloqueos en SQLite

Cada creación y cancelación recibe una sesión nueva. `ReservationRepository.write_transaction` utiliza `database.immediate_transaction`, compartida con incidencias: abre `Session.begin()` y ejecuta `BEGIN IMMEDIATE` **antes de consultar** el equipo, sus incidencias, reservas o referencia externa. Después comprueba las reglas y confirma la escritura dentro de esa transacción. Ningún escritor puede intercalar otra confirmación ni abrir una incidencia entre la consulta y el alta.

SQLite admite un escritor simultáneo para toda la base. La segunda conexión espera; cuando obtiene el turno, sus consultas ven la confirmación de la primera y rechazan el solapamiento. Esto también serializa brevemente escrituras de equipos diferentes; no añade un conflicto de negocio entre ellos. No se usa `SELECT FOR UPDATE` ni un cerrojo de Python, que no resolverían este caso de SQLite entre procesos. La política de transacciones está respaldada por la [documentación de SQLite](https://www.sqlite.org/lang_transaction.html#deferred_immediate_and_exclusive_transactions).

El motor mantiene el modo de transacción heredado de `sqlite3` en Python 3.12: SQLAlchemy inicia la unidad de trabajo lógica y `BEGIN IMMEDIATE` inicia expresamente la transacción SQLite. No debe añadirse un `BEGIN` global automático o cambiar `autocommit` sin adaptar y repetir estas pruebas. Véase [SQLAlchemy y el modo heredado de SQLite](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#legacy-transaction-mode-with-the-sqlite3-driver).

`RENTALAB_SQLITE_BUSY_TIMEOUT_MS` controla la espera (5000 ms por defecto; 0–60000). Al agotar un bloqueo `SQLITE_BUSY` o `SQLITE_LOCKED`, incluso durante `COMMIT`, se revierte la operación y se devuelve 503 con `Retry-After: 1`. No hay bucles de reintentos ni reenvíos automáticos de altas: cada intento vuelve a adquirir el bloqueo y comprobar el estado. Otros errores de persistencia no se convierten en falsos conflictos de bloqueo. En las importaciones, el mismo rollback rechaza sólo esa fila con un mensaje de reintento y permite continuar con las demás; el informe completo mantiene HTTP 200.

La migración `0003_reservations` añade la tabla, su clave foránea, estado y rango válidos, referencia única e índice de consulta. Conserva el catálogo existente y no añade reservas de demostración al arrancar.

## Ejemplo PowerShell

Con backend arrancado, este ejemplo crea una reserva ficticia y la cancela dos veces. Usa una referencia nueva cada vez para no chocar con el historial conservado:

```powershell
$baseUrl = 'http://127.0.0.1:8000'
$equipment = Invoke-RentaLab "$baseUrl/api/equipment?active=true"
$equipmentId = $equipment[0].id
$body = @{
    equipment_id = $equipmentId
    customer_name = 'Cliente de ejemplo'
    customer_email = 'cliente@example.test'
    start_date = '2026-11-10'
    end_date = '2026-11-12'
    external_reference = "DEMO-$([guid]::NewGuid())"
} | ConvertTo-Json

Invoke-RentaLab "$baseUrl/api/equipment/$equipmentId/availability?start_date=2026-11-10&end_date=2026-11-12"
$reservation = Invoke-RentaLab "$baseUrl/api/reservations" -Method Post -ContentType 'application/json; charset=utf-8' -Body $body
Invoke-RentaLab "$baseUrl/api/reservations?equipment_id=$equipmentId&status=confirmed"
Invoke-RentaLab "$baseUrl/api/reservations/$($reservation.id)"
Invoke-RentaLab "$baseUrl/api/reservations/$($reservation.id)/cancel" -Method Post
Invoke-RentaLab "$baseUrl/api/reservations/$($reservation.id)/cancel" -Method Post
```

El ejemplo requiere un equipo activo y un intervalo libre. Si hay una reserva confirmada en esas fechas, la creación devuelve 409; las reglas no se omiten para ejecutar el ejemplo.

## Consumo desde React

`frontend/src/api/client.ts` expone `Reservation`, `ReservationInput`, `ReservationFilters`, `DateRange` y `Availability`, además de estos métodos:

```typescript
api.listReservations({ equipment_id: 1, status: 'confirmed' });
api.getReservation(1);
api.createReservation({
  equipment_id: 1,
  customer_name: 'Cliente de ejemplo',
  customer_email: 'cliente@example.test',
  start_date: '2026-11-10',
  end_date: '2026-11-12',
});
api.cancelReservation(1);
api.getEquipmentAvailability(1, {
  start_date: '2026-11-10', end_date: '2026-11-12',
});
```

Todos usan `/api` relativo y validan la estructura de las respuestas recibidas. React ayuda a introducir los datos, pero el servidor decide la validez definitiva del intervalo, la actividad y los solapamientos. La consulta visual indica equipo y rango, y no retiene material. El estado de conexión se conserva como componente del panel.
