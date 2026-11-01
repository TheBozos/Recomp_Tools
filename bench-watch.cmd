@echo off
rem The bench lock, refreshed every 5 s until you close the window (double-click me).
setlocal
set PY=python
where /q python || set PY=py
"%PY%" -I "%~dp0bench_status.py" --watch 5 %*
endlocal
