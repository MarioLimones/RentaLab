# Incidencias conectadas con las reservas

Contrato de gestión administrativa. La [fase C](OPERACIONES_CLIENTE.md) añade avisos desde reservas propias bajo `/api/me`, respuesta pública separada y `PATCH /api/incidents/{id}` para prioridad, bloqueo y comunicación. Las notas y `resolution` permanecen internas; el detalle administrativo no es accesible con rol cliente.

Una incidencia pertenece a una unidad física. Su prioridad organiza el trabajo; el campo `blocking` determina si impide nuevas reservas mientras esté `open` o `in_progress`. Las incidencias resueltas permanecen como historial.

Para los ejemplos PowerShell, inicia primero una sesión y define `Invoke-RentaLab` según [ACCESO.md](ACCESO.md#api-desde-powershell); conserva la cookie y el token CSRF en esa terminal.
## API

| Método | Ruta | Resultado |
| --- | --- | --- |
| POST | `/api/incidents` | 201, incidencia abierta y cabecera `Location` |
| GET | `/api/incidents` | 200, lista ordenada por identificador, incluidas las resueltas |
| GET | `/api/incidents/{incident_id}` | 200, incidencia y aviso actual sobre reservas |
| PATCH | `/api/incidents/{incident_id}/status` | 200, transición válida y explicación de resolución |

Filtros combinables del listado: `equipment_id`, `status`, `priority` y `blocking=true/false`. Filtrar por un equipo inexistente devuelve 404. No hay borrado, reapertura ni edición de los demás campos en esta fase.

Errores: 404 para equipo o incidencia inexistentes; 409 para una transición inválida; 422 para datos inválidos; 503 para un bloqueo SQLite agotado. El bloqueo agotado incluye `Retry-After: 1` y revierte la operación. Los errores conservan el formato de la API: texto en `detail` para 404/409/503 y detalles de validación FastAPI para 422.

## Crear

```json
{
  "equipment_id": 1,
  "title": "Conector de audio pendiente de revisión",
  "description": "La señal se interrumpe al mover el conector.",
  "priority": "high",
  "blocking": true
}
```

| Campo | Contrato |
| --- | --- |
| `equipment_id` | Entero JSON entre 1 y 9223372036854775807; el equipo debe existir |
| `title` | Obligatorio, 1–160 caracteres recortados y sin NUL |
| `description` | Hasta 2000 caracteres recortados y sin NUL; `""` por defecto |
| `priority` | `low`, `medium` o `high`; `medium` por defecto |
| `blocking` | Booleano real; `false` por defecto |

El servidor asigna `status="open"` y `resolution=""`. Enviar esos campos al crear devuelve 422. Se permiten incidencias de equipos inactivos: registrar un problema no exige que el material pueda reservarse. Una prioridad alta no implica bloqueo; debe indicarse `blocking=true`.

Ejemplo de respuesta con una reserva ya confirmada:

```json
{
  "equipment_id": 1,
  "title": "Conector de audio pendiente de revisión",
  "description": "La señal se interrumpe al mover el conector.",
  "priority": "high",
  "blocking": true,
  "id": 1,
  "status": "open",
  "resolution": "",
  "confirmed_reservation_ids": [7],
  "warning": "El equipo tiene reservas confirmadas. La incidencia no las cancela ni las modifica."
}
```

`confirmed_reservation_ids` y `warning` se calculan para la respuesta; no son columnas. El aviso considera **todas** las reservas actualmente `confirmed` de ese equipo, incluidas fechas pasadas o futuras. Excluye las canceladas y no expone nombres ni correos. Si no hay confirmadas, devuelve `[]` y `null`.

El aviso se devuelve también para incidencias no bloqueantes. Las consultas y cambios de estado lo actualizan según las reservas actuales, incluso cuando la incidencia ya está resuelta. Registrar, avanzar o resolver una incidencia no cambia ningún dato de las reservas.

## Estados y resolución

| Estado actual | Destino permitido | Resolución |
| --- | --- | --- |
| `open` | `in_progress` | Omitir o enviar `null` |
| `open` | `resolved` | Explicación no vacía |
| `in_progress` | `resolved` | Explicación no vacía |
| `resolved` | Ninguno | Se conserva el historial |

Ejemplo para iniciar el trabajo:

```json
{"status":"in_progress"}
```

Ejemplo para resolver:

```json
{"status":"resolved","resolution":"Conector sustituido y comprobado en taller ficticio."}
```

La explicación se recorta, admite hasta 2000 caracteres y rechaza NUL. Omitirla, enviar `null`, `""` o sólo espacios al resolver devuelve 422. En otro destino, enviar una explicación, incluso `""`, también devuelve 422. Un estado desconocido es un dato inválido (422).

Con un cuerpo válido, repetir el estado actual, retroceder o reabrir devuelve 409 y conserva la incidencia. El cambio de estado no es idempotente; la cancelación de reservas mantiene su contrato idempotente independiente. Una incidencia resuelta no admite reemplazar su explicación.

## Disponibilidad compartida

`rentalab/availability.py` contiene `AvailabilityService.check`. Tanto `GET /api/equipment/{id}/availability` como `ReservationService.create` pasan por esa política. Desde la fase 4, la [importación CSV](IMPORTACIONES.md) llama a `ReservationService.create_from_code`, que comparte las comprobaciones y la transacción del alta manual para cada reserva nueva.

La decisión consulta, en este orden:

1. Equipo existente y activo. Si no existe: 404; si está inactivo: `equipment_inactive`.
2. Alguna incidencia del equipo con `blocking=true` y estado `open` o `in_progress`: `blocking_incident`.
3. Alguna reserva `confirmed` del equipo que solape `[inicio, fin)`: `reservation_overlap`.

Si no hay impedimentos, devuelve `available=true` y `reason=null`. Una reserva rechazada por esos impedimentos devuelve 409. No se guarda un booleano de disponibilidad ni se modifica `equipment.active` al resolver.

La disponibilidad mantiene su estructura anterior. Cuando el motivo es `blocking_incident`, devuelve `available=false` y `conflicting_reservation_ids=[]`; esa lista sólo representa conflictos de reservas cuando el motivo es `reservation_overlap`. Para consultar las incidencias se usa `/api/incidents?equipment_id=1&blocking=true` y los estados correspondientes.

Las incidencias no tienen intervalo de fechas en esta fase: una bloqueante sin resolver impide cualquier alta nueva para su equipo. Resolver una de varias no desbloquea mientras quede otra bloqueante abierta o en curso. Después de resolver la última, el equipo todavía debe estar activo y libre para las fechas solicitadas. Las incidencias no bloqueantes nunca impiden reservar por sí mismas.

Ejemplo: se abre una bloqueante, una reserva se rechaza con 409, se inicia la reparación, sigue bloqueada, se resuelve con explicación y vuelve a admitirse la reserva si el intervalo está libre. Si ya existía una reserva en ese rango, se conserva y sigue impidiendo un solapamiento.

## Transacciones y orden concurrente

`database.immediate_transaction(session)` centraliza `Session.begin()` y `BEGIN IMMEDIATE`. Lo comparten los repositorios de reservas e incidencias. Crear incidencias y cambiar su estado adquieren el turno de escritura **antes** de leer el equipo, el estado anterior y las reservas del aviso.

Los datos de la respuesta y el aviso se preparan dentro de esa transacción, y sólo se devuelve éxito después del `COMMIT`. Un fallo al confirmar revierte el alta o el cambio de estado. Se mantiene `RENTALAB_SQLITE_BUSY_TIMEOUT_MS`, el 409 controlado y `Retry-After: 1` del módulo de reservas.

Con dos conexiones sobre el mismo archivo SQLite:

- Si la incidencia bloqueante confirma primero, la reserva posterior la ve y se rechaza.
- Si la reserva confirma primero, se conserva. La incidencia posterior se registra y devuelve su identificador en el aviso.

Ese segundo resultado forma parte del contrato: registrar incidencias no cancela material ya reservado. La prueba de concurrencia verifica ambos órdenes con dos conexiones reales, sin un cerrojo de proceso ni simulación de las reglas.

La migración `0004_incidents` añade la tabla, clave foránea, prioridades y estados permitidos, coherencia de la resolución e índice de consulta. No modifica tablas anteriores ni carga incidencias al iniciar.

## Ejemplo PowerShell

Con un equipo activo y un intervalo libre, desde otra terminal:

```powershell
$baseUrl = 'http://127.0.0.1:8000'
$equipment = Invoke-RentaLab "$baseUrl/api/equipment?active=true"
$equipmentId = $equipment[0].id
$incidentBody = @{
    equipment_id = $equipmentId
    title = 'Conector pendiente de revisión'
    blocking = $true
    priority = 'high'
} | ConvertTo-Json
$incident = Invoke-RentaLab "$baseUrl/api/incidents" -Method Post -ContentType 'application/json; charset=utf-8' -Body $incidentBody

Invoke-RentaLab "$baseUrl/api/equipment/$equipmentId/availability?start_date=2026-11-10&end_date=2026-11-12"
$statusBody = @{ status = 'in_progress' } | ConvertTo-Json
Invoke-RentaLab "$baseUrl/api/incidents/$($incident.id)/status" -Method Patch -ContentType 'application/json; charset=utf-8' -Body $statusBody
$resolutionBody = @{
    status = 'resolved'
    resolution = 'Conector sustituido y comprobado en taller ficticio'
} | ConvertTo-Json
Invoke-RentaLab "$baseUrl/api/incidents/$($incident.id)/status" -Method Patch -ContentType 'application/json; charset=utf-8' -Body $resolutionBody
Invoke-RentaLab "$baseUrl/api/incidents?equipment_id=$equipmentId&status=resolved"
Invoke-RentaLab "$baseUrl/api/equipment/$equipmentId/availability?start_date=2026-11-10&end_date=2026-11-12"
```

El último resultado sigue considerando otras incidencias, el estado activo y las reservas. Resolver esta incidencia no garantiza por sí solo que el rango quede libre.

## Cliente React y comprobaciones

El cliente tipado incorpora `Incident`, `IncidentInput`, `IncidentFilters`, `IncidentStatusChange`, `IncidentPriority` e `IncidentStatus` y estos métodos:

```typescript
api.createIncident({ equipment_id: 1, title: 'Revisar conector', blocking: true });
api.listIncidents({ equipment_id: 1, blocking: false });
api.getIncident(1);
api.changeIncidentStatus(1, { status: 'in_progress' });
api.changeIncidentStatus(1, { status: 'resolved', resolution: 'Conector sustituido.' });
```

Serializa también `blocking=false`, conserva los avisos del servidor y acepta `blocking_incident` como motivo de disponibilidad. Sus guardas comprueban la estructura de las respuestas. Las transiciones y el bloqueo se deciden en Python. La fase 5 incorpora listado, creación, detalle y resolución en la [interfaz React](INTERFAZ.md).

Desde `backend/`, las pruebas específicas son:

```powershell
..\.venv\Scripts\python.exe -m pytest tests/test_incidents.py tests/test_incident_concurrency.py -q
```

Para ejecutar la suite y las comprobaciones generales, utiliza los comandos del [README](../README.md). El registro de resultados reales está en [PROYECTO.md](PROYECTO.md).
