@echo off
setlocal

rem El arranque local siempre conserva la base de esta copia del proyecto.
set "raizRentaLab=%~dp0"
set "baseDatosRentaLab=%raizRentaLab%data\rentalab.db"
set "pythonRentaLab=%raizRentaLab%.venv\Scripts\python.exe"
set "interfazRentaLab=%raizRentaLab%frontend\dist"

if not exist "%baseDatosRentaLab%" (
    echo Falta data\rentalab.db. Restaura la base existente antes de iniciar. 1>&2
    echo No se creara una base vacia. 1>&2
    exit /b 1
)
if not exist "%pythonRentaLab%" (
    echo Falta el entorno Python .venv. Consulta la instalacion en README.md. 1>&2
    exit /b 1
)
if not exist "%raizRentaLab%frontend\package.json" (
    echo Faltan las fuentes del frontend. Revisa la carpeta frontend. 1>&2
    exit /b 1
)
where npm.cmd >nul 2>&1
if errorlevel 1 (
    echo Falta Node.js con npm. Consulta la instalacion en README.md. 1>&2
    exit /b 1
)

rem Estas variables solo afectan a este proceso y sus hijos; no modifican Docker ni .env.
set "rutaBaseRentaLab=%baseDatosRentaLab:\=/%"
set "RENTALAB_DATABASE_URL=sqlite:///%rutaBaseRentaLab%"
set "RENTALAB_FRONTEND_DIST=%interfazRentaLab%"

rem Compila las fuentes guardadas, incluida la animacion del navbar, antes de servirlas.
pushd "%raizRentaLab%frontend"
if errorlevel 1 exit /b 1
echo Preparando la interfaz guardada de RentaLab...
call npm.cmd run build
if errorlevel 1 (
    popd
    echo No se pudo compilar la interfaz; RentaLab no se ha iniciado. 1>&2
    exit /b 1
)
popd

pushd "%raizRentaLab%backend"
if errorlevel 1 exit /b 1

echo Base de datos local: %baseDatosRentaLab%
"%pythonRentaLab%" -c "from rentalab.arranque import preparar_arranque; from rentalab.configuracion import Configuracion; preparar_arranque(Configuracion())"
if errorlevel 1 (
    popd
    exit /b 1
)

echo RentaLab: http://127.0.0.1:8000/catalogo
"%pythonRentaLab%" -m uvicorn rentalab.principal:aplicacion --host 127.0.0.1 --port 8000 --workers 1
set "resultadoArranque=%errorlevel%"
popd
exit /b %resultadoArranque%
