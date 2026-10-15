# Operaciones del cliente — fase C

La API de cliente vive bajo `/api/me`. Exige una sesión vigente de un usuario persistido, activo y con rol `customer`. No acepta identidad, rol u ownership proporcionados por React. Un administrador utiliza las rutas de gestión existentes y recibe 403 en `/api/me`; el operador de transición no tiene ID de cliente persistido.

La fase C entregó estas operaciones HTTP y contratos. La fase D añade el [portal React](PORTAL_CLIENTE.md) que las consume, con reservas, avisos y cuenta propios.

## Reservas propias

| Método y ruta | Entrada | Resultado |
| --- | --- | --- |
| `POST /api/me/reservations` | Equipo y ambas fechas; cabecera UUID `Idempotency-Key` opcional | 201 + Location del detalle propio; repetir una clave conserva la reserva original |
| `POST /api/me/reservations/batch` | Entre 1 y 50 productos distintos y fechas comunes; misma cabecera opcional | 201 con reservas ordenadas; confirmación y recuperación conjunta atómicas |
| `GET /api/me/reservations` | Sin filtros | Sólo reservas propias, incluidas canceladas, orden inicio/ID |
| `GET /api/me/reservations/{reservation_id}` | ID en ruta | Propia 200; ajena, histórica sin dueño o inexistente 404 |
| `POST /api/me/reservations/{reservation_id}/cancel` | Sin cuerpo, null o `{}` | 200 cancelada antes del inicio, sin borrar historial |

Creación acepta **exactamente**:

```json
{"equipment_id":1,"start_date":"2026-11-10","end_date":"2026-11-12"}
```

Respuesta mínima:

```json
{"id":31,"equipment_id":1,"start_date":"2026-11-10","end_date":"2026-11-12","status":"confirmed"}
```

El servidor toma `customer_user_id`, nombre y correo de la identidad que acaba de consultar en SQLite. Persiste nombre/correo como datos de contacto de esa reserva; no los obtiene del cuerpo ni vuelve a asignar reservas por correo. Estado confirmado y referencia externa null se asignan internamente. Se rechazan con 422 `customer_id`, `customer_user_id`, `user_id`, nombre, correo, estado, origen, referencia externa y cualquier campo desconocido. La respuesta propia tampoco expone esas referencias o datos administrativos.

Las fechas siguen siendo días ISO exactos y rango `[inicio, fin)`, con fin posterior a inicio. Formato o estructura inválidos devuelven 422. Un inicio anterior a hoy en **Europe/Madrid** devuelve 409. Hoy sí se admite como inicio: la confirmación es inmediata si hay disponibilidad. Administración y CSV mantienen sus reglas anteriores, incluidas las operaciones históricas; esta restricción temporal es del cliente.

Consultar disponibilidad pública sigue siendo orientativo. El alta usa `ServicioReservas.crear_para_cliente`, la unidad de escritura existente y `_crear_comprobado`, sin una segunda política de solapamiento. Bajo `BEGIN IMMEDIATE` comprueba la fecha y la disponibilidad, inserta propietario y confirma. Dos clientes no pueden confirmar reservas incompatibles: uno obtiene 201 y el otro 409. Para cliente se normalizan los conflictos de disponibilidad a un mensaje comprensible que pide consultar otra vez y elegir otro intervalo; no se revela si la causa fue una avería interna, una reserva o la desactivación de la unidad.

## Creación individual y conjunta con idempotencia

`POST /api/me/reservations` y `POST /api/me/reservations/batch` admiten la cabecera opcional `Idempotency-Key` con un UUID. La clave identifica una intención de reserva de la cuenta autenticada. Un reintento de la misma cuenta con la misma clave, operación, equipos solicitados y fechas devuelve **201 y las mismas reservas y Location**, sin consumir más unidades físicas. Funciona entre sesiones, procesos y reinicios, incluso si se perdió la respuesta después de confirmar la primera petición. Otra cuenta puede utilizar el mismo UUID sin acceder ni reutilizar reservas ajenas.

El servidor conserva los equipos solicitados antes de asignar las unidades físicas, junto con ambas fechas y los vínculos ordenados a las reservas. Reutilizar la clave con otra operación (individual frente a conjunta), otro equipo, distinto orden de productos o fechas diferentes devuelve 409 y no modifica nada; una cabecera que no sea un UUID devuelve 422. La creación y el registro de la intención comparten `BEGIN IMMEDIATE`: dos peticiones concurrentes de la misma intención reciben las mismas reservas. Una conjunta fallida revierte reservas, intención y vínculos; el intento rechazado no consume la clave. La protección también cubre una conjunta de un solo producto.

La repetición se reconoce antes de comprobar disponibilidad, actividad o fecha actual. Si una reserva ya está cancelada, la respuesta devuelve esa misma reserva con `status=cancelled`; tampoco crea otra si la unidad se desactivó o ya pasó la fecha de inicio. Las conjuntas conservan el orden original y el estado actual de cada reserva. Las claves no aparecen en los DTO de reservas. Cambiar de intención requiere un UUID nuevo. Las peticiones sin cabecera conservan el comportamiento anterior.

## Cancelación, reloj e idempotencia

Sólo puede realizarse una nueva cancelación cuando `hoy Madrid < start_date`. En el mismo día de inicio o después devuelve 409 y conserva la reserva confirmada. La operación filtra primero por propietario y, dentro del bloqueo de escritura, comprueba estado y fecha.

Una reserva **ya cancelada** responde 200 con el mismo historial aunque al repetir la petición haya pasado la fecha de inicio. No vuelve a escribir ni necesita reevaluar el plazo de una cancelación ya realizada. Cancelar una ajena sigue siendo 404 incluso si está cancelada. El cuerpo sólo permite ausencia, null o `{}`: enviar campos adicionales devuelve 422.

`rentalab/reloj.py` convierte un instante UTC consciente de zona a `Europe/Madrid`, incluyendo horario de verano/invierno. No usa la fecha del navegador ni la zona horaria local del host. Se inyecta un proveedor `obtener_hoy_proveedor`, no una fecha capturada al entrar en HTTP: el servicio ejecuta `today()` **después de adquirir** `BEGIN IMMEDIATE`. Así una petición que espere por SQLite y cruce medianoche se decide con el nuevo día de Madrid.

En pruebas puede congelarse el proveedor:

```python
from datetime import date
from rentalab.reloj import get_today_provider

app.dependency_overrides[get_today_provider] = lambda: lambda: date(2026, 11, 1)
```

También se puede sustituir `utc_ahora` para probar la conversión real. No existe un parámetro HTTP que permita al usuario alterar el reloj. Se añade `tzdata==2026.5`, fijado con hashes en ambos locks, porque este Windows no tenía datos IANA. Es el mecanismo de compatibilidad recomendado por la [documentación de ZoneInfo](https://docs.python.org/3/library/zoneinfo.html#data-sources). Las versiones anteriores de las dependencias se mantienen.

## Avisos vinculados a reservas

| Método y ruta | Entrada | Resultado |
| --- | --- | --- |
| `POST /api/me/reservations/{reservation_id}/incidents` | `{title,description}` | 201 + Location `/api/me/incidents/{id}` |
| `GET /api/me/incidents` | Sin filtros | Exclusivamente avisos propios vinculados a reservas propias |
| `GET /api/me/incidents/{incident_id}` | ID en ruta | Propio 200; ajeno, sin vínculo conocido o inexistente 404 |

Título es obligatorio, recortado, de 1–160 caracteres sin NUL. Descripción es obligatoria, recortada, de 1–2000 sin NUL. El cliente no puede indicar equipo, reserva en el cuerpo, autor, prioridad, bloqueo, estado, resolución, respuesta pública ni notas internas. Los campos desconocidos se rechazan con 422.

El servidor busca la reserva por **ID y propietario**. Ajena, sin dueño o inexistente: 404 idéntico. Si es propia pero ya no está confirmada: 409. Equipo y autor se deducen de reserva y sesión. La lectura del estado y la inserción del aviso están dentro de la misma transacción `BEGIN IMMEDIATE` usada por cancelación: si gana la cancelación, no se crea el aviso; si el aviso se crea primero, queda en el historial aunque después se cancele.

El aviso se registra en `open` (pendiente de gestión), prioridad por defecto `medium` y `blocking=false`; comunicación pública, notas y resolución empiezan vacías. **Informar no bloquea el equipo**. Sólo administración puede decidir bloqueo/prioridad y tramitar o resolver el problema.

Respuesta propia exacta:

```json
{
  "id":8,
  "reservation_id":31,
  "title":"Problema con el conector",
  "description":"El conector no mantiene la conexión durante la prueba.",
  "status":"open",
  "public_response":""
}
```

Se consultan los avisos con una unión SQL que exige tanto `author_user_id` propio como propietario de la reserva vinculada. Un autor coincidente no permite leer una reserva ajena o histórica sin dueño. Tras cancelar se conserva la consulta del aviso propio; sólo crear exige reserva confirmada.

## Gestión y respuesta pública

Se añade `PATCH /api/incidents/{incident_id}`, exclusivo de administrador con CSRF, para editar únicamente prioridad, bloqueo, respuesta pública y notas internas:

```json
{
  "priority":"high",
  "blocking":true,
  "public_response":"Estamos revisando el equipo y te informaremos del resultado.",
  "internal_notes":"Anotación de gestión que nunca se devuelve por /api/me."
}
```

Campos omitidos se conservan. Objeto vacío, null o campos desconocidos: 422. Los dos textos admiten hasta 2000 caracteres recortados y sin NUL; `""` permite retirarlos. `blocking` exige booleano real y prioridad sigue el enum anterior. La escritura adquiere `BEGIN IMMEDIATE`, de modo que cambiar un bloqueo y confirmar otra reserva se serializan con las reglas existentes de disponibilidad.

El cambio de estado mantiene `PATCH /api/incidents/{id}/status`, con su resolución obligatoria al resolver. `resolution` sigue siendo **interna**: nunca se copia a `public_response`. El cliente ve estado y respuesta pública, sin prioridad, bloqueo, notas, resolución, IDs de otras reservas o datos de gestión. Las lecturas antiguas de detalle `/api/reservations/{id}` y `/api/incidents/{id}` quedan reservadas a administración para impedir que sus esquemas más amplios funcionen como vía alternativa de lectura.

Las respuestas de gestión incluyen autor y vínculo de reserva cuando se conocen, además de los campos anteriores y la comunicación separada. Listados administrativos siguen incluyendo todas las reservas e incidencias históricas, también con propietario, autor o reserva null. No se reasignan datos antiguos automáticamente.

## Seguridad, errores y persistencia

| Situación | HTTP |
| --- | --- |
| Sesión ausente, expirada, revocada o usuario desactivado | 401 |
| Rol incorrecto o CSRF inválido en escritura | 403 |
| Recurso propio inexistente, ajeno o histórico sin dueño/vínculo | 404 uniforme |
| Formato, campos prohibidos o estructura inválida | 422 |
| Inicio pasado, cancelación fuera de plazo, reserva propia no confirmada o indisponibilidad | 409 |
| SQLite ocupada tras agotar espera | 503 con `Retry-After: 1`; no implica fechas ocupadas |

Se conservan cookie HttpOnly, expiración, revocación, consulta de rol vigente y CSRF ligado a la sesión. Toda escritura de `/api/me` exige el token actual; uno de otra cuenta no sirve. Las respuestas llevan `Cache-Control: no-store`. No hay reintento automático de confirmación: recuperar una creación individual o conjunta utiliza la misma `Idempotency-Key`, además de las mismas comprobaciones de sesión, rol y CSRF.

La migración `0008_customer_incidents` añade `incidents.reservation_id` nullable con FK e índice, `public_response` y `internal_notes` vacíos. Conserva `resolution`, autoría y todos los campos anteriores. No copia resolución interna a comunicación pública, no adivina reservas de incidencias históricas y no cambia ownership. Reservas utilizan la relación incorporada en 0006; no hay reconstrucción de tablas de negocio ni carga automática de cuentas/datos.

La migración `0011_booking_requests` añade `booking_requests`, con clave primaria compuesta por cuenta y UUID, operación y fechas, y `booking_request_reservations`, con productos originales, posición y FK única a cada reserva. No inventa claves para reservas anteriores ni modifica inventario, reservas, avisos, usuarios o listas guardadas existentes. Revertir la migración elimina las intenciones y sus vínculos y conserva las reservas.

Las pruebas usan dos clientes y un administrador, identificadores modificados directamente por HTTP, campos falsificados, fechas Madrid, esperas de SQLite, CSRF y conexiones distintas con eventos SQL. [PROYECTO.md](PROYECTO.md) registra resultados, migraciones y límites reales. Las pantallas de cliente y los controles de respuesta administrativa siguen fuera de esta entrega de API.
