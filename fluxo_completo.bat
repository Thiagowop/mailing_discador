@echo off
setlocal enableextensions enabledelayedexpansion
cd /d %~dp0
rem Garante que a raiz do projeto esteja no import path do Python
set "PYTHONPATH=%~dp0"
set "WAIT_SECONDS=40"

echo [Fluxo] Iniciando fluxo completo (extracao + limpeza + atualizacao)

rem Validar Python
where python >nul 2>&1
if errorlevel 1 (
  echo ERRO: Python nao encontrado no PATH.
  set "EXIT_CODE=1"
  goto :wait_and_exit
)

rem 0) Remover CSVs anteriores (campanhas e negociadores) antes da extracao
python -m src.pipeline_cli limpar-csv --prefix Fluxo data\campanhas data\negociadores
if errorlevel 1 (
  echo ERRO: Falha ao limpar CSVs anteriores.
  set "EXIT_CODE=1"
  goto :wait_and_exit
)

rem 1) Extrair mailing por campanha (gera CSVs em data\campanhas)
python src\\gerar_mailing_campanha.py
if errorlevel 1 (
  echo ERRO: Extracao de mailing por campanha falhou.
  set "EXIT_CODE=1"
  goto :wait_and_exit
)

rem 2) Limpar e atualizar listas nas campanhas alvo (3C+)
python -m src.pipeline_cli atualizar-listas
if errorlevel 1 (
  echo ERRO: Atualizacao das listas falhou.
  set "EXIT_CODE=1"
  goto :wait_and_exit
)

echo [Fluxo] Concluido com sucesso.
set "EXIT_CODE=0"
goto :wait_and_exit

:wait_and_exit
echo.
echo A janela sera fechada em %WAIT_SECONDS% segundos...
timeout /t %WAIT_SECONDS% >nul
exit /b %EXIT_CODE%
