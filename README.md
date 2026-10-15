# RentaLab

El catálogo presenta una ficha por modelo (mismo nombre y categoría), aunque existan varias unidades físicas. Cada reserva del portal asigna una unidad libre para todo el periodo dentro de la transacción: dos cámaras admiten dos alquileres coincidentes, y una solicitud adicional se rechaza al agotarse la disponibilidad. El calendario tiene en cuenta esa continuidad y las incidencias. A la derecha de «Ver equipo», la ficha muestra «N reserva(s)» y «En curso y próximas»: `active_reservations_count` suma las reservas confirmadas, sin cancelar, de las unidades activas del modelo con fin posterior a hoy en `Europe/Madrid`, independientemente de las fechas seleccionadas. Excluye las ya terminadas y las devoluciones de hoy. Pulsar el recuento consulta `/api/public/equipment/{id}/reservations` y despliega debajo las fechas de recogida y devolución en orden cronológico, sin datos privados, con estado vacío y opción de reintento ante errores. Los intervalos se muestran por separado aunque coincidan, y la devolución es exclusiva. El recuento y las fechas no indican la capacidad ni la disponibilidad completa del modelo. Administración, CSV y las reservas existentes conservan su unidad física. [Contrato de catálogo y reservas por modelo](docs/CATALOGO_PUBLICO.md).

La ampliación **A–F** integra catálogo público, portal de cliente y panel `/admin` en una sola aplicación React/FastAPI y una base SQLite. Cada cliente accede sólo a sus reservas y avisos; administración conserva la gestión global, importaciones y registros históricos sin propietario. Registrar un correo coincidente nunca asigna ese historial.

La fase F revisa la integración, añade pruebas de recorridos y concurrencia entre portal, administración y CSV, y comprueba rutas directas, migración, base vacía y reinicio persistente. Consulta el [balance ejecutado y los límites pendientes](docs/VALIDACION_INTEGRADA.md), la [matriz de permisos](docs/ACCESO.md#matriz-de-permisos) y el [registro completo](docs/PROYECTO.md).

La [lista guardada](docs/LISTA_GUARDADA.md) permite conservar productos en la cuenta, comparar su disponibilidad en un calendario común y reservar varios para el mismo periodo. La confirmación es atómica: si falla un producto no se crea ninguna reserva del envío.

El esquema vigente es `0011_booking_requests`. Conserva los favoritos de `0010` y añade solicitudes de reserva persistidas por cliente: reintentar una confirmación individual o conjunta con la misma clave recupera sus reservas originales, sin consumir otras unidades. El portal conserva la operación al recargar y ofrece preparar otra reserva de forma explícita. Aplica las migraciones antes de iniciar el backend actualizado. Los datos anteriores conservan sus relaciones y su origen; cuentas y equipos ficticios se crean con comandos explícitos, sin carga automática al arrancar.

El regreso desde una ficha conserva los filtros del catálogo y restaura la posición cuando el intervalo no cambia. Los guardados administrativos que terminan después de abandonar un formulario respetan la pantalla elegida. Nombre, categoría y descripción de equipos rechazan caracteres NUL mediante validación, sin escrituras parciales ni errores internos.

Verificación final de F: **856 pruebas backend y 331 frontend correctas**, Ruff, TypeScript estricto, ESLint y build correctos. Se conserva una omisión POSIX y una advertencia conocida de Starlette/TestClient. El recorrido real se ha comprobado con tres sesiones Edge aisladas, móvil y reinicio, con React compilado servido por FastAPI. Compose valida; la construcción/ejecución Docker continúa pendiente por fallo del motor Linux. No se han publicado servicios externos.

| Acceso | Entrada y operaciones |
| --- | --- |
| Visitante | `/catalogo`, `/equipos/:id`; características y disponibilidad por fechas bajo `/api/public` |
| Cliente | `/mis-reservas`, `/mis-incidencias`, `/mi-cuenta`; sólo recursos propios bajo `/api/me`, cancelación antes del inicio y avisos inicialmente no bloqueantes |
| Administrador | `/admin`; equipos, reservas globales, avisos/bloqueos/respuesta pública e importaciones |

El [portal](docs/PORTAL_CLIENTE.md), las [operaciones propias](docs/OPERACIONES_CLIENTE.md) y el [panel](docs/ADMINISTRACION.md) contienen pantallas y contratos completos.

Aplicación demostrativa para una empresa ficticia de alquiler de material audiovisual. Código en inglés; interfaz y documentación en español. Las fases 1–8 cubren catálogo, reservas, incidencias e importaciones CSV, panel React conectado a FastAPI, SQLite, sesión/CSRF, empaquetado persistente y revisión final para estudiar y explicar el proyecto.

La **fase A** amplía el alcance a usuarios y roles: registro de clientes, acceso/sesión/cierre, administrador persistido creado mediante comando explícito, permisos de backend y migración que conserva los datos anteriores. El operador existente sigue disponible durante la transición. Consulta la [matriz y contratos vigentes](docs/ACCESO.md).

La **fase B** añade la [API de catálogo público](docs/CATALOGO_PUBLICO.md) bajo `/api/public`: equipos activos, búsqueda por nombre/categoría y disponibilidad por fechas sin datos privados. Añade descripción pública, características técnicas e imagen opcional con alternativa SVG local. Las rutas anteriores de equipos son de gestión administrativa.

Verificación registrada de fase B: suite backend con **648 correctas** y cinco casos adicionales después verificados en las **47 pruebas dirigidas** de catálogo; **159 frontend**, linters, TypeScript y build correctos. Una omisión POSIX y advertencia conocida. En esa fase la base local quedó en `0007`, con copia previa y datos conservados. [Registro completo](docs/PROYECTO.md#comprobaciones-reales-de-la-fase-b).

Comprobaciones registradas en fase A: **549 pruebas backend y 159 frontend correctas**, TypeScript estricto, Ruff, ESLint y build correctos. Se mantiene una omisión por permisos POSIX en Windows y la advertencia conocida de Starlette/TestClient. En esa fase se migró la base local a `0006` con copia previa y datos conservados; no se cargaron cuentas automáticamente. Detalle en [PROYECTO.md](docs/PROYECTO.md#comprobaciones-reales-de-la-fase-a).

Consulta el [contrato y las decisiones del proyecto](docs/PROYECTO.md), la [preparación y el contrato de acceso](docs/ACCESO.md), el [recorrido de la interfaz](docs/INTERFAZ.md), los [contratos de reservas](docs/RESERVAS.md), los [contratos de incidencias](docs/INCIDENCIAS.md) y el [formato CSV e informe de importación](docs/IMPORTACIONES.md).

[DESPLIEGUE.md](docs/DESPLIEGUE.md) reúne Compose local, Linux con proxy HTTPS, permisos, actualización, backup y restauración de SQLite, junto con el recorrido para comprobar persistencia al recrear el contenedor.

## Para estudiar y presentar el proyecto

1. [ARQUITECTURA.md](docs/ARQUITECTURA.md): sigue una reserva desde el formulario y el cliente TypeScript hasta la API, el servicio y SQLite, con archivos y funciones reales.
2. [GUIA_DE_ESTUDIO.md](docs/GUIA_DE_ESTUDIO.md): explica intervalos, transacciones, incidencias, CSV y pruebas; incluye preguntas respondidas y tres ejercicios pequeños.
3. [DEMO_LEANMIND.md](docs/DEMO_LEANMIND.md): propuesta de screencast de **8:30**, preparación en una base nueva, recorrido funcional y explicación fiel de la asistencia de IA y del proceso de pruebas. No es un vídeo ya grabado.

El código, las pruebas y la documentación se han elaborado y revisado con asistencia de Codex y agentes. El registro distingue pruebas ejecutadas primero en rojo, comprobaciones añadidas ya verdes y limitaciones de herramientas. No se atribuye experiencia profesional ni un historial de TDD estricto a todo el repositorio.

## Balance histórico de la revisión de fase 8

Están implementados el catálogo, las reservas con cancelación, la disponibilidad compartida, las incidencias, la importación parcial e idempotente y el acceso del operador. La revisión no reprodujo defectos materiales nuevos que justificasen cambiar la arquitectura, las reglas o las pruebas existentes.

- Backend: **482 pruebas correctas, una omitida por permisos POSIX en Windows y una advertencia conocida de Starlette/TestClient**. Ruff check/format y `pip check` correctos.
- Frontend: `npm ci`, typecheck, lint, **145 pruebas Vitest** y build correctos.
- Comprobaciones reales: acceso correcto/incorrecto, conflicto con entradas conservadas, cancelación, bloqueo por incidencia, resolución, nueva reserva, rutas/refresco, cierre móvil, CSRF y errores JSON; reinicio y restauración local sobre bases aisladas conservan los datos.
- La construcción Docker se intentó y falló por error 500 del motor Linux. Compose se valida, pero imagen, permisos Linux, recreación del volumen y proxy HTTPS real siguen pendientes. La subida CSV automatizada en navegador continúa sin verificar por el rechazo de permisos registrado en la fase 5; sus contratos multipart y representación pasan en pytest/Vitest. No se eludió ese rechazo.

La fase A sustituye el límite de una cuenta por **usuarios `customer`/`admin`**. Se mantiene una instancia/un worker y las escrituras SQLite serializadas. No incluye recuperación de contraseña, limitación de intentos de acceso, paginación, pagos ni auditoría completa. La garantía contra solapamientos exige usar los servicios; SQL directo puede saltarse esa regla. No se ha medido capacidad bajo carga. Los resultados actuales se registran en [PROYECTO.md](docs/PROYECTO.md).

[PROYECTO.md](docs/PROYECTO.md#comprobaciones-reales-de-la-fase-8) recoge comandos, resultados, aislamiento, alcance y pasos pendientes. No se ha contratado ni realizado un despliegue externo.

## Requisitos

- Python 3.12 (comprobado con 3.12.15) y el lanzador `py` de Windows.
- Node.js 24.13.0 LTS y npm 11.12.1. La versión de Node queda indicada en `.nvmrc`; si se usa otro gestor de versiones, selecciónala antes de instalar.
- Docker Desktop con el motor Linux iniciado, solo para la opción Docker.

Las dependencias Python están fijadas con hashes en `backend/requirements.lock` y `backend/requirements-dev.lock`. El frontend usa `frontend/package-lock.json`; instala con `npm ci`.

## Desarrollo en Windows con PowerShell

Desde la raíz del repositorio:

```powershell
if (-not (Test-Path .venv\Scripts\python.exe)) { py -3.12 -m venv .venv }
.\.venv\Scripts\python.exe -m pip install --require-hashes -r .\backend\requirements-dev.lock
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Primero configura `RENTALAB_SESSION_SECRET` en `.env`. Si ya tienes un secreto válido, consérvalo y salta este bloque. Para una instalación nueva, el siguiente comando genera uno sin imprimirlo y conserva las demás variables:

```powershell
$initialSessionSecret = (& .\.venv\Scripts\python.exe -c 'import secrets; print(secrets.token_urlsafe(48))')
if ($LASTEXITCODE -ne 0) { throw 'No se ha generado el secreto; no se modifica .env.' }
$initialEnvLines = @(Get-Content -LiteralPath .env | Where-Object {
  $_ -notmatch '^\s*RENTALAB_SESSION_SECRET\s*='
})
[System.IO.File]::WriteAllLines(
  (Join-Path (Get-Location) '.env'),
  [string[]]($initialEnvLines + "RENTALAB_SESSION_SECRET='$initialSessionSecret'"),
  [System.Text.UTF8Encoding]::new($false)
)
Remove-Variable initialSessionSecret, initialEnvLines
```

Después crea las cuentas **explícitamente**, desde la raíz:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m rentalab.auth.manage_users create-admin --name "Administración local" --email "admin@example.test"
# Opcional: Alicia Demo y Bruno Demo; sin reservas asociadas.
..\.venv\Scripts\python.exe -m rentalab.auth.manage_users demo-users
Set-Location ..
```

Cada comando de cuentas pide contraseña y confirmación sin eco. `demo-users` crea `alicia.demo@example.test` y `bruno.demo@example.test` con la contraseña elegida para ese comando; no cambia cuentas existentes. `create-admin` rechaza un correo existente sin promoverlo. En automatización, `--password-env NOMBRE_VARIABLE` recibe el nombre de una variable ya aprovisionada, nunca una contraseña literal. No se cargan cuentas al arrancar. [ACCESO.md](docs/ACCESO.md#preparación-y-transición) documenta el contrato.

La preparación siguiente es **opcional y exclusiva del operador anterior durante la transición**; no es necesaria para las cuentas SQLite creadas arriba. Si ya existe esa configuración, consérvala. El ejemplo usa `operador`; tú eliges la contraseña interactivamente. Conserva las demás variables de `.env` y sólo reemplaza usuario, hash y secreto:

```powershell
Set-Location backend
$demoPasswordHash = (& ..\.venv\Scripts\python.exe -m rentalab.auth.hash_password)
if ($LASTEXITCODE -ne 0) { throw 'No se ha generado el hash; no se modifica .env.' }
$demoSessionSecret = (& ..\.venv\Scripts\python.exe -c 'import secrets; print(secrets.token_urlsafe(48))')
if ($LASTEXITCODE -ne 0) { throw 'No se ha generado el secreto; no se modifica .env.' }
Set-Location ..
$localEnvLines = @(Get-Content -LiteralPath .env | Where-Object {
  $_ -notmatch '^\s*RENTALAB_(OPERATOR_USERNAME|OPERATOR_PASSWORD_HASH|SESSION_SECRET)\s*='
})
[System.IO.File]::WriteAllLines(
  (Join-Path (Get-Location) '.env'),
  [string[]]($localEnvLines + @(
    'RENTALAB_OPERATOR_USERNAME=operador',
    "RENTALAB_OPERATOR_PASSWORD_HASH='$demoPasswordHash'",
    "RENTALAB_SESSION_SECRET='$demoSessionSecret'"
  )),
  [System.Text.UTF8Encoding]::new($false)
)
Remove-Variable demoPasswordHash, demoSessionSecret
```

La contraseña no se escribe en el comando ni en `.env`; sólo se guarda el hash. No repitas la preparación para cada arranque: reemplazar credenciales o secreto invalida sesiones anteriores. El TTL por defecto es una hora, configurable mediante `RENTALAB_SESSION_TTL_SECONDS`. `.env.example` no contiene valores secretos utilizables. La carga opcional `rentalab.demo` tiene cuentas ficticias con credenciales públicas documentadas y distintas de las credenciales elegidas con esta preparación.

Después, desde la raíz, aplica migraciones y arranca:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m rentalab.seed
..\.venv\Scripts\python.exe -m uvicorn rentalab.main:app --reload --host 127.0.0.1 --port 8000
```

La copia de `.env` se hace una sola vez; conserva tu archivo si ya existe. No es necesario activar el entorno virtual ni cambiar la política de ejecución de PowerShell. Las migraciones se ejecutan explícitamente; iniciar FastAPI no crea tablas ni borra datos. La carga ficticia es opcional y repetible: añade las unidades de demostración que falten, sin duplicarlas.

En esta carpeta ya está preparado `.venv` con Python 3.12.15. La máquina tenía únicamente Python 3.14 registrado en `py`, por lo que la creación con `py -3.12` necesita instalar previamente Python 3.12. La alternativa que se ejecutó aquí fue descargar Python dentro del proyecto con uv, sin cambiar PATH ni el registro de Windows. Para repetirla desde la raíz en Windows de 64 bits con algún Python ya instalado y sin `.venv`:

```powershell
py -3 -m pip install --target .tools\uv uv==0.13.1
.\.tools\uv\bin\uv.exe python install 3.12.15 --install-dir .tools\python --no-bin --no-registry
.\.tools\uv\bin\uv.exe venv .venv --python .tools\python\cpython-3.12.15-windows-x86_64-none\python.exe --seed
```

Después continúa con la instalación `pip --require-hashes` y las migraciones del primer bloque. `.tools` es una herramienta local de preparación, no una dependencia de la aplicación ni un archivo versionado.

En otra terminal PowerShell, desde la raíz:

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run dev -- --host 127.0.0.1
```

Abre [el catálogo RentaLab](http://127.0.0.1:5173/catalogo) o [administración](http://127.0.0.1:5173/admin) con una cuenta administradora. Vite reenvía `/api` y `/health` a `http://127.0.0.1:8000`. El cliente React usa rutas relativas; no contiene secretos ni decide reglas de negocio. [PORTAL_CLIENTE.md](docs/PORTAL_CLIENTE.md) explica el recorrido público y propio; [INTERFAZ.md](docs/INTERFAZ.md) conserva el recorrido administrativo y sus comprobaciones.

Puedes comprobar el backend desde una tercera terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Catálogo y disponibilidad son públicos bajo `/api/public`. La gestión requiere sesión administrativa: 401 sin sesión y 403 con rol cliente. React permite registrar clientes y acceder con la cuenta preparada; PowerShell tiene su [auxiliar de sesión y CSRF](docs/ACCESO.md#api-desde-powershell), que conserva `Invoke-RentaLab` para los ejemplos existentes. Navegador y terminal tienen cookies independientes.

Si el puerto 8000 está ocupado, detén el proceso de desarrollo anterior o cambia tanto el puerto de Uvicorn como el destino del proxy en `frontend/vite.config.ts`.

## Demostración de reservas con varios clientes

Desde `backend`, después de aplicar las migraciones:

```powershell
..\.venv\Scripts\python.exe -m rentalab.demo
# O fija una fecha base de hoy o futura:
..\.venv\Scripts\python.exe -m rentalab.demo --base-date 2026-10-15
```

Es una carga local explícita y repetible: un administrador, cinco clientes con acceso independiente (Elena sin reservas), cuatro unidades físicas y seis reservas, incluidas consecutivas y una cancelada. Conserva registros y contraseñas existentes. No se ejecuta al arrancar y se rechaza en `production`. Las [cuentas, fechas y pasos con dos sesiones independientes](docs/RESERVAS_MULTIUSUARIO.md) permiten probar el calendario y el conflicto 409 al confirmar fechas recién ocupadas.

Para ampliar esa demostración con **20 equipos adicionales con fotografías locales y 10 reservas confirmadas**, ejecuta desde `backend`:

```powershell
..\.venv\Scripts\python.exe -m rentalab.catalogue_demo
```

Requiere al menos un cliente activo; reparte las reservas entre los primeros cuatro clientes activos existentes, sin crear cuentas. En la demostración anterior corresponden a Alicia, Bruno, Carla y Diego, y Elena sigue sin reservas. Admite `--base-date YYYY-MM-DD` y por defecto empieza hoy en Madrid, con intervalos distintos durante las dos semanas siguientes. Repetir conserva fichas, fechas y cancelaciones existentes, sin duplicados; los conflictos se informan sin sobrescribir datos. No se ejecuta al arrancar y se rechaza en producción. Las fotografías son ilustrativas de los equipos ficticios y sus [autores y licencias](backend/rentalab/public_catalogue/assets/photo-credits.txt) se sirven también desde el enlace de créditos del catálogo.

## API administrativa de equipos

| Método | Ruta | Comportamiento |
| --- | --- | --- |
| GET | `/health` | Estado de la aplicación: `{"status":"ok"}` |
| POST | `/api/equipment` | Crear una unidad física |
| GET | `/api/equipment` | Listar unidades, incluidas las inactivas |
| GET | `/api/equipment/{equipment_id}` | Consultar una unidad |
| PUT | `/api/equipment/{equipment_id}` | Reemplazar los datos editables de una unidad |
| PATCH | `/api/equipment/{equipment_id}` | Editar campos o cambiar `active` |

Cada unidad administrativa expone `id`, `code`, `name`, `category`, `description`, `active` y los campos de publicación `public_description`, `technical_specs` e `image_url`. El servidor elimina espacios exteriores de `code` y lo pasa a mayúsculas antes de guardarlo; SQLite impone su unicidad. Un código ya registrado responde con 409, datos inválidos con 422 y una unidad inexistente con 404. Desactivar conserva su registro y lo retira del catálogo público. No hay borrado físico.

`code` admite de 1 a 40 caracteres normalizados: letras ASCII, números, guion y guion bajo, empezando por letra o número. `name` y `category` son obligatorios (hasta 120 y 80 caracteres); descripción interna y pública admiten hasta 2000 y por defecto son vacías; `active` es un booleano real y por defecto vale `true`. `technical_specs` admite hasta 20 pares de nombre/valor (80/300 caracteres); `image_url` es opcional, HTTPS o ruta pública local, hasta 2048 caracteres. Se recortan los espacios exteriores de los textos. `PATCH` exige algún campo y conserva los omitidos; sólo `image_url` admite `null`, para retirar la imagen. `PUT` exige `code`, `name` y `category`, y restablece los opcionales omitidos a sus valores por defecto. La lista se ordena por código y permite `?active=true` o `?active=false`. El [contrato administrativo](docs/ADMINISTRACION.md) explica la edición y su separación del catálogo público.

La documentación interactiva está en [Swagger UI](http://127.0.0.1:8000/api/docs), [ReDoc](http://127.0.0.1:8000/api/redoc) y [el esquema OpenAPI](http://127.0.0.1:8000/api/openapi.json). Requieren la sesión del navegador; las escrituras necesitan además CSRF. `/health` y los endpoints necesarios para acceder siguen públicos.

## API de reservas de la fase 2

| Método | Ruta | Comportamiento |
| --- | --- | --- |
| POST | `/api/reservations` | Confirmar una reserva sin solapamientos |
| GET | `/api/reservations` | Listar; filtros `customer`, `customer_user_id`, `equipment_id`, `origin`, `status`, `start_date` y `end_date` |
| GET | `/api/reservations/{reservation_id}` | Consultar la reserva y su estado |
| POST | `/api/reservations/{reservation_id}/cancel` | Cancelar de forma idempotente, conservando el historial |
| GET | `/api/equipment/{equipment_id}/availability?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` | Calcular disponibilidad para un intervalo |

Las fechas siguen `[inicio, fin)`: del 10 al 12 ocupa los días 10 y 11 y admite otra reserva desde el 12. La creación comprueba el equipo activo y las reservas confirmadas dentro de `BEGIN IMMEDIATE`, antes de insertar. Una cancelada no bloquea; la referencia externa, si existe, sigue siendo única tras cancelar. La disponibilidad se calcula y no se guarda como un booleano.

Consulta [RESERVAS.md](docs/RESERVAS.md) para cuerpos JSON, filtros, errores, ejemplos PowerShell y el detalle transaccional. SQLite espera hasta 5000 ms por defecto; `RENTALAB_SQLITE_BUSY_TIMEOUT_MS` permite cambiar ese límite. Si lo agota, devuelve 503 con `Retry-After: 1` y revierte la operación. El 409 queda reservado a conflictos de negocio, como fechas ocupadas.

La [fase E](docs/ADMINISTRACION.md#reservas-propietario-y-origen) añade a la respuesta administrativa propietario nullable y origen asignado por el servidor; no son campos de entrada. El filtro de cliente busca una subcadena literal en nombre o correo, sin distinguir mayúsculas Unicode. La cuenta exacta usa `customer_user_id`; el correo nunca vincula automáticamente históricos.

## API de incidencias de la fase 3

| Método | Ruta | Comportamiento |
| --- | --- | --- |
| POST | `/api/incidents` | Registrar una incidencia abierta y avisar de reservas confirmadas |
| GET | `/api/incidents` | Listar; filtros `equipment_id`, `status`, `priority` y `blocking` |
| GET | `/api/incidents/{incident_id}` | Consultar la incidencia y el aviso actual |
| PATCH | `/api/incidents/{incident_id}` | Gestionar prioridad, bloqueo, notas internas y respuesta pública |
| PATCH | `/api/incidents/{incident_id}/status` | Avanzar a `in_progress` o resolver con una explicación |

Una incidencia bloqueante `open` o `in_progress` impide nuevas reservas. Resolverla sólo deja de bloquear cuando no quedan otras bloqueantes sin resolver; el equipo todavía debe estar activo y libre para el rango. Registrar y resolver incidencias conserva las reservas existentes y devuelve sus identificadores en un aviso. Consulta [INCIDENCIAS.md](docs/INCIDENCIAS.md) para transiciones, validación, transacciones y ejemplos PowerShell.

## API de importaciones de la fase 4

| Método | Ruta | Comportamiento |
| --- | --- | --- |
| POST | `/api/imports` | Subir un CSV UTF-8 en el campo multipart `file` y recibir un informe por fila |
| GET | `/api/imports/example` | Descargar un CSV con tres pedidos ficticios |

La cabecera exacta es `external_reference,customer_name,customer_email,equipment_code,starts_on,ends_on`. Se aceptan comas y UTF-8 con o sin BOM, hasta 1 MiB y 500 registros de datos. Los límites, la cabecera y la estructura se validan antes de insertar. Cada fila correcta crea una reserva en su propia transacción, con las mismas reglas de equipos, solapamientos e incidencias del alta manual. Una referencia repetida con datos normalizados idénticos informa «ya importada», incluso si la reserva está cancelada; cambiar esos datos produce un rechazo sin sobrescribir.

Desde la raíz en PowerShell, con el backend, el catálogo ficticio y la sesión `$apiSession`/`$apiHeaders` de [ACCESO.md](docs/ACCESO.md#api-desde-powershell) preparados y todavía abiertos:

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

Usa `curl.exe` para evitar el alias de Windows PowerShell. Si los equipos del ejemplo están libres, la primera subida acepta tres y la siguiente informa de tres ya importadas. El archivo sólo se descarga en el equipo del usuario; el servidor no guarda la subida. [IMPORTACIONES.md](docs/IMPORTACIONES.md) documenta el informe HTTP 200, los errores globales 413/422 y los reintentos de importaciones parciales.

## Acceso de la fase 6

`GET /api/auth/session` consulta la identidad o devuelve 401. `GET /api/auth/csrf` obtiene el token vinculado a la cookie. `POST /api/auth/login` recibe usuario/contraseña y `POST /api/auth/logout` revoca la sesión; ambos exigen `X-CSRF-Token`. La cookie es HttpOnly y SameSite=Lax, y Secure en producción HTTPS. La nueva migración guarda sesiones revocables y expira por defecto en una hora, sin prolongarse por actividad. [ACCESO.md](docs/ACCESO.md) describe configuración, respuestas, React y ejemplos autenticados.

## Comprobaciones

Desde la raíz, para Python:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m pytest
..\.venv\Scripts\python.exe -m ruff check .
..\.venv\Scripts\python.exe -m ruff format --check .
```

Desde la raíz, para React:

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test
npm.cmd run build
```

`pytest` usa bases SQLite temporales aisladas; no modifica `data/rentalab.db`. Las fixtures se autentican y obtienen CSRF de verdad; se conservan concurrencia y bloqueos de negocio. Incluye acceso, revocación, expiración y configuración. Las pruebas React comprueban también acceso, recuperación de 401, cierre, rutas profundas y respuestas antiguas. El registro real está en `docs/PROYECTO.md`.

## Frontend compilado y Docker

La imagen compila React con `npm ci` y sirve tanto el frontend como la API desde FastAPI, en un mismo origen. Prepara primero `.env` con el secreto de sesión; usuario/hash del operador anterior son opcionales y se conservan juntos sólo durante la transición. Para una demostración exclusivamente local por HTTP usa `RENTALAB_ENVIRONMENT=development`; para producción usa `production` y HTTPS delante de FastAPI. Ejecuta desde la raíz:

```powershell
docker compose config --quiet
docker compose build --pull
docker compose up -d --wait
docker compose exec rentalab python -m rentalab.auth.manage_users create-admin --name "Administración local" --email "admin@example.test"
docker compose exec rentalab python -m rentalab.auth.manage_users demo-users
docker compose exec rentalab python -m rentalab.seed
docker compose logs rentalab
```

Los comandos de cuentas piden contraseñas sin eco. Las cuentas ficticias y el seed son opcionales y explícitos; no hay cuentas predeterminadas. Para la demostración HTTP local abre [el catálogo](http://127.0.0.1:8000/catalogo); en producción abre su URL HTTPS. Comprueba también `/mis-reservas` y `/admin` directamente y al recargar con cada rol. El contenedor aplica migraciones y no carga datos automáticamente. SQLite, usuarios, propiedad de reservas, avisos y sesiones viven en el volumen `rentalab-data` montado en `/data`. `docker compose down` conserva ese volumen; `docker compose down --volumes` lo elimina, por lo que no se usa en el flujo normal.

La imagen ejecuta la aplicación como UID/GID 10001, con un worker, código sin escritura y `/data` persistente. Puerto interno `RENTALAB_PORT` y puerto externo `RENTALAB_HOST_PORT` valen 8000 por defecto. Si has configurado una URL SQLite propia de Windows, usa un archivo de entorno separado para Compose con `RENTALAB_DATABASE_URL=sqlite:////data/rentalab.db`. Docker Desktop debe tener su motor Linux activo. La configuración de Compose puede comprobarse sin motor; construir o arrancar la imagen requiere el motor.

Si necesitas construir antes de preparar el secreto, usa `docker build --pull -t rentalab:local .`; Compose exige `RENTALAB_SESSION_SECRET` al procesar su YAML. Las instrucciones completas de [despliegue, generación del secreto y restauración](docs/DESPLIEGUE.md) no requieren instalar Python en el host Linux. Validar Compose no demuestra que la imagen o el volumen funcionen: el [balance F](docs/VALIDACION_INTEGRADA.md) registra el fallo actual del motor Docker y los pasos pendientes.

También puedes servir la compilación sin Docker. Después de `npm.cmd run build`, desde la raíz:

```powershell
$env:RENTALAB_FRONTEND_DIST = (Resolve-Path .\frontend\dist).Path
Set-Location backend
..\.venv\Scripts\python.exe -m uvicorn rentalab.main:app --host 127.0.0.1 --port 8000
```

Las variables de entorno prevalecen sobre `.env`. Al terminar ese proceso, puedes quitar la variable de la sesión con `Remove-Item Env:RENTALAB_FRONTEND_DIST`.
