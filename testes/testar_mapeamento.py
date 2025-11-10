"""
Script para testar o mapeamento de campanhas para arquivos de mailing.
"""
import os
import sys
from pathlib import Path

# Adicionar src ao path
sys.path.insert(0, str(Path(__file__).parent))

from src.threec.mailing_client import _encontrar_csv_campanha
from src.config_mailing import MAILING_MAP

def testar_mapeamento():
    """Testa se cada campanha mapeada encontra o arquivo correto."""
    
    base_dir = os.path.join("data", "campanhas")
    
    if not os.path.exists(base_dir):
        print(f"❌ Diretório não encontrado: {base_dir}")
        return
    
    print("=" * 80)
    print("TESTE DE MAPEAMENTO: CAMPANHAS → ARQUIVOS")
    print("=" * 80)
    print(f"\nDiretório: {base_dir}")
    print(f"Campanhas mapeadas: {len(MAILING_MAP)}\n")
    
    sucesso = 0
    falha = 0
    
    for campanha, numero in MAILING_MAP.items():
        print(f"\n📋 Testando: {campanha}")
        print(f"   Número mapeado: {numero:06d}")
        
        arquivo = _encontrar_csv_campanha(base_dir, campanha)
        
        if arquivo:
            print(f"   ✅ ENCONTRADO: {os.path.basename(arquivo)}")
            sucesso += 1
        else:
            print(f"   ❌ NÃO ENCONTRADO!")
            falha += 1
    
    print("\n" + "=" * 80)
    print("RESUMO DO TESTE")
    print("=" * 80)
    print(f"  ✅ Sucesso: {sucesso}/{len(MAILING_MAP)}")
    print(f"  ❌ Falha:   {falha}/{len(MAILING_MAP)}")
    
    if falha == 0:
        print("\n🎉 TODOS OS TESTES PASSARAM!")
    else:
        print(f"\n⚠️  {falha} campanha(s) não encontraram arquivo!")
    
    print("=" * 80)

if __name__ == "__main__":
    testar_mapeamento()
