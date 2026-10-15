# Screencast de RentaLab para LeanMind

Duración objetivo: **8 minutos y 30 segundos**. Este guion propone un vídeo de 8–9 minutos; no afirma que exista ya una grabación. Presenta una empresa, equipos y personas ficticias y muestra el alcance actual: visitante, cliente y administrador en una sola aplicación.

La evidencia de suites, navegador, migración y despliegue está en el [balance integrado de F](VALIDACION_INTEGRADA.md) y [PROYECTO.md](PROYECTO.md). Al grabar, distingue los resultados que acabas de observar, las pruebas automatizadas previas y los pasos pendientes. No atribuyas experiencia profesional o colaboración con LeanMind que no haya ocurrido.

## Preparación fuera de cámara

1. Sigue instalación y configuración de acceso del [README](../README.md). Necesitas `RENTALAB_SESSION_SECRET` configurado fuera del repositorio. Elige contraseñas propias con lectura interactiva; no grabes `.env`, hashes, cookies, cabeceras, tokens ni el gestor de contraseñas.
2. Ejecuta las comprobaciones del README antes de grabar y conserva su salida real. Prepara el editor en los archivos y pruebas indicados abajo.
3. Crea una base **nueva de ensayo**, separada de `data/rentalab.db`. No copies usuarios ni reservas de la habitual y no reinicialices esa base. Este bloque PowerShell usa React compilado y FastAPI bajo el mismo origen; no necesita Vite.

Desde la raíz, en una terminal nueva:

~~~powershell
Set-Location frontend
npm.cmd ci
npm.cmd run build
Set-Location ..
$demoDirectory = Join-Path (Get-Location) ('.tools\screencast-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $demoDirectory | Out-Null
$demoDatabase = Join-Path $demoDirectory 'rentalab.db'
$env:RENTALAB_DATABASE_URL = 'sqlite:///' + $demoDatabase.Replace('\', '/')
$env:RENTALAB_FRONTEND_DIST = (Resolve-Path .\frontend\dist).Path
$env:RENTALAB_ENVIRONMENT = 'development'
$env:RENTALAB_PORT = '8008'
Set-Location backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m rentalab.seed
..\.venv\Scripts\python.exe -m rentalab.auth.manage_users create-admin --name "Administración de ensayo" --email ensayo-admin@example.test
..\.venv\Scripts\python.exe -m rentalab.auth.manage_users demo-users
..\.venv\Scripts\python.exe -m rentalab.start
~~~

`create-admin` pide contraseña y confirmación sin mostrarlas. `demo-users` pide otra contraseña configurable y crea `alicia.demo@example.test` y `bruno.demo@example.test` como clientes; ambas cuentas ficticias usan la elegida para ese comando. El registro que se mostrará en vídeo usa **otra cuenta**, por ejemplo `irene.ensayo@example.test`. No existe una contraseña compartida en el repositorio. Para automatización, ambos comandos admiten `--password-env NOMBRE_DE_VARIABLE`: se pasa el nombre de una variable ya configurada, nunca el secreto como argumento.

El seed añade equipos y características ficticias de manera explícita. El arranque vuelve a comprobar migraciones, pero no crea cuentas ni datos. Los comandos de cuentas conservan las existentes y no elevan permisos ni restablecen contraseñas por coincidir el correo. No vuelvas a ejecutar el bloque para continuar un ensayo: reutiliza su misma URL de base y configura sólo lo necesario en la nueva terminal.

4. Usa `http://127.0.0.1:8008` o el puerto libre que elijas. Prepara **perfiles o contextos aislados** para cliente y administrador; pestañas normales del mismo perfil comparten cookie. Dos ventanas privadas de un mismo perfil también pueden compartir contexto. Para comprobar otro cliente usa un tercer contexto independiente con Alicia o Bruno.
5. Elige una unidad del seed desde el catálogo, sin suponer su ID. Usa fechas futuras, por ejemplo **2030-11-10 / 2030-11-12**. Si grabas después de ellas, sustitúyelas: las nuevas reservas de cliente rechazan inicios pasados. Ten otro rango libre, como 14–16 del mismo mes, para observar el bloqueo sin mezclarlo con la reserva.
6. Ten abierta una versión estrecha del portal para mostrar móvil brevemente, y comprueba refresco de `/catalogo`, `/mis-reservas` y `/admin`. Una ruta privada muestra acceso hasta iniciar la sesión correspondiente.
7. El CSV no requiere una subida en cámara. La selección automatizada de archivos fue rechazada por un permiso guardado del navegador y no se eludió. La API multipart y el informe tienen pruebas; si una persona hace una subida manual durante otro ensayo, registra su resultado por separado. No presentes una descarga o un mock como una importación real.
8. Ensaya una vez y guarda la ruta de esta base. Para un ensayo limpio crea otra carpeta, sin borrar la habitual. Al terminar detén el servidor con Ctrl+C y cierra la terminal para retirar esas variables temporales.

## Escaleta: 8:30

| Tiempo | Duración | Acción y explicación |
| --- | --- | --- |
| 00:00–00:30 | 0:30 | Problema, tres tipos de acceso y uso real de IA |
| 00:30–01:20 | 0:50 | Visitante: catálogo, características y fechas |
| 01:20–02:20 | 1:00 | Registro/acceso conservando equipo y fechas |
| 02:20–03:15 | 0:55 | Confirmación expresa, detalle propio y refresco |
| 03:15–03:55 | 0:40 | Comunicar un aviso desde la reserva |
| 03:55–05:20 | 1:25 | Admin: propietario, respuesta pública y bloqueo |
| 05:20–06:10 | 0:50 | Resolución, cancelación e historial visible al cliente |
| 06:10–07:30 | 1:20 | Regla compartida, transacción y pruebas reales |
| 07:30–08:30 | 1:00 | CSV, despliegue persistente y límites comprobados |

Las duraciones suman 510 segundos. Si una operación tarda más, recorta explicación repetida; no cortes un error para fingir un resultado. No es necesario escribir todas las contraseñas ni esperar la suite completa dentro del vídeo.

## 00:00–00:30 · Presentación y uso de IA

Adapta esta frase a tu experiencia real:

> «RentaLab es un proyecto de aprendizaje para una empresa ficticia de alquiler audiovisual. Un visitante consulta; un cliente reserva y comunica problemas; un administrador gestiona el conjunto. He utilizado Codex y agentes para asistir en generación, revisión de código, pruebas y documentación. Voy a explicar una regla y la evidencia que la respalda.»

No afirmes haber escrito cada línea sin asistencia. Explica decisiones que hayas estudiado y puedas defender. Algunas pruebas tuvieron fase roja registrada y otras se añadieron ya verdes; no presentes todo el repositorio como TDD estricto.

## 00:30–01:20 · Catálogo público y disponibilidad

En el contexto sin sesión abre `/catalogo`. Busca una cámara, filtra categoría y abre su ficha. Muestra descripción pública y características. La imagen alternativa es local; no hace falta una web de imágenes externa.

Antes de seleccionar fechas, señala «Selecciona inicio y fin». Elige 10–12 de noviembre de 2030 y consulta. Explica: «El resultado pertenece a este rango, no es una propiedad permanente del equipo. El fin está excluido: se ocupan los días 10 y 11».

La API usa DTO públicos explícitos en [public_catalogue/schemas.py](../backend/rentalab/public_catalogue/schemas.py); no envía notas internas, clientes ni reservas individuales para que React los oculte.

## 01:20–02:20 · Registro y acceso con fechas conservadas

Pulsa **Acceder para reservar**, pasa a **Crear cuenta de cliente** y registra Irene con el correo de ensayo y una contraseña propia, sin exponerla. El registro crea siempre `customer` y no inicia sesión. Accede después con esa cuenta.

Muestra que se conservan equipo y rango y que aún aparece **Confirmar reserva**. Volver del acceso no ejecutó la reserva. [destinations.ts](../frontend/src/auth/destinations.ts) acepta únicamente destinos internos permitidos, y [LoginPage.tsx](../frontend/src/pages/LoginPage.tsx) conserva ese destino al cambiar entre acceso y registro.

Si ya existe el correo por un ensayo previo, usa otra base/cuenta preparada o accede a la existente y explica que estás mostrando acceso; no presentes el error de duplicado como registro exitoso.

## 02:20–03:15 · Confirmación y reserva propia

Pulsa **Confirmar reserva**. Muestra referencia `Reserva #id`, estado y enlace al detalle. Abre `/mis-reservas`, vuelve al detalle y refresca la ruta. La sesión y los datos se consultan al backend al recargar.

Explica: «El navegador manda equipo y fechas; el servidor obtiene propietario, nombre y correo de la sesión. No acepta elegir otro cliente ni estado». [me/reservations.py](../backend/rentalab/me/reservations.py) define el contrato mínimo.

En el editor señala la prueba `test_reservation_lists_and_direct_ids_are_isolated` de [test_me_security.py](../backend/tests/test_me_security.py): otro cliente modifica los identificadores HTTP y recibe 404. La ausencia de un enlace en la interfaz no es la protección. No intentes una reserva duplicada sólo para avanzar el guion.

## 03:15–03:55 · Un aviso de cliente

Desde la reserva confirmada informa de un problema: título «El visor no responde» y descripción ficticia útil. Abre Mis incidencias y observa su estado pendiente/abierto.

Explica: «El equipo se deduce de mi reserva. Este aviso empieza sin bloquear el equipo; sólo administración decide prioridad, bloqueo y resolución». En [me/incidents.py](../backend/rentalab/me/incidents.py), `CustomerIncidentService.create` fija `blocking=False` y registra autor/reserva dentro de la transacción. No requiere que la reserva ya haya comenzado.

## 03:55–05:20 · Gestión en el contexto de administrador

Cambia al contexto aislado del administrador, accede y abre `/admin`. Localiza la reserva de Irene; muestra propietario y origen Portal. Abre el aviso, añade una respuesta pública, una nota interna ficticia diferenciada y marca prioridad alta y bloqueante con confirmación.

Vuelve al cliente y a Mis incidencias: aparece la respuesta pública, sin nota ni resolución internas. Consulta el **otro rango libre** 14–16: no está disponible desde el bloqueo. No uses 10–12 para atribuir el resultado únicamente a la incidencia, porque ya contiene la reserva.

Aclara: «Panel y portal comparten la base y las reglas. El aviso no canceló una reserva confirmada». Si hay tiempo muestra un refresco móvil; no afirmes auditoría completa de accesibilidad por una única vista.

## 05:20–06:10 · Resolución y cancelación conservando historial

En administración resuelve el aviso con una explicación interna y conserva una respuesta pública comprensible. Consulta 14–16 de nuevo: estará libre **si no queda otra incidencia, el equipo sigue activo y no hay solapamiento**. No digas que resolver activa el equipo.

Cancela la reserva desde administración con confirmación y vuelve al detalle del cliente: se ve Cancelada y sus fechas permanecen. El intervalo 10–12 deja de estar ocupado por esa reserva.

Explica la diferencia de roles: «Un cliente sólo cancela antes del inicio según Europe/Madrid; administración puede cancelar también después. Repetir una cancelación conserva el resultado». El ejemplo futuro no demuestra por sí solo ese límite: lo prueba `test_cannot_cancel_on_or_after_start` en [test_me_reservations.py](../backend/tests/test_me_reservations.py).

## 06:10–07:30 · Una regla y sus pruebas

Ten preparados estos archivos:

1. `create_for_customer` y `_create_checked`, en [reservations/service.py](../backend/rentalab/reservations/service.py).
2. `AvailabilityService.check`, en [availability.py](../backend/rentalab/availability.py).
3. `conflicting_ids` y `has_blocking_incident`, en [reservations/repository.py](../backend/rentalab/reservations/repository.py).
4. `immediate_transaction`, en [database.py](../backend/rentalab/database.py).

Explica: «Consulta pública, portal, administración y CSV comparten disponibilidad. La consulta previa no retiene el equipo. Antes de confirmar pido el turno SQLite con `BEGIN IMMEDIATE`, compruebo y escribo en la misma unidad. Dos confirmaciones incompatibles dejan una sola reserva. Resolver una de varias averías bloqueantes no libera el equipo».

Desde `backend/`, ejecuta este subconjunto contra bases temporales:

~~~powershell
..\.venv\Scripts\python.exe -m pytest -q tests/test_me_reservation_concurrency.py::test_two_customers_using_distinct_connections_cannot_double_book tests/test_incidents.py::test_multiple_blocking_incidents_require_resolving_the_last_one tests/test_admin_connected.py::test_csv_keeps_its_owner_unknown_even_when_a_matching_email_registers
~~~

Muestra las aserciones: conexiones distintas, un éxito y un conflicto, una reserva persistida; un segundo bloqueo pendiente sigue impidiendo reservar; CSV sin propietario no aparece por registrar un correo coincidente. No leas sólo el contador final.

Señala [ProductPage.test.tsx](../frontend/src/portal/ProductPage.test.tsx), caso `keeps dates and focuses a conflict, then requires a fresh check and another explicit confirmation`. Sus respuestas HTTP simuladas prueban recuperación de la interfaz; SQLite se verifica en backend. Si el tiempo no permite ejecutar ese test en cámara, muestra la salida real previa y dilo.

## 07:30–08:30 · Entrega y límites verificables

Muestra en administración la sección Importaciones y una reserva CSV de un ensayo previo **sólo si realmente existe**. Si no, señala la prueba ejecutada. Explica el contrato: cabecera y límites conservados, referencia idempotente, informe por fila y `customer_user_id=null` sin asignación por correo. Administración conserva también históricos de origen desconocido.

Abre [Dockerfile](../Dockerfile), [compose.yaml](../compose.yaml) y [DESPLIEGUE.md](DESPLIEGUE.md): React compilado, API del mismo origen, SQLite en `/data` persistente, migraciones al iniciar y un worker. Seed y cuentas son explícitos; no hay reinicialización automática. La compilación local que acabas de mostrar no prueba por sí sola la imagen ni el volumen Docker.

Cierra con lo que conste en la fase F del registro: comandos ejecutados, navegación con roles, base vacía, migración y reinicio, y las limitaciones reales de Docker/HTTPS o subida automatizada. No conviertas un motor no disponible o un permiso rechazado en una prueba superada. No se publicaron servicios externos.

Límites de producto: no hay pagos, cesta, varias empresas, recuperación de contraseña, paginación, auditoría completa ni medición de carga. Hay registro de clientes, roles y aislamiento de reservas; no repitas el antiguo límite de operador único. La sesión Secure de producción requiere HTTPS; este ensayo es HTTP local development.

## Preguntas para preparar después del vídeo

- **¿Qué protege el catálogo de nuevos campos privados?** Proyección explícita en Python y pruebas de claves/contenido, además de contratos TypeScript.
- **¿Por qué no vincular por correo?** Un contacto histórico no acredita la relación con una cuenta; la propiedad persistida es la que autoriza.
- **¿Por qué no basta un worker?** Pueden competir peticiones y conexiones; la prueba concurrente verifica la unidad de decisión y escritura.
- **¿Qué aprendiste tú?** Responde con decisiones que hayas estudiado y puedas explicar. La [guía de estudio](GUIA_DE_ESTUDIO.md) aporta ejercicios; no inventa experiencia.
- **¿Qué falta probar?** Separa suite, navegador real, imagen Docker y HTTPS externo según [PROYECTO.md](PROYECTO.md).

