@echo off
cd /d %~dp0

tasklist | find /i "python.exe" >nul
if not errorlevel 1 (
  wmic process where "CommandLine like %%nst_gui.py%%" get CommandLine | find /i "nst_gui.py" >nul
  if not errorlevel 1 (
    echo NST Ultimate sudah berjalan.
    pause
    exit
  )
)

python nst_gui.py
