@echo off
rem Fallback launcher (use if antivirus blocks NTA-Agent.exe).
cd /d "%~dp0app"
start "" "%~dp0runtime\python\pythonw.exe" -m nta_agent.app
