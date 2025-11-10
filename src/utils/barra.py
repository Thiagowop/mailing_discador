"""Utilitário simples de barra de progresso (console).

Princípios:
- Idioma pt-BR
- Sem dependências externas
- Config First: respeita PROGRESS_BAR no ambiente

Uso:
    from src.barra import atualizar_barra
    for i in range(total):
        # ... trabalho ...
        atualizar_barra(i + 1, total, prefixo="Extração")
"""

from __future__ import annotations

import os
import sys
from typing import Optional, Tuple
import threading
import time


def _habilitado() -> bool:
    """Verifica flag PROGRESS_BAR no ambiente (default: habilitado)."""
    val = str(os.getenv("PROGRESS_BAR", "1")).lower()
    return val in ("1", "true", "yes")

def _percent_habilitado() -> bool:
    """Controla a exibição da barra de porcentagem via PROGRESS_BAR_PERCENT (default: desabilitado)."""
    val = str(os.getenv("PROGRESS_BAR_PERCENT", "0")).lower()
    return val in ("1", "true", "yes")


def atualizar_barra(atual: int, total: int, *, prefixo: Optional[str] = None, largura: int = 40) -> None:
    """Atualiza a barra de progresso no console.

    - Exibe uma única linha atualizada via carriage return (\r).
    - Garante 100% ao finalizar (quando atual >= total).

    Parâmetros:
    - atual: itens já processados (>= 0)
    - total: itens a processar (> 0)
    - prefixo: texto opcional antes da barra (ex.: "Extração")
    - largura: quantidade de blocos na barra (default 40)
    """
    if not _habilitado() or not _percent_habilitado():
        return

    if total <= 0:
        # Sem total conhecido: não exibir barra
        return

    if atual < 0:
        atual = 0
    if atual > total:
        atual = total

    percentual = int((atual / total) * 100)
    completos = int((percentual * largura) / 100)
    barra = "#" * completos
    espacos = " " * (largura - completos)

    texto_prefixo = f"{prefixo}: " if prefixo else ""
    linha = f"\r{texto_prefixo}[{barra}{espacos}] {percentual:3d}% ({atual}/{total})"
    # Escrever sem quebra de linha, atualizando a mesma linha
    sys.stdout.write(linha)
    sys.stdout.flush()

    # Ao finalizar, quebrar linha para encerrar visual cristalino
    if atual >= total:
        sys.stdout.write("\n")
        sys.stdout.flush()


def iniciar_spinner(mensagem: str = "Processando", intervalo: float = 0.1) -> Optional[Tuple[threading.Event, threading.Thread, str]]:
    """Inicia um spinner (progresso indefinido) em nova linha.

    - Respeita PROGRESS_BAR no ambiente.
    - Retorna um token (stop_event, thread, mensagem) para ser usado em parar_spinner.
    """
    if not _habilitado():
        return None

    stop_event = threading.Event()

    def _spin() -> None:
        simbolos = "|/-\\"
        i = 0
        # Alocar linha abaixo
        sys.stdout.write("\n")
        sys.stdout.flush()
        while not stop_event.is_set():
            ch = simbolos[i % len(simbolos)]
            sys.stdout.write(f"\r{mensagem} {ch}")
            sys.stdout.flush()
            time.sleep(intervalo)
            i += 1

    th = threading.Thread(target=_spin, daemon=True)
    th.start()
    return (stop_event, th, mensagem)


def parar_spinner(token: Optional[Tuple[threading.Event, threading.Thread, str]], mensagem_conclusao: Optional[str] = None) -> None:
    """Finaliza o spinner e imprime conclusão na mesma linha.

    - Aceita token retornado por iniciar_spinner; ignora se None.
    """
    if token is None or not _habilitado():
        return
    stop_event, th, msg = token
    try:
        stop_event.set()
        th.join(timeout=2.0)
    except Exception:
        pass
    texto = mensagem_conclusao or f"{msg} concluido"
    sys.stdout.write(f"\r{texto} [OK]\n")
    sys.stdout.flush()
