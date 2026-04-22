@echo off
:: Start Prometheus Monitoring Stack
title Prometheus Monitoring Stack

echo ========================================
echo   Starting Prometheus Stack
echo ========================================

:: Set paths - UPDATE THESE TO MATCH YOUR INSTALLATION
set PROMETHEUS_PATH=<PROMETHEUS_PATH>
set EXPORTER_PATH=<EXPORTER_PATH>
set ALERTMANAGER_PATH=<ALERTMANAGER_PATH>

:: Kill existing processes
echo Stopping any existing processes...
taskkill /f /im prometheus.exe 2>nul
taskkill /f /im windows_exporter.exe 2>nul
taskkill /f /im alertmanager.exe 2>nul

timeout /t 2 /nobreak >nul

:: Start Windows Exporter
echo [1/3] Starting Windows Exporter on port 9182...
start "Windows Exporter" /min cmd /c "cd /d %EXPORTER_PATH% && windows_exporter-0.31.6-amd64.exe"
timeout /t 3 /nobreak >nul

:: Start Prometheus
echo [2/3] Starting Prometheus on port 9090...
start "Prometheus" /min cmd /c "cd /d %PROMETHEUS_PATH% && prometheus.exe --config.file=prometheus.yml"
timeout /t 5 /nobreak >nul

:: Start Alertmanager
echo [3/3] Starting Alertmanager on port 9093...
start "Alertmanager" /min cmd /c "cd /d %ALERTMANAGER_PATH% && alertmanager.exe --config.file=alertmanager.yml"
timeout /t 3 /nobreak >nul

echo.
echo ========================================
echo   All services started!
echo ========================================
echo.
echo Services running on:
echo   - Windows Exporter: http://localhost:9182
echo   - Prometheus:       http://localhost:9090
echo   - Alertmanager:     http://localhost:9093
echo.
echo Press any key to close this window (services will keep running)...
pause >nul