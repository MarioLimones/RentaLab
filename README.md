# RentaLab

Aplicación web para gestionar el alquiler de material audiovisual: catálogo público, reservas por fechas, portal de cliente y panel de administración.

Construida con **React, TypeScript, FastAPI y SQLite**. La interfaz y la documentación están en español; el código, en inglés.

## Funcionalidades

- **Catálogo público:** búsqueda por nombre y categoría, fichas con imágenes y características técnicas, calendario de disponibilidad y consulta de fechas reservadas sin datos privados.
- **Reservas por modelo:** una ficha agrupa varias unidades físicas; al confirmar se asigna una unidad disponible durante todo el periodo.
- **Lista guardada:** productos vinculados a la cuenta, calendario compartido y reserva conjunta. Si un producto no está disponible, no se confirma ninguno del envío.
- **Portal de cliente:** registro, acceso, consulta y cancelación de reservas propias antes de su inicio, comunicación de incidencias y datos de la cuenta.
- **Administración:** gestión de equipos, reservas globales e incidencias, bloqueos de disponibilidad, notas internas y respuestas públicas.
- **Importación CSV:** validación e informe por fila, importación parcial y reintentos sin duplicar reservas.
- **Acceso por roles:** permisos comprobados en el backend, sesiones revocables, contraseñas con Argon2id y protección CSRF.
- **Persistencia:** migraciones con Alembic y almacenamiento SQLite, con volumen dedicado en Docker.

## Tecnologías

| Área | Tecnologías |
| --- | --- |
| Frontend | React 19, TypeScript, React Router y Vite |
| Backend | Python 3.12, FastAPI y Pydantic |
| Base de datos | SQLite, SQLAlchemy 2 y Alembic |
| Pruebas | pytest, Vitest y Testing Library |
| Calidad | Ruff, ESLint y TypeScript estricto |
| Empaquetado | Docker, Docker Compose y Uvicorn |

## Requisitos

- Python **3.12** y el lanzador `py` para los comandos de Windows.
- Node.js **24.13.0**, indicado en `.nvmrc`, y npm **11.x**. El gestor fijado es npm 11.12.1.
- Docker con motor Linux, si utilizas la opción de contenedores.

Las dependencias Python están fijadas con hashes en `backend/requirements.lock` y `backend/requirements-dev.lock`. El frontend utiliza `frontend/package-lock.json`.

## Desarrollo en Windows con PowerShell

Ejecuta los comandos desde la carpeta donde hayas clonado el repositorio.

### 1. Instalar el backend

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r .\backend\requirements-dev.lock
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Genera un secreto de sesión para la instalación nueva:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
```

Copia el resultado en `RENTALAB_SESSION_SECRET` dentro de `.env` y conserva `RENTALAB_ENVIRONMENT=development` para el acceso HTTP local. Mantén el secreto existente si ya tenías una instalación configurada. `.env` está excluido de Git.

### 2. Aplicar migraciones y crear el administrador

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m rentalab.auth.manage_users create-admin --name "Administración local" --email "admin@example.test"
Set-Location ..
```

El comando solicita la contraseña y su confirmación sin mostrarlas en pantalla. Los clientes pueden crear su cuenta desde `/registro`. El arranque no crea cuentas ni carga datos automáticamente.

### 3. Arrancar la API

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m uvicorn rentalab.main:app --reload --host 127.0.0.1 --port 8000
```

### 4. Arrancar el frontend

En otra terminal, desde la raíz:

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

Abre el [catálogo local](http://127.0.0.1:5173/catalogo). Vite redirige `/api` y `/health` al backend en el puerto 8000.

No necesitas activar el entorno virtual ni modificar la política de ejecución de PowerShell. En arranques posteriores basta con iniciar backend y frontend; aplica las migraciones cuando actualices el esquema.

### Datos de ejemplo opcionales

Para añadir equipos ficticios sin crear reservas ni cuentas, desde la raíz:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m rentalab.seed
Set-Location ..
```

La carga conserva los equipos existentes y puede repetirse. También puedes crear clientes ficticios con `rentalab.auth.manage_users demo-users`, que solicita una contraseña, o gestionar los equipos desde `/admin`.

## Pantallas y acceso

| Ruta | Acceso | Contenido |
| --- | --- | --- |
| `/catalogo` | Público | Catálogo, filtros y disponibilidad |
| `/equipos/:id` | Público | Ficha del modelo y calendario |
| `/acceso` y `/registro` | Público | Inicio de sesión y registro de clientes |
| `/mi-lista` | Cliente | Productos guardados y reserva conjunta |
| `/mis-reservas` | Cliente | Reservas propias y cancelación |
| `/mis-incidencias` | Cliente | Comunicación y seguimiento de avisos propios |
| `/mi-cuenta` | Cliente | Datos de la cuenta |
| `/admin` | Administrador | Gestión global e importaciones |

Cada cliente accede únicamente a sus recursos. Las reservas históricas sin propietario no se vinculan automáticamente por coincidencia de correo.

## Reglas de disponibilidad

Las reservas utilizan intervalos **[inicio, fin)**: una reserva del 10 al 12 ocupa los días 10 y 11; otra puede comenzar el día 12.

La disponibilidad requiere una unidad activa, libre durante todo el intervalo y sin incidencias bloqueantes pendientes. La comprobación y la creación se ejecutan dentro de una transacción para evitar reservas simultáneas sobre la misma unidad. Cancelar conserva el historial y libera el periodo.

Los reintentos de confirmación con la misma clave recuperan las reservas originales. En las reservas conjuntas, la operación es atómica. El recuento de reservas del catálogo muestra las que están en curso o son próximas; la disponibilidad se consulta para el intervalo elegido.

## API

| Ruta base | Uso |
| --- | --- |
| `/health` | Estado de la aplicación |
| `/api/public` | Catálogo, imágenes y disponibilidad pública |
| `/api/auth` | Registro, sesión, acceso, cierre y CSRF |
| `/api/me` | Reservas, lista guardada e incidencias del cliente |
| `/api/equipment` | Gestión administrativa de unidades físicas |
| `/api/reservations` | Gestión administrativa de reservas |
| `/api/incidents` | Gestión administrativa de incidencias |
| `/api/imports` | Importación de reservas desde CSV |

Con el backend en marcha, la documentación interactiva está en [Swagger UI](http://127.0.0.1:8000/api/docs), [ReDoc](http://127.0.0.1:8000/api/redoc) y el [esquema OpenAPI](http://127.0.0.1:8000/api/openapi.json). Requieren sesión; las operaciones de escritura protegidas requieren además `X-CSRF-Token`.

## Comprobaciones

Backend, desde la raíz:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m pytest
..\.venv\Scripts\python.exe -m ruff check .
..\.venv\Scripts\python.exe -m ruff format --check .
Set-Location ..
```

Frontend, desde la raíz:

```powershell
Set-Location frontend
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test
npm.cmd run build
Set-Location ..
```

Las pruebas backend utilizan bases SQLite temporales aisladas. Cubren permisos, reservas, concurrencia, incidencias, importaciones y persistencia; las del frontend incluyen formularios, navegación, sesión y recuperación ante errores.

## Docker

Prepara primero `.env` con el secreto de sesión. Para HTTP local utiliza `RENTALAB_ENVIRONMENT=development`. Si defines `RENTALAB_DATABASE_URL`, en Docker debe apuntar al volumen: `sqlite:////data/rentalab.db`.

Desde la raíz:

```powershell
docker compose config --quiet
docker compose build --pull
docker compose up -d --wait
docker compose exec rentalab python -m rentalab.auth.manage_users create-admin --name "Administración local" --email "admin@example.test"
```

Abre el [catálogo servido por FastAPI](http://127.0.0.1:8000/catalogo). La imagen compila React y sirve frontend y API desde el mismo origen. El contenedor aplica las migraciones antes de arrancar; los datos de ejemplo se cargan sólo mediante comandos explícitos.

SQLite se guarda en el volumen `rentalab-data`, montado en `/data`. `docker compose down` conserva el volumen. La configuración utiliza una instancia y un worker. En producción, configura `RENTALAB_ENVIRONMENT=production` y HTTPS mediante un proxy inverso.

Consulta la [guía de despliegue](docs/DESPLIEGUE.md) para configuración, copias de seguridad y restauración. El [registro de validación](docs/VALIDACION_INTEGRADA.md) documenta las comprobaciones realizadas y las verificaciones Docker pendientes.

## Estructura del repositorio

```text
backend/
  rentalab/       API, autenticación y lógica de negocio
  alembic/        Migraciones de base de datos
  tests/          Pruebas del backend
frontend/
  src/            Catálogo, portal de cliente y administración
  public/         Recursos estáticos
  package.json    Dependencias y comandos del frontend
docs/             Documentación técnica y operativa
deploy/           Ejemplo de configuración de proxy inverso
compose.yaml      Servicio y volumen persistente
Dockerfile        Construcción del frontend e imagen de ejecución
.env.example      Plantilla de configuración
```

## Documentación

- [Arquitectura](docs/ARQUITECTURA.md)
- [Autenticación y permisos](docs/ACCESO.md)
- [Catálogo público](docs/CATALOGO_PUBLICO.md)
- [Portal de cliente](docs/PORTAL_CLIENTE.md) y [operaciones propias](docs/OPERACIONES_CLIENTE.md)
- [Lista guardada y reserva conjunta](docs/LISTA_GUARDADA.md)
- [Administración](docs/ADMINISTRACION.md)
- [Reservas](docs/RESERVAS.md) e [incidencias](docs/INCIDENCIAS.md)
- [Importaciones CSV](docs/IMPORTACIONES.md)
- [Despliegue y copias de seguridad](docs/DESPLIEGUE.md)
- [Créditos de las fotografías](backend/rentalab/public_catalogue/assets/photo-credits.txt)

## Alcance actual

RentaLab incluye catálogo, reservas, incidencias y gestión administrativa. No integra pagos, recuperación de contraseñas, limitación de intentos de acceso ni auditoría completa. Utiliza una única instancia con escrituras SQLite serializadas; su capacidad bajo carga no se ha medido.
