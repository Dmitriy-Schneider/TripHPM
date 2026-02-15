@echo off
chcp 65001 >nul
title Trip Report System Server (Production)

echo ========================================
echo    Trip Report System - Продакшен
echo ========================================
echo.

cd /d "%~dp0backend"

:: Проверяем наличие виртуального окружения
if exist "..\venv\Scripts\activate.bat" (
    echo [OK] Активация виртуального окружения...
    call "..\venv\Scripts\activate.bat"
) else (
    echo [!] Виртуальное окружение не найдено
)

echo.
echo [*] Запуск сервера на http://127.0.0.1:8080
echo [*] Режим: Продакшен (без auto-reload)
echo [*] Для остановки нажмите Ctrl+C
echo.
echo ========================================
echo.

python -m app.main --port 8080 --no-reload

pause
