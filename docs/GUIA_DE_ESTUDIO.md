# Guía de estudio de RentaLab

Esta guía recorre el alcance vigente: catálogo para visitantes, reservas y avisos propios para clientes, y gestión global para administradores. Se mantienen una aplicación React, una API FastAPI y SQLite; el acceso de operador único quedó sustituido por los roles de la ampliación A–F.

El objetivo es poder explicar una reserva desde el formulario hasta SQLite, razonar sobre sus límites y reconocer qué garantiza cada prueba. Lee primero el [contrato del proyecto](PROYECTO.md) y usa [ARQUITECTURA.md](ARQUITECTURA.md) para seguir el recorrido entre capas. Esta guía describe el código existente; no presupone que hayas desarrollado antes una aplicación de alquiler.

## Antes de las reglas: quién actúa y qué puede conocer

| Persona | Entrada | Puede consultar o modificar |
| --- | --- | --- |
| Visitante | `/catalogo`, `/equipos/:id`; `/api/public` | Fichas activas y disponibilidad por fechas, sin historial ni datos privados |
| Cliente | `/mis-reservas`, `/mis-incidencias`, `/mi-cuenta`; `/api/me` y sesión | Sus reservas, avisos y perfil de lectura; no el listado global |
| Administrador | `/admin`; rutas de gestión existentes | Equipos, todas las reservas, incidencias e importaciones |

Sigue `ServicioAutenticacion.buscar_sesion` en [autenticacion/servicio.py](../backend/rentalab/autenticacion/servicio.py): una cookie válida necesita además sesión vigente en SQLite; el usuario se consulta otra vez para comprobar `active`, rol y versión de contraseña. Después [autenticacion/dependencias.py](../backend/rentalab/autenticacion/dependencias.py) centraliza `obtener_actual_usuario`, `exigir_administrador` y `exigir_cliente`. Ocultar la barra administrativa sólo organiza la interfaz; el servidor protege también las URLs antiguas. La [matriz de permisos](ACCESO.md) es el contrato completo.

El registro valida [SolicitudRegistro](../backend/rentalab/autenticacion/esquemas.py) con campos extra prohibidos y la ruta llama a `register(data)` sin permitir elegir rol: crea `customer`. El correo normalizado es único y la contraseña se persiste como hash Argon2id. Para crear un administrador se usa el comando explícito [gestionar_usuarios.py](../backend/rentalab/autenticacion/gestionar_usuarios.py); no un selector en React. `test_registrar_rechaza_cualquier_administrativa_o_desconocido_campo`, en [test_usuarios.py](../backend/tests/test_usuarios.py), envía campos prohibidos por HTTP.

## Una ficha pública no es un equipo administrativo serializado

En [catalogo_publico/servicio.py](../backend/rentalab/catalogo_publico/servicio.py), `publico_equipo` asigna uno a uno los campos de `PublicoEquipoLectura`: nombre, categoría, descripción pública, características e imagen/fallback local, además del ID público. No hereda el DTO administrativo ni elimina unas pocas claves después de serializarlo. Así un nuevo campo interno no aparece accidentalmente en el catálogo.

`ServicioCatalogoPublico.listar` filtra activos y aplica búsqueda por nombre y categoría mediante `casefold`; `%` y `_` se tratan literalmente. `comprobar_disponibilidad` reutiliza `DisponibilidadServicio`, pero publica sólo estado, fechas y booleano. Sin fechas devuelve `select_dates` y `available=null`; un equipo inactivo da 404 público. Una avería sólo permite deducir «no disponible».

Compruébalo en `test_privado_cliente_y_reserva_datos_hacer_no_aparecen_en_cualquier_publico_respuesta` y `test_publico_y_administrativa_disponibilidad_comparten_dia_solapamiento_reglas`, en [test_catalogo_publico.py](../backend/tests/test_catalogo_publico.py). No basta con observar que una tarjeta no pinta un campo: hay que revisar el JSON real.

## Sigue una reserva de cliente hasta su propietario

1. [PaginaProducto.tsx](../frontend/src/portal/PaginaProducto.tsx) conserva equipo y fechas ISO en la URL. [PaginaAcceso.tsx](../frontend/src/paginas/PaginaAcceso.tsx) comparte acceso/registro y conserva un `next` validado por [destinos.ts](../frontend/src/autenticacion/destinos.ts).
2. Registrarse no inicia sesión automáticamente. Después de acceder se vuelve al equipo, pero se necesita pulsar **Confirmar reserva**; volver al destino no ejecuta una reserva.
3. `api.crearMiReserva` en [api/cliente.ts](../frontend/src/api/cliente.ts) sólo envía equipo y fechas a `POST /api/me/reservations`, con cookie y CSRF centralizados.
4. [cuenta/reservas.py](../backend/rentalab/cuenta/reservas.py) obtiene propietario, nombre y correo de `ClienteUsuario`. `ClienteReservaCrear` rechaza identidad, origen y estado enviados por el navegador.
5. `ServicioReservas.crear_para_cliente` comprueba la fecha Madrid y reutiliza `_crear_comprobado` dentro de la transacción. Persiste `customer_user_id` y `origin="portal"`; devuelve únicamente ID, equipo, fechas y estado al cliente.
6. `listar_para_cliente` y `obtener_para_cliente` restringen por ID de propietario. Cambiar directamente el ID de la URL no permite leer, cancelar ni informar sobre una reserva ajena: devuelve 404.

La propiedad es nullable. Una reserva histórica, administrativa o importada sin dueño conocido sigue visible en administración; registrar su mismo correo **no la atribuye**. `origin` distingue `portal`, `admin`, `csv` y `legacy`; no demuestra por sí solo propiedad. `0006_users_ownership` añadió relaciones conservadoras y `0009_reservation_origin` marcó anteriores como `legacy` sin inferir su origen ni borrar propiedad existente.

En [test_cuenta_seguridad.py](../backend/tests/test_cuenta_seguridad.py), `test_reserva_lista_y_directa_ids_son_aislado` usa dos sesiones y peticiones HTTP; `test_cliente_reserva_creacion_rechaza_identidad_y_administrativa_campos` intenta falsificar la identidad. [test_administrador_conectado.py](../backend/tests/test_administrador_conectado.py) comprueba además que un CSV no se vincula a una cuenta registrada después con correo coincidente.

## 1. Empieza por la unidad física y las fechas

`CAM-001` y `CAM-002` pueden representar el mismo modelo de cámara, pero son dos objetos físicos. Una reserva ocupa una unidad identificada por `equipment_id`. Alquilar `CAM-001` no consume automáticamente `CAM-002`.

Una reserva del **10 al 12 de noviembre de 2030** ocupa los días **10 y 11**. El día 12 está excluido y puede ser el inicio de la siguiente. Se escribe `[2030-11-10, 2030-11-12)`: el corchete incluye el inicio y el paréntesis excluye el fin. No hay horas, duración cero ni conversiones de zona horaria en estas fechas de alquiler.

En [reservations/schemas.py](../backend/rentalab/reservas/esquemas.py), `exigir_iso_fecha` exige el formato exacto `YYYY-MM-DD`; Pydantic comprueba además que exista la fecha. `IntervaloFechas.exigir_positivo_intervalo` rechaza `end_date <= start_date`. En React, los formularios conservan cadenas ISO y [fechas.ts](../frontend/src/utilidades/fechas.ts) las presenta sin convertirlas a instantes UTC. El reloj Europe/Madrid decide «hoy» para crear/cancelar como cliente; no transforma las fechas de alquiler en horas.

## 2. Deduce la regla de solapamiento

Supón que ya existe una reserva confirmada `A = [10, 12)` para `CAM-001`. Una nueva solicitud `B` solapa cuando se cumplen las dos condiciones:

```text
A.start_date < B.end_date
AND
A.end_date > B.start_date
```

La primera descarta que A esté completamente después de B; la segunda descarta que A esté completamente antes. Los operadores son estrictos porque tocar el límite no ocupa el mismo día.

| Solicitud B | ¿Solapa A? | Motivo |
| --- | --- | --- |
| `[8, 10)` | No | Termina cuando empieza A |
| `[12, 14)` | No | Empieza cuando termina A |
| `[11, 13)` | Sí | Ambas ocupan el día 11 |
| `[9, 11)` | Sí | Ambas ocupan el día 10 |
| `[9, 13)` | Sí | Contiene toda A |
| `[10, 12)` | Sí | Coincide con toda A |

Los números de la tabla son días de noviembre de 2030, no cantidades de horas. La consulta real está en `RepositorioReservas.en_conflicto_ids`, en [reservations/repository.py](../backend/rentalab/reservas/repositorio.py): filtra también por el **mismo equipo** y `status == "confirmed"`. Una cancelada conserva sus fechas, pero deja de participar en esa consulta.

Las pruebas `test_parcial_total_y_contenidos_solapamientos_son_conflictos`, `test_adyacentes_y_separados_intervalos_son_disponible_y_puede_ser_reservado` y `test_la_mismo_fechas_puede_ser_reservado_para_distinto_fisica_unidades`, en [test_reservas.py](../backend/tests/test_reservas.py), comprueban esos comportamientos a través de HTTP. Así detectan errores en la integración entre validación, consulta y respuesta, sin copiar la expresión SQL como única aserción.

## 3. Entiende por qué consultar no reserva

`GET /api/public/equipment/{equipment_id}/disponibilidad` calcula la respuesta pública para un equipo activo y un intervalo. Su equivalente administrativo es `/api/equipment/{equipment_id}/disponibilidad`, con más información de gestión. Ninguno crea una retención. Entre consulta y confirmación, otra petición puede reservar.

`DisponibilidadServicio.comprobar`, en [disponibilidad.py](../backend/rentalab/disponibilidad.py), aplica este orden:

1. El equipo debe existir; de lo contrario se devuelve 404.
2. Debe estar activo: motivo `equipment_inactive` si no lo está.
3. No puede tener incidencias bloqueantes sin resolver: `blocking_incident`.
4. No puede tener reservas confirmadas solapadas: `reservation_overlap`.

`ServicioCatalogoPublico.comprobar_disponibilidad` y `ServicioReservas.disponibilidad` delegan en esa política. `_crear_comprobado` la usa al crear reservas de cliente, administrativas y CSV con referencia nueva. No existe una columna `available`: sería insuficiente sin rango y quedaría desactualizada al cambiar reservas o incidencias. El panel de resumen consulta las disponibilidades para fechas explícitas; no inventa otra fórmula en React.

En el formulario administrativo, `comprobarDisponibilidad` muestra el resultado con sus fechas y descarta respuestas antiguas. En el portal, `PaginaProducto` asocia la consulta al equipo/rango y, tras un 409, pide consultar otra vez y confirmar expresamente. Una consulta anterior no concede permiso de reserva. La interfaz ayuda, mientras Python toma la decisión definitiva.

## 4. Protege la decisión y la escritura juntas

Sin una transacción adecuada, dos peticiones podrían leer «no hay reservas» antes de que ninguna inserte. Comprobar primero y guardar después no basta si otro escritor puede introducirse entre ambos pasos.

`inmediata_transaccion`, en [base_datos.py](../backend/rentalab/base_datos.py), combina `Sesion.begin()` con `BEGIN IMMEDIATE` **antes de las lecturas que deciden la escritura**. `Sesion.begin()` se ocupa de confirmar o revertir. El helper se usa mediante los repositorios de reservas e incidencias.

La secuencia buscada para dos reservas incompatibles es:

```text
Petición A: obtiene turno de escritura → comprueba → inserta → COMMIT
Petición B: espera ese turno            → comprueba de nuevo → detecta A → conflicto
```

SQLite admite un escritor simultáneo. `BEGIN IMMEDIATE` pide ese turno al comenzar; puede fallar si no se libera a tiempo. Esta elección encaja con el alcance de una demo de una instancia, a costa de serializar las escrituras. No significa que sólo pueda llegar una petición HTTP ni que se prohíban lectores. Consulta la [documentación oficial de transacciones SQLite](https://www.sqlite.org/lang_transaction.html).

Hay un detalle del controlador: en el modo heredado de `sqlite3` utilizado aquí, un `SELECT` por sí solo no emite el `BEGIN` necesario para esta decisión. Por eso el proyecto lo declara explícitamente, en vez de asumir que abrir una sesión SQLAlchemy ya ha adquirido el turno de escritura. El comportamiento del controlador está descrito en [SQLAlchemy y SQLite](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#legacy-transaction-mode-with-the-sqlite3-driver).

El tiempo de espera se configura con `RENTALAB_SQLITE_BUSY_TIMEOUT_MS`, por defecto 5000 ms. Un bloqueo agotado produce 409 con `Retry-After: 1`; un conflicto de solapamiento produce 409 con su explicación de negocio y sin esa cabecera. La aplicación revierte ante errores, incluso si el bloqueo sucede en `COMMIT`. No reintenta altas automáticamente.

La base añade otras defensas en [reservas/modelos.py](../backend/rentalab/reservas/modelos.py): clave foránea, `end_date > start_date`, estados admitidos y referencia externa única. No hay una restricción SQL que exprese por sí sola el solapamiento: esa garantía depende del servicio y de que las escrituras respeten su transacción. Escribir reservas directamente con SQL podría saltarse la política de disponibilidad.

## 5. Conecta incidencias e historial

Una incidencia bloquea si `blocking` es verdadero y su estado es `open` o `in_progress`. `RepositorioReservas.tiene_bloqueante_incidencia` comprueba si existe **alguna** que cumpla esas condiciones.

Imagina dos incidencias bloqueantes en `CAM-001`: un conector roto y una fuente defectuosa. Resolver la primera no basta; la segunda sigue bloqueando. Una incidencia no bloqueante puede permanecer abierta sin impedir reservas. Resolver todas tampoco activa por sí solo un equipo desactivado ni elimina los solapamientos.

`ServicioIncidencias.cambiar_estado`, en [incidencias/servicio.py](../backend/rentalab/incidencias/servicio.py), aplica `PERMITIDOS_TRANSICIONES`: `open → in_progress`, `open → resolved` e `in_progress → resolved`. [incidencias/esquemas.py](../backend/rentalab/incidencias/esquemas.py) exige una explicación no vacía para resolver. No existe reapertura ni borrado de incidencias en esta demo.

Registrar una avería después de confirmar una reserva no cancela esa reserva. `ServicioIncidencias._lectura` calcula `ids_reservas_confirmadas` y `warning` para que el operador revise el problema. El aviso incluye las reservas que estén confirmadas en ese momento, sin filtro temporal; no es un snapshot histórico ni una orden automática de cancelación.

Administración usa `ServicioReservas.cancelar` sin límite temporal; el cliente usa `cancelar_para_cliente` sólo antes del inicio en Madrid. La comprobación del reloj sucede tras adquirir el turno SQLite. Repetir una ya cancelada sigue funcionando incluso pasado el inicio. Ambas conservan identificador, cliente, fechas y referencia; el historial es el registro y su estado final, no una bitácora completa.

El cliente informa desde una reserva propia confirmada mediante `ClienteIncidenciaServicio.crear`, en [cuenta/incidencias.py](../backend/rentalab/cuenta/incidencias.py). El servidor deduce equipo y autor, fija `open`, prioridad media y no bloqueante. Sólo administración decide bloquear y resolver. `public_response` es la respuesta visible; `internal_notes` y `resolution` permanecen privadas. Mira `test_publico_respuesta_es_separados_desde_internas_notas_y_resolucion`, en [test_cuenta_incidencias.py](../backend/tests/test_cuenta_incidencias.py), y `test_cliente_y_administrador_comparten_cancelacion_comunicacion_y_disponibilidad`, en [test_administrador_conectado.py](../backend/tests/test_administrador_conectado.py).

Lee `test_multiples_bloqueante_incidencias_exigir_resolviendo_la_ultimo_una`, `test_incidencia_advierte_sobre_todos_confirmadas_reservas_sin_modificando_ellos` y `test_bloqueante_incidencia_impide_reserva_hasta_resuelta`, en [test_incidencias.py](../backend/tests/test_incidencias.py). [test_incidencia_concurrencia.py](../backend/tests/test_incidencia_concurrencia.py) comprueba además qué ocurre si compiten el alta de una incidencia y la de una reserva: el orden confirmado determina el resultado y las reservas previas se conservan.

## 6. Separa validez del archivo y validez de cada pedido

`POST /api/imports` recibe un archivo multipart. Su cabecera exacta es:

```csv
external_reference,customer_name,customer_email,equipment_code,starts_on,ends_on
```

`analizar_csv`, en [importaciones/lector_csv.py](../backend/rentalab/importaciones/lector_csv.py), comprueba antes de la primera escritura el tamaño de hasta 1 MiB, UTF-8 con o sin BOM, cabecera, estructura CSV y máximo de 500 registros. Un archivo que no puede delimitarse correctamente no se importa parcialmente. Una fila delimitada con datos inválidos sí puede rechazarse sin perder otras filas.

Después, `ImportacionServicio.ejecutar` y `_procesar`, en [importaciones/servicio.py](../backend/rentalab/importaciones/servicio.py), validan cada fila y abren una sesión nueva para ella. `_procesar` mapea las columnas `starts_on`/`ends_on` a `start_date`/`end_date`. `ReservaPorCodigo` valida los campos resultantes reutilizando tipos de reservas y equipo: recorta nombre y referencia, normaliza el correo y recorta/pasa a mayúsculas el código. La referencia distingue mayúsculas: `ORDER-1` y `order-1` son distintas.

`ServicioReservas.crear_desde_codigo` decide dentro de `BEGIN IMMEDIATE`:

| Situación | Resultado | Cambio persistido |
| --- | --- | --- |
| Referencia nueva y reserva válida | `accepted` | Una reserva confirmada |
| Referencia existente con mismos datos normalizados | `already_imported` | Ninguno; devuelve la original |
| Referencia existente con cliente, correo, equipo o fechas distintos | `rejected` | Ninguno; no sobrescribe |
| Referencia nueva con equipo inactivo, avería o solapamiento | `rejected` | Ninguno para esa fila |

Para comparar el equipo se resuelve su código actual a su identificador. Si se renombra el código, reenviar el código antiguo puede dejar de identificar la misma unidad; la referencia no es una operación de actualización del catálogo.

La comparación idéntica ocurre antes de comprobar la disponibilidad actual: volver a importar una reserva cancelada no la reactiva, y una avería posterior no convierte un reintento idéntico en una reserva nueva. La referencia sigue siendo única después de cancelar.

Cada fila confirma o revierte por separado. Si un archivo tiene dos pedidos válidos y uno solapado, se conservan los dos válidos y se informa del rechazo. Al reenviarlo, los dos aceptados se reconocen por referencia y la fila corregida puede reintentarse. Esta importación parcial exige leer los totales **y** cada resultado; un HTTP 200 no significa que todas las filas se aceptasen. El contrato completo está en [IMPORTACIONES.md](IMPORTACIONES.md).

La transacción serializa también referencias concurrentes y la restricción `UNIQUE` protege su almacenamiento. [test_importacion_concurrencia.py](../backend/tests/test_importacion_concurrencia.py), en `test_simultaneos_importaciones_con_la_mismo_referencia_son_atomico_y_idempotente`, verifica dos casos: misma referencia/datos iguales deja una aceptada y otra ya importada; datos distintos deja una aceptada y una rechazada. En ambos persiste una sola reserva.

## 7. Comprueba el comportamiento en varias capas

| Pregunta | Dónde buscar la prueba |
| --- | --- |
| ¿Se permiten límites adyacentes y se rechaza el intervalo inválido? | [test_reservas.py](../backend/tests/test_reservas.py) |
| ¿Dos conexiones reales evitan una doble reserva? | `test_dos_conexiones_no_puede_confirmar_incompatibles_reservas`, en [test_reserva_concurrencia.py](../backend/tests/test_reserva_concurrencia.py) |
| ¿Un lector que bloquea el commit provoca rollback completo? | `test_a_confirmar_bloqueado_por_a_lector_revierte_regreso_sin_creando_a_reserva`, en ese mismo archivo |
| ¿Una avería conserva los datos de reservas previas? | [test_incidencias.py](../backend/tests/test_incidencias.py) |
| ¿Reimportar conserva también una reserva cancelada? | `test_canceladas_identico_importacion_permanece_idempotente_pese_real_indisponibilidad`, en [test_importaciones.py](../backend/tests/test_importaciones.py) |
| ¿El formulario conserva valores y permite recuperarse de un 409? | [PaginaReservas.test.tsx](../frontend/src/paginas/PaginaReservas.test.tsx) |
| ¿El informe muestra todos los resultados que devuelve Python? | [PaginaImportaciones.test.tsx](../frontend/src/paginas/PaginaImportaciones.test.tsx) |
| ¿El acceso y un 401 retiran las pantallas privadas? | [Autenticacion.test.tsx](../frontend/src/Autenticacion.test.tsx) |
| ¿El registro fuerza customer y el rol vigente procede de SQLite? | [test_usuarios.py](../backend/tests/test_usuarios.py) y [test_rol_access.py](../backend/tests/test_acceso_rol.py) |
| ¿Dos clientes no pueden manipular IDs ni campos administrativos? | [test_cuenta_seguridad.py](../backend/tests/test_cuenta_seguridad.py) |
| ¿Se respeta hoy en Madrid y la cancelación idempotente? | [test_cuenta_reservas.py](../backend/tests/test_cuenta_reservas.py) |
| ¿Dos clientes incompatibles confirman una sola reserva? | [test_cuenta_reserva_concurrencia.py](../backend/tests/test_cuenta_reserva_concurrencia.py) |
| ¿Se conservan equipo/fechas al acceder y tras un 409? | [PaginaProducto.test.tsx](../frontend/src/portal/PaginaProducto.test.tsx) |
| ¿Cliente y admin comparten estados sin filtrar notas privadas? | [test_administrador_conectado.py](../backend/tests/test_administrador_conectado.py) |
| ¿Se migra desde vacío y se recupera una copia coherente? | [test_arranque.py](../backend/tests/test_arranque.py) y [test_copias_seguridad.py](../backend/tests/test_copias_seguridad.py) |

En [conftest.py](../backend/tests/conftest.py), `settings` apunta a un archivo SQLite dentro de `tmp_path` y `app` aplica las migraciones Alembic reales. `client` inicia sesión y obtiene CSRF; no desactiva la protección. Las credenciales de esa fixture pertenecen sólo a bases desechables y no son una cuenta instalada. [`tmp_path`](https://docs.pytest.org/en/stable/how-to/tmp_path.html) es la fixture de pytest para directorios temporales.

Las pruebas concurrentes crean otra aplicación con otro motor contra el mismo archivo temporal. Los eventos SQL y `threading.Event` retienen el primer escritor y detectan el intento del segundo, sin depender de una pausa arbitraria. Comprueban conexiones diferentes, respuestas y datos finales. Esto aporta evidencia que una prueba de una función aislada o dos llamadas consecutivas no daría.

Las pruebas React interactúan con etiquetas y botones, y simulan respuestas HTTP controladas. Su objetivo es observar lo que hace el usuario, siguiendo el enfoque de [React Testing Library](https://testing-library.com/docs/react-testing-library/intro/). No demuestran que SQLite rechace un solapamiento: eso lo cubren las pruebas backend y los recorridos integrados.

Para estudiar un subconjunto, desde `backend/`:

```powershell
..\.venv\Scripts\python.exe -m pytest -q tests/test_reservas.py tests/test_incidencias.py tests/test_importaciones.py
..\.venv\Scripts\python.exe -m pytest -q tests/test_reserva_concurrencia.py tests/test_incidencia_concurrencia.py tests/test_importacion_concurrencia.py
..\.venv\Scripts\python.exe -m pytest -q tests/test_catalogo_publico.py tests/test_cuenta_seguridad.py tests/test_cuenta_reservas.py tests/test_cuenta_incidencias.py tests/test_administrador_conectado.py tests/test_cuenta_reserva_concurrencia.py
```

Desde `frontend/`:

```powershell
npm.cmd test -- src/paginas/PaginaReservas.test.tsx src/paginas/PaginaImportaciones.test.tsx src/Autenticacion.test.tsx
npm.cmd test -- src/portal/PaginaProducto.test.tsx src/portal/PaginaMisReservas.test.tsx
```

Las pruebas usan sus propias bases y mocks; no requieren reservar en la base habitual. Para los resultados actuales de suites, navegador, migración y contenedor, consulta el [balance integrado de F](VALIDACION_INTEGRADA.md) y su registro en [PROYECTO.md](PROYECTO.md). Una propuesta de comprobación no equivale a una ejecución registrada.

## 8. Sitúa acceso y persistencia en el recorrido

El cliente [api/cliente.ts](../frontend/src/api/cliente.ts) centraliza credenciales del mismo origen, CSRF, errores y comprobación de respuestas. [ProveedorAutenticacion](../frontend/src/autenticacion/ProveedorAutenticacion.tsx) consulta la sesión y `ExigirRol`, definido en [Aplicacion.tsx](../frontend/src/Aplicacion.tsx), impide montar pantallas privadas antes de comprobarla; `IntermediarioAutenticacion` en [autenticacion/intermediario.py](../backend/rentalab/autenticacion/intermediario.py) protege las rutas privadas de `/api`. El catálogo público y el [portal de cliente](PORTAL_CLIENTE.md) tienen rutas separadas de `/admin`. Un 401 vuelve al acceso; un 403 indica rol insuficiente o CSRF inválido; un 422 indica datos inválidos. No son intercambiables.

El frontend compilado puede ser público porque no lleva datos privados ni secretos. La cookie firmada contiene un identificador y contexto CSRF; el servidor exige además un registro de sesión vigente en SQLite. No se almacenan contraseñas ni tokens de sesión en localStorage. [ACCESO.md](ACCESO.md) explica preparación, expiración y cierre.

`/mi-cuenta` representa los datos de la sesión real, con perfil de sólo lectura en esta versión. No existe una edición de correo, contraseña o rol desde esa pantalla; inventar esos campos en una petición no amplía el contrato de la API.

Las migraciones cambian el esquema sin seed automático. El contenedor usa una instancia/un worker y monta `/data` completo. Los comandos de [copias_seguridad.py](../backend/rentalab/copias_seguridad.py) usan el mecanismo de backup SQLite, en lugar de copiar sólo un `.db` vivo ignorando WAL u otros auxiliares. El procedimiento de detener, restaurar y rotar secreto está en [DESPLIEGUE.md](DESPLIEGUE.md).

## Preguntas con respuesta

**¿Por qué el fin es exclusivo?** Permite expresar días completos y encadenar devoluciones y nuevas reservas sin inventar una hora de corte. `[10, 12)` y `[12, 14)` no comparten día.

**¿Por qué no basta con que React deshabilite el botón?** La petición puede llegar desde otro cliente y el dato puede cambiar después de consultar. El servidor valida y comprueba dentro de la transacción.

**¿Por qué un correo coincidente no demuestra propiedad?** Es un dato de contacto histórico, no una relación autenticada. Sólo `customer_user_id` concede acceso propio; el registro no rellena esa columna en reservas antiguas.

**¿Por qué 404 al cambiar un ID ajeno?** El contrato no confirma a otro cliente si ese recurso privado existe. La falta de sesión da 401 y la gestión con rol insuficiente da 403.

**¿Puede un aviso de cliente bloquear equipos?** Se registra no bloqueante. Administración decide bloqueo; el texto del cliente o un `blocking=true` falsificado no concede ese permiso.

**¿La referencia única evita por sí sola dobles reservas?** Evita duplicar esa referencia. Dos referencias diferentes todavía podrían pedir el mismo equipo y rango; para eso están disponibilidad y transacción.

**¿Un único worker elimina la necesidad de transacciones?** No. Puede haber peticiones concurrentes y otros procesos conectados al archivo. La consistencia no depende sólo del número de workers.

**¿Resolver una incidencia significa que el equipo está disponible?** Sólo elimina ese impedimento. Puede haber otra bloqueante, equipo inactivo o reservas en el intervalo solicitado.

**¿Cancelar libera la referencia externa?** No. Conserva reserva e identidad del pedido, y evita que un reintento la vuelva a crear.

**¿Por qué la importación no usa una transacción para todo el archivo?** El contrato permite aceptar pedidos independientes y corregir sólo los rechazados. La validación estructural global sigue ocurriendo antes de cualquiera de esas transacciones.

**¿Por qué no borrar los archivos WAL/SHM durante una restauración?** Pueden pertenecer a la base y sus conexiones. El procedimiento exige detener todas las aplicaciones usuarias y utiliza el mecanismo SQLite; borrar auxiliares manualmente no equivale a una restauración segura.

**¿Todas las pruebas nacieron rojas?** No se afirma eso. [PROYECTO.md](PROYECTO.md) identifica grupos y regresiones ejecutados primero en rojo, y distingue aserciones añadidas ya verdes. La suite actual demuestra comportamiento actual, no reconstruye por sí sola la historia de desarrollo.

## Tres ejercicios pequeños

Realízalos en una rama o copia de trabajo. No apuntes comandos HTTP a la base habitual: usa las fixtures temporales de pytest y no cambies su URL hacia `data/rentalab.db`.

### Ejercicio 1: razona sobre los límites

En papel, parte de `CAM-001` confirmada del 10 al 12. Predice si se admite: A) la misma unidad del 12 al 13; B) la misma unidad del 11 al 12; C) `CAM-002` del 10 al 12; D) cualquier unidad del 12 al 12. Después localiza las pruebas que respaldan cada respuesta y ejecuta:

```powershell
..\.venv\Scripts\python.exe -m pytest -q tests/test_reservas.py
```

**Autocomprobación:** A se admite por adyacencia; B devuelve 409 por solapamiento; C se admite por ser otra unidad, si está activa y sin incidencias; D devuelve 422 porque el rango no es positivo. Debes poder explicar por qué en A aparece `<` y no `<=` en el límite de la consulta.

### Ejercicio 2: combina dos impedimentos

Añade una prueba de comportamiento en un archivo nuevo dentro de `backend/tests/`. Con `client` y `equipment_payload`, crea un equipo inactivo y una incidencia bloqueante. Resuelve la incidencia con una explicación y consulta disponibilidad para un rango válido. Activa luego el equipo y repite la consulta. Reutiliza las rutas HTTP existentes; no consultes atributos privados del servicio.

**Autocomprobación:** tras resolver, el equipo continúa inactivo y el motivo es `equipment_inactive`; tras activarlo, el mismo rango queda libre si no creaste reservas. La incidencia sigue consultable como `resolved`, con su explicación. La prueba no necesita borrar ni modificar datos reales y debe dejar la suite existente verde.

### Ejercicio 3: comprueba un reintento sin sobrescritura

Añade una prueba que cree `CAM-001` mediante la fixture, importe una fila con referencia `STUDY-001` y la importe idéntica otra vez. Cambia sólo `customer_name` en un tercer envío. Usa el patrón multipart de [test_importaciones.py](../backend/tests/test_importaciones.py), sin subir archivos al servidor habitual.

**Autocomprobación:** los tres informes indican, respectivamente, una `accepted`, una `already_imported` y una `rejected`. El listado contiene una única reserva con el nombre del primer envío y el mismo identificador. No basta con comprobar tres HTTP 200: comprueba los resultados por fila y el estado persistido.

## Límites que debes poder explicar

RentaLab demuestra visitantes, registro público de clientes y administradores persistidos, con una instancia y un worker SQLite. La compatibilidad del operador anterior es transitoria. No incluye varias empresas, pagos, cesta, recuperación de contraseña, gestión completa de usuarios, paginación ni auditoría completa. Las escrituras se serializan; no se ha medido capacidad ni alta disponibilidad. Docker, HTTPS y subida de archivos por navegador sólo se presentan como verificados cuando consta su ejecución en el registro.

Las [dependencias de usuario actual de FastAPI](https://fastapi.tiangolo.com/tutorial/security/get-current-user/) ayudan a leer la autorización centralizada. La referencia de [OAuth2 scopes](https://fastapi.tiangolo.com/advanced/security/oauth2-scopes/) explica permisos granulares, pero aquí se usan roles SQLite y cookie, sin OAuth2/JWT. [React Router declarativo](https://reactrouter.com/start/declarative/routing) explica los layouts anidados; [React con TypeScript](https://react.dev/learn/typescript) permite estudiar props y hooks estrictos junto a las comprobaciones de JSON del cliente.

La IA asistió en generación, revisión y documentación del código, mediante Codex y agentes. Leer, ejecutar y explicar estos recorridos sirve para comprobar tu comprensión; no convierte automáticamente el trabajo asistido en experiencia profesional previa. El [guion de demo](DEMO_LEANMIND.md) propone una forma fiel de presentarlo.
