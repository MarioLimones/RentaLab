# Convenciones de RentaLab

- Escribe en español los identificadores propios: módulos, archivos, componentes, clases, funciones, variables, propiedades internas, comentarios y descripciones de pruebas.
- Usa identificadores sin tildes: `camelCase` en TypeScript, `snake_case` en Python y `PascalCase` para clases, tipos y componentes. Los hooks de React mantienen el prefijo obligatorio `use`, seguido de un nombre en español.
- Conserva los nombres exigidos por lenguajes, bibliotecas y herramientas. Mantén compatibles las rutas HTTP, claves JSON, encabezados, opciones de navegador, variables de entorno, formatos guardados y nombres físicos de SQLite. Usa alias explícitos cuando difieran de los nombres internos.
- Conserva las revisiones históricas de Alembic: no reescribas migraciones ya existentes para traducir sus identificadores o textos.
- Una traducción o refactorización de nombres debe conservar la presentación, los textos visibles y el comportamiento. Actualiza importaciones, pruebas, comandos y enlaces de documentación al renombrar archivos.
- Consulta [la documentación del código en español](docs/CODIGO_EN_ESPANOL.md) y [el contrato del proyecto](docs/PROYECTO.md). Comprueba backend con pytest y Ruff, y frontend con análisis de tipos, ESLint, Vitest y compilación. Las pruebas deben usar datos temporales aislados.
