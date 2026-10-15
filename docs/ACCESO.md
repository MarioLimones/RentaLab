# Usuarios, acceso y permisos — fases A–F

RentaLab pasa del operador único a usuarios persistidos con roles `customer` y `admin`. FastAPI y React siguen siendo una sola aplicación, con SQLite, SQLAlchemy y Alembic. La fase A entrega identidad y autorización; la fase B añade la [API pública](CATALOGO_PUBLICO.md). La fase C añade las [operaciones propias](OPERACIONES_CLIENTE.md) de reservas y avisos. La fase D conecta esas APIs con el [portal React](PORTAL_CLIENTE.md), separado del panel `/admin`, con cuenta de solo lectura. La fase E completa la [gestión y los recorridos conectados](ADMINISTRACION.md), con propietario/origen de reservas y separación de comunicación pública e interna.

## Preparación y transición

Desde `backend`, aplica las migraciones antes de crear cuentas. Se utiliza la base de `RENTALAB_DATABASE_URL` o la base local configurada en `.env`:

```powershell
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m rentalab.auth.manage_users create-admin --name "Administración local" --email "admin@example.test"
# Opcional: dos clientes ficticios; no se ejecuta al arrancar ni al migrar.
..\.venv\Scripts\python.exe -m rentalab.auth.manage_users demo-users
```

Las contraseñas se eligen mediante `getpass`, sin eco y con confirmación. No hay contraseña predeterminada ni contraseñas como argumentos. Para ejecución no interactiva puede indicarse `--password-env RENTALAB_ADMIN_PASSWORD` o `--password-env RENTALAB_DEMO_PASSWORD`: el argumento es el **nombre** de una variable previamente aprovisionada, no su valor. Retírala después. No la imprimas, no la guardes en el repositorio ni la incluyas en una orden con un literal sensible. Las cuentas ficticias son `alicia.demo@example.test` y `bruno.demo@example.test`. Las cuentas existentes se conservan: el comando no las promueve ni les cambia la contraseña.

La CLI de cuentas crea usuarios, no equipos ni reservas, y no inicia sesiones. `rentalab.seed` conserva su función de cargar únicamente equipos ficticios. Para la demostración completa existe el comando separado y explícito `python -m rentalab.demo`: un administrador, cinco clientes con contraseñas locales distintas, unidades y reservas relativas a una fecha base. [RESERVAS_MULTIUSUARIO.md](RESERVAS_MULTIUSUARIO.md) contiene sus credenciales públicas de prueba, repetibilidad y recorrido. Se prohíbe ejecutarlo en `production`. El registro HTTP nunca crea administradores.

| Configuración | Contrato vigente |
| --- | --- |
| `RENTALAB_SESSION_SECRET` | Obligatorio; secreto aleatorio de al menos 32 caracteres, exclusivo del backend |
| `RENTALAB_SESSION_TTL_SECONDS` | Caducidad absoluta; 3600 por defecto, de 1 a 86400 segundos |
| `RENTALAB_ENVIRONMENT` | `development`/`test` para HTTP local; `production` requiere HTTPS y cookie Secure |
| `RENTALAB_OPERATOR_USERNAME` y `RENTALAB_OPERATOR_PASSWORD_HASH` | Pareja opcional para conservar el administrador anterior; ambos configurados o ambos ausentes |

La configuración existente no se reescribe. El operador anterior sigue entrando con usuario y hash Argon2id de entorno; sus sesiones anteriores conservan acceso mientras sigan vigentes y no cambien las credenciales. Se representa como `role: "admin", user: null`, una excepción transitoria explícita. Para pasar a cuentas persistidas crea el administrador con la CLI, comprueba su acceso y retira después ambos valores del operador cuando decidas terminar la transición. No se convierten usuarios al iniciar FastAPI. `rentalab.auth.hash_password` sigue disponible para esa compatibilidad. Si el nombre del operador es un correo, esa dirección queda reservada y el registro/CLI devuelve conflicto; no cambies después esa configuración a una dirección que ya pertenezca a una cuenta persistida, porque el acceso anterior tiene prioridad.

Para usuarios persistidos el correo, nombre, rol y estado activo se consultan en SQLite en cada petición autenticada. Desactivar o cambiar el rol surte efecto en la siguiente petición. Cambiar el hash invalida sus sesiones. Rotar el secreto invalida todas las cookies. Una petición ya autorizada y en curso no se cancela retroactivamente.

## Contrato HTTP de identidad

Todas las rutas usan `/api` y JSON. Los errores tienen `detail`; las respuestas de autenticación y validación no incluyen contraseña, hash ni cuerpo sensible. La validación devuelve 422, la unicidad de correo 409, las credenciales incorrectas 401 y el CSRF inválido 403.

| Método y ruta | Entrada y resultado |
| --- | --- |
| `GET /api/auth/csrf` | Público; devuelve `{csrf_token}` y prepara el contexto anónimo si hace falta |
| `POST /api/auth/register` | CSRF; `{name,email,password}` → 201 con usuario público; no inicia sesión |
| `POST /api/auth/login` | CSRF; `{username,password}`; `username` es el correo o el usuario del operador anterior; devuelve sesión 200 |
| `GET /api/auth/session` | Sesión 200 o 401 si está ausente, caducada, revocada o inactiva |
| `POST /api/auth/logout` | Sesión y CSRF; revoca, borra la cookie y devuelve `{authenticated:false}` |

Registro acepta **exactamente** `name`, `email` y `password`: nombre recortado de 1–120 caracteres sin NUL; correo válido de hasta 254 caracteres, normalizado y sin distinción de mayúsculas; contraseña de 8–1024 caracteres, sin recortar espacios. El servidor asigna `role="customer"` y `active=true`. Enviar `role`, `active`, `id`, `password_hash` o cualquier campo desconocido produce 422, incluso si se envía `role="customer"`. La restricción única SQLite resuelve también carreras entre registros. No se consulta DNS ni se envían mensajes de verificación.

Respuesta del registro:

```json
{"id":1,"name":"Cliente ficticio","email":"cliente@example.test","role":"customer","active":true}
```

Respuesta de sesión persistida:

```json
{
  "authenticated": true,
  "username": "cliente@example.test",
  "expires_at": "2026-11-10T12:00:00Z",
  "role": "customer",
  "user": {"id":1,"name":"Cliente ficticio","email":"cliente@example.test","role":"customer","active":true}
}
```

`username` se conserva para consumidores anteriores. `expires_at` es UTC, independiente de las fechas de alquiler. React valida la respuesta; los permisos del servidor siempre proceden de la identidad comprobada.

## Matriz de permisos

Contrato ampliado del producto: visitante consulta catálogo/características/disponibilidad; cliente añade sus propias reservas, perfil y problemas vinculados a sus reservas; administrador gestiona equipos, todas las reservas, incidencias, importaciones y su panel.

La matriz recoge las APIs habilitadas y las pantallas conectadas hasta la fase E. Una URL visual bajo `/admin` no sustituye las dependencias de autorización del backend:

| Recurso u operación | Visitante | Cliente | Administrador |
| --- | --- | --- | --- |
| Salud, CSRF, registro y acceso | Sí; escrituras con CSRF | Sí | Sí |
| `GET /api/public/equipment[?q=…&category=…]`, `GET /api/public/equipment/{id}` | Sólo activos, esquema público | Igual | Igual |
| `GET /api/public/equipment/{id}/availability` | Sin fechas solicita selección; con fechas sólo disponibilidad | Igual | Igual |
| `GET /api/public/images/equipment-placeholder.svg` | Sí, recurso local | Sí | Sí |
| Lecturas antiguas `/api/equipment`, detalle y disponibilidad | 401 | 403 | Sí, información de gestión |
| Sesión / cierre | 401 | Propia | Propia |
| Crear, reemplazar o editar equipos, incluidos `public_description`, `technical_specs`, `image_url` y `active` | 401 | 403 | Sí; CSRF al escribir |
| `GET /api/reservations` y filtros de cliente, ID de cuenta, equipo, fechas, estado y origen | 401 | 403 | Todas, también sin dueño; incluye `customer_user_id` y `origin` |
| Crear o cancelar reservas por las rutas de gestión | 401 | 403 | Sí; CSRF, origen asignado por el servidor |
| `GET /api/reservations/{id}` (gestión) | 401 | 403 | Todas, también sin dueño; identidad, propietario y origen |
| `/api/me/reservations`, detalle y cancelación | 401 | Propias; 404 ajenas, CSRF al escribir | 403; utiliza gestión |
| `POST /api/incidents`, `PATCH /api/incidents/{id}` de prioridad/bloqueo/notas/respuesta pública y `PATCH /api/incidents/{id}/status` | 401 | 403 | Sí; CSRF; resolución y notas sólo internas |
| `GET /api/incidents` con filtros y `GET /api/incidents/{id}` (gestión) | 401 | 403 | Todas, también históricas |
| `/api/me/incidents` y avisos desde `/api/me/reservations/{id}/incidents` | 401 | Autor y reserva propios; 404 ajenas, CSRF al escribir | 403; utiliza gestión |
| Importar CSV / descargar ejemplo | 401 | 403 | Sí |
| `/api/docs`, `/api/redoc`, OpenAPI y redirección OAuth | 401 | 403 | Sí |
| Panel React `/admin` y enlaces administrativos antiguos | Acceso requerido; sin datos privados | Acceso restringido, sin navegación administrativa | Panel completo, con enlace al catálogo |
| Pantallas del portal visual | Catálogo y ficha pública; acceso/registro | Lo anterior, reservas/avisos propios y cuenta de solo lectura | Catálogo público y gestión en `/admin` |

La fase C habilita altas, consulta y cancelación propias y avisos vinculados mediante esquemas de cliente. [OPERACIONES_CLIENTE.md](OPERACIONES_CLIENTE.md) detalla plazos Madrid y comunicación pública. El servidor asigna propietario/autor, nunca el cuerpo HTTP; no se ofrece reasignación de históricos. La sesión incluye datos básicos de perfil; no hay edición de perfil ni cambio de contraseña por HTTP.

`customer_user_id` y `origin` son metadatos de respuesta de gestión; no se añaden a los DTO públicos o propios. No pueden indicarse al crear una reserva desde cliente o administración. Registrar un correo coincidente no vincula reservas antiguas ni CSV, y filtrar por correo no asigna ownership. La respuesta de un aviso propio incluye estado y `public_response`; nunca `internal_notes`, `resolution`, prioridad, bloqueo o identificadores de reservas ajenas. Dar una respuesta pública a una incidencia interna no la vincula a un cliente.

`get_current_user`, `require_customer` y `require_admin`, en `auth/dependencies.py`, centralizan identidad y rol. Las rutas de gestión llevan dependencias de administrador; mover una ruta o esconder el botón no elimina esa comprobación. El middleware deniega por defecto el resto de la API y rechaza sesión/rol antes de leer cuerpos privados o multipart. Sin sesión: 401; rol insuficiente: 403; recurso privado ajeno o histórico sin dueño: el mismo 404 que uno inexistente. Los campos administrativos y ownership no forman parte de los esquemas de alta de negocio.

## Persistencia y migración conservadora

`0006_users_ownership` sigue a `0005_auth_sessions`, sin editar migraciones anteriores. Añade `users` con hash Argon2id, rol restringido y correo único; `auth_sessions.user_id`; `reservations.customer_user_id`; e `incidents.author_user_id`, con claves foráneas e índices. Las relaciones nuevas admiten `NULL`: no se deduce ownership por nombre o correo. Reservas antiguas y CSV siguen sin propietario conocido, aunque después alguien registre el mismo correo.

Crear una reserva desde la gestión conserva propietario desconocido. Crear una incidencia con administrador persistido guarda autor desde la sesión; el operador de transición no tiene ID persistido y deja autor nulo. HTTP no permite falsificar autoría. Las relaciones restringen borrar el usuario referenciado; no se añade borrado de usuarios.

La migración no carga cuentas ni reinicializa datos. Las pruebas aplican `0005`, insertan datos y sesiones anteriores, migran a `head` y comparan campos, relaciones, integridad y restricciones sobre bases temporales.

La fase E añade `0009_reservation_origin` después de `0008_customer_incidents`: ALTER TABLE conserva las relaciones y añade origen restringido a `portal`, `admin`, `csv` y `legacy`. Todos los registros anteriores reciben `legacy`, manteniendo su propietario exacto, conocido o nulo. No se infiere CSV por tener referencia externa ni se cambia el origen al reimportar una reserva idéntica. Las altas posteriores asignan origen desde el servicio; [ADMINISTRACION.md](ADMINISTRACION.md) detalla filtros y migración.

## Cookie, CSRF y React

Se conserva `SessionMiddleware`: cookie firmada `rentalab_session`, HttpOnly, SameSite=Lax, ruta `/`, Secure en producción. Sólo contiene sid aleatorio y contexto CSRF; la firma no cifra. La sesión SQLite impone caducidad absoluta y revocación además de la firma. El cierre invalida también copias anteriores de la cookie. Reiniciar conserva sesiones válidas si base/configuración permanecen iguales.

Toda escritura, incluidos registro, acceso y cierre, exige `X-CSRF-Token` de `/api/auth/csrf` con la misma cookie. Acceder rota sid y CSRF; token anterior, cruzado, ausente o incorrecto → 403. Una operación privada sin sesión devuelve primero 401. Las respuestas API llevan `Cache-Control: no-store`; bloqueo SQLite agotado → 409 y `Retry-After: 1`.

React usa `credentials: 'same-origin'`, mantiene CSRF en memoria y no reintenta escrituras automáticamente. Se conservan defensas ante respuestas atrasadas, errores recuperables y retirada de pantallas privadas tras 401. Sólo admin monta las páginas de gestión; el cliente utiliza `/api/me` para sus reservas y avisos. Registro tiene etiquetas visibles, autocompletado y errores con foco; después se accede con la cuenta creada. El destino de retorno usa una lista de rutas internas permitidas, conserva equipo/fechas y nunca confirma una reserva automáticamente. No hay secretos `VITE_`, contraseñas en el bundle ni credenciales en localStorage/sessionStorage.

## Verificación y límites

La [validación integrada de F](VALIDACION_INTEGRADA.md) verifica esta matriz por HTTP con dos clientes y un administrador, incluidas rutas administrativas anteriores, IDs ajenos, CSRF y campos falsificados. Los permisos siguen procediendo del usuario vigente en SQLite; el reinicio conserva sesiones válidas si base y secreto permanecen iguales.

Un cliente HTTP debe conservar cookies, obtener CSRF, enviar registro/acceso con su cabecera y renovar CSRF después del acceso. Navegador y PowerShell no comparten sesiones. El catálogo/disponibilidad bajo `/api/public` no exige cookie; las URLs antiguas de gestión requieren administrador. No compartas cabeceras ni introduzcas contraseñas como literales en comandos o capturas.

Flujo manual: registrar, rechazar correo repetido, acceder, refrescar, comprobar identidad sin panel administrativo y cerrar. Como administrador anterior o persistido, se conservan equipos/reservas/incidencias/importaciones. Las pruebas cubren también llamadas sin React, caducidad, desactivación, cambios de rol, ownership y migración. Resultados ejecutados en [PROYECTO.md](PROYECTO.md).

No se implementan recuperación de contraseña, verificación de correo, limitación de intentos ni edición de perfil. El recorrido visual disponible se describe en [PORTAL_CLIENTE.md](PORTAL_CLIENTE.md). Se conservan las limitaciones de [DESPLIEGUE.md](DESPLIEGUE.md); ninguna prueba local implica publicación externa.

## API desde PowerShell

Este auxiliar conserva los ejemplos administrativos de reservas, incidencias e importaciones. Usa la misma terminal y sólo URLs del entorno RentaLab. Lee la contraseña sin eco; no imprime cookies ni tokens. El navegador tiene su propia sesión.

```powershell
$apiBase = 'http://127.0.0.1:8000'
$csrf = Invoke-RestMethod "$apiBase/api/auth/csrf" -SessionVariable apiSession
$apiUser = Read-Host 'Correo o usuario anterior'
$apiPassword = Read-Host 'Contraseña' -AsSecureString
$apiCredential = [System.Management.Automation.PSCredential]::new($apiUser, $apiPassword)
$loginBody = @{
  username = $apiUser
  password = $apiCredential.GetNetworkCredential().Password
} | ConvertTo-Json -Compress
try {
  Invoke-RestMethod "$apiBase/api/auth/login" -Method Post `
    -WebSession $apiSession -Headers @{'X-CSRF-Token'=$csrf.csrf_token} `
    -ContentType 'application/json; charset=utf-8' `
    -Body ([System.Text.Encoding]::UTF8.GetBytes($loginBody))
} finally {
  Remove-Variable apiPassword, apiCredential, loginBody -ErrorAction SilentlyContinue
}
$apiHeaders = @{
  'X-CSRF-Token' = (Invoke-RestMethod "$apiBase/api/auth/csrf" -WebSession $apiSession).csrf_token
}
function Invoke-RentaLab {
  param(
    [Parameter(Mandatory=$true)][string]$Uri,
    [string]$Method = 'GET',
    [object]$Body,
    [string]$ContentType = 'application/json'
  )
  $requestParameters = @{
    Uri=$Uri; Method=$Method; WebSession=$apiSession; Headers=$apiHeaders
  }
  if ($PSBoundParameters.ContainsKey('Body')) {
    if ($Body -is [string] -and $ContentType -like 'application/json*') {
      $requestParameters.Body = [System.Text.Encoding]::UTF8.GetBytes($Body)
      $requestParameters.ContentType = 'application/json; charset=utf-8'
    } else {
      $requestParameters.Body = $Body
      $requestParameters.ContentType = $ContentType
    }
  }
  Invoke-RestMethod @requestParameters
}
Invoke-RentaLab "$apiBase/api/equipment"
# Ejecutar sólo al terminar los demás ejemplos:
# Invoke-RentaLab "$apiBase/api/auth/logout" -Method Post
# Remove-Variable apiHeaders, apiSession
```
