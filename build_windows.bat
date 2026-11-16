@echo off
setlocal

cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON=py -3"
) else (
    where python >nul 2>nul
    if %errorlevel% neq 0 (
        echo.
        echo ERRO: Python nao esta instalado neste computador.
        echo Este script precisa de Python para criar o executavel.
        echo.
        pause
        exit /b 1
    )
    set "PYTHON=python"
)

call %PYTHON% -m venv .build-venv
if errorlevel 1 goto :failed
call .build-venv\Scripts\activate.bat
if errorlevel 1 goto :failed
python -m pip install --upgrade pip
if errorlevel 1 goto :failed
python -m pip install pyinstaller==6.11.1
if errorlevel 1 goto :failed
python -m PyInstaller --noconfirm --clean --onefile --windowed --name Atualizador app.py
if errorlevel 1 goto :failed

echo.
echo Executavel criado em:
echo %CD%\dist\Atualizador.exe
pause
exit /b 0

:failed
echo.
echo ERRO: a compilacao falhou. O executavel nao foi criado.
pause
exit /b 1
