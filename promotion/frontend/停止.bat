@echo off
chcp 65001 >nul
call "%~dp0..\..\scripts\stop_service_by_port.bat" "返佣系统前端服务" "9001"
exit /b %errorlevel%
