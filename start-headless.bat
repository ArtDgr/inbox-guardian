@echo off
cd /d "%~dp0"
start /b py -m email_agent.server > data\server.log 2>&1
