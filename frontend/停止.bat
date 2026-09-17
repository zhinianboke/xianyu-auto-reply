@echo off
chcp 65001 >nul
call "%~dp0..\scripts\stop_service_by_port.bat" "前端服务" "9000"
exit /b %errorlevel%
