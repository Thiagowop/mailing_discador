# Integração 3C Plus – Guia Técnico e Operacional

## Visão Geral

Este projeto executa o ciclo completo de atualização das campanhas do discador 3C Plus a partir de dados extraídos do banco **Candiotto_std**. O fluxo principal remove listas antigas das campanhas-alvo, gera novos mailings em CSV e realiza o upload via API.

### Fluxograma do Pipeline

```mermaid
flowchart TD
    A[fluxo_completo.bat / pipeline opção 1] --> B[Limpar CSVs locais]
    B --> C[Gerar mailings (src/gerar_mailing_campanha.py)]
    C --> D[Atualizar listas no 3C Plus]
    D --> E{Sucesso?}
    E -- Não --> F[Logs + retorno de erro]
    E -- Sim --> G[Relatório em console]
```

## Configuração do Ambiente

- Copie `.env.template` para `.env` e preencha as credenciais do banco, URL/Base da API e usuário/senha ou token.
- **Campanhas-alvo:** configure `THREECPLUS_TARGET_CAMPAIGNS` com uma lista separada por vírgulas. Exemplo:

  ```ini
  THREECPLUS_TARGET_CAMPAIGNS=RSF Judicial, Direcional Judicial
  ```

  > Sempre utilize o nome exatamente como aparece no 3C Plus. A atualização considerará apenas essas campanhas.

- Variáveis opcionais:
  - `PIPELINE_LOG_LEVEL` – nível de log exibido no console (default: `WARNING`). Utilize `INFO` para depuração.
  - `PROGRESS_BAR` e `PROGRESS_BAR_PERCENT` – controlam a exibição da barra de progresso (já habilitadas no fluxo).

## Módulos Principais

### `src/extracao_bases.py`
- Responsável por normalizar CSVs gerados pela extração com separador `;`.
- Remove cabeçalho inválido, higieniza telefones e usa `src.barra` para indicar progresso.

### `src/threec/auth.py`
- Cliente de autenticação. Carrega credenciais do `.env`, realiza login e mantém a sessão HTTP (`requests.Session`).
- Lida com retries básicos e exceções customizadas (`Unauthorized`, `InputInvalid`, etc.).

### `src/threec/mailing_client.py`
- Operações de alto nível sobre a API 3C Plus:
  - `listar_campanhas()` com paginação automática.
  - `listar_listas_da_campanha()`, `deletar_lista_da_campanha()`, `criar_mailing_por_csv_em_campanha()`.
  - `enviar_mailing_csv()` (fluxo legado de 2 passos, mantido para compatibilidade).
- Todos os logs ficam em `logs/3cplus.log` (INFO) e `logs/error.log` (ERROR).

### `src/gerar_mailing_campanha.py`
- Executa a consulta principal no SQL Server, aplica filtros (ex.: RO recente) e gera um CSV por campanha.
- Mostra spinner durante a consulta e barra percentual ao gravar os arquivos.
- Produz resumo dos arquivos gerados (quantidade e linhas).

### `src/pipeline_cli.py`
- Interface em Python acionada pelos `.bat`. Principais comandos:
  - `limpar-csv` – limpa diretórios de mailings.
  - `atualizar-listas` – remove listas antigas e envia CSVs novos (resumo final com sucessos/falhas).
  - `limpar-listas`, `listar-campanhas`, `mostrar-configuradas`, `testar-conexao`.
- Ajusta o nível de log do cliente para reduzir verbosidade no console.

### `fluxo_completo.bat`
- Executa `limpar-csv`, gera mailings e roda `atualizar-listas` em sequência.
- Mantém a janela aberta por 40 segundos (variável `WAIT_SECONDS`) para leitura do resultado.

### `pipeline_fluxo.bat`
- Menu interativo (ou modo direto via argumento) com as seguintes opções:
  1. Fluxo completo
  2. Somente extração por campanha
  3. Extração por negociador
  4. Alimentar listas (sem nova extração)
  5. Limpar listas
  6. Listar campanhas no 3C Plus
  7. Testar conexão com o banco
  8. Exibir campanhas configuradas e disponíveis
  9. Sair
- Sempre retorna ao menu após `pause`.

## Execução e Operação

### Via Script (Windows)

```bat
:: Fluxo completo (gera CSV + atualiza campanhas)
fluxo_completo.bat

:: Menu interativo
pipeline_fluxo.bat

:: Execução direta de uma opção (exemplo: alimentar listas)
pipeline_fluxo.bat 4
```

### Via n8n (planejado)

- A automação n8n ainda não foi implementada.
- Próximos passos sugeridos:
  1. Criar workflow que invoque `fluxo_completo.bat` via `Execute Command`.
  2. Capturar logs e status de saída para envio (e-mail/Slack).
  3. Parametrizar `THREECPLUS_TARGET_CAMPAIGNS` em variáveis do n8n ou secrets manager.

## Formato dos Dados

- **Entrada SQL**: consulta consolidada via `src/gerar_mailing_campanha.py` agrupa dados por campanha.
- **CSV gerado**:
  - Colunas fixas: `COD`, `CPFCNPJ CLIENTE`, `NOME / RAZAO SOCIAL`, `CAMPANHA`.
  - Telefones: `TELEFONE_1`…`TELEFONE_20`.
  - Separador `;`, encoding `utf-8-sig`.
- **Upload 3C Plus**:
  - Cabeçalho sanitizado para `identifier,name,document,areacodephone`.
  - Endpoints testados: `api/v1/campaigns/{id}/lists/csv`, `api/v1/agent/...`, `api/v1/campaigns/{id}/mailing`.

## Monitoramento e Logs

- `logs/3cplus.log`: tentativas de upload, status HTTP, transaction_id.
- `logs/error.log`: exceções não tratadas/erros de API.
- Consoles dos `.bat`: resumo final (listas removidas, campanhas atualizadas).
- Ajuste `PIPELINE_LOG_LEVEL=INFO` para diagnosticar problemas diretamente no console.

## Troubleshooting

| Sintoma | Possível causa | Como agir |
| --- | --- | --- |
| `ERRO: Python nao encontrado` | Python fora do PATH | Instalar/adicionar ao PATH |
| `Variaveis ausentes no .env` | `.env` incompleto | Conferir credenciais e campanhas |
| `Erro 401/403` | Credenciais inválidas ou sessão expirada | Revisar usuário/senha/token |
| `Erro 422 "header obrigatório"` | CSV com cabeçalho inesperado | Verificar se a consulta gerou colunas padrão; usar arquivo do dia |
| `Campanha nao encontrada` | Nome não bate com 3C Plus | Ajustar `THREECPLUS_TARGET_CAMPAIGNS` |
| `Falha ao deletar lista` | API não permite exclusão ou timeout | Conferir logs detalhados (`logs/error.log`), tentar novamente |

## Manutenção Futura

- Revisar periodicamente os endpoints na classe `ThreeCMailingClient` (a 3C Plus costuma introduzir variantes).
- Se o número de campanhas-alvo crescer, considere paginar a geração dos CSVs para reduzir o tempo de consulta SQL.
- Planejar a automação no n8n usando os scripts existentes (sem necessidade de refatorar).
- Adicionar testes automatizados para o `pipeline_cli` conforme novas regras de negócio.

---

**Contato rápido:** qualquer erro durante o fluxo completo é registrado no console (com retardo de 40s) e detalhado em `logs/error.log`. Utilize essas pistas antes de modificar o código.
