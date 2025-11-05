import pandas as pd
import pyodbc
import re
from datetime import datetime
import os
import warnings
import logging
from pandas.errors import PerformanceWarning
from dotenv import load_dotenv
import time
import sys
from pathlib import Path

# Adiciona o diretório raiz ao path para permitir imports
if __name__ == "__main__":
    root_dir = Path(__file__).parent.parent
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))

from src.utils import iniciar_spinner, parar_spinner, atualizar_barra

# Carregar variáveis de ambiente
load_dotenv()
os.environ.setdefault("PROGRESS_BAR_PERCENT", "1")

# Configuração de logs (processo e erros)
LOG_DIR = os.getenv("LOG_DIR", "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_LEVEL = str(os.getenv("LOG_LEVEL", "INFO")).upper()
logger = logging.getLogger("mailing_campanha")
if not logger.handlers:
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    # Log de processo por script
    fh = logging.FileHandler(os.path.join(LOG_DIR, "mailing_campanha.log"), encoding="utf-8")
    fh.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    fh.setFormatter(fmt)
    # Log comum de erros
    eh = logging.FileHandler(os.path.join(LOG_DIR, "error.log"), encoding="utf-8")
    eh.setLevel(logging.ERROR)
    eh.setFormatter(fmt)
    # Console
    ch = logging.StreamHandler()
    ch.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(eh)
    LOG_CONSOLE = str(os.getenv("LOG_CONSOLE", "0")).lower() in ("1", "true", "yes")
    if LOG_CONSOLE:
        logger.addHandler(ch)

# Suprimir warnings não essenciais
warnings.simplefilter("ignore", PerformanceWarning)
# Suprimir aviso de uso de DBAPI2 sem SQLAlchemy
warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    message=r".*pandas only supports SQLAlchemy.*"
)

def _require_env(nome):
    val = os.getenv(nome)
    if val is None or str(val).strip() == "":
        raise ValueError(f"Variável de ambiente ausente: {nome}. Ação: defina {nome} no .env")
    return val

# Conectar ao banco de dados (suporte opcional a porta e certificado)
_server = _require_env('DB_SERVER')
_port = os.getenv('DB_PORT')
if _port:
    _server = f"{_server},{_port}"

_database = _require_env('DB_DATABASE')
_user = _require_env('DB_USER')
_password = _require_env('DB_PASSWORD')

_driver_raw = _require_env('DB_DRIVER')
_driver = re.sub(r"^[{]+|[}]+$", "", _driver_raw.strip())
if not _driver:
    raise ValueError("DB_DRIVER inválido: valor vazio. Ação: defina um driver válido, ex.: 'ODBC Driver 18 for SQL Server'")

_trust = os.getenv('DB_TRUST_CERT')
_tls_segment = "Encrypt=yes;TrustServerCertificate=yes;" if str(_trust).lower() in ("1", "true", "yes") else ""

# Fail-fast específico para Driver 18 (exige criptografia/trust quando não há CA confiável)
if re.search(r"(?i)\b18\b", _driver) and not _tls_segment:
    raise ValueError(
        "Conexão inválida (driver=18, certificado não confiável). Ação: defina DB_TRUST_CERT=1 no .env ou instale a CA raiz confiável (https://go.microsoft.com/fwlink/?linkid=2226722)"
    )

def _connect_with_retries(max_tentativas: int = 3, espera_segundos: int = 2):
    """Tenta conectar ao SQL Server com tentativas e espera entre falhas.

    Erros são registrados com causa e ação. Falhas críticas após N tentativas geram exceção.
    """
    tentativa = 0
    ultima_excecao = None
    while tentativa < max_tentativas:
        tentativa += 1
        try:
            logger.info("Tentativa de conexão #%s", tentativa)
            return pyodbc.connect(
                f"DRIVER={{{_driver}}};"
                f"SERVER={_server};"
                f"DATABASE={_database};"
                f"UID={_user};"
                f"PWD={_password};"
                f"{_tls_segment}"
            )
        except Exception as e:
            ultima_excecao = e
            msg = str(e)
            if "SSL" in msg or "criptografia" in msg or "certificate" in msg.lower():
                logger.error("Conexão falhou (SSL/Certificado): %s | Ação: habilite DB_TRUST_CERT=1 ou instale CA raiz.", e)
            elif "server" in msg.lower() or "SQLServer" in msg or "SQLDriverConnect" in msg:
                logger.error("Conexão falhou (rede/servidor): %s | Ação: valide DB_SERVER/porta e alcance de rede.", e)
            else:
                logger.error("Conexão falhou: %s", e)
            if tentativa < max_tentativas:
                time.sleep(espera_segundos)
    raise RuntimeError(f"Falha crítica: impossível conectar após {max_tentativas} tentativas. Causa: {ultima_excecao}")

def _run_sql_with_reconnect(conn, sql: str, descricao: str, max_tentativas: int = 2):
    """Executa consulta com tentativa de reconexão em falha de conexão."""
    tentativa = 0
    ultima_excecao = None
    while tentativa < max_tentativas:
        tentativa += 1
        try:
            logger.info("Executando %s (tentativa #%s)", descricao, tentativa)
            return pd.read_sql_query(sql, conn)
        except Exception as e:
            ultima_excecao = e
            logger.error("Falha ao executar %s: %s", descricao, e)
            # Reconectar e tentar novamente
            try:
                conn.close()
            except Exception:
                pass
            conn = _connect_with_retries()
    raise RuntimeError(f"Falha crítica: {descricao} não executada após {max_tentativas} tentativas. Causa: {ultima_excecao}")

print(f"Conectando ao banco: servidor={_server} db={_database}")
logger.info("Conectando ao banco: servidor=%s db=%s", _server, _database)
conn = _connect_with_retries()
print("Conexão estabelecida.")
logger.info("Conexão estabelecida.")

# Função para determinar o número máximo de telefones (principais ou não)
def get_max_telefones(cursor, is_principal=True):
    query = f"""
        SELECT MAX(TelefonePosicao) AS MaxTelefonePosicao
        FROM (
            SELECT 
                PesPessoasID AS PessoaID,
                ROW_NUMBER() OVER (PARTITION BY PesPessoasID ORDER BY PesTelefone) AS TelefonePosicao
            FROM PessoasContatos
            WHERE 
                ISNULL(PesTelefoneInativo, 0) <> 1
                AND ISNULL(PesTelefonePrincipal, 0) = {1 if is_principal else 0}
                AND PesTelefone <> ''
        ) AS Temp;
    """
    cursor.execute(query)
    result = cursor.fetchone()
    return result.MaxTelefonePosicao if result else 0

# Criar cursor e calcular limites
cursor = conn.cursor()
max_principais = get_max_telefones(cursor, is_principal=True)
max_nao_principais = get_max_telefones(cursor, is_principal=False)
logger.info("Telefones principais=%s nao_principais=%s", max_principais, max_nao_principais)

# Colunas dinâmicas
dynamic_columns_principais = ', '.join([
    f"MAX(CASE WHEN T.TelefonePosicao = {i} THEN T.Telefone END) AS telefone_principal{i}"
    for i in range(1, max_principais + 1)
])
dynamic_columns_nao_principais = ', '.join([
    f"MAX(CASE WHEN TN.TelefonePosicao = {i} THEN TN.Telefone END) AS telefone_nao_principal{i}"
    for i in range(1, max_nao_principais + 1)
])

# Query principal (SEM NEGOCIADOR / SEM OUTER APPLY)
query_dynamic = f"""
WITH Inadimplentes AS (
    SELECT DISTINCT
        dbo.RetornaNomeCampanha(MoCampanhasID, 1) AS CAMPANHA,
        dbo.RetornaNomeRazaoSocial(MoClientesID) AS CREDOR,
        dbo.RetornaCPFCNPJ(MoInadimplentesID, 1) AS CPFCNPJ_CLIENTE,
        dbo.RetornaNomeRazaoSocial(MoInadimplentesID) AS NOME_RAZAO_SOCIAL,
        MoInadimplentesID AS PessoaID,
        CASE 
            WHEN DATEDIFF(DAY, MIN(MoDataVencimento), GETDATE()) <= 90 THEN '1. Até 90 dias'
            WHEN DATEDIFF(DAY, MIN(MoDataVencimento), GETDATE()) BETWEEN 91 AND 180 THEN '2. 91 a 180 dias'
            WHEN DATEDIFF(DAY, MIN(MoDataVencimento), GETDATE()) BETWEEN 181 AND 360 THEN '3. 181 a 360 dias'
            WHEN DATEDIFF(DAY, MIN(MoDataVencimento), GETDATE()) BETWEEN 361 AND 720 THEN '4. 361 a 720 dias'
            ELSE '5. Acima de 720 dias'
        END AS FAIXA_AGING
    FROM Movimentacoes
        INNER JOIN Pessoas ON MoInadimplentesID = Pessoas_ID
    WHERE 
        MoStatusMovimentacao = 0
        AND MoDataVencimento < GETDATE()
        AND MoOrigemMovimentacao IN ('C', 'I')
        AND MoCampanhasID NOT IN (12,16,20,35,38,42,44,47,48,49,64,65)
        -- Exclui quem tiver alguma parcela de acordo aberta
        AND NOT EXISTS (
            SELECT 1
            FROM Movimentacoes m2
            WHERE m2.MoInadimplentesID     = Movimentacoes.MoInadimplentesID
              AND m2.MoOrigemMovimentacao  = 'A'  -- Acordo
              AND m2.MoStatusMovimentacao  = 0    -- Aberto
        )
    GROUP BY 
        dbo.RetornaNomeCampanha(MoCampanhasID, 1),
        dbo.RetornaNomeRazaoSocial(MoClientesID),
        dbo.RetornaCPFCNPJ(MoInadimplentesID, 1),
        dbo.RetornaNomeRazaoSocial(MoInadimplentesID),
        MoInadimplentesID
),
TelefonesPrincipais AS (
    SELECT 
        PesPessoasID AS PessoaID,
        CONCAT(PesDDD, PesTelefone) AS Telefone,
        ROW_NUMBER() OVER (PARTITION BY PesPessoasID ORDER BY PesTelefone) AS TelefonePosicao
    FROM PessoasContatos
    WHERE 
        ISNULL(PesTelefoneInativo, 0) <> 1 
        AND ISNULL(PesTelefonePrincipal, 0) = 1 
        AND PesTelefone <> ''
),
TelefonesNaoPrincipais AS (
    SELECT 
        PesPessoasID AS PessoaID,
        CONCAT(PesDDD, PesTelefone) AS Telefone,
        ROW_NUMBER() OVER (PARTITION BY PesPessoasID ORDER BY PesTelefone) AS TelefonePosicao
    FROM PessoasContatos
    WHERE 
        ISNULL(PesTelefoneInativo, 0) <> 1 
        AND ISNULL(PesTelefonePrincipal, 0) = 0 
        AND PesTelefone <> ''
)
SELECT 
    I.CAMPANHA,
    I.CREDOR,
    I.CPFCNPJ_CLIENTE,
    I.NOME_RAZAO_SOCIAL,
    {dynamic_columns_principais},
    {dynamic_columns_nao_principais}
FROM Inadimplentes I
LEFT JOIN TelefonesPrincipais T ON I.PessoaID = T.PessoaID
LEFT JOIN TelefonesNaoPrincipais TN ON I.PessoaID = TN.PessoaID
GROUP BY 
    I.CAMPANHA,
    I.CREDOR,
    I.CPFCNPJ_CLIENTE,
    I.NOME_RAZAO_SOCIAL;
"""

print("Extraindo dados (consulta principal)...")
logger.info("Extraindo dados (consulta principal)...")
sp = iniciar_spinner("Extraindo (consulta principal)")
try:
    df = _run_sql_with_reconnect(conn, query_dynamic, "consulta principal")
finally:
    parar_spinner(sp, "Extração (consulta principal)")
print(f"Extração concluída: registros={len(df)} campanhas={df['CAMPANHA'].nunique()}")
logger.info("Extração concluída: registros=%s campanhas=%s", len(df), df['CAMPANHA'].nunique())

# Consulta dos CPFs com RO recente
query_ro = """
    SELECT DISTINCT
        REPLACE(REPLACE(REPLACE(CPF_CNPJ_CLIENTE, '.', ''), '-', ''), '/', '') AS CPF_CNPJ_CLIENTE
    FROM [Candiotto_reports].dbo.tabelaacionamento
    WHERE 
        RoId IN (56, 57, 58, 59)
        AND [DATA] >= DATEADD(DAY, -7, GETDATE())
"""
print("Consultando CPFs com RO recente...")
logger.info("Consultando CPFs com RO recente...")
sp2 = iniciar_spinner("Consultando RO recente")
try:
    df_ro = _run_sql_with_reconnect(conn, query_ro, "consulta RO recente")
finally:
    parar_spinner(sp2, "Consulta RO")
print(f"CPFs com RO recente: {len(df_ro)}")
logger.info("CPFs com RO recente: %s", len(df_ro))
conn.close()

# Normalizar CPF no mailing e filtrar quem teve RO recente
df['CPF_CNPJ_LIMPO'] = df['CPFCNPJ_CLIENTE'].str.replace(r'\D', '', regex=True)
cpfs_com_ro = set(df_ro['CPF_CNPJ_CLIENTE'])
df = df[~df['CPF_CNPJ_LIMPO'].isin(cpfs_com_ro)].copy()
print(f"Após filtro RO: registros={len(df)} campanhas={df['CAMPANHA'].nunique()}")
logger.info("Após filtro RO: registros=%s campanhas=%s", len(df), df['CAMPANHA'].nunique())

# Limpeza de telefones
telefone_cols = [c for c in df.columns if c.startswith('telefone_principal') or c.startswith('telefone_nao_principal')]

def limpar_telefone(telefone):
    if pd.isnull(telefone):
        return ""
    telefone = re.sub(r'\D', '', str(telefone))
    return telefone if len(telefone) >= 10 else ""

for col in telefone_cols:
    df[col] = df[col].apply(limpar_telefone)

df['telefones'] = df[telefone_cols].apply(lambda row: [tel for tel in row if tel], axis=1)

# Layout final
mailing_columns = ['COD', 'CPFCNPJ CLIENTE', 'NOME / RAZAO SOCIAL', 'CAMPANHA'] + [f'TELEFONE_{i}' for i in range(1, 21)]

def preencher_telefones(row):
    telefones = row['telefones'][:20]
    return telefones + [""] * (20 - len(telefones))

# Geração dos arquivos (um por CAMPANHA)
OUTPUT_RESUMO = str(os.getenv("OUTPUT_RESUMO", "1")).lower() in ("1", "true", "yes")
resultados: list[tuple[str, int]] = []
data_atual = datetime.now().strftime('%Y-%m-%d')
base_dir = os.path.join("data", "campanhas")
os.makedirs(base_dir, exist_ok=True)

total_campanhas = df['CAMPANHA'].nunique()
print(f"Gerando arquivos CSV por campanha: {total_campanhas}")
logger.info("Gerando arquivos CSV por campanha: %s", total_campanhas)
if total_campanhas > 0:
    atualizar_barra(0, total_campanhas, prefixo="Gerando CSVs")
for idx, (campanha, grupo) in enumerate(df.groupby('CAMPANHA'), start=1):
    mailing_base = pd.DataFrame({
        'COD': grupo['CPFCNPJ_CLIENTE'],
        'CPFCNPJ CLIENTE': grupo['CPFCNPJ_CLIENTE'],
        'NOME / RAZAO SOCIAL': grupo['NOME_RAZAO_SOCIAL'],
        'CAMPANHA': grupo['CAMPANHA']
    })

    telefones_expandidos = grupo.apply(preencher_telefones, axis=1)
    telefones_df = pd.DataFrame(
        telefones_expandidos.tolist(),
        columns=[f'TELEFONE_{i}' for i in range(1, 21)]
    )
    mailing = pd.concat([mailing_base, telefones_df], axis=1).copy()
    mailing = mailing.drop_duplicates(subset=['COD'])

    nome_arquivo = f"Mailing {campanha} - {data_atual}.csv"
    nome_arquivo = nome_arquivo.replace("/", "-").replace("\\", "-").replace(":", "-")
    caminho_arquivo = os.path.join(base_dir, nome_arquivo)
    try:
        mailing.to_csv(caminho_arquivo, index=False, sep=';', encoding='utf-8-sig')
    except Exception as e:
        logger.error("Falha ao gravar CSV '%s': %s", caminho_arquivo, e)
        raise
    resultados.append((caminho_arquivo, len(mailing)))
    if not OUTPUT_RESUMO:
        print(f"OK: arquivo='{os.path.basename(caminho_arquivo)}' linhas={len(mailing)}")
    logger.info("OK: arquivo='%s' linhas=%s", os.path.basename(caminho_arquivo), len(mailing))
    if total_campanhas > 0:
        atualizar_barra(idx, total_campanhas, prefixo="Gerando CSVs")

if OUTPUT_RESUMO:
    total_arqs = len(resultados)
    total_linhas = sum(l for _, l in resultados)
    print(f"Arquivos gerados: {total_arqs} | Total de linhas: {total_linhas}")
    for fpath, linhas in resultados:
        print(f"- {os.path.basename(fpath)} linhas={linhas}")

print("Arquivos de mailing por campanha gerados com sucesso!")
logger.info("Arquivos de mailing por campanha gerados com sucesso!")
