from __future__ import annotations

import csv
import os
from typing import Any, Dict, List

try:
    from .barra import atualizar_barra
except ImportError:
    from barra import atualizar_barra


def carregar_contatos_csv_semicolon(caminho_csv: str) -> List[Dict[str, Any]]:
    """Carrega contatos de CSV com separador ';' no formato padrão.

    Fail-fast: arquivo ausente ou sem cabeçalho gera erro explícito.
    Saída compatível com o envio JSON no 3C+.
    """
    if not os.path.exists(caminho_csv):
        raise FileNotFoundError(f"CSV não encontrado: {caminho_csv}")
    contatos: List[Dict[str, Any]] = []
    # Contar linhas (sem cabeçalho) para exibir progresso real e finalizar em 100%
    with open(caminho_csv, "r", encoding="utf-8-sig", newline="") as fh_count:
        reader_count = csv.reader(fh_count, delimiter=";")
        total = 0
        # Primeira linha é cabeçalho; começar a contagem a partir da segunda
        try:
            next(reader_count)
        except StopIteration:
            raise ValueError("Cabeçalho ausente no CSV")
        for _ in reader_count:
            total += 1
    with open(caminho_csv, "r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=";")
        if not reader.fieldnames:
            raise ValueError("Cabeçalho ausente no CSV")
        atual = 0
        for row in reader:
            phones: List[str] = []
            for k, v in row.items():
                if not isinstance(k, str):
                    continue
                if k.upper().startswith("TELEFONE") and v and str(v).strip():
                    num = _so_digitos(str(v).strip())
                    if num:
                        phones.append(num)
            contato = {
                "name": _clean(row.get("NOME / RAZAO SOCIAL") or row.get("NOME") or ""),
                "document": _clean(row.get("CPFCNPJ CLIENTE") or row.get("CPF") or row.get("CNPJ") or ""),
                "external_id": _clean(row.get("COD") or ""),
                "phones": phones,
            }
            contatos.append(contato)
            atual += 1
            atualizar_barra(atual, total, prefixo="Extração")
    return contatos


def _clean(v: str | None) -> str | None:
    if v is None:
        return None
    v2 = str(v).strip()
    return v2 or None


def _so_digitos(v: str) -> str:
    return "".join(ch for ch in v if ch.isdigit())
