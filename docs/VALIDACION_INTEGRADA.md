# Validación integrada de RentaLab — fase F

Revisión del 15/10/2026 sobre la ampliación A–E. Se conserva una aplicación React, un backend FastAPI y SQLite. Esta fase añade cobertura de comportamiento y actualiza la documentación; la revisión no reprodujo un fallo de producción que exigiera cambiar servicios, contratos, dependencias o migraciones. No se publicaron servicios externos.

## Comprobaciones ejecutadas

Desde `backend/`:

```powershell
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m ruff check .
..\.venv\Scripts\python.exe -m ruff format --check .
..\.venv\Scripts\python.exe -m pip check
```

Desde `frontend/`:

```powershell
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test
npm.cmd run build
```

| Comprobación | Resultado de esta fase |
| --- | --- |
| pytest completo | **856 correctas**, 1 omitida y 1 advertencia; ejecución final de 222,54 s |
| Ruff check y format | Correctos en todo el backend, **88 archivos** formateados |
| Dependencias Python | `pip check` correcto |
| TypeScript estricto | Correcto |
| ESLint | Correcto, sin advertencias |
| Vitest / React Testing Library | **331 pruebas correctas, 20 archivos**, 18,82 s |
| Build Vite | Correcto, 64 módulos; JS 391,88 kB / 112,45 kB gzip; CSS 30,79 kB / 7,08 kB gzip |
| Compose | `docker compose config --quiet` correcto, con secreto temporal y sin imprimir configuración |

Se conserva la omisión de permisos POSIX en Windows (`test_backup.py:99`) y la advertencia conocida de Starlette/TestClient sobre `httpx`. No se cambian dependencias para ocultar esa advertencia. Las nuevas pruebas se añadieron ya verdes; no se atribuye una fase roja que no se ejecutó.

## Cobertura de los ocho recorridos

Las pruebas HTTP usan SQLite migrada y temporal, sesiones independientes y CSRF. La tabla identifica ejemplos de cobertura, no sólo pruebas del renderizado de botones.

| Recorrido | Evidencia automatizada |
| --- | --- |
| Visitante: ficha, características y fechas | [test_public_catalogue.py](../backend/tests/test_public_catalogue.py), [test_public_catalogue_security.py](../backend/tests/test_public_catalogue_security.py) y `test_visitor_registers_signs_in_and_explicitly_confirms_a_public_equipment` en [test_integrated_roles.py](../backend/tests/test_integrated_roles.py): DTO público, SVG local, selección de fechas y ausencia de texto interno |
| Registro, acceso y reserva propia | El mismo recorrido integrado comprueba correo normalizado, rol `customer`, cero reservas antes de confirmar, identidad asignada en servidor y detalle propio; [test_users.py](../backend/tests/test_users.py) cubre unicidad, expiración/desactivación y sesión |
| Otro cliente conoce el identificador | [test_me_security.py](../backend/tests/test_me_security.py): GET, cancelación y aviso ajenos → 404, identidad administrativa falsificada → 422, sesión ausente → 401, rol insuficiente y CSRF → 403 |
| Administración recibe reserva y aviso | `test_customer_and_administrator_share_cancellation_communication_and_availability` en [test_admin_connected.py](../backend/tests/test_admin_connected.py): propietario, origen portal, aviso no bloqueante, gestión y respuesta pública sin notas/resolución internas |
| Varios bloqueos y equipo activo | El recorrido conectado y [test_incidents.py](../backend/tests/test_incidents.py) comprueban que resolver uno de varios no libera y que resolver no activa equipos |
| Cancelación según rol | `test_cancellation_frees_only_its_interval_under_each_roles_policy`: cliente antes/en inicio, admin en/después del rango, historial, adyacencia e idempotencia; [test_me_reservations.py](../backend/tests/test_me_reservations.py) verifica Europe/Madrid con reloj controlable |
| Confirmaciones incompatibles | [test_me_reservation_concurrency.py](../backend/tests/test_me_reservation_concurrency.py) y [test_cross_role_concurrency.py](../backend/tests/test_cross_role_concurrency.py): conexiones SQLite distintas, cliente contra cliente/admin/CSV; una sola confirmación persistida, incluidos ambos órdenes de adquisición del bloqueo |
| CSV y registros sin dueño | [test_imports.py](../backend/tests/test_imports.py) conserva formato, límites e idempotencia; `test_csv_keeps_its_owner_unknown_even_when_a_matching_email_registers` comprueba lectura/cancelación/aviso denegados y ausencia en listas propias tras registrar el correo coincidente |

La fase añade **23 casos**: nueve de recorridos/cancelación/concurrencia y catorce de entrega SPA/reinicio/errores. Además refuerza las aserciones del CSV y del arranque vacío existentes. Las pruebas frontend existentes conservan fechas tras acceso, conflictos y listas propias. [ACCESO.md](ACCESO.md#matriz-de-permisos) sigue siendo la matriz contractual; no basta con ocultar navegación en React.

## Navegador real y mismo origen

Microsoft Edge mediante Playwright, tres contextos independientes: administrador, cliente registrado desde la interfaz y Bruno Demo creado explícitamente por CLI. FastAPI sirvió `frontend/dist` y API desde una única URL de loopback, con SQLite exclusiva del ensayo. No se utilizaron mocks de red para estos recorridos.

- Visitante abrió catálogo, ficha y características con imagen alternativa local. Eligió 10–12/12/2030, pasó por acceso → registro → acceso y volvió al mismo equipo/rango. La confirmación expresa creó la reserva #1 y enfocó su referencia.
- El segundo cliente había consultado el mismo intervalo libre. Su confirmación posterior recibió 409, conservó fechas y enfocó el conflicto, exigiendo nueva consulta. No se creó otra reserva.
- En la sesión del segundo cliente se enviaron peticiones HTTP directas de lectura, cancelación y aviso sobre #1 y consulta del aviso ajeno: 404. Listado global, ejemplo CSV y modificaciones de equipo/bloqueo: 403. Campos de propietario/origen falsificados: 422. Escritura sin CSRF: 403. Sus listas propias permanecieron vacías; la ruta ajena mostró «La reserva no existe».
- Administración vio la cuenta propietaria y origen portal. El aviso empezó abierto y no bloqueante. Se guardaron bloqueo con confirmación, nota interna centinela y respuesta pública. Se creó otra incidencia interna bloqueante, se resolvió la primera y una consulta pública sobre **otro intervalo libre**, 20–22/12/2030, siguió indicando no disponible; confirmar devolvió 409 sin motivo interno.
- El cliente recibió la respuesta pública en Mis incidencias sin los textos internos. Las consultas y recargas consultan estados persistidos; no se afirma comunicación en tiempo real.

- Resolver también la segunda incidencia devolvió disponibilidad para 20–22/12/2030. Administración canceló #1 con confirmación por Enter; al recargar, el cliente vio Cancelada, conservó sus fechas y el intervalo 10–12 volvió a estar disponible.
- Revisión visual en móvil **375×812**, catálogo en horizontal **844×390** y comprobación de escritorio. Catálogo, aviso/respuesta y panel sin desbordamiento horizontal del documento; los cinco controles del catálogo tenían etiqueta asociada, y Tab mostró foco de 3 px. Se inspeccionaron las capturas reales, no sólo las dimensiones del DOM. No equivale a auditoría completa de accesibilidad.

Las respuestas 401/403/404/409/422 deliberadas aparecen en la consola como errores de red; no se observaron excepciones propias de la aplicación ni advertencias React.

## Migraciones, base vacía y persistencia

- Se ejecutaron las pruebas de migración desde el esquema de operador (`0005`), catálogo público (`0007`) y versión anterior `0008_customer_incidents` a `0009_reservation_origin`. Conservan reservas, incidencias, relaciones, propiedad conocida y valores previos; los registros sin dueño siguen sin él. La nueva columna marca los registros existentes como `legacy`, sin adivinar origen ni dueño por correo.
- `test_startup_applies_real_migrations_without_loading_demo_data` comprueba cinco tablas vacías antes de cualquier aprovisionamiento. El ensayo real confirmó también **cero equipos, usuarios, reservas, incidencias y sesiones** tras `prepare_startup`, antes de ejecutar explícitamente `create-admin`, `demo-users` y `seed`.
- `test_restart_preserves_accounts_sessions_ownership_and_customer_reports` recrea aplicación y motor, conserva filas y cookies, permite acceder de nuevo con hashes persistidos y mantiene la separación pública/interna del aviso.
- Además se detuvo y volvió a lanzar el **proceso Uvicorn real**, con la misma base y secreto. Una comparación de todas las filas de seis tablas antes/después fue idéntica: 4 equipos, 4 usuarios, 1 reserva, 2 incidencias y 3 sesiones, más la versión Alembic. Integridad y claves foráneas correctas. Los tres navegadores conservaron su sesión al recargar; el cliente propietario volvió a ver su reserva y Bruno mantuvo la suya vacía.
- Sobre el servidor reiniciado, GET directos `/catalogo`, `/mis-reservas` y `/admin` devolvieron HTML compilado 200; recurso estático y equipo público inexistentes, JSON 404; API desconocida sin sesión, JSON 401. [test_spa.py](../backend/tests/test_spa.py) comprueba también HEAD, errores 422 y métodos 405 con `Allow` conservado.

El ensayo no sustituye el reinicio de contenedor ni los permisos de un volumen Linux. La comparación SHA-256 final confirmó `.env` y `data/rentalab.db` habituales intactos. Se cerraron las tres sesiones y ventanas y se detuvo el servidor temporal: quedan cero sesiones de ensayo, la reserva cancelada con su propietario y dos incidencias resueltas, con integridad/FK correctas. Se retiraron contraseña y secreto del archivo temporal de configuración; las capturas y evidencias quedan ignoradas bajo `.tools/phaseF`. El escaneo de 199 archivos candidatos y compilados no encontró los secretos conocidos. No se crearon commits ni se publicaron servicios.

## Cuentas, demostración y límites

Los comandos completos de instalación y cuentas están en [README](../README.md#desarrollo-en-windows-con-powershell), [ACCESO.md](ACCESO.md#preparación-y-transición) y [DESPLIEGUE.md](DESPLIEGUE.md). Admin y clientes ficticios se crean sólo mediante comandos explícitos; las contraseñas se eligen con `getpass` o una variable ya aprovisionada. No hay secretos ni contraseñas predeterminadas en el repositorio. Arrancar/migrar no reinicializa ni carga cuentas.

Dockerfile multietapa y Compose conservan React compilado, API del mismo origen, un worker, usuario sin privilegios y volumen `/data`. La revisión no encontró un cambio necesario en esos archivos. **La imagen y el volumen Docker no están verificados**: el intento actual pasó de pipe ausente a HTTP 500 del motor Linux y timeout de 20 segundos. Docker Desktop quedó detenido, sin crear imagen, contenedores o volúmenes. Compose parseado no equivale a contenedor probado.

La selección/subida CSV automatizada por navegador permanece pendiente por el rechazo de un permiso guardado registrado previamente; no se reintentó ni eludió. Su contrato multipart, persistencia, límites, permisos e informe sí se prueban por pytest y RTL. No se ha probado proxy HTTPS real, lector de pantalla, dispositivo físico ni capacidad bajo carga. No hay publicación externa ni vídeo grabado: [DEMO_LEANMIND.md](DEMO_LEANMIND.md) es un guion de **8:30** con uso de IA descrito fielmente.
