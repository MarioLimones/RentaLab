# Código en español

El código propio de RentaLab utiliza nombres en español para módulos, componentes, clases, funciones, variables, propiedades internas, comentarios y descripciones de pruebas. Los nombres técnicos se escriben sin tildes para facilitar su uso desde herramientas y terminales; los textos en español conservan su ortografía.

## Convenciones

- TypeScript: `camelCase` para variables y funciones, `PascalCase` para tipos y componentes, y mayúsculas con guiones bajos para constantes.
- Python: `snake_case` para funciones y variables, `PascalCase` para clases, y mayúsculas con guiones bajos para constantes.
- Los archivos y directorios propios describen su responsabilidad en español. Los nombres definidos por las herramientas, como `package.json`, `vite.config.ts` o `__init__.py`, mantienen su formato reconocido.
- Las pruebas conservan sus aserciones y escenarios; sus títulos describen en español el comportamiento comprobado.

## Compatibilidad

Las palabras reservadas y las API de TypeScript, Python y las dependencias conservan los nombres que exigen sus herramientas. También se mantienen los contratos de integración existentes: rutas HTTP, campos JSON, encabezados, valores persistidos, identificadores de almacenamiento, variables de entorno y nombres históricos del esquema de base de datos. Cuando un nombre interno cambia, sus alias y referencias conservan esos contratos. Los parámetros HTTP validan exclusivamente los alias públicos originales: el nombre interno español no se acepta como campo adicional de una petición. Los constructores de Python y la lectura de objetos ORM sí utilizan los nombres internos españoles.

El cambio de idioma conserva los textos mostrados, la estructura de las pantallas y el contenido de las hojas de estilo. Los selectores CSS y los atributos estándar HTML y ARIA siguen coincidiendo con sus usos.

## Evidencia de conservación

La referencia anterior al cambio es el commit `d4c6435c0fd4536f847a2c97f865a3af11efa4e9`.

Se creó una copia aislada del frontend de esa referencia y se ejecutaron correctamente el análisis de tipos, ESLint, las 531 pruebas de sus 28 archivos y la compilación de producción. El frontend traducido también supera el análisis de tipos, ESLint, sus 531 pruebas y la compilación de producción sin modificar los escenarios comprobados.

La auditoría sintáctica comprueba las 82 fuentes TypeScript: conserva estructura, operadores, literales, relaciones entre referencias y destinos de importación. También verifica el contenido de los once archivos estáticos comparados. Solo normaliza los cambios documentados de nombres, alias, rutas de archivos y títulos diagnósticos de Vitest. Los demás textos en ejecución siguen comparándose íntegramente. Los finales de línea CRLF y LF se consideran equivalentes.

Hay tres anotaciones de tipos nuevas para mantener enlazadas propiedades inferidas después del cambio de nombres: el retorno `FilaEspecificacionTecnica` en el formulario de equipos, `EstadoAutenticacion` en una prueba de producto y las propiedades de `ReservasCatalogo` en su prueba. La auditoría registra expresamente estas anotaciones y el import de tipo asociado; no generan instrucciones en ejecución. Los 369 títulos diagnósticos comprobados están en español.

Además, una comparación con Microsoft Edge verifica doce estados de la interfaz: catálogo en 1440, 844, 390 y 320 píxeles; consulta de fechas reservadas; selector de fechas; búsqueda sin resultados; ficha de producto en escritorio y móvil; acceso en escritorio y móvil; y registro. Las doce capturas PNG son idénticas píxel a píxel; también coinciden HTML, texto, títulos y controles. No se detectan errores de ejecución ni desbordamientos horizontales. Se utilizan las mismas respuestas HTTP y una fecha fija: el 15 de octubre de 2026 a las 12:00 UTC. Las respuestas se interceptan en el navegador, sin escribir datos ni usar la base de datos local.

La comparación visual final se repitió el 16 de octubre de 2026 sobre las fuentes traducidas completas y volvió a obtener coincidencia en los doce estados.

### Comprobación final del servidor

Se recopilaron los 1112 casos de pytest y se ejecutó la suite completa en tres procesos con bases temporales independientes. Después de corregir las referencias de las propias pruebas a nombres anteriores, se repitieron los cinco módulos afectados: 159 casos en cuatro módulos y 29 en el de usuarios, todos correctos. La cobertura consolidada deja **1111 pruebas correctas y una omitida** porque comprueba permisos POSIX en Windows. La aplicación no cambió entre la ejecución completa y estas repeticiones.

Ruff y su comprobación de formato pasan en los 111 archivos Python. El frontend supera sus **531 pruebas**, el análisis de tipos, ESLint y la compilación final. `git diff --check` y la revisión de enlaces locales y comandos de pruebas documentados también pasan. Los registros de pytest se conservan en `.tools/idioma/pytest_backend_grupo_*.log`, `.tools/idioma/pytest_backend_usuarios_final.log` y `.tools/idioma/pytest_backend_modulos_corregidos.log`.

En el backend se comparan las claves JSON de 41 esquemas con sus campos originales y se comprueba que los literales de las once migraciones se conservan. Once pruebas específicas con HTTP real sobre bases temporales verifican que registro, acceso, edición, reservas y filtros rechazan nombres internos adicionales, aceptan los campos públicos y conservan las respuestas. También comprueban que los constructores internos y la lectura ORM funcionan con nombres españoles.

## Repetir las comprobaciones locales

Las herramientas temporales de verificación se guardan en `output/`; esta carpeta no forma parte del código distribuido.

```powershell
# Auditoría de fuentes frente a la copia aislada de la referencia.
node output/auditar-idioma.cjs

# Comparación de las dos capturas con las mismas respuestas HTTP.
python output/comparar-pantallas-idioma.py

# Comprueba que los títulos de las pruebas ya están traducidos.
node .tools/idioma/descripciones_pruebas.cjs
```

Los informes detallados son `output/auditoria-idioma.json`, `output/comparacion-pantallas-idioma.json` y `output/baseline-idioma.json`. La comparación del navegador cubre los estados enumerados; las pruebas automatizadas comprueban adicionalmente los flujos administrativos, de sesión, reservas e incidencias.
