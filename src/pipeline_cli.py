"""Utilitarios de linha de comando usados pelos scripts .bat.

Fornece operacoes para limpar CSVs, atualizar e listar campanhas,
testar conexoes e exibir configuracoes do ambiente.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from dotenv import load_dotenv
from datetime import datetime


def _limpar_arquivos_csv(bases: Sequence[str], prefixo: str) -> int:
    """Remove arquivos CSV das pastas informadas."""
    for base in bases:
        caminho = Path(base)
        print(f"[{prefixo}] Removendo CSVs em {caminho}")
        removidos = 0
        if caminho.is_dir():
            for arquivo in caminho.iterdir():
                if arquivo.suffix.lower() == ".csv":
                    try:
                        arquivo.unlink()
                        removidos += 1
                    except Exception as exc:  # pragma: no cover - log de erro
                        print(f"Falha ao remover {arquivo.name}: {exc}")
        else:
            print(f"AVISO: Diretorio nao encontrado: {caminho}")
        print(f"Removidos {removidos} arquivos")
    return 0


def limpar_csvs(bases: Sequence[str], prefixo: str) -> int:
    """Wrapper publico para limpeza de CSVs."""
    return _limpar_arquivos_csv(bases, prefixo)


def _criar_cliente_mailing():
    """Instancia cliente autenticado do 3C+."""
    from .threec.auth import ThreeCAuthClient
    from .threec.mailing_client import ThreeCMailingClient

    auth = ThreeCAuthClient()
    auth.login()
    cliente = ThreeCMailingClient(auth)
    _ajustar_logger_console(cliente)
    return cliente


def _ajustar_logger_console(cliente: Any) -> None:
    """Reduz verbosidade do logger no console para evitar poluicao."""
    import logging

    alvo = str(os.getenv("PIPELINE_LOG_LEVEL", "WARNING")).upper()
    try:
        level = getattr(logging, alvo)
    except AttributeError:
        level = logging.WARNING

    logger = getattr(cliente, "logger", None)
    if logger is None:
        return
    for handler in getattr(logger, "handlers", []):
        if handler.__class__.__name__ == "StreamHandler":
            handler.setLevel(level)


def _obter_campanhas_destino() -> list[str]:
    load_dotenv()
    alvo = os.getenv("THREECPLUS_TARGET_CAMPAIGNS")
    if not alvo:
        raise RuntimeError("THREECPLUS_TARGET_CAMPAIGNS ausente no .env")
    return [item.strip() for item in alvo.split(",") if item.strip()]


def atualizar_campanhas(diretorio_csv: str) -> int:
    """Remove listas existentes e alimenta novas listas com base nos CSVs."""
    try:
        nomes = _obter_campanhas_destino()
    except RuntimeError as exc:
        print(exc)
        return 1

    cliente = _criar_cliente_mailing()
    campanhas = cliente.listar_campanhas()
    ids = {camp.get("name"): camp.get("id") for camp in campanhas if camp.get("name")}

    erros: list[str] = []
    falhas_delecao: list[str] = []
    sucessos: list[str] = []
    total_deletadas = 0

    for nome in nomes:
        cid = ids.get(nome)
        if cid is None:
            erros.append(f"Campanha nao encontrada: {nome}")
            continue

        listas_resp = cliente.listar_listas_da_campanha(cid)
        listas: Iterable[dict] = []
        if isinstance(listas_resp, dict):
            for chave in ("data", "lists", "items"):
                valor = listas_resp.get(chave)
                if isinstance(valor, list):
                    listas = valor
                    break

        for item in listas:
            lid = item.get("id") or item.get("list_id") or item.get("mailing_id")
            if not lid:
                continue
            try:
                cliente.deletar_lista_da_campanha(cid, lid)
                total_deletadas += 1
            except Exception as exc:  # pragma: no cover - log de erro
                falhas_delecao.append(f"{nome} -> lista {lid}: {exc}")

        from .threec.mailing_client import _encontrar_csv_campanha

        csv = _encontrar_csv_campanha(diretorio_csv, nome)
        if not csv:
            erros.append(f"CSV nao encontrado para: {nome}")
            continue
        try:
            # Usar o mesmo mapeamento de colunas do modulo principal para maior compatibilidade
            colmap = {
                "COD": "identifier",
                "CPFCNPJ CLIENTE": "document",
                "NOME / RAZAO SOCIAL": "name",
                "CAMPANHA": "name",
            }
            for i in range(1, 21):
                colmap[f"TELEFONE_{i}"] = "areacodephone"

            nome_csv = os.path.splitext(os.path.basename(csv))[0]
            criado = cliente.criar_mailing_por_csv_em_campanha(
                cid,
                csv,
                filename=nome_csv,
                colmap=colmap,
            )
            # Ajustar peso para garantir visibilidade (100)
            list_id: int | None = None
            try:
                # Tenta extrair id diretamente da resposta
                list_id = int(getattr(cliente, "_extract_id")(criado, ["data.list_id", "list_id", "id"]))
            except Exception:
                list_id = None
            if list_id is None:
                # Reconsulta listas e escolhe maior id como último criado
                try:
                    listas_resp_new = cliente.listar_listas_da_campanha(cid)
                    listas_new: list[dict] = []
                    if isinstance(listas_resp_new, dict):
                        for chave in ("data", "lists", "items"):
                            v = listas_resp_new.get(chave)
                            if isinstance(v, list):
                                listas_new = v
                                break
                    if listas_new:
                        try:
                            list_id = max(
                                [
                                    int(x.get("id") or x.get("list_id") or x.get("mailing_id"))
                                    for x in listas_new
                                    if (x.get("id") or x.get("list_id") or x.get("mailing_id"))
                                ]
                            )
                        except Exception:
                            list_id = None
                except Exception:
                    list_id = None

            try:
                if list_id is not None:
                    cliente.ajustar_peso_mailing(list_id, 100, campaign_id=cid)
            except Exception:
                pass

            sucessos.append(f"{nome} [{Path(csv).name}]")
        except Exception as exc:  # pragma: no cover - log de erro
            erros.append(f"Falha ao criar lista para {nome}: {exc}")

    if total_deletadas:
        print(f"Listas removidas: {total_deletadas}")
    if falhas_delecao:
        print("Falhas ao remover listas:")
        for msg in falhas_delecao:
            print(f" - {msg}")

    if erros:
        for msg in erros:
            print(msg)
        return 3

    if sucessos:
        print(f"Campanhas atualizadas ({len(sucessos)}):")
        for msg in sucessos:
            print(f" - {msg}")
    else:
        print("Nenhuma campanha atualizada (verifique configuracao).")

    print("Atualizacao concluida.")
    return 0


def limpar_listas() -> int:
    """Apenas remove listas das campanhas de destino."""
    try:
        nomes = _obter_campanhas_destino()
    except RuntimeError as exc:
        print(exc)
        return 1

    cliente = _criar_cliente_mailing()
    campanhas = cliente.listar_campanhas()

    falhas: list[str] = []
    total_deletadas = 0

    for nome in nomes:
        cid = None
        for campanha in campanhas:
            if campanha.get("name") == nome:
                cid = campanha.get("id")
                break
        if cid is None:
            print(f"Campanha nao encontrada: {nome}")
            continue

        listas_resp = cliente.listar_listas_da_campanha(cid)
        listas: Iterable[dict] = []
        if isinstance(listas_resp, dict):
            for chave in ("data", "lists", "items"):
                valor = listas_resp.get(chave)
                if isinstance(valor, list):
                    listas = valor
                    break

        for item in listas:
            lid = item.get("id") or item.get("list_id") or item.get("mailing_id")
            if not lid:
                continue
            try:
                cliente.deletar_lista_da_campanha(cid, lid)
                total_deletadas += 1
            except Exception as exc:  # pragma: no cover - log de erro
                falhas.append(f"{nome} -> lista {lid}: {exc}")

    if total_deletadas:
        print(f"Listas removidas: {total_deletadas}")
    if falhas:
        print("Falhas ao remover listas:")
        for msg in falhas:
            print(f" - {msg}")
    print("Limpeza concluida.")
    return 0


def listar_campanhas() -> int:
    """Lista campanhas disponiveis no 3C+."""
    cliente = _criar_cliente_mailing()
    campanhas = cliente.listar_campanhas()
    print("Campanhas (id - nome):")
    for campanha in campanhas:
        identificador = campanha.get("id")
        nome = campanha.get("name")
        print(f"{identificador} - {nome}")
    return 0


def mostrar_configuradas() -> int:
    """Mostra campanhas configuradas no .env e as disponiveis na API."""
    load_dotenv()
    raw = os.getenv("THREECPLUS_TARGET_CAMPAIGNS") or ""
    configuradas = [item.strip() for item in raw.split(",") if item.strip()]
    print("Campanhas configuradas (.env):")
    if configuradas:
        for nome in configuradas:
            print(" -", nome)
    else:
        print(" - (nenhuma)")
        print("OBS: defina THREECPLUS_TARGET_CAMPAIGNS no .env")

    print()
    print("Campanhas disponiveis no 3C+:")
    try:
        cliente = _criar_cliente_mailing()
        campanhas = cliente.listar_campanhas()
        for campanha in campanhas:
            marcador = "*" if campanha.get("name") in configuradas else " "
            identificador = campanha.get("id")
            nome = campanha.get("name")
            total, ultima = _resumo_listas_campanha(cliente, identificador)
            linha = f" {marcador} {identificador} - {nome}"
            if total is not None:
                linha += f" | registros={total}"
            if ultima:
                linha += f" | ultima={ultima}"
            print(linha)
        print()
        print("Legenda: * = configurada no .env")
    except Exception as exc:  # pragma: no cover - log de erro
        print(f"Nao foi possivel listar campanhas no 3C+: {exc}")
    return 0


def _extrair_total_da_lista(item: Dict[str, Any]) -> Optional[int]:
    for chave in (
        "total",
        "records",
        "contacts",
        "size",
        "pending",
        "contacts_total",
    ):
        valor = item.get(chave)
        if isinstance(valor, (int, float)):
            return int(valor)
    summary = item.get("summary")
    if isinstance(summary, dict):
        for chave in ("total", "records", "contacts"):
            valor = summary.get(chave)
            if isinstance(valor, (int, float)):
                return int(valor)
    return None


def _resumo_listas_campanha(cliente: Any, campaign_id: int) -> tuple[Optional[int], Optional[str]]:
    """Soma registros e identifica ultima atualizacao das listas."""
    try:
        resp = cliente.listar_listas_da_campanha(campaign_id)
    except Exception:
        return None, None

    listas: Iterable[dict] = []
    if isinstance(resp, dict):
        for chave in ("data", "lists", "items"):
            valor = resp.get(chave)
            if isinstance(valor, list):
                listas = valor
                break

    total_registros = 0
    ultima_data: Optional[datetime] = None
    encontrou = False

    for item in listas:
        encontrou = True
        t = _extrair_total_da_lista(item)
        if isinstance(t, int):
            total_registros += t
        for chave in ("updated_at", "created_at"):
            valor = item.get(chave)
            if not valor:
                continue
            try:
                dt = datetime.fromisoformat(str(valor))
            except ValueError:
                try:
                    dt = datetime.strptime(str(valor)[:19], "%Y-%m-%d %H:%M:%S")
                except Exception:
                    continue
            if ultima_data is None or dt > ultima_data:
                ultima_data = dt

    if not encontrou:
        return 0, None
    ultima_str = ultima_data.strftime("%Y-%m-%d %H:%M:%S") if ultima_data else None
    return total_registros, ultima_str


def validar_listas(*, nome_campanha: Optional[str] = None, todas: bool = False, detalhado: bool = False) -> int:
    """Consulta as listas das campanhas configuradas e mostra quantidade de registros."""
    cliente = _criar_cliente_mailing()
    campanhas = cliente.listar_campanhas(somente_ativas=False)
    ids = {camp.get("name"): camp.get("id") for camp in campanhas if camp.get("name")}

    if nome_campanha:
        nomes = [nome_campanha]
    elif todas:
        nomes = list(ids.keys())
    else:
        try:
            nomes = _obter_campanhas_destino()
        except RuntimeError as exc:
            print(exc)
            return 1

    for nome in nomes:
        cid = ids.get(nome)
        if cid is None:
            print(f"Campanha nao encontrada: {nome}")
            continue

        resp = cliente.listar_listas_da_campanha(cid)
        listas: Iterable[dict] = []
        if isinstance(resp, dict):
            for chave in ("data", "lists", "items"):
                valor = resp.get(chave)
                if isinstance(valor, list):
                    listas = valor
                    break

        listas = list(listas)
        if not listas:
            print(f"Campanha '{nome}' (id={cid}): nenhuma lista retornada.")
            continue

        print(f"Campanha '{nome}' (id={cid}) - {len(listas)} lista(s):")
        for item in listas:
            lid = item.get("id") or item.get("list_id") or item.get("mailing_id")
            nome_lista = item.get("name") or item.get("mailing_name") or item.get("list_name") or ""
            total = _extrair_total_da_lista(item)
            importando = "importando" if item.get("importing") else ""
            resumo = (
                f"  - id={lid} nome='{nome_lista}' registros={total if total is not None else '?'} {importando}"
            )
            if detalhado:
                resumo += (
                    f" | original='{item.get('original_name','')}'"
                    f" | headers={','.join(item.get('headers', [])) or '-'}"
                    f" | criado={item.get('created_at')} atualizado={item.get('updated_at')}"
                )
            print(resumo)
    return 0


def atualizar_campanha_individual(nome: str, csv_path: Optional[str] = None) -> int:
    """Atualiza apenas uma campanha usando um CSV específico."""
    cliente = _criar_cliente_mailing()
    campanhas = cliente.listar_campanhas(somente_ativas=False)
    ids = {camp.get("name"): camp.get("id") for camp in campanhas if camp.get("name")}
    cid = ids.get(nome)
    if cid is None:
        print(f"Campanha nao encontrada: {nome}")
        return 1

    if csv_path is None:
        from .threec.mailing_client import _encontrar_csv_campanha

        csv_path = _encontrar_csv_campanha(os.path.join("data", "campanhas"), nome)
    if not csv_path or not os.path.exists(csv_path):
        print(f"CSV nao encontrado para '{nome}'. Informe com --csv.")
        return 1

    colmap = {
        "COD": "identifier",
        "CPFCNPJ CLIENTE": "document",
        "NOME / RAZAO SOCIAL": "name",
        "CAMPANHA": "name",
    }
    for i in range(1, 21):
        colmap[f"TELEFONE_{i}"] = "areacodephone"

    resultado = cliente.criar_mailing_por_csv_em_campanha(
        cid,
        csv_path,
        filename=os.path.splitext(os.path.basename(csv_path))[0],
        colmap=colmap,
    )
    try:
        list_id = getattr(cliente, "_extract_id")(resultado, ["data.list_id", "list_id", "id"])
    except Exception:
        list_id = None

    if list_id:
        try:
            cliente.ajustar_peso_mailing(list_id, 100, campaign_id=cid)
        except Exception:
            pass

    print(f"Campanha '{nome}' atualizada com {os.path.basename(csv_path)}")
    return 0


def testar_conexao() -> int:
    """Valida conexao com o banco via pyodbc."""
    load_dotenv()
    try:
        import pyodbc  # type: ignore
    except ImportError as exc:
        print(f"pyodbc nao encontrado: {exc}")
        return 1

    server = os.getenv("DB_SERVER")
    database = os.getenv("DB_DATABASE")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    driver = os.getenv("DB_DRIVER", "{ODBC Driver 18 for SQL Server}")
    trust = str(os.getenv("DB_TRUST_CERT", "0")).lower() in ("1", "true", "yes")

    missing = [
        chave
        for chave, valor in (
            ("DB_SERVER", server),
            ("DB_DATABASE", database),
            ("DB_USER", user),
            ("DB_PASSWORD", password),
        )
        if not valor
    ]
    if missing:
        print("Variaveis ausentes no .env: " + ", ".join(missing))
        return 1

    tls = "Encrypt=yes;TrustServerCertificate=yes;" if trust else "Encrypt=yes;"
    conn = pyodbc.connect(
        f"DRIVER={driver};SERVER={server};DATABASE={database};UID={user};PWD={password};{tls}"
    )
    cursor = conn.cursor()
    cursor.execute("select 1")
    print("Conexao OK (select 1)")
    conn.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m src.pipeline_cli",
        description="Ferramentas auxiliares para pipeline 3C+.",
    )
    subparsers = parser.add_subparsers(dest="comando", required=True)

    limpar = subparsers.add_parser("limpar-csv", help="Remover CSVs das pastas indicadas.")
    limpar.add_argument("bases", nargs="+", help="Pastas que contem CSVs.")
    limpar.add_argument(
        "--prefixo",
        default="Pipeline",
        help="Prefixo impresso nas mensagens (default: Pipeline).",
    )

    alimentar = subparsers.add_parser(
        "atualizar-listas",
        help="Limpa listas das campanhas configuradas e insere novos CSVs.",
    )
    alimentar.add_argument(
        "--diretorio-csv",
        default=str(Path("data", "campanhas")),
        help="Diretorio onde os CSVs das campanhas sao procurados.",
    )

    subparsers.add_parser(
        "limpar-listas",
        help="Somente remove listas das campanhas configuradas no .env.",
    )
    subparsers.add_parser("listar-campanhas", help="Lista campanhas disponiveis na API.")
    subparsers.add_parser(
        "mostrar-configuradas",
        help="Exibe campanhas configuradas e as disponiveis na API.",
    )
    validar = subparsers.add_parser(
        "validar-listas",
        help="Consulta listas nas campanhas configuradas e exibe total de registros.",
    )
    validar.add_argument("--campanha", help="Nome exato da campanha para validar (ignora .env).")
    validar.add_argument("--todas", action="store_true", help="Validar todas as campanhas do tenant.")
    validar.add_argument("--detalhes", action="store_true", help="Mostrar headers e timestamps.")

    atualizar_unica = subparsers.add_parser(
        "atualizar-campanha",
        help="Atualiza apenas uma campanha informada.",
    )
    atualizar_unica.add_argument("--nome", required=True, help="Nome exato da campanha.")
    atualizar_unica.add_argument(
        "--csv",
        help="Caminho do CSV a enviar. Se omitido, procura em data/campanhas.",
    )
    subparsers.add_parser("testar-conexao", help="Testa conexao com banco via pyodbc.")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.comando == "limpar-csv":
        return limpar_csvs(args.bases, args.prefixo)
    if args.comando == "atualizar-listas":
        return atualizar_campanhas(args.diretorio_csv)
    if args.comando == "limpar-listas":
        return limpar_listas()
    if args.comando == "listar-campanhas":
        return listar_campanhas()
    if args.comando == "mostrar-configuradas":
        return mostrar_configuradas()
    if args.comando == "validar-listas":
        return validar_listas(
            nome_campanha=args.campanha,
            todas=args.todas,
            detalhado=getattr(args, "detalhes", False),
        )
    if args.comando == "atualizar-campanha":
        return atualizar_campanha_individual(args.nome, args.csv)
    if args.comando == "testar-conexao":
        return testar_conexao()

    parser.error("Comando desconhecido.")
    return 2


if __name__ == "__main__":
    sys.exit(main())
