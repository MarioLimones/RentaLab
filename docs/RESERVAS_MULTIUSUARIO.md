# Reservas con varios usuarios: demostración local

FastAPI, SQLAlchemy, SQLite y React/TypeScript se conservan. El portal cliente sigue bajo `/catalogo`, `/equipos` y `/mis-reservas`; la gestión administrativa, bajo `/admin`. Las cuentas siguientes usan el acceso real, Argon2id, cookies de sesión revocables y CSRF.

## Preparar los datos

Desde la raíz del proyecto, en PowerShell, después de preparar `.env` y las dependencias según el README:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m rentalab.demo
```

También se puede fijar una base futura:

```powershell
..\.venv\Scripts\python.exe -m rentalab.demo --base-date 2026-10-15
```

Sin `--base-date` se usa el día actual de Europe/Madrid. La base explícita no puede estar en el pasado. No se añaden datos al arrancar ni al migrar. El comando rechaza `RENTALAB_ENVIRONMENT=production` antes de abrir la base.

La carga añade sólo los registros ausentes. Los correos, códigos y referencias estables impiden duplicados. Repetir con otra base conserva las reservas ya existentes, sus fechas, estado y propietario; no las mueve al futuro ni restaura cancelaciones. Para otra demostración futura usa una base SQLite local nueva mediante `RENTALAB_DATABASE_URL` y aplica sus migraciones. Los conflictos con datos existentes se informan; nunca se resuelven borrando o sobrescribiendo información.

## Cuentas locales

Estas contraseñas son públicas y ficticias, exclusivas de la carga local explícita. Las cuentas existentes conservan su contraseña y sus permisos; las credenciales de la tabla sólo corresponden a cuentas nuevas creadas por este comando.

| Cuenta | Correo | Contraseña inicial |
| --- | --- | --- |
| Administración | `admin.demo@rentalab.example.test` | `Demo-RentaLab-Admin-2026!` |
| Alicia | `alicia.demo@rentalab.example.test` | `Demo-RentaLab-Alicia-2026!` |
| Bruno | `bruno.demo@rentalab.example.test` | `Demo-RentaLab-Bruno-2026!` |
| Carla | `carla.demo@rentalab.example.test` | `Demo-RentaLab-Carla-2026!` |
| Diego | `diego.demo@rentalab.example.test` | `Demo-RentaLab-Diego-2026!` |
| Elena, cliente nuevo | `elena.demo@rentalab.example.test` | `Demo-RentaLab-Elena-2026!` |

Elena empieza sin reservas. El acceso independiente utiliza correo y contraseña propios; no hay un usuario compartido ni simulación de sesión en React.

## Reservas iniciales

`B` representa la fecha base. Cada código corresponde a una unidad física; las dos cámaras son unidades diferentes.

| Referencia | Cliente | Unidad | Inicio incluido | Fin excluido | Estado |
| --- | --- | --- | --- | --- | --- |
| RENTALAB-DEMO-01 | Alicia | CAM-001 | B + 7 días | B + 10 días | Confirmada |
| RENTALAB-DEMO-02 | Bruno | CAM-001 | B + 10 días | B + 13 días | Confirmada |
| RENTALAB-DEMO-03 | Carla | CAM-002 | B + 7 días | B + 11 días | Confirmada |
| RENTALAB-DEMO-04 | Diego | AUD-001 | B + 3 días | B + 5 días | Confirmada |
| RENTALAB-DEMO-05 | Alicia | LGT-001 | B + 15 días | B + 17 días | Confirmada |
| RENTALAB-DEMO-06 | Carla | CAM-001 | B + 20 días | B + 22 días | Cancelada |

Las dos primeras reservas son consecutivas. La cancelada permanece en el historial de Carla y no ocupa días. Las unidades previamente editadas conservan su ficha, incluso cuando su nombre público difiera del ejemplo original.

## Recorrido con sesiones independientes

1. Arranca backend y frontend según el README. Abre una ventana normal y otra privada, o dos navegadores con perfiles separados. Dos pestañas del mismo perfil comparten cookie y no sirven como dos clientes.
2. Accede como Alicia en una ventana y como Bruno en la otra. Abre el mismo equipo CAM-001 desde el catálogo. En el panel administrador se puede consultar el código para identificar su ficha; el catálogo público no publica datos internos.
3. En ambas ventanas elige recogida y devolución sobre el calendario para un intervalo futuro libre, por ejemplo `[B+30, B+32)`. La disponibilidad se comprueba automáticamente. Las dos consultas pueden indicar disponible; no retienen la unidad.
4. Confirma en Alicia. La aplicación muestra éxito después de recibir la reserva guardada por el servidor.
5. Sin recargar la ventana de Bruno, confirma el mismo rango. Recibe 409 y un mensaje que invita a elegir otro periodo o equipo. Sus fechas se conservan y el calendario vuelve a consultar el backend, mostrando los días ahora ocupados.
6. Selecciona en Bruno `[B+32, B+34)`; el nuevo intervalo se comprueba automáticamente. Puede confirmar porque el día de fin de Alicia no se incluye. Otra unidad física también puede reservarse para las fechas originales.
7. Alicia puede cancelar su reserva antes del inicio desde «Mis reservas». El detalle actualiza disponibilidad desde el servidor. Al consultar de nuevo el equipo en Bruno o Elena, los días quedan libres.
8. En Elena comprueba «Mis reservas» vacío y el calendario con reservas ajenas sin nombres, correos, referencias ni identificadores de reservas. La API devuelve 404 al intentar leer o cancelar una reserva de otro cliente.

El calendario se carga al abrir la ficha y se actualiza al cambiar de mes, reintentar y tras las operaciones. El intervalo se comprueba al completar o modificar las fechas. No hay comunicación automática entre ventanas: una consulta previa puede quedarse desactualizada, y el servidor siempre decide al confirmar.

## Por qué no se duplica la reserva

El servicio común de reservas abre una transacción SQLite con `BEGIN IMMEDIATE` antes de leer disponibilidad. Obtiene el permiso de escritura para toda la operación: leer unidad/incidencias/reservas, validar, insertar y confirmar. Una segunda conexión espera; cuando consigue el turno ve la primera reserva guardada y rechaza el solapamiento. Portal, administración e importación CSV utilizan ese mismo servicio. No depende de un bloqueo en memoria ni de desactivar un botón.

Sólo bloquean reservas confirmadas de la misma unidad cuando `inicio_existente < fin_solicitado` y `fin_existente > inicio_solicitado`. Por eso se admiten unidades distintas y reservas consecutivas. La interfaz explica que el fin está excluido y nunca muestra éxito antes del commit.

La espera está limitada por `RENTALAB_SQLITE_BUSY_TIMEOUT_MS` (5000 ms por defecto). Un bloqueo temporal agotado revierte la transacción y devuelve 503 con `Retry-After: 1`; una falta de disponibilidad devuelve 409. No hay reintentos automáticos de escrituras. Un doble envío del mismo intervalo se rechaza al volver a comprobarlo bajo el bloqueo; React añade una guarda inmediata y estado de envío para evitarlo también en la interacción.

## Comprobaciones reproducibles

Desde `backend`:

```powershell
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m ruff check .
..\.venv\Scripts\python.exe -m ruff format --check .
```

Desde `frontend`:

```powershell
npm.cmd test
npm.cmd run lint
npm.cmd run build
```

`build` incluye la comprobación de tipos. Las pruebas utilizan SQLite temporal en disco, migraciones reales y clientes autenticados independientes; no modifican `data/rentalab.db`.

Los resultados de esta implementación y los límites de la comprobación están registrados en [PROYECTO.md](PROYECTO.md).

En la comprobación del 15/10/2026 pasaron **909 pruebas de backend** (una omitida en Windows) y **361 de frontend**; cinco rondas reales de la misma unidad dieron 201/409 y una sola fila, y cinco rondas con unidades distintas dieron 201/201. La base local recibió la carga dos veces sin duplicados. Las dos reservas adicionales creadas por el recorrido de navegador se cancelaron y permanecen como historial: quedan seis cuentas, cuatro unidades y ocho reservas (cinco confirmadas y tres canceladas). Elena sigue sin reservas. Se verificó también la persistencia al detener y arrancar de nuevo Uvicorn.
