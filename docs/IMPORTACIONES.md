# Importación de pedidos desde CSV

La fase 4 interpreta cada fila como una solicitud de reserva para una unidad física. No hay cesta ni pagos. El servidor valida el archivo completo antes de escribir y después procesa cada fila por separado mediante el servicio de reservas. Desde la fase 5, la [interfaz React](INTERFAZ.md) permite descargar el ejemplo, subir un CSV y consultar el informe por fila.

## Archivo y petición

`POST /api/imports` recibe `multipart/form-data` con un único archivo en el campo `file`. Desde la fase 6 requiere [sesión válida y cabecera CSRF](ACCESO.md); el ejemplo descargable también requiere sesión. No admite otros campos ni varios archivos. La extensión y el nombre del archivo no determinan su validez: se comprueba su contenido y nunca se utiliza el nombre como ruta.

La cabecera, en este orden y sin espacios adicionales, debe ser exactamente:

```csv
external_reference,customer_name,customer_email,equipment_code,starts_on,ends_on
```

Condiciones del archivo:

- Codificación UTF-8, con o sin BOM; separador de comas. Admite finales de línea LF y CRLF y campos entrecomillados, incluso con comas o saltos de línea.
- Máximo **1 MiB (1 048 576 bytes)** de contenido CSV, incluido el BOM si existe, y **500 registros de datos** sin contar la cabecera. Los límites son inclusivos. Una fila vacía o con columnas incorrectas cuenta como registro y se rechaza individualmente.
- Cada registro debe contener exactamente seis columnas. `starts_on` y `ends_on` exigen `YYYY-MM-DD` y fin posterior al inicio, con intervalo `[inicio, fin)`.
- Un archivo con sólo la cabecera es válido y devuelve totales a cero. Un archivo vacío no tiene la cabecera requerida.

El receptor cuenta los bytes durante la lectura, también sin `Content-Length`, y conserva como máximo el contenido permitido en memoria. Se usa `python-multipart` sin archivos temporales de subida; no se guarda el archivo recibido. El envoltorio multipart tiene un margen adicional de 64 KiB y límites de cabeceras del analizador. La lectura es asíncrona y el análisis CSV y las operaciones SQL se ejecutan en el pool de hilos.

Antes de la primera inserción se comprueban tamaño, UTF-8, cabecera, estructura CSV y cantidad de registros. Si una comilla sin cerrar impide analizar el archivo, se rechaza el archivo completo. Los errores globales tienen este contrato:

| HTTP | Causa | Escrituras |
| --- | --- | --- |
| 413 | Más de 1 MiB, más de 500 registros o envoltorio multipart excesivo | Ninguna |
| 422 | Multipart ausente, incorrecto o incompleto; UTF-8, cabecera o estructura CSV inválidos | Ninguna |
| 200 | Archivo estructuralmente válido, aunque algunas o todas sus filas sean rechazadas | Sólo las filas aceptadas |

Los errores globales devuelven `{"detail":"Explicación en español"}`. Un equipo inexistente o un conflicto de una fila se expresa dentro del informe HTTP 200: no detiene el resto del archivo. Las APIs individuales de reservas mantienen sus códigos 404, 409 y 422.

## Normalización e idempotencia

Cada fila se valida con los tipos Python del catálogo y las reservas:

- `external_reference`: obligatoria, de 1 a 120 caracteres tras recortar espacios exteriores, sin NUL. Distingue mayúsculas y minúsculas: `PED-1` y `ped-1` son referencias distintas.
- `customer_name`: contenido obligatorio, hasta 120 caracteres, recortado y sin NUL.
- `customer_email`: hasta 254 caracteres de entrada, recortado y validado sin DNS; se conserva la normalización del validador de reservas, por ejemplo el dominio en minúsculas. Se admiten dominios ficticios `.test`.
- `equipment_code`: recortado y convertido a mayúsculas, con los límites del catálogo. Se resuelve al identificador de la unidad física existente.
- Fechas: formato ISO exacto, sin horas, sin recortar espacios y sin imponer que sean futuras. Se convierten a los campos `start_date` y `end_date` de la reserva.

| Situación | Resultado |
| --- | --- |
| Referencia nueva y fila válida, con equipo activo, sin avería bloqueante ni solapamiento | `accepted`: crea una reserva `confirmed` |
| Referencia existente, con la misma unidad, nombre, correo y fechas normalizados | `already_imported`: devuelve la reserva existente sin cambios |
| Referencia existente con algún dato distinto | `rejected`: informa del conflicto sin sobrescribir |
| Datos inválidos, equipo inexistente o sin disponibilidad | `rejected`: explica el motivo sin insertar |

La comparación de una referencia existente ignora el estado: una reserva cancelada sigue siendo «ya importada», conserva `cancelled` y no se reactiva. La reimportación idéntica se reconoce antes de comprobar la disponibilidad actual; funciona aunque después se haya desactivado el equipo, abierto una incidencia o confirmado otra reserva. Una fila inválida no se vuelve válida por usar una referencia conocida.

Se compara la identidad física del equipo al resolver su código actual. Si se cambia el código del catálogo, el código anterior deja de identificarlo; hay que usar el nuevo. No se almacena una copia del CSV ni un segundo estado de disponibilidad. El alta manual `POST /api/reservations` conserva su contrato anterior: una referencia repetida devuelve 409; la respuesta idempotente pertenece a la importación.

Las filas se procesan en orden. Dos filas idénticas del mismo archivo producen una aceptada y otra ya importada. Si la segunda cambia los datos, se rechaza. Una fila rechazada no consume su referencia, por lo que otra posterior puede usarla con datos válidos.

## Contrato del informe para React

La respuesta contiene `totals` y `rows`, en el mismo orden del archivo:

| Campo | Tipo | Significado |
| --- | --- | --- |
| `totals.total` | entero | Número de registros procesados |
| `totals.accepted` | entero | Reservas creadas en esta petición |
| `totals.already_imported` | entero | Reservas existentes idénticas |
| `totals.rejected` | entero | Filas rechazadas |
| `rows[].line` | entero | Línea física donde empieza el registro; la cabecera empieza en 1 |
| `rows[].external_reference` | texto o `null` | Referencia recortada; `null` si falta o está vacía |
| `rows[].status` | `accepted`, `already_imported` o `rejected` | Resultado de la fila |
| `rows[].reservation` | `ReservationRead` o `null` | Reserva nueva o existente para los dos primeros estados; `null` si se rechaza |
| `rows[].message` | texto | Explicación legible en español, sin trazas ni SQL |

`total = accepted + already_imported + rejected`. Un campo entrecomillado con saltos de línea ocupa varias líneas físicas, pero cuenta como un registro de datos. Ejemplo de informe parcial:

```json
{
  "totals": {"total": 3, "accepted": 1, "already_imported": 1, "rejected": 1},
  "rows": [
    {
      "line": 2,
      "external_reference": "PED-001",
      "status": "accepted",
      "reservation": {
        "id": 7, "equipment_id": 1,
        "customer_name": "Estudio Aurora", "customer_email": "aurora@example.test",
        "start_date": "2026-11-10", "end_date": "2026-11-12",
        "status": "confirmed", "external_reference": "PED-001"
      },
      "message": "Reserva creada."
    },
    {
      "line": 3,
      "external_reference": "PED-001",
      "status": "already_imported",
      "reservation": {
        "id": 7, "equipment_id": 1,
        "customer_name": "Estudio Aurora", "customer_email": "aurora@example.test",
        "start_date": "2026-11-10", "end_date": "2026-11-12",
        "status": "confirmed", "external_reference": "PED-001"
      },
      "message": "La reserva ya estaba importada; se conserva sin cambios."
    },
    {
      "line": 4,
      "external_reference": "PED-002",
      "status": "rejected",
      "reservation": null,
      "message": "El equipo indicado no existe."
    }
  ]
}
```

`frontend/src/api/client.ts` expone `api.importReservations(file: File): Promise<ImportReport>` e `IMPORT_EXAMPLE_URL`. Usa `FormData` y deja al navegador generar `Content-Type` con su boundary. El cliente comprueba la estructura de la respuesta y conserva los mensajes; React no analiza el CSV ni reproduce las reglas de disponibilidad o idempotencia.

## Transacciones y conexión con reservas e incidencias

`ImportService` analiza primero todo el archivo. Después valida cada fila y abre una sesión independiente. `ReservationService.create_from_code` toma `BEGIN IMMEDIATE` **antes** de consultar la referencia, resolver el equipo y decidir si crea o reconoce una reserva.

Para una referencia nueva, la creación delega en el mismo método `_create_checked` que el alta manual y consulta `AvailabilityService.check`: equipo activo, ninguna incidencia bloqueante sin resolver y ninguna reserva confirmada solapada. El intervalo usa `existing.start_date < requested.end_date AND existing.end_date > requested.start_date`. No hay inserciones directas que eviten esas reglas.

SQLite serializa los escritores. Si dos importaciones compiten por una referencia, la segunda consulta después del commit de la primera y ve «ya importada» o el conflicto de datos. La restricción `UNIQUE` de `reservations.external_reference` protege además el almacenamiento. Se conserva la migración `0003_reservations`, que ya contiene esa restricción; **no hay cambios de esquema ni nueva migración en la fase 4**. Alembic sigue en `0004_incidents`.

Cada fila aceptada confirma su propia transacción. Un rechazo o bloqueo revierte esa fila y cierra su sesión antes de continuar con la siguiente. Los bloqueos SQLite agotados se presentan como un rechazo con una explicación para reintentar; el resto de errores SQL se oculta tras un mensaje genérico. No se devuelve una traza ni datos internos del motor.

Esta importación parcial conserva las filas correctas aunque otra esté mal. Se puede corregir y reenviar el archivo completo: las referencias ya confirmadas se reconocen, las rechazadas se vuelven a intentar y una referencia modificada nunca sobrescribe la reserva anterior. No es una transacción única para todo el archivo.

## Ejemplo verificable en PowerShell

Con backend, migraciones y catálogo ficticio preparados según [README.md](../README.md), y la sesión `$apiSession`/`$apiHeaders` todavía abierta según [ACCESO.md](ACCESO.md#api-desde-powershell), desde la raíz:

```powershell
Invoke-WebRequest "$apiBase/api/imports/example" -WebSession $apiSession -OutFile .\pedidos-ejemplo.csv
$apiCookieHeader = $apiSession.Cookies.GetCookieHeader([uri]$apiBase)
$report = curl.exe --silent --show-error --fail-with-body `
  -H "Cookie: $apiCookieHeader" -H "X-CSRF-Token: $($apiHeaders['X-CSRF-Token'])" `
  -F 'file=@pedidos-ejemplo.csv;type=text/csv' `
  "$apiBase/api/imports" | ConvertFrom-Json
Remove-Variable apiCookieHeader
$report.totals
$report.rows | Select-Object line, external_reference, status, message
```

Se usa `curl.exe` explícitamente para evitar el alias `curl` de Windows PowerShell. No se fija manualmente la cabecera multipart. También funciona con la URL de Vite `http://127.0.0.1:5173/api/imports`; el proxy conserva la subida.

`GET /api/imports/example` descarga `rentalab-pedidos-ejemplo.csv`, con tres solicitudes ficticias para `CAM-001`, `CAM-002` y `AUD-001`. En un catálogo recién cargado y libre, la primera subida acepta tres y repetirla informa de tres ya importadas. Si ya hay reservas o incidencias para esos equipos y fechas, el informe refleja ese estado real.

Las fixtures de comportamiento están en `backend/tests/fixtures/imports/`: `valid.csv`, `mixed.csv` e `invalid_header.csv`. El resto de límites y casos malformados se genera en las pruebas para no guardar archivos grandes.

## Comprobaciones

Desde `backend`, ejecuta `..\.venv\Scripts\python.exe -m pytest -q`. Para centrarse en el módulo: `..\.venv\Scripts\python.exe -m pytest tests/test_imports.py tests/test_import_concurrency.py -q`.

Las pruebas cubren cabecera y límites antes de escribir, BOM, fechas, UTF-8, multipart truncado y sin `Content-Length`, mezcla de filas, equipos inexistentes/inactivos, solapamientos, incidencias, cancelaciones, normalización, referencias repetidas/modificadas y persistencia. Dos aplicaciones con conexiones distintas sobre SQLite temporal en disco verifican importaciones simultáneas; otra prueba provoca un bloqueo real y comprueba que la siguiente fila se procesa con una sesión limpia. El registro de ejecuciones y resultados está en [PROYECTO.md](PROYECTO.md).
