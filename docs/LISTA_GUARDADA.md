# Lista guardada y reserva de varios productos

Cada cliente dispone de una lista persistente en su cuenta. «Guardar en mi lista» permite añadir modelos desde el catálogo o su ficha; «Mi lista» reúne los guardados para preparar un alquiler conjunto. Acceder o registrar otra cuenta no comparte los favoritos de la anterior. Guardar un producto no lo reserva ni bloquea sus unidades.

## Recorrido

1. Accede como cliente y guarda los productos que necesitas.
2. Abre `/mi-lista`. Selecciona los productos que quieras alquilar juntos; puedes conservar los demás para otro proyecto.
3. Elige recogida y devolución. El calendario común permite comparar fechas y cada producto muestra su disponibilidad para el periodo. También puedes desplegar su calendario individual.
4. Si todos los seleccionados están disponibles, confirma su reserva conjunta. El servidor vuelve a comprobarlos dentro de una única transacción.
5. La confirmación ofrece las referencias de las reservas creadas y acceso a «Mis reservas». La lista de favoritos se conserva.

Se mantienen las fechas de calendario y la regla `[inicio, fin)`: la recogida está incluida y el día de devolución no se alquila. El inicio no puede ser anterior a hoy en Madrid. Un día aparentemente libre en varios calendarios no garantiza que cada modelo tenga una misma unidad libre durante todo el intervalo; la consulta de disponibilidad del periodo y la confirmación verifican esa continuidad.

Si alguien ocupa uno de los productos antes de confirmar, la operación devuelve conflicto y **no guarda ninguna de las reservas de ese envío**. La interfaz conserva la selección y actualiza la disponibilidad. No reintenta automáticamente la escritura.

## API

Todas estas rutas requieren cliente autenticado. Las escrituras requieren el token CSRF de la sesión. La identidad del propietario procede del servidor.

| Método y ruta | Entrada y resultado |
| --- | --- |
| `GET /api/me/saved-products` | Devuelve `{ "equipment_ids": [1, 2] }`, exclusivamente de la cuenta actual |
| `PUT /api/me/saved-products/{equipment_id}` | Añade el modelo de forma idempotente y devuelve la lista actualizada |
| `DELETE /api/me/saved-products/{equipment_id}` | Retira el modelo de forma idempotente y devuelve la lista actualizada |
| `POST /api/me/reservations/batch` | Recibe `equipment_ids`, `start_date` y `end_date`; devuelve `201` con un array de reservas propias |

El envío conjunto admite entre 1 y 50 identificadores distintos. Repetir un identificador es un error de validación; enviar dos unidades del mismo modelo se rechaza. Cada producto obtiene una unidad física disponible durante todo el periodo mediante la misma lógica del alquiler individual. La disponibilidad, las incidencias y las reservas administrativas siguen compartiendo las mismas reglas y el mismo bloqueo de escritura SQLite.

La respuesta mantiene el orden de los productos solicitados. Cada reserva conserva su referencia propia, su propietario, estado y origen `portal`, y se puede consultar y cancelar individualmente con las reglas anteriores. No se añade pago, cantidad por modelo ni cancelación colectiva.

## Persistencia

La migración `0010_saved_products` añade la tabla `saved_products`, con propietario y equipo como clave compuesta. No modifica las reservas anteriores. La lista identifica modelos aunque existan varias unidades físicas; si cambia la unidad representativa, la API resuelve una unidad activa del mismo modelo. Un modelo retirado del catálogo sigue siendo eliminable de la lista.

En una instalación existente, crea una copia coherente de SQLite y aplica `alembic upgrade head` antes de reiniciar el backend. El arranque de desarrollo no ejecuta migraciones automáticamente.

## Verificación ejecutada el 15 de octubre de 2026

- Backend completo: `python -m pytest -q`, **1.000 pruebas correctas**, una omisión por permisos POSIX en Windows y la advertencia existente de Starlette/TestClient. Ruff y comprobación de formato correctos.
- Frontend completo: `npm test -- --maxWorkers=2`, **449 pruebas correctas**; TypeScript, ESLint y compilación Vite correctos. Dos trabajadores evitaron un timeout de una prueba anterior bajo carga paralela. Después del ajuste final del mensaje de confirmación se ejecutaron las 17 pruebas dirigidas de la lista, TypeScript, ESLint y build de nuevo, con resultado correcto; el navegador comprobó los tres mensajes «Reservado del… al…».
- Navegador Edge, React compilado y FastAPI reales, sobre una copia aislada de la demostración: alta y acceso de cliente de prueba, lista vacía, guardado desde catálogo y ficha, persistencia al recargar, selección por teclado, calendario individual, selección conjunta del 17 al 20 de octubre y confirmación de tres productos mediante un solo envío.
- Conflicto real desde otra pestaña: una reserva individual ocupó el panel después de consultar la lista. La confirmación de los tres devolvió `409`; la lista conservó productos y fechas, actualizó la disponibilidad y la base confirmó que no había ninguna reserva parcial. Tras cancelar la reserva individual de prueba, la confirmación conjunta creó las tres reservas con origen `portal`.
- Vista de 375, 390, 844 y 1.440 píxeles sin desbordamiento horizontal, selección de 44 × 44 píxeles, movimiento reducido y texto ampliado comprobados.

Las dos bases locales existentes se migraron con copia coherente previa y comprobaciones de integridad. Se conservaron sus usuarios, equipos, reservas, incidencias y sesiones. Los usuarios y alquileres del recorrido de navegador pertenecen exclusivamente a la copia de prueba; no se insertaron en la demostración en uso. Las capturas están en `output/playwright/saved-list-final-*.png`, `saved-list-conflict.png` y `saved-list-confirmed-final.png`.
