"""Módulo de utilitários gerais.

Contém funções auxiliares para barra de progresso,
extração de bases de dados e outros utilitários.
"""

from .barra import iniciar_spinner, parar_spinner, atualizar_barra
from .extracao_bases import carregar_contatos_csv_semicolon

__all__ = [
    "iniciar_spinner",
    "parar_spinner",
    "atualizar_barra",
    "carregar_contatos_csv_semicolon",
]
