@echo off
REM Run inbox guardian daemon in background
cd /d "%~dp0"
python -m email_agent.main --daemon
