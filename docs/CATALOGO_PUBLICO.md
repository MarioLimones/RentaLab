# Catálogo público y disponibilidad — fase B

El catálogo de lectura vive bajo `/api/public`. Sus esquemas no heredan las respuestas administrativas: sólo publican los campos necesarios para presentar equipos activos. La gestión existente conserva sus URLs y requiere administrador, incluida la lectura de códigos, descripción interna, unidades inactivas y motivos detallados de disponibilidad.

El catálogo muestra una sola ficha por modelo. Las unidades con el mismo nombre y categoría se agrupan tras recortar espacios, normalizar Unicode NFC e ignorar mayúsculas. La ficha utiliza los datos públicos de la unidad activa con menor ID; los enlaces anteriores de otras unidades activas siguen resolviendo el modelo. Los códigos y las reservas históricas mantienen su unidad física, sin migrar ni fusionar registros. No se muestra una cantidad de unidades en la ficha.

La disponibilidad pública exige una unidad activa, sin incidencia bloqueante y libre durante **todo** el intervalo. Confirmar desde el portal selecciona esa unidad bajo `BEGIN IMMEDIATE` y guarda su ID físico. Con dos cámaras libres se aceptan dos reservas coincidentes; la tercera se rechaza. Cancelar libera sólo su unidad. Administración y CSV conservan la selección explícita por unidad y código.

## Rutas públicas

| Método y ruta | Resultado |
| --- | --- |
| `GET /api/public/equipment` | Lista de equipos activos |
| `GET /api/public/equipment?q=cámara&category=Cámaras` | Búsqueda por nombre y filtro de categoría combinables |
| `GET /api/public/equipment/{equipment_id}` | Detalle público activo o 404 |
| `GET /api/public/equipment/{equipment_id}/reservations` | Fechas de recogida y devolución de las reservas en curso y próximas del modelo |
| `GET /api/public/equipment/{equipment_id}/disponibilidad` | Sin fechas: solicita seleccionarlas, sin afirmar disponibilidad |
| `GET /api/public/equipment/{equipment_id}/disponibilidad?start_date=2026-11-10&end_date=2026-11-12` | Disponibilidad orientativa para `[inicio, fin)` |
| `GET /api/public/images/equipment-placeholder.svg` | Imagen alternativa incluida en el backend; funciona sin internet ni frontend compilado |

No exigen sesión ni CSRF. No hay operaciones de escritura en este namespace. OpenAPI marca estas lecturas sin seguridad requerida; la documentación interactiva completa conserva acceso administrativo.

La búsqueda `q` encuentra un fragmento literal del nombre; `%` y `_` no actúan como comodines SQL. La categoría coincide completa. Ambos filtros recortan espacios y comparan sin distinguir mayúsculas mediante `casefold`; un valor vacío equivale a no filtrar. `q` admite hasta 120 caracteres y categoría hasta 80. El orden es nombre e identificador; sin coincidencias se devuelve `[]`. No se admite `active=false` para abrir unidades inactivas, ni parámetros desconocidos. La implementación actual filtra en Python los equipos activos para mantener comparación Unicode coherente con SQLite; no se añade paginación ni se afirma rendimiento para catálogos grandes.

## Respuestas explícitas y privacidad

Un equipo público tiene exactamente estos campos:

```json
{
  "id": 1,
  "name": "Cámara Aurora S4",
  "category": "Cámaras",
  "public_description": "Cámara ficticia para entrevistas y grabaciones en estudio.",
  "technical_specs": {"Resolución": "4K UHD", "Conexiones": "HDMI y USB-C"},
  "image_url": null,
  "image_fallback_url": "/api/public/images/equipment-placeholder.svg",
  "active_reservations_count": 4
}
```

El ID permite solicitar detalle, disponibilidad y fechas de reservas. Se excluyen `code`, `active`, `description` interna, propietario, autoría, datos de clientes, identificadores de reservas y unidades, referencias, estados de incidencia, prioridades, averías y cualquier dato de administración. Las fechas de reservas se publican únicamente mediante el contrato limitado descrito a continuación. El contrato es el mismo para visitante, cliente y administrador al usar `/api/public`.

`active_reservations_count` cuenta las reservas confirmadas, sin cancelar, de todas las unidades físicas activas del modelo cuyo `end_date` sea posterior a hoy en `Europe/Madrid`. Incluye las reservas en curso y futuras, sin filtrar por las fechas seleccionadas para consultar disponibilidad. Excluye las ya terminadas y las que se devuelven hoy, porque el fin es exclusivo. Cuenta reservas, no unidades disponibles ni capacidad del modelo. La ficha del catálogo muestra «N reserva» o «N reservas», con el texto «En curso y próximas», a la derecha de «Ver equipo». Al pulsar el recuento se consultan las fechas y se despliegan debajo de esa fila, con recogida, devolución y un recordatorio de que el día de devolución no forma parte del intervalo ocupado. El despliegue presenta un mensaje si no hay reservas y permite reintentar si falla la consulta.

`GET /api/public/equipment/{equipment_id}/reservations` devuelve el ID canónico del modelo y una lista cronológica de intervalos que aplica el mismo alcance que el recuento:

```json
{
  "equipment_id": 1,
  "reservations": [
    {"start_date": "2026-11-10", "end_date": "2026-11-12"},
    {"start_date": "2026-11-10", "end_date": "2026-11-12"}
  ]
}
```

Cada reserva conserva su propio intervalo, incluidos los intervalos idénticos de distintas unidades; no se fusionan. La consulta se realiza al abrir el despliegue y sólo publica fechas, sin identificadores de reservas o unidades ni datos privados de clientes o gestión. Una reserva de una unidad no implica que el modelo completo esté indisponible: pueden quedar otras unidades libres. El calendario y la consulta de disponibilidad siguen determinando si se puede reservar el modelo para el periodo elegido.

La descripción pública es una columna nueva: migrar **no copia** el texto previo de `description`. La administración debe escribir contenido pensado para publicarse. Las características técnicas y la imagen también son campos de publicación; no deben contener notas internas. La proyección del servidor no convierte anotaciones de gestión en contenido público.

Con fechas completas:

```json
{
  "equipment_id": 1,
  "start_date": "2026-11-10",
  "end_date": "2026-11-12",
  "available": false,
  "status": "unavailable"
}
```

Sin fechas:

```json
{
  "equipment_id": 1,
  "start_date": null,
  "end_date": null,
  "available": null,
  "status": "select_dates"
}
```

`available=true/status=available` sólo se devuelve tras evaluar ambas fechas para todas las unidades activas del modelo hasta encontrar una libre. Si no queda ninguna utilizable, la respuesta pública es únicamente `available=false/status=unavailable`: no incluye `reason`, identificadores de reservas/incidencias ni descripción del problema. El único recuento público de reservas es `active_reservations_count` en el equipo; no se publican otras estadísticas de reservas ni de averías.

## Fechas y reglas compartidas

Las fechas son días ISO exactos `YYYY-MM-DD`, sin hora, y el fin debe ser posterior al inicio. El inicio se incluye y el fin se excluye: una reserva del 10 al 12 ocupa el 10 y el 11; otra puede comenzar el 12. Una sola fecha, formato inválido, día inexistente, intervalo vacío/invertido o parámetro desconocido producen 422.

Detalle y disponibilidad de una unidad inactiva o inexistente devuelven el mismo 404. Sin fechas no se consulta ni se afirma que una unidad esté libre; primero hay que seleccionarlas. Con fechas se reutiliza `IntervaloFechas` y `DisponibilidadServicio.comprobar`, ya utilizado por las consultas de gestión, el alta de reservas y el CSV. Se mantienen exactamente las reglas: sólo reservas confirmadas solapadas bloquean; canceladas y rangos adyacentes no; incidencias bloqueantes abiertas/en curso impiden reservar y las resueltas o no bloqueantes no lo impiden.

El catálogo no guarda una segunda columna de disponibilidad. Aplica el servicio compartido a cada unidad del modelo. La respuesta es orientativa: entre consulta y alta puede cambiar el estado. Confirmar reserva vuelve a evaluar las reglas dentro de la transacción `BEGIN IMMEDIATE` existente.

## Calendario público de días ocupados

`GET /api/public/equipment/{id}/calendar?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD` requiere un intervalo completo `[inicio, fin)` de hasta 366 días. Devuelve equipo, límites consultados, `intervalos_ocupados` con los días en que todas las unidades utilizables están reservadas y `can_book` con el estado general de nuevas reservas. Sólo cuentan reservas confirmadas; se agrupan los días consecutivos sin revelar identificadores, referencias o datos de clientes. `can_book=false` indica que ninguna unidad activa admite reservas. Equipo inactivo o inexistente devuelve 404.

El parámetro opcional `booking_start` indica la recogida seleccionada. `unavailable_end_dates` contiene las devoluciones dentro del rango visible para las que no existe una única unidad libre desde esa recogida (vacío sin parámetro). La ventana desde recogida hasta fin de consulta también admite como máximo 366 días. Esto evita ofrecer un alquiler que exigiría cambiar de cámara a mitad del periodo aunque siempre quede alguna cámara libre en días sueltos. El portal vuelve a consultar al cambiar la recogida, incluso dentro del mismo mes, y conserva el foco del calendario durante esa actualización.

El portal muestra un mes navegable con texto accesible para distinguir ocupado y libre. La consulta de un rango y la confirmación siguen utilizando las reglas compartidas del servidor; el calendario no retiene fechas. Tras crear, cancelar o recibir un conflicto de disponibilidad se consulta de nuevo el backend. [RESERVAS_MULTIUSUARIO.md](RESERVAS_MULTIUSUARIO.md) explica la demostración y las sesiones independientes.

## Edición administrativa y compatibilidad

Los campos se editan mediante `POST /api/equipment`, `PUT /api/equipment/{id}` o `PATCH /api/equipment/{id}`, siempre con sesión administrativa y CSRF. Clientes reciben 403; sin sesión, 401. Las lecturas antiguas `/api/equipment`, `/api/equipment/{id}` y `/api/equipment/{id}/disponibilidad` también pasan a ser administrativas para cerrar la exposición de códigos/notas/motivos detallados de fase A.

Ejemplo de cuerpo PATCH para publicar presentación:

```json
{
  "public_description": "Cámara ficticia para entrevistas y grabaciones en estudio.",
  "technical_specs": {"Resolución": "4K UHD", "Conexiones": "HDMI y USB-C"},
  "image_url": null
}
```

`public_description` admite hasta 2000 caracteres, recortados y sin NUL. `technical_specs` es un objeto con hasta 20 pares: claves recortadas de 1–80 caracteres y valores de 1–300, todos cadenas sin NUL; se rechazan claves repetidas tras normalizar espacios. Cada equipo conserva su propio objeto. `image_url` admite `null`, HTTPS sin credenciales, consulta ni fragmento, o una ruta segura dentro de `/api/public/images/`; no se admiten rutas de disco, `data:`, JavaScript ni traversal. El backend no descarga imágenes remotas.

Omitir campos en PATCH los conserva; `image_url:null` retira la imagen. Los demás campos no admiten null. PUT mantiene su contrato de reemplazo y los valores omitidos toman defaults (`""`, `{}`, `null`). El formulario React anterior cambia su guardado a PATCH para que editar nombre/categoría no borre los campos públicos que todavía no presenta. Esta fase entrega la API; no construye el catálogo visual ni nuevos controles de publicación.

## Imágenes y datos ficticios

Siempre se devuelve `image_fallback_url`, con un SVG local autocontenido. Cuando `image_url` es null, el consumidor usa directamente esa alternativa; si configura una imagen opcional que falla, debe sustituirla por la alternativa local una vez. El futuro frontend deberá implementar ese manejo de error. No hay una dependencia obligatoria de un proveedor de imágenes ni se añade subida de archivos.

La migración `0007_public_catalogue` añade las columnas con defaults seguros, conserva IDs y referencias y no publica descripciones internas. El comando explícito `python -m rentalab.cargar_datos`, desde backend tras migrar, prepara cuatro equipos ficticios con descripciones públicas y características útiles: dos cámaras, un micrófono y un panel de iluminación. Todas sus imágenes opcionales son null y tienen alternativa local. El seed sigue siendo insert-only: no sobrescribe equipos existentes ni rellena silenciosamente sus nuevos campos. Para comprobar las fichas enriquecidas usa una base de demostración nueva o edita los campos públicos explícitamente como administrador.

Las pruebas cubren búsqueda y filtros, Unicode y comodines literales, fechas, inactivos, cancelación, adyacencia, incidencias, esquema exacto de respuestas, valores privados centinela, permisos de edición, migración y recurso SVG local. Las comprobaciones ejecutadas y sus límites se registran en [PROYECTO.md](PROYECTO.md).
