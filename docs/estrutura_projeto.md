# 🏗️ Estrutura do Projeto - Mailing 3C+

## 📂 Organização de Pastas

```
3c/
├── data/                           # 📊 Dados de Saída
│   ├── campanhas/                 # CSVs gerados por campanha
│   │   └── .gitkeep              # Mantém estrutura no Git
│   └── negociadores/              # CSVs gerados por negociador
│       └── .gitkeep              # Mantém estrutura no Git
│
├── src/                           # 🐍 Código-fonte Python
│   ├── threec/                   # 🔌 Cliente API 3C+
│   │   ├── __init__.py
│   │   ├── auth.py              # Autenticação com retry e backoff
│   │   └── mailing_client.py    # Cliente de mailing (CRUD)
│   │
│   ├── utils/                    # 🛠️ Utilitários
│   │   ├── __init__.py
│   │   ├── barra.py            # Barra de progresso
│   │   └── extracao_bases.py   # Funções de extração SQL
│   │
│   ├── __init__.py
│   ├── gerar_mailing_campanha.py     # 📋 Gera CSVs por campanha
│   ├── gerar_mailing_negociador.py   # 👤 Gera CSVs por negociador
│   └── pipeline_cli.py               # ⚙️ CLI para automação
│
├── logs/                         # 📝 Logs de execução
├── docs/                         # 📚 Documentação
│   ├── estrutura_projeto.md     # Este arquivo
│   └── integracao_3cplus.md     # Documentação da API
│
├── .env                          # ⚙️ Configurações (NÃO versionar)
├── .env.template                 # 📋 Template de configurações
├── .gitignore                    # 🚫 Arquivos ignorados pelo Git
├── README.md                     # 📖 Documentação principal
├── fluxo_completo.bat           # 🔄 Fluxo completo automatizado
└── pipeline_fluxo.bat           # 📱 Menu interativo
```

## 🔄 Fluxo de Trabalho

### 1. Extração de Dados
```bash
# Por campanha
python src\gerar_mailing_campanha.py

# Por negociador
python src\gerar_mailing_negociador.py
```

### 2. Atualização no 3C+
```bash
# Atualizar listas das campanhas configuradas
python -m src.pipeline_cli atualizar-listas

# Apenas limpar listas existentes
python -m src.pipeline_cli limpar-listas
```

### 3. Comandos Auxiliares
```bash
# Listar campanhas disponíveis
python -m src.pipeline_cli listar-campanhas

# Ver campanhas configuradas
python -m src.pipeline_cli mostrar-configuradas

# Testar conexão com banco
python -m src.pipeline_cli testar-conexao

# Limpar CSVs antigos
python -m src.pipeline_cli limpar-csv data\campanhas data\negociadores
```

## 📋 Uso do Menu Interativo

Execute `pipeline_fluxo.bat` para acessar o menu:

```
=============================
 Pipeline de Fluxo (3C+)
=============================
1) Executar fluxo_completo (extracao + limpar + atualizar)
2) Extracao mailing campanha
3) Extracao mailing por negociador
4) Alimentar BD / Listas (limpar e atualizar listas 3C+)
5) Limpeza de listas (apenas deletar listas das campanhas alvo)
6) Lista de campanhas no 3C+
7) Testar conexao com banco
8) Campanhas configuradas (.env)
9) Sair
```

## 🔧 Configuração (.env)

Variáveis obrigatórias:

```bash
# Banco de Dados SQL Server
DB_DRIVER=ODBC Driver 17 for SQL Server
DB_SERVER=servidor.exemplo.com
DB_DATABASE=nome_database
DB_USER=usuario
DB_PASSWORD=senha
DB_TRUST_CERT=True

# API 3C+
THREECPLUS_BASE_URL=https://mcsa.3c.plus
THREECPLUS_USER=seu_usuario
THREECPLUS_PASSWORD=sua_senha

# Campanhas Alvo (separadas por vírgula)
THREECPLUS_TARGET_CAMPAIGNS=RSF Judicial,Direcional Judicial,LCM,Foco Aluguel

# Logs
LOG_DIR=logs
LOG_LEVEL=INFO

# Opcionais
PROGRESS_BAR_PERCENT=1
OUTPUT_RESUMO=1
```

## 📦 Módulos

### `src.threec.auth`
- `ThreeCAuthClient`: Autenticação com retry automático
- Gerencia token e renovação automática
- Backoff exponencial em caso de falha

### `src.threec.mailing_client`
- `ThreeCMailingClient`: CRUD de mailings
- Suporta múltiplas variações de endpoints
- Fail-fast com mensagens claras

### `src.utils.barra`
- Barra de progresso para console
- Spinner para operações longas
- Configurável via variáveis de ambiente

### `src.utils.extracao_bases`
- Funções para carregar dados do SQL Server
- Parsing de CSVs com separador ";"
- Tratamento de encoding UTF-8

### `src.pipeline_cli`
- Interface de linha de comando
- Automação de tarefas repetitivas
- Integração com scripts .bat

## 🎯 Convenções

### Arquivos CSV
- **Formato**: `Mailing {CampanhaID} - {NomeCampanha} - {Data}.csv`
- **Exemplo**: `Mailing 000032 - RSF Judicial - 2025-11-05.csv`
- **Separador**: `;` (ponto e vírgula)
- **Encoding**: `utf-8-sig` (BOM para Excel)

### Colunas Esperadas
- `COD`: Identificador único
- `CPFCNPJ CLIENTE`: Documento (CPF/CNPJ)
- `NOME / RAZAO SOCIAL`: Nome do cliente
- `CAMPANHA`: Nome da campanha
- `TELEFONE_1` até `TELEFONE_20`: Telefones

### Logs
- **Formato**: `{tipo}_{data}.log`
- **Tipos**: `processo`, `erros`
- **Rotação**: Diária

## 🚫 Arquivos Ignorados (.gitignore)

- ❌ `.env` (credenciais)
- ❌ `logs/` (logs de execução)
- ❌ `data/**/*.csv` (CSVs gerados)
- ❌ `__pycache__/` (cache Python)
- ✅ `.gitkeep` nas pastas `data/` (mantém estrutura)

## 🔐 Segurança

1. **Nunca versione** o arquivo `.env`
2. Use `.env.template` como referência
3. Senhas devem ter caracteres especiais escapados
4. Logs podem conter dados sensíveis

## 🧪 Testes

```bash
# Testar imports
python -c "from src.utils import iniciar_spinner; print('OK')"

# Testar conexão
python -m src.pipeline_cli testar-conexao

# Testar API 3C+
python -m src.pipeline_cli listar-campanhas
```

## 📊 Monitoramento

- Logs em `logs/processo_{data}.log`
- Erros em `logs/erros_{data}.log`
- Barra de progresso no console
- Resumo ao final de cada operação

## 🆘 Troubleshooting

### Erro: "Campanha não encontrada"
- Verifique `THREECPLUS_TARGET_CAMPAIGNS` no `.env`
- Execute: `python -m src.pipeline_cli mostrar-configuradas`

### Erro: "CSV não encontrado"
- Verifique se os CSVs estão em `data/campanhas/`
- Nome do CSV deve conter o nome da campanha

### Erro: "Falha ao deletar lista"
- Alguns tenants não suportam DELETE
- Lista será desativada com peso=0 (fallback)

### Erro de conexão SQL
- Verifique credenciais no `.env`
- Teste: `python -m src.pipeline_cli testar-conexao`
- Verifique firewall/VPN

---

**Última atualização**: 2025-11-05  
**Versão**: 2.0 (Estrutura reorganizada)
