# Arquitectura de RentaLab

RentaLab reúne catálogo público, portal de cliente y panel administrativo en una aplicación React, una API FastAPI y una base SQLite. Python decide permisos y reglas; React presenta sus resultados. El [contrato y registro de comprobaciones](PROYECTO.md) distingue lo implementado, lo ejecutado y las limitaciones de herramientas; el [balance integrado de F](VALIDACION_INTEGRADA.md) reúne la evidencia final.

## Responsabilidades y puntos de entrada

| Responsabilidad | Código real | Decisión |
| --- | --- | --- |
| Navegación y layouts | [App.tsx](../frontend/src/App.tsx), [ClientLayout.tsx](../frontend/src/portal/ClientLayout.tsx), [AdminApp.tsx](../frontend/src/admin/AdminApp.tsx) | Un router y navegación de cliente separada de `/admin` |
| Identidad | [AuthProvider.tsx](../frontend/src/auth/AuthProvider.tsx), [destinations.ts](../frontend/src/auth/destinations.ts) | Sesión real al recargar y destinos internos permitidos por rol |
| HTTP tipado | [api/client.ts](../frontend/src/api/client.ts), [types/api.ts](../frontend/src/types/api.ts) | Único `fetch`, CSRF, errores y validación de JSON recibido como `unknown` |
| Composición HTTP | [main.py](../backend/rentalab/main.py) | Rutas, errores, middleware y compilación React |
| Autenticación y autorización | [auth/middleware.py](../backend/rentalab/auth/middleware.py), [auth/dependencies.py](../backend/rentalab/auth/dependencies.py), [auth/service.py](../backend/rentalab/auth/service.py) | Sesión persistida, usuario vigente, rol y CSRF |
| Catálogo público | [public_catalogue/routes.py](../backend/rentalab/public_catalogue/routes.py), [public_catalogue/schemas.py](../backend/rentalab/public_catalogue/schemas.py) | Proyección explícita de equipos activos sin motivos privados |
| Operaciones propias | [me/reservations.py](../backend/rentalab/me/reservations.py), [me/incidents.py](../backend/rentalab/me/incidents.py) | Identidad desde la sesión y aislamiento por propietario |
| Reglas de reserva | [reservations/service.py](../backend/rentalab/reservations/service.py), [availability.py](../backend/rentalab/availability.py) | Disponibilidad, cancelación e idempotencia compartidas |
| Persistencia | [reservations/repository.py](../backend/rentalab/reservations/repository.py), [database.py](../backend/rentalab/database.py) | SQLAlchemy, conflictos y unidad de escritura SQLite |
| Esquema | [modelos de reservas](../backend/rentalab/reservations/models.py), [migraciones](../backend/alembic/versions) | Restricciones, propiedad nullable y evolución conservadora |

Las páginas no conocen SQL. Los servicios reciben datos y repositorios Python; rutas y manejadores traducen errores de dominio a HTTP. TypeScript comprueba contratos para representar datos y errores; no sustituye la autorización del servidor.

## Tres contratos de acceso

| Zona | Acceso | Datos publicados |
| --- | --- | --- |
| `/api/public` | Visitante, cliente y administrador | Nombre, categoría, descripción pública, características, imagen/fallback y disponibilidad por fechas |
| `/api/me` | Cliente autenticado | Sus reservas, sus avisos y respuesta pública |
| Gestión antigua `/api/equipment`, `/api/reservations`, `/api/incidents` y `/api/imports` | Administrador | Gestión global y campos internos |

`/admin` organiza pantallas; ocultar botones o cambiar una URL no concede permisos. Las rutas antiguas siguen protegidas. Administración utiliza gestión; `require_customer` no convierte a un administrador en cliente de `/api/me`. La [matriz completa](ACCESO.md) incluye sesión y OpenAPI.

`AuthGuardMiddleware` comprueba cookie firmada, registro `AuthSession` y CSRF en escrituras. `AuthService.find_session` consulta el usuario asociado en cada petición: activo, rol vigente y versión de contraseña. `get_current_user`, `require_admin` y `require_customer` centralizan las dependencias. La cookie no lleva un permiso de rol confiable para el backend.

Los hashes Argon2id de usuarios viven en `users`; el secreto de firma se configura fuera del repositorio. El par opcional de operador anterior conserva acceso administrativo durante la transición, con `user_id=null`. No crea usuarios ni atribuye historial.

## Recorrido completo: reservar desde el portal

~~~mermaid
sequenceDiagram
    participant U as Cliente
    participant R as ProductPage
    participant C as Cliente TypeScript
    participant H as FastAPI
    participant S as ReservationService
    participant D as SQLite
    U->>R: Equipo y fechas
    R->>H: GET /api/public/equipment/id/availability
    H-->>R: Disponibilidad orientativa
    U->>R: Confirmar con sesión de cliente
    R->>C: api.createMyReservation(datos)
    C->>H: POST /api/me/reservations + cookie + CSRF
    H->>H: Usuario vigente y contrato permitido
    H->>S: create_for_customer(datos, user_id, reloj)
    S->>D: BEGIN IMMEDIATE
    S->>S: Día Madrid y AvailabilityService.check
    alt Libre y válido
        S->>D: INSERT con propietario y origin=portal; COMMIT
        H-->>C: 201 + datos propios + Location
        R-->>U: Referencia y enlace al detalle
    else Conflicto
        S->>D: ROLLBACK
        H-->>C: 409 comprensible sin datos ajenos
        R-->>U: Error y fechas conservadas
    end
~~~

1. [ProductPage.tsx](../frontend/src/portal/ProductPage.tsx) conserva fechas ISO en la URL. Acceso y registro conservan un destino interno validado; volver no crea automáticamente una reserva.
2. `reserve` llama a `api.createMyReservation` tras la confirmación explícita. El cliente común adjunta cookie del mismo origen y `X-CSRF-Token`; para multipart permite que el navegador construya su boundary.
3. `CustomerReservationCreate` sólo permite `equipment_id`, `start_date` y `end_date`. Rechaza propietario, estado, origen e identidad de otro cliente. La ruta obtiene nombre, correo y propietario de `CustomerUser`.
4. `create_for_customer` adquiere la transacción y lee después el día de negocio con el reloj inyectado de [clock.py](../backend/rentalab/clock.py). Rechaza inicios pasados en Europe/Madrid.
5. `_create_checked` usa `AvailabilityService.check` antes de insertar `confirmed`, propietario y `origin="portal"`. Se confirma o revierte toda la unidad.
6. La respuesta propia contiene identificador, equipo, fechas y estado. React muestra `Reserva #id` y enlaza a `/mis-reservas/:id`; el detalle vuelve a consultar la API.

La gestión conserva [ReservationFormPage.tsx](../frontend/src/pages/ReservationFormPage.tsx): admite datos del pedido y referencia opcional, llama a `api.createReservation` y crea `origin="admin"` sin asignar una cuenta por correo.

## Una política de disponibilidad para todos los caminos

`AvailabilityService.check` calcula disponibilidad; no existe una columna `available`. Comprueba equipo activo, ausencia de incidencias bloqueantes sin resolver y ausencia de reservas confirmadas solapadas. La respuesta pública no revela IDs de reservas, contactos, descripción de averías ni motivos internos.

| Entrada | Regla común |
| --- | --- |
| Consulta pública | `PublicCatalogueService.check_availability` → `AvailabilityService.check`; no retiene equipo |
| Consulta administrativa | `ReservationService.availability` → `AvailabilityService.check`; no retiene equipo |
| Reserva de cliente | `create_for_customer` → `_create_checked` dentro de transacción |
| Reserva administrativa | `create` → `_create_checked` dentro de transacción |
| CSV con referencia nueva | `create_from_code` → `_create_checked` dentro de transacción |

Sin inicio y fin el catálogo pide seleccionar fechas; no afirma disponibilidad. Un equipo inactivo queda fuera del listado y su detalle público devuelve 404. `ReservationRepository.conflicting_ids` aplica:

~~~text
mismo equipo
AND status = confirmed
AND existing.start_date < requested.end_date
AND existing.end_date > requested.start_date
~~~

`[inicio, fin)` alquila días completos: del 10 al 12 ocupa 10 y 11; otra reserva puede comenzar el 12. `immediate_transaction` combina `Session.begin()` con `BEGIN IMMEDIATE` antes de las lecturas de decisión. El segundo escritor espera y vuelve a comprobar tras el primero. La garantía depende de estos servicios; no existe una restricción SQL de exclusión de intervalos contra un `INSERT` arbitrario.

## Propiedad, cancelación e historial

`Reservation.customer_user_id` es nullable. `list_for_customer` y `get_for_customer` filtran por ese identificador, no por correo. Una reserva ajena o sin dueño conocido devuelve 404 en rutas propias. Registrarse con un correo coincidente con un CSV no reclama históricos.

`origin` distingue `portal`, `admin`, `csv` y `legacy`. `0009_reservation_origin` marca los anteriores como `legacy` sin inferir su procedencia, conservando su propiedad. Administración sigue viendo todos, incluidos «Sin propietario de cuenta».

`cancel_for_customer` sólo cancela antes del día de inicio en Madrid; repetir una ya cancelada devuelve el mismo resultado incluso después de esa fecha. `cancel` permite cancelación administrativa sin ese límite. Mantienen el registro y liberan sólo su solapamiento: puede quedar otro impedimento.

## Avisos de cliente y gestión de incidencias

`CustomerIncidentService.create` lee reserva propia confirmada e inserta el aviso bajo el mismo turno de escritura que la cancelación. Deduce equipo, reserva y autor; el cliente sólo envía título y descripción. Se crea `open`, prioridad `medium` y `blocking=False`.

Administración decide prioridad, bloqueo, notas internas y `public_response` mediante PATCH. `IncidentService.change_status` exige explicación para resolver. El esquema de cliente contiene únicamente su título, descripción, estado, reserva y respuesta pública; excluye `internal_notes`, `resolution` y prioridad.

Una incidencia bloquea si `blocking=True` y estado `open` o `in_progress`. `ReservationRepository.has_blocking_incident` comprueba si existe alguna: resolver una de varias no elimina las demás. Resolver todas tampoco activa un equipo ni elimina reservas. Un aviso posterior no cancela compromisos confirmados; `IncidentService._read` informa al administrador de las reservas afectadas. Se conserva el registro y su estado final, sin auditoría completa de cada transición.

## CSV e idempotencia

[ImportService.run](../backend/rentalab/imports/service.py) valida antes de insertar tamaño, UTF-8, cabecera, sintaxis y cantidad mediante `parse_csv`. Cada fila usa después su sesión y transacción. Las nuevas aceptadas tienen `origin="csv"` y propietario desconocido.

`create_from_code` comprueba referencia y datos normalizados dentro de la transacción. Si ya existe idéntica devuelve la anterior, incluso cancelada; si difiere rechaza la fila. No sobrescribe, reactiva ni atribuye usuario. Restricción única y turno de escritura cubren reimportaciones simultáneas. Un 200 requiere leer el informe por fila.

## Interfaz, errores y sesión

`AuthProvider` consulta sesión antes de montar páginas privadas. `RequireRole` y layouts separan navegación; las generaciones del cliente descartan respuestas tardías de otra identidad. No se guardan reservas ni tokens en localStorage. Un 401 desmonta pantallas privadas; un 403 de CSRF permite un reintento decidido por la persona, sin repetir escrituras automáticamente.

| Respuesta | Significado |
| --- | --- |
| 401 | Falta sesión válida, expiración o cuenta desactivada; también credenciales incorrectas |
| 403 | Rol insuficiente o CSRF incorrecto |
| 404 | Recurso inexistente; en `/api/me` también privado ajeno |
| 405 | Método no permitido; conserva `Allow` |
| 409 | Conflicto de reglas, plazo o espera SQLite agotada; esta última añade `Retry-After: 1` |
| 413 | CSV demasiado grande o con demasiadas filas |
| 422 | Datos o campos no permitidos |

La cookie HttpOnly contiene identificador y contexto CSRF firmados; la firma no cifra. SQLite conserva sesión y expiración absoluta; cerrar sesión elimina el registro. Producción requiere cookie Secure y HTTPS. HTTP local en development no verifica un despliegue HTTPS.

## Migraciones, arranque y distribución

Alembic conserva `0001`–`0009`: catálogo, corrección NUL, reservas, incidencias, sesiones, usuarios/propiedad, ficha pública, avisos de cliente y origen. No se usa `create_all`. [start.prepare_startup](../backend/rentalab/start.py) valida configuración/permisos y aplica migraciones antes de HTTP; no crea cuentas ni carga ejemplos.

[Dockerfile](../Dockerfile) compila React en Node y copia `dist` al runtime Python sin privilegios. [Compose](../compose.yaml) monta `/data` completo y mantiene una instancia/un worker. Cuentas y seed son comandos explícitos. Vite reenvía `/api` y `/health` en desarrollo; FastAPI sirve compilación y API bajo el mismo origen.

`add_frontend_routes` y `FrontendRoute.matches` admiten GET/HEAD de `/catalogo`, `/mis-reservas` y `/admin` directamente; excluyen rutas del servidor y recursos inexistentes, conservando sus errores en vez de devolver HTML.

[backup.create_backup](../backend/rentalab/backup.py) utiliza SQLite y valida integridad/relaciones. Restaurar exige detener todos los usuarios de la base. [DESPLIEGUE.md](DESPLIEGUE.md) contiene comandos; [PROYECTO.md](PROYECTO.md) registra pruebas reales y pendientes.

## Evidencia y límites

- [test_public_catalogue.py](../backend/tests/test_public_catalogue.py): búsqueda, filtros, fechas, inactivos y exclusión de campos privados.
- [test_me_security.py](../backend/tests/test_me_security.py), [test_me_reservations.py](../backend/tests/test_me_reservations.py) y [test_me_incidents.py](../backend/tests/test_me_incidents.py): IDs y campos manipulados por HTTP con identidades separadas.
- [test_admin_connected.py](../backend/tests/test_admin_connected.py): reserva, cancelación, aviso, bloqueo múltiple, resolución y CSV sin propietario.
- [test_me_reservation_concurrency.py](../backend/tests/test_me_reservation_concurrency.py) y las suites concurrentes de gestión, incidencias y CSV: conexiones distintas al mismo SQLite en disco.
- [ProductPage.test.tsx](../frontend/src/portal/ProductPage.test.tsx) y [MyReservationsPage.test.tsx](../frontend/src/portal/MyReservationsPage.test.tsx): fechas tras acceso, conflicto y respuesta propia; mocks HTTP no demuestran FastAPI.
- [test_startup.py](../backend/tests/test_startup.py), [test_spa.py](../backend/tests/test_spa.py) y [test_backup.py](../backend/tests/test_backup.py): migración, distribución y recuperación. Navegador y resultados ejecutados se registran aparte.

Hay registro público de clientes y dos roles persistidos. No hay varias empresas, pagos, cesta, recuperación de contraseña ni gestión completa de usuarios. Los listados no están paginados; no hay auditoría completa, prueba de carga ni alta disponibilidad. SQLite serializa escrituras; las cifras de pruebas no establecen capacidad de producción.

## Referencias oficiales y relación con este código

- [FastAPI: obtener usuario actual](https://fastapi.tiangolo.com/tutorial/security/get-current-user/): composición de dependencias, concretada en `get_current_user` y exigencias de rol.
- [FastAPI: OAuth2 scopes](https://fastapi.tiangolo.com/advanced/security/oauth2-scopes/): contexto de permisos granulares. RentaLab usa roles SQLite y sesiones con cookie; no implementa OAuth2, scopes ni JWT por citar esa guía.
- [React Router: rutas declarativas](https://reactrouter.com/start/declarative/routing): rutas anidadas y layouts aplicados en `App.tsx`.
- [React con TypeScript](https://react.dev/learn/typescript): props, estado y hooks tipados, junto a validación de API en ejecución.
- [Transacciones SQLite](https://www.sqlite.org/lang_transaction.html) y [SQLAlchemy/SQLite](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#legacy-transaction-mode-with-the-sqlite3-driver): contexto del turno de escritura explícito.

