@echo off
rem La petite fenetre de veille sur le bench lock (double-clic sur ce fichier).
setlocal
set PY=pythonw
where /q pythonw || set PY=python
start "bench lock" "%PY%" -I "%~dp0bench_gui.pyw" %*
endlocal
