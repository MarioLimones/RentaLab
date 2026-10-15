# Portal público y de cliente — fase D

RentaLab incorpora el catálogo y el recorrido de alquiler al mismo frontend React, con TypeScript estricto, Vite y React Router. El panel administrativo conserva sus funciones bajo `/admin` y su barra lateral. El portal tiene cabecera, navegación de catálogo/cuenta y pie propios; una cuenta cliente no recibe navegación administrativa.

El portal consume las APIs existentes de [catálogo público](CATALOGO_PUBLICO.md), [identidad y permisos](ACCESO.md) y [operaciones propias](OPERACIONES_CLIENTE.md). Las reglas, transacciones, datos y migraciones siguen perteneciendo al backend FastAPI y SQLite. Esta fase no añade tablas, migraciones ni otra copia de los datos de negocio.

## Pantallas y permisos

| Ruta React | Acceso y contenido |
| --- | --- |
| `/` | Redirige a `/catalogo` |
| `/catalogo` | Público: búsqueda por nombre, categoría, fechas, filtro de disponibles y tarjetas |
| `/equipos/:id` | Público: ficha, descripción pública, características, imagen, fechas y disponibilidad; el cliente puede confirmar una reserva |
| `/acceso` | Formulario de acceso; conserva un destino interno permitido |
| `/registro` | Registro de cliente; tras crearlo conduce al acceso, conservando el destino y preseleccionando el correo |
| `/mis-reservas` | Cliente: listado propio con reservas confirmadas y canceladas |
| `/mi-lista` | Cliente: productos guardados, calendario común y reserva de varios productos para el mismo periodo |
| `/mis-reservas/:id` | Cliente: referencia, equipo, fechas, estado, cancelación dentro de plazo y aviso desde reserva confirmada |
| `/mis-incidencias` | Cliente: avisos propios, estado y respuesta pública de RentaLab |
| `/mi-cuenta` | Cliente: nombre y correo de la sesión comprobada, de solo lectura |
| `/admin` | Administrador: resumen de gestión y acceso a equipos, reservas, incidencias e importaciones |

La sesión cliente no permite abrir `/admin`; el administrador utiliza su panel para gestionar reservas y no se presenta como cliente de `/api/me`. Si falta sesión al entrar en una pantalla propia, se ofrece acceso conservando la ruta. Una sesión con rol diferente recibe una pantalla de acceso restringido, con enlace a su zona.

Las rutas administrativas actuales son `/admin/equipos`, `/admin/equipos/nuevo`, `/admin/equipos/:id`, `/admin/equipos/:id/editar`, `/admin/reservas`, `/admin/reservas/nueva`, `/admin/reservas/:id`, `/admin/incidencias`, `/admin/incidencias/nueva`, `/admin/incidencias/:id` y `/admin/importaciones`. Algunos enlaces anteriores de gestión redirigen tras exigir administrador. **`/equipos/:id` es ahora la ficha pública**; para información de gestión debe usarse `/admin/equipos/:id`. El prefijo de las APIs administrativas se conserva: cambiar rutas visuales no abre sus endpoints.

## Elegir fechas y confirmar

1. Escribe en «Buscar equipo» de `/catalogo`: la búsqueda se aplica automáticamente tras una pausa de **150 ms**, sin pulsar Enter. Las tarjetas anteriores siguen visibles durante la consulta y se conserva espacio para evitar saltos de scroll; el encabezado indica «Actualizando…». No se consulta por cada letra ni durante la composición de texto, y las respuestas antiguas se descartan. Sin fechas aplicadas, las tarjetas solicitan inicio y fin; no afirman que el material esté libre.
2. Abre «Fecha de inicio» o «Fecha de fin» para elegir recogida y devolución en el calendario del catálogo; el rango queda resaltado. «Hoy» cambia al mes actual y «Borrar fechas» limpia ambos extremos. El calendario admite flechas, Inicio/Fin y Re Pág/Av Pág; Escape lo cierra y devuelve el foco al control. En móvil se despliega dentro del formulario. Pulsa **Consultar catálogo** para aplicar las fechas y consultar la disponibilidad pública de cada equipo del resultado. El filtro «Solo disponibles» se puede activar siempre y se aplica inmediatamente, conservando únicamente respuestas explícitamente disponibles. Sin fechas aplicadas muestra la disponibilidad de hoy; con un intervalo aplicado utiliza esas fechas. Cambiar o borrar las fechas conserva el filtro, y el nuevo intervalo se aplica al consultar. Las tarjetas y sus enlaces usan el intervalo de la última consulta aplicada; un borrador sin enviar no cambia esa disponibilidad.
3. Abre la ficha. El calendario muestra la ocupación real desde la primera carga, sin elegir fechas: días disponibles, ocupados y pasados. Pulsa un día de recogida y otro de devolución; el intervalo se comprueba automáticamente. Los botones de resumen permiten editar cada extremo y «Cambiar fechas» limpia la selección. Equipo y fechas viajan en la URL, por ejemplo `/equipos/1?start_date=2027-11-10&end_date=2027-11-12`.
4. Si falta sesión, «Acceder para reservar» conduce a `/acceso?next=…`. Pasar a registro conserva ese destino; registrar una cuenta no inicia sesión ni crea una reserva.
5. Tras acceder como cliente se vuelve a la ficha con sus fechas. **Volver no ejecuta ningún POST de reserva.** Revisa el intervalo y pulsa expresamente «Confirmar reserva».
6. El servidor comprueba disponibilidad y fechas dentro de la transacción y confirma inmediatamente si siguen siendo válidas. La pantalla muestra referencia `#id`, estado, intervalo confirmado y enlace a su detalle propio.

Las fechas siguen siendo cadenas de calendario `YYYY-MM-DD`, sin horas ni conversiones a UTC. El alquiler utiliza `[inicio, fin)`: el inicio está incluido y el día de devolución queda excluido. El frontend detecta campos incompletos o fechas invertidas; Python conserva la validación definitiva. Para orientar el alta y el plazo de cancelación, React obtiene hoy con `Intl.DateTimeFormat` en `Europe/Madrid`; el backend decide con su reloj de Madrid, incluido el momento de adquirir la transacción.

La búsqueda automática actualiza sólo `q` en la URL, reemplazando la entrada actual sin añadir una por letra. Conserva categorías y fechas pendientes de aplicar: no las confirma ni las borra al escribir. **Consultar catálogo** o Enter permite aplicar categoría/fechas y consultar de inmediato, además de volver a comprobar el mismo intervalo sin cambiar filtros. Abrir un enlace directo o usar Atrás/Adelante restaura los filtros de esa URL. **Ver todo el catálogo** limpia tanto los filtros aplicados como cualquier borrador pendiente. Mientras se actualizan resultados, sus fechas, disponibilidad y enlaces siguen correspondiendo a la última respuesta completada, hasta sustituirla por la nueva. Los errores de búsqueda se anuncian sin mover el foco del campo.

El calendario impide comenzar en días pasados u ocupados y atravesar reservas; permite devolver el equipo el primer día ocupado por la siguiente reserva, porque ese día queda excluido. Al navegar a un mes posterior comprueba también el intervalo desde la recogida hasta ese mes: la ocupación mensual recortada no basta para decidir una devolución. Se puede recorrer con flechas, Inicio/Fin y Re Pág/Av Pág, y seleccionar con Intro. Carga y errores no se presentan como días libres.

Consultar disponibilidad no retiene equipo ni garantiza el resultado de una confirmación posterior. Un 409 de alta conserva equipo/fechas, muestra un conflicto comprensible y actualiza automáticamente calendario e intervalo. No se reintentan escrituras automáticamente. Durante el envío se impiden nuevas confirmaciones y cambios en sus fechas.

## Reservas, avisos y cuenta

La [lista guardada y reserva conjunta](LISTA_GUARDADA.md) amplía este recorrido: los favoritos se guardan por cuenta en SQLite y `/mi-lista` permite seleccionar varios productos, comparar disponibilidad y confirmarlos en una única transacción. La migración adicional es `0010_saved_products`; el alcance sin tablas nuevas descrito al inicio corresponde a la fase D original.

Los listados propios utilizan exclusivamente `/api/me`. React no descarga reservas administrativas para filtrarlas: el servidor consulta por propietario y devuelve un esquema mínimo. Crear reserva envía solo `equipment_id`, `start_date` y `end_date`; el backend obtiene propietario, nombre y correo de la cuenta autenticada. No se asocian reservas anteriores por coincidencia de correo.

El detalle conserva referencia, fechas y estado después de cancelar. La acción exige confirmación y solo se presenta antes del día de inicio en Madrid. Cancelar actualiza la pantalla con la respuesta persistida y vuelve a consultar el recurso. La idempotencia, el plazo y la conservación del historial siguen garantizados por el servicio Python. Un rechazo conserva los datos y explica el problema.

Una reserva propia confirmada ofrece «Informar de un problema». El formulario solo pregunta título y descripción; equipo, reserva y autor se obtienen del contexto validado por el backend. El aviso nace pendiente de gestión y no bloqueante. Su envío no permite seleccionar prioridad, bloqueo, estado, respuesta o resolución. En `/mis-incidencias` se muestran título, descripción, estado y `public_response`; una respuesta vacía se presenta como «Pendiente de respuesta». Notas y resolución internas no se reciben ni se copian a esta vista.

`/mi-cuenta` muestra nombre y correo de `GET /api/auth/session`. **El perfil es de solo lectura en esta versión**: no se añade PATCH de nombre, correo, contraseña, identidad ni permisos. El cierre está disponible en la cabecera y revoca la sesión del backend.

Los equipos inactivos no aparecen en el catálogo y su ficha pública devuelve 404. Una reserva histórica de un equipo ya retirado sigue visible con «Equipo #id (ficha no disponible)»; no se consulta la API administrativa para recuperar datos privados. Los registros históricos sin propietario siguen visibles para administración y no se atribuyen a una cuenta desde React.

## Cliente HTTP, sesión y recuperación

`frontend/src/api/cliente.ts` concentra `fetch`, tipos, validación de respuestas, errores por campo y CSRF. Las páginas utilizan métodos públicos o propios explícitos. Las peticiones se realizan al mismo origen, con `credentials: 'same-origin'`; la cookie de sesión sigue siendo HttpOnly. CSRF permanece en memoria, se obtiene antes de escribir y se invalida al cambiar de sesión. No hay contraseñas, cookies, tokens de sesión o reservas guardados en `localStorage`/`sessionStorage`.

`ProveedorAutenticacion` consulta la sesión real al recargar y retira las pantallas privadas ante un 401. El cliente HTTP descarta respuestas privadas de una sesión anterior y el layout desmonta el estado de sus pantallas cuando cambia la identidad. La ficha/listado público vincula cada disponibilidad a equipo y fechas y descarta respuestas tardías; cambiar el intervalo no conserva una afirmación anterior de disponibilidad.

`frontend/src/autenticacion/destinos.ts` admite únicamente rutas internas conocidas. Descarta URLs externas, rutas con doble barra inicial, barras invertidas y caracteres de control; reconstruye solo los parámetros permitidos. Para catálogo/ficha conserva fechas de calendario válidas; en catálogo también búsqueda, categoría y filtro de disponibles. Las altas administrativas conservan únicamente el parámetro positivo `equipment_id` para preseleccionar una unidad. Un cliente no puede usar `next` para ir a administración. Tras acceder, el destino por defecto del cliente es `/mi-cuenta`; el del administrador es `/admin`, conservando solo un destino administrativo permitido.

Los enlaces de acceso y registro de la cabecera también conservan el destino permitido, incluso al alternar entre ambos formularios. En móvil pequeño la cabecera muestra «Acceder» y el registro sigue disponible desde su formulario. Los enlaces administrativos anteriores de listados/altas se redirigen bajo `/admin`, conservando la preselección del equipo; `/equipos/:id` corresponde ahora a la ficha pública.

| Respuesta o estado | Tratamiento en el portal |
| --- | --- |
| Carga | Mensaje de estado; las pantallas privadas esperan la consulta de sesión |
| Lista vacía | Explicación y siguiente acción: catálogo, reservas o ajuste de filtros |
| Error de conexión o carga | Mensaje y reintento explícito; se conservan los valores del formulario |
| 401 | Se invalida la sesión privada y se ofrece acceso; equipo y fechas permanecen en la ruta de retorno |
| 403 | Se explica la falta de permiso; el servidor sigue decidiendo rol y CSRF |
| 404 | Equipo fuera de catálogo o recurso privado no encontrado; no se revela un propietario ajeno |
| 409 | Conflicto con fechas conservadas; nueva consulta antes de otra confirmación |
| 422 | Errores asociados a los campos y resumen accesible |

Los avisos usan texto además de color. Los formularios tienen etiquetas persistentes, ayudas, `aria-describedby` y `aria-invalid`. Los errores reciben foco; la cancelación mueve el foco a la confirmación y lo devuelve al volver, o a los datos tras completarse. La confirmación de alta recibe foco y ofrece el detalle como siguiente paso. Hay navegación por teclado, enlace para saltar al contenido y disposición de una columna en móvil. Estas decisiones de implementación no sustituyen el registro de comprobaciones reales.

## Código y comprobaciones

`Aplicacion.tsx` separa rutas públicas, propias y administrativas. `portal/DisposicionCliente.tsx` contiene cabecera y pie; `PaginaCatalogo.tsx` y `PaginaProducto.tsx` implementan catálogo/ficha; `PaginaMisReservas.tsx`, `PaginaMiReserva.tsx`, `PaginaMisIncidencias.tsx` y `PaginaMiCuenta.tsx` cubren la cuenta. `portal/intervaloFechas.ts` comparte la validación de formulario y hoy Madrid. El panel conserva sus páginas existentes bajo `administracion/AplicacionAdministracion.tsx`.

Desde `frontend` pueden ejecutarse:

```powershell
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test
npm.cmd run build
```

Vitest y React Testing Library comprueban el recorrido de acceso, fechas conservadas, confirmación explícita, conflicto y reservas propias, además de estados y accesibilidad de los controles. Las reglas de ownership, transacción, concurrencia y CSRF se conservan en las suites backend. [PROYECTO.md](PROYECTO.md) registra las ejecuciones, el recorrido de navegador y sus limitaciones reales; este documento no implica despliegue externo ni comprobaciones pendientes completadas.
