# Administración y conexión con el portal — fase E

RentaLab utiliza una aplicación React, un backend FastAPI y una base SQLite. El panel vive bajo `/admin`, con barra lateral propia y enlace **Ver catálogo público**. El portal mantiene su cabecera y sus rutas. Abrir una ficha pública desde administración no cambia el rol ni la sesión; el administrador vuelve a su panel desde la cabecera del portal.

Prepara el acceso y aplica las migraciones según [ACCESO.md](ACCESO.md). No hay cuentas ni contraseñas predeterminadas. Las rutas visuales no conceden permisos: todas las operaciones administrativas siguen protegidas en FastAPI, incluidas las APIs anteriores que conservan su URL.

## Pantallas del panel

| Ruta | Comportamiento |
| --- | --- |
| `/admin` | Cifras acumuladas reales, próximas reservas según hoy Madrid, incidencias bloqueantes y consulta de disponibilidad con intervalo explícito |
| `/admin/equipos` | Búsqueda por código/nombre/descripción, categoría y actividad; activar/desactivar sin borrar |
| `/admin/equipos/nuevo`, `/admin/equipos/:id/editar` | Datos internos y ficha pública en secciones separadas |
| `/admin/equipos/:id` | Datos, ficha pública, reservas e incidencias del equipo; acceso a catálogo y altas |
| `/admin/reservas` | Todas las reservas, también sin propietario; filtros combinables de cliente, ID de cuenta, equipo, fechas, estado y origen |
| `/admin/reservas/:id` | Identidad guardada, propietario, origen, fechas, estado y cancelación con confirmación |
| `/admin/incidencias` | Avisos del cliente e incidencias internas/históricas; filtros de equipo, estado, prioridad y bloqueo |
| `/admin/incidencias/:id` | Reserva/autor cuando se conocen, prioridad, bloqueo, notas internas, respuesta pública y estado/resolución |
| `/admin/importaciones` | Ejemplo y subida CSV con el formato, límites, informe e idempotencia existentes |

El resumen distingue **equipos activos** de **equipos disponibles**. Sus contadores de actividad abarcan todas las fechas. Las próximas reservas son confirmadas, aún no terminadas en la fecha de Europe/Madrid, ordenadas por inicio e ID, hasta seis. La disponibilidad pide inicio y fin, consulta cada unidad activa mediante la API administrativa existente y muestra el número disponible junto al intervalo `[inicio, fin)`. Cambiar fechas invalida el resultado previo; una respuesta tardía no sustituye la consulta vigente. La consulta es orientativa y crear vuelve a comprobar dentro de la transacción.

## Edición de la ficha pública

La descripción interna (`description`) se conserva separada de `public_description`. El nombre y la categoría forman parte de la presentación pública; el código y las notas internas no se publican. El formulario usa PATCH al editar y precarga los campos públicos existentes.

| Campo | Límite y uso |
| --- | --- |
| `public_description` | Texto opcional de hasta 2000 caracteres, visible en el catálogo |
| `technical_specs` | Objeto de hasta 20 pares nombre/valor; nombres únicos tras recortar, de 1–80 caracteres; valores de 1–300 |
| `image_url` | Opcional, hasta 2048 caracteres; HTTPS sin credenciales, consulta ni fragmento, o ruta de imagen bajo `/api/public/images/...` |
| `active` | Desactivar retira del catálogo y evita nuevas reservas; conserva datos e historial |

Las filas de características tienen etiquetas, errores y controles para añadir/quitar por teclado. La imagen vacía se envía como `null` para retirarla; el catálogo usa la alternativa SVG local. No se añade subida de imágenes ni se necesita un proveedor externo. Las rutas locales admitidas deben corresponder a imágenes públicas servidas por la aplicación; una imagen inexistente utiliza la alternativa del portal.

## Reservas: propietario y origen

`GET /api/reservations` y su detalle son administrativos. La respuesta incluye los datos de la reserva anteriores y añade `customer_user_id` nullable y `origin`. No se añaden estos campos al esquema de cliente bajo `/api/me`.

| Origen persistido | Asignación del servidor |
| --- | --- |
| `portal` | Nueva reserva creada desde `/api/me/reservations`; propietario obtenido de la sesión |
| `admin` | Nueva reserva creada desde `/api/reservations`; propietario desconocido, `null` |
| `csv` | Nueva reserva creada por una fila CSV; propietario desconocido, `null` |
| `legacy` | Registro que ya existía al aplicar la migración de esta fase; origen anterior no inferido |

Origen y propietario son decisiones del servidor. Enviarlos en un cuerpo de creación, incluso con un valor válido, produce 422. No hay endpoint para asignar reservas históricas a una cuenta. El panel muestra **Sin propietario de cuenta** cuando `customer_user_id` es `null` y distingue **Histórico · origen no conocido** del CSV creado desde esta fase. Un registro anterior con propietario conocido conserva ese propietario aunque su nuevo origen sea `legacy`.

Los filtros de la lista son combinables:

| Parámetro | Contrato |
| --- | --- |
| `customer` | Subcadena literal de nombre o correo guardados, recortada, de 1–254 caracteres; comparación Unicode sin distinguir mayúsculas; `%` y `_` son caracteres literales |
| `customer_user_id` | ID de cuenta positivo exacto; no busca coincidencias por correo |
| `equipment_id` | ID de equipo positivo, incluidas unidades inactivas |
| `status` | `confirmed` o `cancelled` |
| `origin` | `portal`, `admin`, `csv` o `legacy` |
| `start_date`, `end_date` | Ambos o ninguno, ISO sin hora; fin posterior al inicio; seleccionan reservas que solapan `[inicio, fin)` |

El orden sigue siendo inicio e ID. La búsqueda de cliente se realiza en el servidor; React envía el filtro, no decide qué reservas puede consultar cada rol. La política de cancelación del cliente sigue siendo anterior al día de inicio Madrid. Administración conserva la cancelación de gestión, sin ese límite de fecha, con confirmación visual, CSRF e idempotencia; no se borra el historial.

## Incidencias: gestión interna y comunicación

El aviso del cliente parte de una reserva propia confirmada. El servidor deduce equipo y autor y lo registra `open`, prioridad `medium` y **sin bloqueo**. Administración identifica la reserva vinculada y el autor cuando existen; los registros internos o históricos sin esos vínculos se conservan y se indican como tales.

| Método y ruta | Entrada administrativa |
| --- | --- |
| `POST /api/incidents` | Alta interna: equipo, título y descripción/prioridad/bloqueo opcionales; autor desde la sesión |
| `GET /api/incidents`, `GET /api/incidents/{id}` | Todos los registros y datos internos, sólo administrador |
| `PATCH /api/incidents/{id}` | Cualquier subconjunto no vacío de `priority`, `blocking`, `internal_notes`, `public_response` |
| `PATCH /api/incidents/{id}/status` | `status` y explicación `resolution` no vacía al resolver |

PATCH conserva los campos omitidos, rechaza `null` y campos desconocidos; `internal_notes` y `public_response` admiten texto vacío para borrar su contenido y tienen límite de 2000 caracteres. El estado conserva las transiciones existentes `open → in_progress`, `open → resolved` e `in_progress → resolved`.

**Guardar gestión** persiste prioridad, bloqueo y comunicación. Convertir una incidencia sin resolver en bloqueante pide confirmación: se rechazan nuevas reservas, mientras que las ya confirmadas se mantienen y se muestran para gestión. La prioridad por sí sola no bloquea. Resolver exige explicación interna; no la copia a la respuesta pública. La persona que comunicó el problema ve sólo sus avisos, estado y `public_response`, sin notas, prioridad, resolución interna ni otras reservas.

Resolver o retirar el bloqueo de una incidencia no fuerza disponibilidad. El servicio común vuelve a comprobar otras incidencias bloqueantes sin resolver, actividad del equipo y solapamientos confirmados del intervalo. Catálogo, portal, administración y CSV usan estas mismas reglas; React no mantiene una segunda implementación.

## Recorrido conectado

1. Un cliente confirma expresamente desde el portal con fechas futuras. Administración la consulta como origen `portal`, con su ID de cuenta y la identidad guardada en el servidor.
2. Administración cancela desde el detalle y confirma. El cliente, al volver a su listado/detalle o recargar, ve `cancelled` y conserva las fechas y su historial.
3. Sobre otra reserva propia confirmada, el cliente informa de un problema. Aparece en administración como aviso no bloqueante, con reserva y autor.
4. Administración guarda respuesta pública y notas internas, activa el bloqueo y lo confirma. El cliente ve la respuesta pública al volver a sus avisos. Intentar otra reserva del equipo recibe un conflicto por las reglas compartidas.
5. Si existe otra incidencia bloqueante, resolver la primera no libera el equipo. Tras resolver todas, tampoco se libera si está inactivo o el intervalo ya tiene reserva confirmada.

Los listados consultan al montar y al regresar a la vista. Las operaciones actualizan la respuesta persistida y vuelven a consultar donde corresponde; hay controles explícitos de actualización/reintento. Se descartan respuestas de cargas anteriores y se informa si falla una recarga. No se añade comunicación en tiempo real ni una caché global de reservas o disponibilidad.

## Migración y conservación del CSV

`0009_reservation_origin` añade únicamente la columna `origin` con valor inicial `legacy` y CHECK de los cuatro valores. Usa ALTER TABLE directo en SQLite y conserva propietarios existentes, IDs, referencias, incidencias vinculadas y demás columnas. No modifica migraciones anteriores ni intenta averiguar el origen por referencias externas o correos. No carga usuarios, reservas ni datos ficticios al arrancar o migrar.

La cabecera CSV sigue siendo `external_reference,customer_name,customer_email,equipment_code,starts_on,ends_on`, UTF-8 con o sin BOM, hasta **1 MiB y 500 registros**. Se mantiene la validación global y la transacción por fila. Una referencia repetida con datos normalizados idénticos devuelve `already_imported`, incluso después de cancelar; conserva origen y propietario del registro existente. Datos distintos no lo sobrescriben. Una referencia externa no demuestra que el registro histórico procediera de CSV. El detalle permanece en [IMPORTACIONES.md](IMPORTACIONES.md).

## Autorización y verificación

La [matriz de permisos](ACCESO.md#matriz-de-permisos) es la referencia. Sin sesión, API privada devuelve 401; con rol cliente, gestión devuelve 403, incluso con una petición HTTP directa a las URLs antiguas. Los recursos privados ajenos consultados mediante `/api/me` devuelven 404. Importar, modificar equipos, listar reservas globales y cambiar bloqueo requieren administrador y CSRF al escribir. El catálogo sólo expone sus esquemas públicos; una incidencia bloqueante produce indisponibilidad, sin publicar la avería.

Los comandos de pruebas, migración y arranque se conservan en [README.md](../README.md). Las comprobaciones realmente ejecutadas, métricas y límites de esta fase se registran en [PROYECTO.md](PROYECTO.md), sin deducir publicación externa a partir de pruebas locales.
