@echo off
setlocal enableextensions enabledelayedexpansion
cd /d %~dp0
set "PYTHONPATH=%~dp0"

rem Execucao direta por argumento (ex.: pipeline_fluxo.bat 2)
if not "%~1"=="" (
  set "opt=%~1"
  goto despachar
)

rem Menu de pipeline de fluxo
:menu
cls
echo =============================
echo  Pipeline de Fluxo (3C+)
echo =============================
echo ATENCAO: Opcoes 1 2 e 3 APAGAM CSVs antes de extrair
echo 1) Executar fluxo_completo (extracao + limpar + atualizar)
echo 2) Extracao mailing campanha
echo 3) Extracao mailing por negociador
echo 4) Alimentar BD / Listas (limpar e atualizar listas 3C+)
echo 5) Limpeza de listas (apenas deletar listas das campanhas alvo)
echo 6) Lista de campanhas no 3C+
echo 7) Testar conexao com banco
echo 8) Campanhas configuradas (.env)
echo 9) Validar listas (registros no 3C+)
echo 10) Sair
echo.
set "opt="
set /p opt=Escolha uma opcao [1-10]:
if "%opt%"=="" goto menu

:despachar
if "%opt%"=="1" goto fluxo
if "%opt%"=="2" goto campanha
if "%opt%"=="3" goto negociador
if "%opt%"=="4" goto alimentar
if "%opt%"=="5" goto limpar
if "%opt%"=="6" goto listar
if "%opt%"=="7" goto testar
if "%opt%"=="8" goto configuradas
if "%opt%"=="9" goto validar
if "%opt%"=="10" goto sair
echo Opcao invalida: %opt%
goto aguardar_e_menu
goto menu

:fluxo
call "%~dp0\fluxo_completo.bat"
goto aguardar_e_menu

:campanha
rem Limpa CSVs anteriores (campanhas) antes da extracao
python -m src.pipeline_cli limpar-csv --prefix Extracao data\campanhas
if errorlevel 1 (
  echo ERRO: Falha ao limpar CSVs de campanha.
  goto aguardar_e_menu
)
python src\\gerar_mailing_campanha.py
if errorlevel 1 (
  echo ERRO: Extracao por campanha falhou.
)
goto aguardar_e_menu

:negociador
rem Limpa CSVs anteriores (negociadores) antes da extracao
python -m src.pipeline_cli limpar-csv --prefix Extracao data\negociadores
if errorlevel 1 (
  echo ERRO: Falha ao limpar CSVs de negociador.
  goto aguardar_e_menu
)
python src\\gerar_mailing_negociador.py
if errorlevel 1 (
  echo ERRO: Extracao por negociador falhou.
)
goto aguardar_e_menu

:alimentar
python -m src.pipeline_cli atualizar-listas
if errorlevel 1 (
  echo ERRO: Atualizacao das listas falhou.
)
goto aguardar_e_menu

:limpar
python -m src.pipeline_cli limpar-listas
goto aguardar_e_menu

:listar
python -m src.pipeline_cli listar-campanhas
goto aguardar_e_menu

:testar
python -m src.pipeline_cli testar-conexao
if errorlevel 1 (
  echo ERRO: Conexao com banco falhou.
)
goto aguardar_e_menu

:configuradas
python -m src.pipeline_cli mostrar-configuradas
goto aguardar_e_menu

:validar
python -m src.pipeline_cli validar-listas
goto aguardar_e_menu

:sair
echo Encerrando.
exit /b 0

:aguardar_e_menu
echo.
pause
goto menu
