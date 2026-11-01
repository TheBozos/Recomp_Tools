@echo off
rem Status of the shared PS2Recomp bench lock: bench-status [--short|--json|--watch [s]|--procs-all|--no-procs]
setlocal
set PY=python
where /q python || set PY=py
"%PY%" -I "%~dp0bench_status.py" %*
endlocal
