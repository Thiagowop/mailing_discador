# Integracao 3C Plus - Manual Tecnico e Operacional

Este documento descreve toda a integracao com a API da 3C Plus: configuracao, fluxos, funcoes existentes, pontos de monitoramento e procedimentos de manutencao. A intencao e permitir que qualquer pessoa consiga operar, evoluir ou depurar o pipeline sem depender de conhecimento tacito.

## Objetivo do projeto

- Extrair mailings do banco **Candiotto_std**, higienizar os dados e gerar CSVs padronizados.
- Remover listas antigas no discador 3C Plus e publicar as novas listas de forma automatizada.
- Disponibilizar ferramentas para operadores tecnicos acompanharem Rodadas, consultas e logs.

## Arquitetura geral

| Camada | Arquivo / Script | Papel | Entrada / Saida |
| --- | --- | --- | --- |
| Autenticacao API | `src/threec/auth.py` | Obtem e renova tokens via `login`. | `.env` + API 3C Plus. |
| Cliente de mailing | `src/threec/mailing_client.py` | Lista campanhas, deleta listas, faz upload CSV, ajusta peso e registra logs. | CSVs higienizados / respostas API. |
| Extracao | `src/gerar_mailing_campanha.py` e `src/gerar_mailing_negociador.py` | Executam as consultas no SQL Server e gravam `data/campanhas/*.csv`. | Banco -> CSV. |
| Utilitarios | `src/utils/barra.py` | Barra de progresso e spinner para dar feedback visual nas extrações. | Events -> console. |
| Orquestrador CLI | `src/pipeline_cli.py` | Comandos para limpar, alimentar, validar e testar conexoes. Usado pelos `.bat`. | Operador -> API + logs. |
| Scripts Windows | `fluxo_completo.bat`, `pipeline_fluxo.bat` | Automacoes clicaveis para o time operacional. | CLI -> stdout/logs. |
| Mapeamento | `src/config_mailing.py` | Relaciona nomes de campanha x numero de mailing nos arquivos CSV. | Nome 3C+ -> prefixo `Mailing 000123 - ...`. |

## Fluxo ponta a ponta

```mermaid
flowchart TD
    A[Operador / Scheduler] --> B[pipeline_fluxo.bat ou fluxo_completo.bat]
    B --> C[Scripts de extracao (gerar_mailing_*.py)]
    C --> D[data/campanhas/*.csv + logs]
    D --> E[pipeline_cli atualizar-listas]
    E --> F[ThreeCAuthClient -> login/token]
    F --> G[ThreeCMailingClient: listar/deletar/upload/ajustar peso]
    G --> H[Campanhas atualizadas + logs/info em console]
    H --> I[Monitoramento em logs/3cplus.log e logs/error.log]
```

## Configuracao do ambiente

### Passos iniciais

1. `cp .env.template .env`.
2. Preencha as credenciais de banco (prefixo `DB_`) e as configuracoes da 3C Plus.
3. Defina o diretorio de logs se necessario (`LOG_DIR`, default `logs`) e garanta que existe.
4. Crie as pastas `data/campanhas` e `logs` se ainda nao existirem (os scripts assumem esse layout).

### Variaveis principais (.env)

| Variavel | Descricao | Obrigatoria | Exemplo |
| --- | --- | --- | --- |
| `THREECPLUS_BASE_URL` | URL do tenant sem `/api/v1`. | Sim | `https://acme.3c.plus` |
| `THREECPLUS_USERNAME` / `THREECPLUS_PASSWORD` | Credenciais do usuario operacional. | Sim | `operador@empresa` |
| `THREECPLUS_COMPANY_ID` / `THREECPLUS_COMPANY_DOMAIN` | Identificadores complementares exigidos por alguns tenants (quando a API valida multi-empresa). | Opcional | `123`, `empresa` |
| `THREECPLUS_API_TOKEN` | Token pronto para uso (substitui login). So use se o tenant permitir tokens long-lived. | Opcional | `eyJhbGciOi...` |
| `THREECPLUS_TARGET_CAMPAIGNS` | Lista (separada por virgula) das campanhas que o pipeline deve processar em cada execucao. | Sim | `RSF Judicial, Direcional Judicial` |
| `LOG_DIR` e `LOG_LEVEL` | Controlam onde e em qual nivel os logs sao gravados. | Opcional | `logs`, `INFO` |
| `PROGRESS_BAR` e `PROGRESS_BAR_PERCENT` | Habilitam barra textual nas geracoes (`1` para ativar). | Opcional | `1`, `1` |
| `DB_*` | Conexao SQL Server (driver, servidor, banco, usuario, senha, opcional `DB_TRUST_CERT=1`). | Sim | vide template |

> Valide o `.env` executando `python -m src.pipeline_cli mostrar-configuradas`. O comando carrega o arquivo e indica variaveis ausentes.

### Como adicionar ou remover campanhas

1. Confirme o nome exato da campanha no painel 3C Plus (respeite maiusculas/minusculas e espacos).
2. Abra `.env` e edite `THREECPLUS_TARGET_CAMPAIGNS`, mantendo os nomes separados por virgula. Somente essas campanhas participam da limpeza/upload.
3. Gere (ou copie) os CSVs correspondentes para `data/campanhas`. O nome esperado segue o padrao `Mailing 000074 - Nome - AAAA-MM-DD.csv`.
4. Se a campanha ainda nao estiver em `src/config_mailing.py`, inclua o par `"Nome": numero`. Isso acelera a localizacao do CSV correto.
5. Execute `pipeline_fluxo.bat 6` (listar campanhas) para verificar se o nome inserido aparece na API. Caso contrario, a etapa `atualizar-listas` vai registrar `Campanha nao encontrada`.

### Mapeamento de mailings (`src/config_mailing.py`)

O dicionario `MAILING_MAP` associa o nome da campanha ao numero do mailing presente no prefixo dos arquivos CSV. A classe `ThreeCMailingClient` utiliza esse mapa em `_encontrar_csv_campanha` e `_encontrar_csvs_campanha` para:

- Priorizar o arquivo cujo nome comeca com `Mailing {numero:06d} -`.
- Aceitar multiplos numeros (lista de inteiros) quando uma campanha compartilha varios mailings.
- Cair no modo antigo (busca por nome) se o numero nao for encontrado.

**Como atualizar o mapa:**

1. Abra `src/config_mailing.py`.
2. Adicione o par `"Nome exato da campanha": 74`.
3. Para campanhas com variantes (ex.: extrajudicial/judicial com mailings diferentes), use comentarios explicando. Se forem multiplos IDs, utilize uma lista: `"Campanha X": [74, 83]`.
4. Salve e, opcionalmente, rode `python testes\\testar_mapeamento.py` para validar a numeracao.

## Modulos e responsabilidades

### Autenticacao (`src/threec/auth.py`)

- `ThreeCAuthClient` carrega o `.env`, monta `base_url/api/v1` e inicializa uma `requests.Session`.
- `login` tenta autenticar ate `max_retries` (default 3), tratando `Timeout`, `RateLimitExceeded`, `ApiUnavailable` e `InvalidCredentials`.
- Mantem o token em memoria; se `THREECPLUS_API_TOKEN` estiver no `.env`, ja configura o header `Authorization`.
- Oferece helpers como `logout`, `refresh_token` (quando vastro), e normaliza excecoes (`Unauthorized`, `TokenExpired`, `InputInvalid`).
- Todos os erros relevantes sao enviados ao logger (nome `ThreeCAuthClient`), que por padrao escreve em `logs/3cplus.log`.

### Cliente de mailing (`src/threec/mailing_client.py`)

`ThreeCMailingClient` encapsula tudo que toca em listas/campanhas.

- **Endpoints dinamicos:** `DEFAULT_ENDPOINTS` guarda possiveis rotas (com e sem `/agent` ou `/api/v1`). `_resolve_endpoint` percorre ate encontrar um caminho que responda (`HTTP 2xx`). Isso evita edicoes ad-hoc quando o tenant muda.
- **Operacoes principais:**
  - `listar_campanhas(filtro, somente_ativas)` pagina automaticamente e remove duplicados.
  - `listar_listas_da_campanha(campaign_id)` retorna a representacao crua da API (a funcao chama diferentes chaves `data`, `lists`, `items`).
  - `deletar_lista_da_campanha(campaign_id, list_id)` remove listas antigas antes do upload.
  - `criar_mailing_por_csv_em_campanha(campaign_id, caminho_csv, filename, header, colmap)` realiza o fluxo oficial (upload CSV direto na campanha) e tenta sanitizar o arquivo para o cabecalho `identifier,areacodephone,ddd,phone`. Telefone e higienizado por `_split_ddd_phone`.
  - `atualizar_lista_por_csv`, `inativar_todas_listas_da_campanha` e `ajustar_peso_mailing` garantem que a lista nova fica ativa e com peso definido.
- **Utilitarios internos:** `_encontrar_csv_campanha`, `_encontrar_csvs_campanha` e `_normalizar_nome_campanha` conectam `MAILING_MAP` aos arquivos em `data/campanhas`.
- **Logs e resiliencia:** cada requisicao cria um `Idempotency-Key`, a sessao reusa cookies e toda resposta e validada por `_handle_response` (gera `UploadFailed`, `CreateMailingFailed` etc. quando necessario).

### Pipeline CLI (`src/pipeline_cli.py`)

Interface usada pelos scripts `.bat` e tambem acessivel direto via `python -m src.pipeline_cli <comando>`.

Principais comandos:

- `limpar-csv <pasta...>`: exclui arquivos `.csv` dos diretorios informados.
- `atualizar-listas --diretorio-csv data/campanhas`: para cada campanha configurada, remove as listas existentes e envia os CSVs atualizados. Gera um resumo (sucesso, falha de delecao, CSV ausente).
- `limpar-listas`: apenas apaga listas das campanhas configuradas.
- `listar-campanhas`: imprime as campanhas retornadas pela API (nome, id, status).
- `mostrar-configuradas`: compara as campanhas do `.env` com as existentes na API.
- `validar-listas [--campanha NOME | --todas]`: consulta as listas e conta registros.
- `atualizar-campanha --nome "Campanha" [--csv caminho]`: upload direcionado, ignorando `THREECPLUS_TARGET_CAMPAIGNS`.
- `testar-conexao`: faz um `select 1` via `pyodbc` com as credenciais do `.env`.

O helper `_criar_cliente_mailing` instancia `ThreeCAuthClient` + `ThreeCMailingClient` e reduz o log no console conforme `PIPELINE_LOG_LEVEL`.

### Geracao de arquivos (`src/gerar_mailing_campanha.py` e `src/gerar_mailing_negociador.py`)

- Executam stored procedures/consultas no SQL Server, com filtros de data e status definidos no codigo.
- Convertem o resultado em CSV com separador `;`, encoding `utf-8-sig` e colunas padronizadas (`COD`, `CPFCNPJ CLIENTE`, `NOME / RAZAO SOCIAL`, `TELEFONE_1...20`, `CAMPANHA`).
- Utilizam `utils.barra` para exibir progresso textual e respeitam `PROGRESS_BAR` / `PROGRESS_BAR_PERCENT`.
- Geram estatisticas ao final (tempo, numero de linhas por campanha).

### Utilitarios (`src/utils`)

- `barra.py`: implementa barra de progresso e spinner modular, permitindo habilitar/desabilitar via ambiente.

### Scripts em lote

- `fluxo_completo.bat`: sequencia automatica `limpar-csv -> gerar_mailing_campanha -> pipeline_cli atualizar-listas`. No final aguarda ~40s (`WAIT_SECONDS`) antes de fechar a janela.
- `pipeline_fluxo.bat`: menu numerico com nove opcoes (fluxo completo, extracoes isoladas, alimentar listas, limpar listas, listar campanhas, testar conexao, mostrar configuradas, sair). Tambem aceita um argumento (`pipeline_fluxo.bat 4`) para acionar direto uma opcao.

### Testes e validacoes auxiliares (`/testes`)

- `testar_mapeamento.py` e `mapear_campanhas_faltantes.py` ajudam a manter `MAILING_MAP` sincronizado com a 3C Plus.

## Dados e formatos

- **Consulta SQL:** gera um CSV por campanha com colunas fixas. Telefones ocupam 20 campos (vazios quando nao utilizados).
- **CSV sanitizado para upload:** `ThreeCMailingClient` converte para `identifier,areacodephone,ddd,phone`. O `identifier` recebe `COD` e o telefone e truncado para remover DDI, caracteres nao numericos e garantir DDD+numero.
- **Diretorios padrao:** `data/campanhas` (campanhas), `data/negociadores` (quando aplicavel), `logs` (saida do logger). Se outro caminho for desejado, passe via argumentos do CLI (`--diretorio-csv`).

## Logs e monitoramento

- `logs/3cplus.log`: informacoes operacionais (login, endpoints utilizados, quantidade de registros, status HTTP).
- `logs/error.log`: stack traces e erros que interrompem o fluxo.
- `run_output.log`: historico das ultimas execucoes (gerado pelos .bat).
- Console dos scripts `.bat`: mostra barras de progresso, IDs de campanha/lista, contagem de registros removidos/adicionados.
- Ajuste `LOG_LEVEL=DEBUG` ou `PIPELINE_LOG_LEVEL=INFO` para detalhar mais quando necessario.

## Troubleshooting rapido

| Sintoma | Causa provavel | Solucao |
| --- | --- | --- |
| `Variaveis ausentes no .env` | `.env` incompleto ou com nomes errados. | Reabra `pipeline_fluxo.bat 8` ou `mostrar-configuradas` para identificar e preencher. |
| `Campanha nao encontrada` no `atualizar-listas` | Nome nao existe ou grafia diferente da API. | Copie exatamente como aparece em `listar-campanhas`; atualize `.env` e, se preciso, `MAILING_MAP`. |
| `Arquivo CSV nao encontrado` | CSV nao gerado ou nome fora do padrao `Mailing XXXX -`. | Rode `gerar_mailing_campanha.py` novamente e verifique `data/campanhas`. |
| `Erro 401/403` | Credenciais invalidas ou token expirado. | Refaça login (apague `THREECPLUS_API_TOKEN` se estiver desatualizado) e confirme `THREECPLUS_BASE_URL`. |
| `Erro 422 header obrigatorio` | Cabecalho nao reconhecido / CSV vazio. | Abra o CSV e valide se possui `COD`, `CPFCNPJ`, `TELEFONE_1...`. Se faltar, revise a consulta SQL. |
| `Falha ao deletar lista` | API recusou a exclusao ou houve timeout. | Reexecute o comando ou tente `pipeline_cli validar-listas --campanha "Nome"` para conferir o estado atual. |
| `pyodbc nao encontrado` | Dependencia nao instalada no host. | Instale `pyodbc` (msiexec do ODBC Driver + `pip install pyodbc`) ou rode o comando em um ambiente que possua o driver. |

> Em qualquer falha, confira primeiro `logs/error.log`. A maioria das excecoes contem o `transaction_id` retornado pela 3C Plus, facilitando abrir um chamado com o suporte do discador.

## Procedimentos de manutencao

- **Adicionar nova campanha:** atualizar `.env` e `src/config_mailing.py`, gerar CSV e testar com `pipeline_cli atualizar-campanha --nome "Campanha"`.
- **Alterar formato dos CSVs:** adapte `src/gerar_mailing_campanha.py` e valide se `_csv_sanitizado_bytes` continua identificando as colunas obrigatorias (`COD`, `NOME`, `CPFCNPJ`, `TELEFONE_X`). Ajuste os indices se renomear campos.
- **Atualizar endpoints:** caso a 3C Plus altere rotas, adicione novos caminhos a `DEFAULT_ENDPOINTS` no `ThreeCMailingClient` (mantendo o fallback existente).
- **Revisar credenciais:** tokens e senhas devem ser atualizados sempre que o time de segurança solicitar. Aproveite `pipeline_cli listar-campanhas` para validar apos cada troca.
- **Limpeza de logs:** `logs/3cplus.log` pode crescer. Utilize `powershell Clear-Content logs\\3cplus.log` (ou rotacione) periodicamente.

## Checklist operacional

1. Conferir se as bases desejadas estao listadas em `THREECPLUS_TARGET_CAMPAIGNS`.
2. Executar `pipeline_fluxo.bat 2` (ou script especifico) para gerar CSVs atualizados.
3. Validar rapidamente o cabecalho dos arquivos (abrir 1 CSV e conferir colunas).
4. Rodar `pipeline_fluxo.bat 4` (alimentar listas) ou `fluxo_completo.bat` para o ciclo completo.
5. Ler o resumo exibido ao final (sucessos/falhas) e, em caso de erro, abrir `logs/error.log`.
6. (Opcional) `pipeline_cli validar-listas --campanha "Nome"` para confirmar o total de registros ativos.

Seguindo este manual, o time consegue configurar novas campanhas, operar o fluxo diario e executar troubleshootings basicos sem depender de alteracoes no codigo-fonte.
