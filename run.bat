@echo off
set "CONDA_PYTHON=C:\ProgramData\anaconda3\python.exe"
set "PATH=C:\ProgramData\anaconda3;C:\ProgramData\anaconda3\Library\bin;%PATH%"
"%CONDA_PYTHON%" main.py %*
