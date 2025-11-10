"""
Script para listar campanhas do 3C Plus e suas listas/mailings.
Ajuda a identificar qual número de mailing está sendo usado em cada campanha.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv()

from src.threec.auth import ThreeCAuthClient
from src.threec.mailing_client import ThreeCMailingClient

def listar_campanhas_com_listas():
    """Lista todas as campanhas do 3C Plus e seus mailings."""
    
    print("=" * 100)
    print("CAMPANHAS E LISTAS NO 3C PLUS")
    print("=" * 100)
    
    auth = ThreeCAuthClient()
    auth.login()
    client = ThreeCMailingClient(auth)
    
    try:
        campanhas = client.listar_campanhas()
        
        print(f"\nTotal de campanhas: {len(campanhas)}\n")
        
        for camp in campanhas:
            camp_id = camp.get('id')
            camp_nome = camp.get('name', 'Sem nome')
            
            print(f"\n{'=' * 100}")
            print(f"Campanha: {camp_nome}")
            print(f"ID: {camp_id}")
            
            # Tentar listar os mailings da campanha
            try:
                resultado = client.listar_listas_da_campanha(camp_id)
                mailings = resultado.get('lists', [])
                
                if mailings:
                    print(f"OK - {len(mailings)} lista(s) encontrada(s):")
                    for mailing in mailings:
                        mailing_id = mailing.get('id', 'N/A')
                        mailing_nome = mailing.get('name', 'Sem nome')
                        total = mailing.get('total', 0)
                        criado = mailing.get('created_at', 'N/A')
                        
                        print(f"   Lista ID: {mailing_id} | Nome: {mailing_nome}")
                        print(f"   Total: {total} contatos | Criado em: {criado}")
                else:
                    print(f"AVISO - Nenhuma lista encontrada")
                    
            except Exception as e:
                print(f"ERRO ao buscar listas: {e}")
        
        print("\n" + "=" * 100)
        
    except Exception as e:
        print(f"ERRO ao listar campanhas: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    listar_campanhas_com_listas()
