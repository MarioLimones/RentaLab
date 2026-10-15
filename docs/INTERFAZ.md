# Interfaz de RentaLab

La fase D incorpora el [portal público y de cliente](PORTAL_CLIENTE.md), con catálogo, ficha, acceso/registro, reservas, avisos y cuenta. La fase E completa el [panel y los recorridos conectados](ADMINISTRACION.md). Este documento conserva el recorrido del panel administrativo bajo `/admin`; sus operaciones requieren administrador. El detalle público `/equipos/:id` y el administrativo `/admin/equipos/:id` utilizan APIs y esquemas separados. Contratos y permisos en [ACCESO.md](ACCESO.md).

La fase 5 incorpora el panel React conectado a FastAPI. Las operaciones se guardan en SQLite mediante las APIs existentes. Se conservan backend, migraciones, contratos y datos; no había una interfaz Jinja2 que migrar. La fase 6 añade [acceso y cierre de sesión](ACCESO.md); primero prepara una cuenta e inicia sesión para seguir este recorrido.

## Pantallas y rutas

| Ruta | Uso |
| --- | --- |
| `/admin` | Cifras acumuladas reales, próximas reservas según hoy Madrid, avisos bloqueantes y disponibilidad para un rango explícito |
| `/admin/equipos` | Buscar por código, nombre o descripción y filtrar por categoría/estado; activar o desactivar |
| `/admin/equipos/nuevo` | Crear una unidad física y su presentación pública |
| `/admin/equipos/:id` | Datos internos y públicos, reservas/incidencias, enlaces a catálogo y altas |
| `/admin/equipos/:id/editar` | Editar datos internos, descripción pública, características, imagen y actividad |
| `/admin/reservas` | Todas las reservas; filtrar por cliente, ID de cuenta, equipo, estado, intervalo y origen |
| `/admin/reservas/nueva` | Consultar disponibilidad y crear una reserva |
| `/admin/reservas/:id` | Consultar y cancelar con confirmación, manteniendo el historial |
| `/admin/incidencias` | Filtrar por equipo, estado, prioridad y bloqueo |
| `/admin/incidencias/nueva` | Registrar un problema de una unidad |
| `/admin/incidencias/:id` | Gestionar prioridad/bloqueo, notas internas, respuesta pública, estado y resolución interna |
| `/admin/importaciones` | Descargar ejemplo, seleccionar CSV, subirlo y revisar cada resultado |

Las altas de reservas e incidencias admiten `?equipment_id=5` para preseleccionar una unidad al llegar desde su ficha. Las rutas desconocidas muestran una recuperación hacia el resumen. Se pueden abrir y recargar enlaces directos tanto en Vite como en el frontend compilado servido por FastAPI.

El resumen obtiene sus cifras de los listados reales y señala que son acumuladas. «Equipos activos» describe el catálogo, no la disponibilidad. Las próximas reservas son confirmadas que todavía no han terminado según hoy Europe/Madrid, ordenadas por inicio e identificador, con un máximo de seis. Los avisos agrupan por equipo las incidencias bloqueantes sin resolver. **Disponibilidad por fechas** exige un intervalo válido y muestra el número disponible entre las unidades activas junto al rango consultado. Cambiar fechas retira el resultado previo y descarta respuestas tardías. No se muestra un contador de equipos libres sin rango.

## Recorrido de uso

1. En **Equipos → Crear equipo**, introduce un código único, nombre y categoría. **Datos de gestión** separa la descripción interna de **Ficha pública del catálogo**: descripción pública, hasta 20 características con nombre/valor e imagen opcional. **Añadir característica** y **Eliminar característica** gestionan filas con etiquetas y foco; dejar imagen vacía conserva la alternativa local. El detalle muestra los datos normalizados y persistidos. Editar y activar/desactivar conservan la unidad y su historial; desactivar la retira del catálogo público.
2. Desde su detalle, pulsa **Crear reserva**. Introduce cliente y fechas; puedes consultar disponibilidad para ese equipo e intervalo antes de guardar. La consulta no retiene material. Crear vuelve a comprobar todo en Python.
3. Intenta otra reserva solapada para comprobar el conflicto. El mensaje se anuncia y recibe el foco; los valores permanecen para corregirlos. Una consulta anterior se oculta al cambiar equipo o fechas y las respuestas tardías se descartan.
4. En **Reservas**, combina cliente (nombre/correo literal), ID de cuenta exacto, equipo, origen, estado y ambas fechas. El listado y detalle indican propietario y origen; los históricos sin propietario se identifican sin asignarlos por correo. Abre la reserva, pulsa **Cancelar reserva** y confirma con **Sí, cancelar reserva**. **Volver** cierra la confirmación y devuelve el foco al botón inicial. Al cancelar se conserva cliente, referencia y fechas; el propietario ve el nuevo estado al volver a consultar en el portal.
5. El problema enviado desde una reserva del cliente aparece en **Incidencias** inicialmente no bloqueante, con reserva vinculada y autor. También se conservan los registros internos o históricos sin esos vínculos. En su detalle, **Guardar gestión** persiste prioridad, bloqueo, notas internas y respuesta visible al cliente. Activar un bloqueo sin resolver exige **Sí, guardar y bloquear**. La ficha del equipo y el resumen muestran el impedimento; las reservas confirmadas existentes se conservan.
6. **Iniciar trabajo** cambia a «En curso». Resolver exige una explicación interna que no se copia a la respuesta pública. Al resolver se conserva el historial y el foco vuelve a los datos de la incidencia. Otras incidencias bloqueantes, el estado activo y las fechas siguen condicionando la disponibilidad. El cliente ve sólo estado/respuesta pública en sus avisos, sin notas ni resolución internas.
7. En **Importaciones**, descarga el ejemplo, selecciona un CSV y pulsa **Importar pedidos**. Los totales y la tabla utilizan el informe del servidor; las reservas creadas o ya importadas tienen enlace a su detalle. Los rechazos muestran la explicación de cada fila. Ante un error global se conserva el archivo seleccionado.

No se guardan reservas ni incidencias en `localStorage`. Volver a un listado o al resumen vuelve a consultar la API; las operaciones actualizan el resultado persistido y recargan los datos donde corresponde. Los controles **Actualizar datos**, **Actualizar listado** y reintento permiten consultar de nuevo sin comunicación en tiempo real. Los filtros y borradores pertenecen a cada pantalla y no se conservan al abandonarla; el detalle de reserva puede abrir el listado filtrado por su ID de cuenta. El contexto compartido contiene la sesión; no gestiona datos de negocio ni una caché de disponibilidad. La cabecera del panel enlaza al catálogo y la del portal ofrece el retorno a `/admin` sólo a administradores.

## Organización del código

```text
frontend/src/
  Aplicacion.tsx           # Rutas públicas, propias y exigencia visual de rol
  administracion/          # Disposición administrativa, resumen por fechas y etiquetas de propiedad/origen
  portal/                 # Disposición pública, catálogo y páginas propias
  paginas/                # Resumen, catálogos, formularios, detalles e importaciones
  componentes/            # Campos, avisos, estados, iconos y conexión HTTP
  hooks/
    useRecurso.ts         # Carga, error, reintento y descarte de respuestas antiguas
    useRetroalimentacionFormulario.ts  # Estado de envío y errores del formulario
  tipos/api.ts            # Tipos de datos alineados con OpenAPI
  api/cliente.ts          # Único punto de fetch y comprobación de respuestas
  utilidades/fechas.ts     # Fechas de calendario sin conversión a UTC
  estilos.css             # Tokens y estilos adaptables propios
```

El cliente conserva sus reexportaciones de tipos para los consumidores anteriores. `ErrorApi` mantiene estado HTTP y mensaje, y añade errores por campo derivados de las rutas de validación de FastAPI. Los textos estándar de validación se presentan en español. Los mensajes de conflicto de Python se conservan. Los contratos de reservas, incidencias y CSV siguen en [RESERVAS.md](RESERVAS.md), [INCIDENCIAS.md](INCIDENCIAS.md) e [IMPORTACIONES.md](IMPORTACIONES.md).

`useRecurso` sólo aplica respuestas del cargador vigente; una respuesta antigua no reemplaza una nueva. Los detalles se aíslan por identificador. Un cambio correcto conserva la respuesta persistida aunque una lectura posterior falle: el error de recarga se muestra y permite reintentar. Un GET posterior correcto sustituye esa respuesta. Esto no es una segunda persistencia: sólo representa el resultado de la operación HTTP durante la vida de la pantalla.

La validación local ayuda con campos obligatorios, correo, intervalo, características públicas, imagen, explicación de resolución y tamaño del archivo. Python sigue decidiendo unicidad, actividad, transiciones, solapamientos, incidencias e idempotencia. El resumen consulta la disponibilidad del servicio existente; React no reproduce sus reglas. No se analiza el CSV en React. Las respuestas de gestión incorporan propietario/origen de reservas y comunicación de incidencias; los DTO públicos/propios mantienen su separación. No se han añadido dependencias ni modificado los locks.

## Fechas, diseño y accesibilidad

Las fechas de alquiler se conservan como cadenas `YYYY-MM-DD` y se envían sin horas. `formatearFecha` sólo reordena sus partes para mostrar `DD/MM/YYYY`; nunca usa `new Fecha(fecha)` ni `toISOString()`. La fecha actual del resumen se obtiene para Europe/Madrid, igual que la orientación de fechas del portal. La decisión definitiva de cliente sigue en el reloj del backend.

El panel usa fondo claro, texto oscuro, acento azul, iconos SVG propios y fuentes del sistema. No requiere fuentes ni imágenes de terceros; las imágenes HTTPS configuradas opcionalmente para fichas públicas tienen alternativa local. En escritorio hay barra lateral; en móvil las cinco secciones siguen visibles sin menú oculto. Los formularios pasan a una columna. Las tablas mantienen sus columnas dentro de una región desplazable y enfocables por teclado.

Los controles tienen etiquetas persistentes, ayudas y errores asociados mediante `aria-describedby` y `aria-invalid`. El resumen de errores recibe foco y enlaza con cada campo. Un error persistente no roba el foco al escribir. Carga y éxito se anuncian con estados accesibles; los estados usan texto además de color. Hay enlace de salto, navegación con `aria-current`, títulos de documento por sección, foco visible y respeto por movimiento reducido y colores forzados.

Contraste calculado sobre blanco: texto principal **13,84:1**, texto secundario **5,25:1**, azul **6,16:1**, placeholder **4,94:1** y borde de controles **3,23:1**. Son comprobaciones de estos tokens; no constituyen una auditoría completa de todas las combinaciones o tecnologías de apoyo.

## Arranque y comprobaciones

Los comandos de instalación reproducible y arranque PowerShell siguen en [README.md](../README.md). Con Uvicorn en 8000 y Vite en 5173, abre `http://127.0.0.1:5173`. Vite reenvía `/api` y `/health`; el cliente nunca cambia a una URL absoluta. La compilación servida por FastAPI utiliza el mismo origen sin proxy.

Desde la raíz:

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test
npm.cmd run build
Set-Location ..\backend
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m ruff check .
..\.venv\Scripts\python.exe -m ruff format --check .
..\.venv\Scripts\python.exe -m alembic check
```

`npm test` ejecuta Vitest sin modo interactivo. Las pruebas usan el cliente simulado para comprobar comportamiento de presentación; las pruebas Python ejecutan las reglas y persistencia en bases temporales.

Validación real registrada en la fase 5 (las comprobaciones adicionales de acceso de la fase 6 están en [PROYECTO.md](PROYECTO.md)):

- **121 pruebas frontend correctas**, incluidas conflicto con datos retenidos, fechas y disponibilidad, cancelación y foco, informe mixto y reintento de importación, filtros, formularios, resumen, errores por campo, respuestas tardías y recargas fallidas. Las 89 pruebas anteriores se conservan; las tres de conexión se trasladaron a su componente.
- Typecheck, ESLint y build correctos; **338 pruebas backend correctas**, con la advertencia conocida de Starlette sobre TestClient/httpx. Ruff, dependencias y Alembic correctos.
- Navegador real con frontend compilado, Uvicorn en 8005 y SQLite aislada `.tools/phase5-ui-20261015.sqlite3`: alta de `UI-005`, reserva confirmada, otra solapada rechazada, cancelación confirmada, incidencia bloqueante y nuevo rechazo por avería. La lectura posterior confirma una única reserva cancelada, con referencia `UI-FLOW-001` y fechas originales, y una incidencia abierta bloqueante.
- Revisados escritorio de 1440 px, móvil de 375 px, catálogo y demás listados/formulario de importación a 320 px, y tableta de 768 px. Se corrigió un desbordamiento de texto oculto de tabla: a 320 px el ancho de documento pasó de 437 a 305 px, y sólo la tabla conserva desplazamiento horizontal. Flecha derecha sobre la región desplazó su contenido 40 px. Controles observados con etiquetas; navegación móvil con objetivos de 59 px de alto. Enlace de salto, tabulación, foco de 3 px, confirmación y foco del error verificados. No se ejecutó una sesión de lector de pantalla ni un barrido exhaustivo a todos los niveles de zoom.
- La consola del recorrido no mostró errores ni advertencias. El proxy de desarrollo sigue respondiendo; la base habitual conserva sus cuatro equipos y cero reservas e incidencias.
- **Limitación de navegador:** el control de permisos rechazó la selección/subida del CSV ficticio en 8005. No se reintentó con otro mecanismo ni se eludió ese bloqueo. La presentación del informe y la retención del archivo se comprueban con Vitest; la importación real se cubre en la suite backend y en el recorrido HTTP de la fase 4.

Para completar manualmente esa comprobación de CSV, abre **Importaciones** en el entorno local, descarga el ejemplo, selecciónalo con el control nativo y pulsa **Importar pedidos**. Comprueba las tres aceptadas si los equipos están libres; repite para ver tres ya importadas y abre uno de sus detalles. Prueba además `backend/tests/fixtures/imports/mixed.csv` en una base aislada para ver aceptadas y rechazos juntos. No uses datos reales de clientes.

Las decisiones, el registro TDD y las limitaciones de Docker están en [PROYECTO.md](PROYECTO.md).
