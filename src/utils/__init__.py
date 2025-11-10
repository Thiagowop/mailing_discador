"""Módulo de utilitários gerais.

Contém funções auxiliares para barra de progresso e outros utilitários leves.
"""

from .barra import iniciar_spinner, parar_spinner, atualizar_barra

__all__ = [
    "iniciar_spinner",
    "parar_spinner",
    "atualizar_barra",
]
