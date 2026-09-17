@echo off
chcp 65001 >nul
call "%~dp0..\scripts\stop_service_by_port.bat" "WebSocket服务" "8090"
exit /b %errorlevel%
