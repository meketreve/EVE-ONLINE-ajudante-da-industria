@echo off
title EVE Industry Tool
setlocal EnableDelayedExpansion
cd /d "%~dp0eve_industry_tool"

echo ============================================
echo  EVE Industry Tool
echo ============================================
echo.

set "VENV_PY=.venv\Scripts\python.exe"
if exist "%VENV_PY%" goto :deps

:: -- 1. Localiza um Python 3.11+ -------------------------------------------
call :find_python
if defined PY goto :create_venv

echo [!] Python 3.11 ou superior nao encontrado.
echo.
echo     O Python e necessario para rodar o programa.
echo     Posso instala-lo agora automaticamente (requer internet).
echo.
set /p OPCAO="Instalar Python agora? [S/N]: "
if /i not "!OPCAO!"=="S" (
    echo.
    echo Baixe em https://www.python.org/downloads/ e marque "Add Python to PATH".
    start https://www.python.org/downloads/
    pause
    exit /b 1
)

winget --version >nul 2>&1
if errorlevel 1 (
    echo [!] Instalacao automatica indisponivel neste Windows.
    echo     Baixe em https://www.python.org/downloads/ e marque "Add Python to PATH".
    start https://www.python.org/downloads/
    pause
    exit /b 1
)

echo.
echo [..] Instalando Python 3.12...
winget install --id Python.Python.3.12 --source winget --accept-package-agreements --accept-source-agreements
call :find_python
if not defined PY (
    echo.
    echo [OK] Python instalado. Feche esta janela e abra o Iniciar.bat de novo.
    pause
    exit /b 0
)

:: -- 2. Cria ambiente isolado ----------------------------------------------
:create_venv
echo [..] Preparando ambiente do programa (so na primeira vez)...
%PY% -m venv .venv
if errorlevel 1 (
    echo [!] Falha ao criar o ambiente Python.
    pause
    exit /b 1
)

:: -- 3. Instala/atualiza dependencias quando requirements.txt muda ---------
:deps
fc /b requirements.txt .venv\requirements.installed >nul 2>&1
if not errorlevel 1 goto :run

echo [..] Instalando componentes (pode levar alguns minutos)...
"%VENV_PY%" -m pip install --upgrade pip --quiet --disable-pip-version-check
"%VENV_PY%" -m pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo [!] Falha ao instalar componentes. Verifique sua internet e tente de novo.
    pause
    exit /b 1
)
copy /y requirements.txt .venv\requirements.installed >nul
echo [OK] Componentes instalados.

:: -- 4. Inicia o app -------------------------------------------------------
:run
echo.
echo [OK] Abrindo o EVE Industry Tool...
echo      No primeiro uso os dados do jogo sao baixados automaticamente.
echo      Nao feche esta janela enquanto usa o programa.
echo ============================================
echo.
set PYTHONIOENCODING=utf-8
"%VENV_PY%" -m app.main
if errorlevel 1 pause
exit /b 0

:: -- Procura py launcher, python no PATH e instalacoes padrao -------------
:find_python
set "PY="
set "CHECK=-c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)""
py -3 !CHECK! >nul 2>&1 && (set "PY=py -3" & exit /b 0)
python !CHECK! >nul 2>&1 && (set "PY=python" & exit /b 0)
for %%V in (313 312 311) do (
    for %%D in ("%LOCALAPPDATA%\Programs\Python\Python%%V" "%ProgramFiles%\Python%%V") do (
        if exist "%%~D\python.exe" (
            set "PY="%%~D\python.exe""
            exit /b 0
        )
    )
)
exit /b 0
