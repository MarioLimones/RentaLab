# Empaquetado y operación de RentaLab

La imagen contiene el backend, las migraciones hasta `0009_reservation_origin` y React compilado. Node sólo se utiliza durante la construcción. FastAPI sirve catálogo, portal, panel y `/api` en un mismo origen; Vite no participa en producción. El volumen contiene **todo `/data`**, con SQLite en `/data/rentalab.db`, incluidas sus posibles dependencias `-wal`, `-shm` y `-journal`. Usuarios, sesiones, propiedad de reservas y avisos también persisten; creación explícita de administrador y transición en [ACCESO.md](ACCESO.md).

Esta demo utiliza una única instancia y un único worker. No escales el servicio ni arranques otra aplicación sobre ese volumen. No se ejecuta seed al arrancar. Las migraciones se aplican antes de abrir el puerto HTTP; un fallo impide servir peticiones.

## Preparación local y comprobaciones

El [README](../README.md#desarrollo-en-windows-con-powershell) contiene los bloques completos para instalar Python 3.12, dependencias con hashes, Node/npm, `npm ci`, generar la cuenta interactivamente, migrar y arrancar Uvicorn y Vite en PowerShell. [ACCESO.md](ACCESO.md) describe sesión y CSRF. Conserva `.env`; no lo incluyas en Git ni en la imagen.

Desde la raíz, cada bloque comienza en su propio directorio:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m ruff check .
..\.venv\Scripts\python.exe -m ruff format --check .
..\.venv\Scripts\python.exe -m pip check
..\.venv\Scripts\python.exe -m alembic current
..\.venv\Scripts\python.exe -m alembic check
```

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test
npm.cmd run build
```

Detén Vite antes de repetir `npm ci` en Windows: un módulo nativo abierto puede provocar `EPERM`. Si faltan migraciones, ejecuta `alembic upgrade head` antes de `alembic check`.

## Variables del servidor

| Variable | Uso |
| --- | --- |
| `RENTALAB_ENVIRONMENT` | `development` para HTTP local; `production` para HTTPS y cookie Secure |
| `RENTALAB_OPERATOR_USERNAME` | Opcional, administrador anterior durante transición; configurar junto al hash |
| `RENTALAB_OPERATOR_PASSWORD_HASH` | Opcional, hash Argon2id del operador anterior, entre comillas simples en `.env` |
| `RENTALAB_SESSION_SECRET` | Secreto aleatorio de al menos 32 caracteres |
| `RENTALAB_SESSION_TTL_SECONDS` | Caducidad absoluta, 3600 s por defecto, entre 1 y 86400 |
| `RENTALAB_PORT` | Puerto interno HTTP, 8000 por defecto |
| `RENTALAB_HOST_PORT` | Sólo Compose: puerto publicado en `127.0.0.1`, 8000 por defecto |
| `RENTALAB_DATABASE_URL` | URL SQLite; Compose usa `sqlite:////data/rentalab.db` por defecto |
| `RENTALAB_SQLITE_BUSY_TIMEOUT_MS` | Espera SQLite: 5000 ms por defecto; 0–60000 |
| `RENTALAB_FRONTEND_DIST` | Compilación pública; imagen: `/app/frontend/dist` |
| `RENTALAB_FORWARDED_ALLOW_IPS` | Direcciones de proxy de confianza; por defecto `127.0.0.1` |

Las claves foráneas se activan en cada conexión. El directorio de datos debe permitir crear la base y sus archivos auxiliares. La imagen usa UID/GID `10001:10001`, `/data` privado y código sin permisos de escritura para ese usuario. Un volumen nombrado nuevo hereda esos permisos. Si reutilizas un bind mount, prepara su directorio con propietario `10001:10001` y permisos `0700` antes de arrancar. No uses `chmod 777`.

Si sobrescribes `RENTALAB_DATABASE_URL` en Docker, mantén su ruta dentro de `/data`. Una URL absoluta de Windows no es válida para el contenedor: prepara otro archivo de entorno y úsalo siempre con `docker compose --env-file .env.docker …`. No cambies la ruta al actualizar sin un procedimiento de traslado/restauración.

Las credenciales sólo se pasan al contenedor en ejecución. No hay argumentos de construcción con secretos ni variables `VITE_` de autenticación. `.dockerignore` excluye entornos, bases, copias, herramientas y dependencias locales. El HTML y los recursos estáticos son públicos y sólo contienen la aplicación; los datos privados se solicitan después de validar sesión.

## Docker Compose en Windows: HTTP local

Prepara primero un archivo `.env` privado mediante el README, con un secreto de sesión aleatorio, y usa `RENTALAB_ENVIRONMENT=development`. No necesitas credenciales del operador anterior para usar cuentas SQLite: sus dos variables pueden quedar ausentes. Docker Desktop debe tener el motor Linux disponible. Desde la raíz:

```powershell
docker info
docker compose config --quiet
docker compose build --pull
docker compose up -d --wait
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/health
```

Abre `http://127.0.0.1:8000/catalogo`. La navegación y su recarga usan FastAPI; no arranques Vite para esta comprobación. El volumen se crea vacío, sin usuarios ni datos ficticios. Provisiona las cuentas y los equipos sólo mediante comandos explícitos:

```powershell
docker compose exec rentalab python -m rentalab.autenticacion.gestionar_usuarios create-admin --name "Administración ficticia" --email "admin@example.test"
docker compose exec rentalab python -m rentalab.autenticacion.gestionar_usuarios demo-users
docker compose exec rentalab python -m rentalab.cargar_datos
```

Los dos primeros comandos piden y confirman una contraseña sin eco. Elige una para el administrador y otra para los clientes ficticios `alicia.demo@example.test` y `bruno.demo@example.test`; no se incluyen valores de ejemplo ni cuentas por defecto. `demo-users` crea sólo las cuentas que falten y no modifica permisos ni contraseñas de las existentes. `create-admin` rechaza un correo ya registrado, sin promoverlo. `seed` no crea reservas ni incidencias ni reemplaza equipos existentes. Puedes registrar otros clientes desde `/registro`.

Para aprovisionamiento automatizado existe `--password-env NOMBRE_VARIABLE`: recibe el **nombre** de una variable ya presente en el entorno del comando, nunca la contraseña como argumento. No guardes su valor en el repositorio, un Dockerfile, una grabación ni el historial del terminal.

Si sólo necesitas generar el secreto y todavía no tienes Python en el host, puedes construir la imagen antes de procesar Compose:

```powershell
docker build --pull -t rentalab:local .
docker run --rm --entrypoint python rentalab:local -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Guarda la salida únicamente en `RENTALAB_SESSION_SECRET` del archivo privado. No la publiques. `docker build` no necesita credenciales; Compose exige el secreto al procesar su YAML. Para conservar acceso al operador anterior, mantén conjuntamente su nombre y hash; `python -m rentalab.autenticacion.hash_contrasena` sigue disponible como herramienta interactiva, pero no es necesaria para crear usuarios persistentes.

Comprueba `/catalogo`, `/mis-reservas` y `/admin` abriéndolas directamente y recargando: todas reciben el HTML compilado. React consulta la sesión real y aplica el destino de cada rol; una ruta privada sin acceso muestra el acceso o la denegación correspondiente. El HTML público no concede permisos: FastAPI protege cada operación de datos.

`docker compose logs --tail 100 rentalab` muestra arranque y migraciones. `docker compose down` conserva el volumen; **no uses `down --volumes`** para actualizar o recrear. El proyecto de Compose determina el nombre del volumen: conserva el mismo directorio/nombre de proyecto o indica siempre el mismo `--project-name`.

El healthcheck comprueba sólo `/health`; indica que el proceso responde después de migrar, no que el operador pueda acceder. Las API desconocidas devuelven JSON: 401 sin sesión y 404 con sesión. Un recurso estático que no existe devuelve 404; nunca devuelve `index.html`.

## Linux con volumen y proxy HTTPS

Prepara un servidor con Docker Engine, plugin Compose y Nginx siguiendo sus instrucciones oficiales. Copia el proyecto sin `.env` ni bases locales. Usa el mismo lock y Dockerfile. No es necesario instalar Node en el servidor.

Construye primero y prepara un `.env` privado (`chmod 600 .env`) con secreto, TTL y `RENTALAB_ENVIRONMENT=production`. Usuario y hash del operador anterior son opcionales y deben configurarse juntos si se conservan. Mantén el puerto del contenedor publicado únicamente en `127.0.0.1`. Elige un dominio real bajo tu control y proporciona un certificado TLS válido; no se solicita ninguno como parte de este proyecto.

```bash
docker build --pull -t rentalab:local .
# Preparar ahora .env privado: secreto, TTL y environment=production.
docker compose config --quiet
docker compose up -d --wait
docker compose ps
curl --fail http://127.0.0.1:8000/health
docker compose exec rentalab python -m rentalab.autenticacion.gestionar_usuarios create-admin --name "Administración" --email "admin@example.test"
```

Adapta [deploy/nginx.conf.example](../deploy/nginx.conf.example): sustituye dominio, certificados y puerto si cambió `RENTALAB_HOST_PORT`. Instálalo en el directorio de configuración de tu distribución, comprueba `sudo nginx -t` y recarga `sudo systemctl reload nginx`. La plantilla redirige HTTP a HTTPS y reenvía todas las rutas al mismo FastAPI, sin sustituir sus errores ni caché de API. Sólo se exponen al exterior 80/443; 8000 permanece local.

En Linux, el salto desde el proxy del host al contenedor puede aparecer con la dirección del gateway del bridge. Consulta las direcciones del contenedor y de su red:

```bash
docker inspect --format '{{range .NetworkSettings.Networks}}{{.Gateway}}{{end}}' "$(docker compose ps -q rentalab)"
```

Configura `RENTALAB_FORWARDED_ALLOW_IPS` con la dirección concreta observada del proxy, recrea el servicio y comprueba redirecciones HTTPS. No uses `*` si otros clientes pueden alcanzar directamente FastAPI. Nginx sobrescribe las cabeceras reenviadas; una cabecera enviada por Internet no se conserva como autoridad. La cookie Secure depende del modo `production`, no de una cabecera del cliente.

Comprueba por la URL HTTPS: catálogo y disponibilidad como visitante; acceso de cliente y `/mis-reservas` abierto directamente y recargado; acceso administrativo y `/admin`; una operación con CSRF, cierre y cookie con `Secure`, `HttpOnly` y `SameSite=Lax`. No intentes iniciar sesión por el HTTP directo de producción: el navegador no debe enviar allí su cookie Secure. Esta documentación no constituye un despliegue externo realizado.

## Actualizar conservando datos

Haz primero una copia coherente y guárdala fuera del volumen como se describe después. Después, con el mismo nombre de proyecto y volumen:

```powershell
docker compose build --pull
docker compose stop rentalab
docker compose up -d --force-recreate --wait
docker compose exec rentalab python -m alembic current
docker compose exec rentalab python -m alembic check
```

El nuevo arranque migra hasta `head` antes de aceptar peticiones. Si una migración falla, revisa el error y conserva el volumen: no reinicialices la base. Para una revisión explícita con el servicio detenido puedes ejecutar `docker compose run --rm --no-deps rentalab python -m alembic upgrade head` y luego arrancar. Las migraciones y los datos existentes se mantienen; el seed no forma parte de una actualización.

Volver a una imagen anterior no revierte el esquema. Si necesitas recuperar una copia previa, detén el servicio y restaura en una base compatible con aquella versión. Verifica siempre primero sobre una base temporal. Cada comando que devuelve un error debe detener el procedimiento; no continúes el arranque tras una migración/restauración fallida.

## Copias coherentes de SQLite

El comando utiliza `sqlite3.Conexion.backup`, que toma un snapshot consistente incluso si hay transacciones confirmadas aún en WAL. Valida integridad y claves foráneas. No copies únicamente `rentalab.db` mientras la aplicación escribe, ni combines un `.db` de una fecha con auxiliares de otra. SQLite administra `-wal`, `-shm` y `-journal`; no los borres para intentar quitar un bloqueo.

Desde PowerShell, con el servicio en ejecución:

```powershell
$backupName = 'rentalab-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.db'
New-Item -ItemType Directory -Force .tools\backups | Out-Null
docker compose exec rentalab python -m rentalab.copias_seguridad create "/data/backups/$backupName"
if ($LASTEXITCODE -ne 0) { throw 'No se ha creado la copia.' }
docker compose cp "rentalab:/data/backups/$backupName" ".tools/backups/$backupName"
if ($LASTEXITCODE -ne 0) { throw 'No se ha exportado la copia.' }
```

El destino de `create` debe ser nuevo: una copia anterior no se sobrescribe. `docker compose cp` exporta ese snapshot cerrado, no la base viva. `.tools` queda excluido de Git y del contexto Docker. Guarda una copia adicional fuera de este ordenador/servidor mediante tu procedimiento habitual, sin incluirla en el repositorio. Los backups contienen clientes, reservas y sesiones; protégelos como la base original.

En Linux puedes usar `backup_name="rentalab-$(date -u +%Y%m%d-%H%M%S).db"`, `mkdir -p backups`, `docker compose exec -T rentalab python -m rentalab.copias_seguridad create "/data/backups/$backup_name"` y `docker compose cp "rentalab:/data/backups/$backup_name" "backups/$backup_name"`. Conserva el directorio `backups` fuera del repositorio/contexto de construcción y con acceso restringido.

Sin Docker, desde `backend/`, usa `..\.venv\Scripts\python.exe -m rentalab.copias_seguridad create ..\.tools\backups\copia.db`. Se utiliza `RENTALAB_DATABASE_URL` de tu configuración. Las copias no necesitan credenciales de acceso de la SPA.

## Ensayar y realizar una restauración

Primero restaura en una base temporal dentro del volumen, sin tocar `/data/rentalab.db`. Usa un destino inexistente y distinto del servicio:

```powershell
docker compose run --rm --no-deps -e RENTALAB_DATABASE_URL=sqlite:////data/restore-check/rentalab.db rentalab python -m rentalab.copias_seguridad restore "/data/backups/$backupName" --app-stopped
if ($LASTEXITCODE -ne 0) { throw 'La restauración de ensayo ha fallado.' }
docker compose run --rm --no-deps -e RENTALAB_DATABASE_URL=sqlite:////data/restore-check/rentalab.db rentalab python -m alembic current
```

`--app-stopped` declara que ninguna aplicación usa **la base de destino**; en el ensayo la aplicación habitual usa otra ruta. Para comprobar sus datos abre el destino con SQLite o levanta una instancia temporal en otro puerto/volumen exclusivo. Nunca apuntes dos instancias al mismo destino durante la restauración.

Para recuperar la base real, conserva primero una copia del estado actual, detén el servicio y ejecuta:

```powershell
docker compose stop rentalab
docker compose run --rm --no-deps rentalab python -m rentalab.copias_seguridad restore "/data/backups/$backupName" --app-stopped
if ($LASTEXITCODE -ne 0) { throw 'Restauración fallida: mantener el servicio detenido.' }
```

El comando valida un snapshot temporal antes de restaurar mediante la propia API SQLite y no elimina auxiliares de una base en uso. El indicador no puede detectar procesos ajenos: cerrar todas las conexiones al destino es responsabilidad del operador. Cambia `RENTALAB_SESSION_SECRET` después de restaurar para invalidar sesiones que hubiera en la copia. A continuación `docker compose up -d --force-recreate --wait` aplica migraciones pendientes y carga la nueva configuración. Comprueba salud, acceso y las reservas recuperadas.

Para introducir una copia externa mientras el servicio está detenido puedes crear un contenedor detenido con `docker compose create`, usar `docker compose cp .tools/backups/copia.db rentalab:/data/backups/copia.db` sobre un directorio ya existente y ejecutar el mismo comando de restauración; conserva permisos de lectura para UID10001. Una alternativa es montar sólo el archivo de backup como lectura en un contenedor puntual. Nunca sustituyas a mano la base activa con `cp`.

## Recorrido reproducible de persistencia

1. Arranca Compose con un volumen nuevo y comprueba que `/api/public/equipment` devuelve `[]`. Crea explícitamente el administrador, los dos clientes ficticios y los equipos con los comandos anteriores.
2. Usa tres perfiles/sesiones independientes: administrador, Alicia y Bruno. Como Alicia, elige equipo y fechas en `/catalogo`, consulta disponibilidad, confirma y anota la referencia de reserva. Comunica un problema desde su detalle. Como administrador, comprueba propietario y origen `portal`, añade una respuesta pública y una nota interna distinta.
3. Recarga `/catalogo`, `/mis-reservas` y `/admin` directamente en sus sesiones. Alicia ve su reserva y respuesta pública; Bruno no ve su historial y recibe 404 al intentar sus identificadores por HTTP. `/api/no-existe` devuelve 404 JSON con sesión administrativa y 401 sin sesión; el detalle público de un equipo inexistente y `/assets/no-existe.js`, 404 JSON.
4. Ejecuta `docker compose up -d --force-recreate --wait`. Conservando secreto y volumen, recarga: cuentas, sesiones no caducadas, reserva con propietario y aviso permanecen. No ejecutes seed ni `down --volumes`.
5. Crea/exporta un backup, restaura sobre un destino temporal y comprueba identificador, propietario, datos y estado de la reserva y el aviso. La base habitual debe conservarlos. Los registros históricos/importados sin propietario siguen en administración y no se asignan al registrar su mismo correo.

Pruebas duraderas relacionadas: `tests/test_arranque.py` comprueba arranque vacío sin usuarios/datos y recreación de aplicación/motor con cuentas, cookies, propiedad y avisos persistidos; `tests/test_contrato_reservas_administrador.py::test_origen_migracion_preserva_propia_desconocido_y_vinculada_incidencia_filas` migra de `0008` a `head`, conserva todas las columnas previas y comprueba integridad y claves foráneas; `tests/test_spa.py` cubre GET/HEAD, recarga de rutas actuales y conservación de errores JSON 401/404/405/422. Son pruebas de aplicación, no un ensayo de volumen Docker.

Las comprobaciones realmente ejecutadas y sus limitaciones se registran en [PROYECTO.md](PROYECTO.md). No se confunde validar YAML o ejecutar TestClient con construir y recrear un contenedor real.

## Revisión de integración de la fase F

El 15/10/2026 se volvió a comprobar el motor: Docker CLI `29.2.0` y Compose `5.0.2` están instalados. Inicialmente faltaba el pipe `dockerDesktopLinuxEngine`; después de iniciar Docker Desktop, `docker version` devolvió HTTP 500 en `/v1.53/version` y una comprobación posterior agotó 20 segundos. Se detuvo Docker Desktop al terminar, sin crear contenedores ni volúmenes. `docker compose --env-file .env.example config --quiet` pasó usando un secreto temporal sólo en el entorno del proceso, sin mostrarlo ni modificar `.env`.

Se conservaron Dockerfile y Compose porque ya incluyen compilación multietapa, frontend/API con un origen, usuario sin privilegios, un worker, migración previa y volumen `/data`, sin seed automático. La construcción de la imagen, permisos reales del volumen, recreación del contenedor y HTTPS siguen pendientes de un motor operativo y un entorno de despliegue. Las pruebas de arranque, persistencia de aplicación/motor y rutas SPA se ejecutaron con SQLite temporal y TestClient; no sustituyen esas comprobaciones del contenedor.

Referencias: [backup de sqlite3 en Python](https://docs.python.org/3.12/library/sqlite3.html#sqlite3.Connection.backup), [volúmenes Docker](https://docs.docker.com/engine/storage/volumes/), [proxy Nginx](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_set_header) y [HTTPS en Nginx](https://nginx.org/en/docs/http/configuring_https_servers.html).

