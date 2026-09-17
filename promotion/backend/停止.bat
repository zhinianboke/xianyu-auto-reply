@echo off
chcp 65001 >nul
call "%~dp0..\..\scripts\stop_service_by_port.bat" "返佣系统后端服务" "8092"
exit /b %errorlevel%
