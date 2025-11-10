"""
Script para identificar campanhas que precisam de mapeamento.
Lista arquivos disponíveis para facilitar o mapeamento manual.
"""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from src.config_mailing import MAILING_MAP

def extrair_info_arquivo(nome_arquivo):
    """Extrai número e nome da campanha do arquivo."""
    # Formato: Mailing XXXXXX - NOME - DATA.csv
    if not nome_arquivo.startswith("Mailing "):
        return None, None
    
    partes = nome_arquivo.replace(".csv", "").split(" - ")
    if len(partes) < 2:
        return None, None
    
    numero_str = partes[0].replace("Mailing ", "").strip()
    nome_campanha = partes[1].strip() if len(partes) > 1 else ""
    
    try:
        numero = int(numero_str)
        return numero, nome_campanha
    except ValueError:
        return None, None

def listar_campanhas_disponiveis():
    """Lista todas as campanhas disponíveis nos arquivos."""
    base_dir = Path("data/campanhas")
    
    if not base_dir.exists():
        print(f"❌ Diretório não encontrado: {base_dir}")
        return
    
    # Coletar informações dos arquivos
    arquivos_info = []
    for arquivo in base_dir.glob("*.csv"):
        numero, nome = extrair_info_arquivo(arquivo.name)
        if numero and nome:
            mtime = arquivo.stat().st_mtime
            arquivos_info.append({
                'numero': numero,
                'nome': nome,
                'arquivo': arquivo.name,
                'mtime': mtime,
                'mapeado': nome in MAILING_MAP or any(
                    nome.lower() in k.lower() or k.lower() in nome.lower() 
                    for k in MAILING_MAP.keys()
                )
            })
    
    # Ordenar por número
    arquivos_info.sort(key=lambda x: x['numero'])
    
    print("=" * 100)
    print("CAMPANHAS DISPONÍVEIS PARA MAPEAMENTO")
    print("=" * 100)
    print(f"\nTotal de arquivos encontrados: {len(arquivos_info)}")
    print(f"Campanhas já mapeadas: {len(MAILING_MAP)}\n")
    
    # Separar mapeadas e não mapeadas
    mapeadas = [a for a in arquivos_info if a['mapeado']]
    nao_mapeadas = [a for a in arquivos_info if not a['mapeado']]
    
    # Mostrar campanhas JÁ MAPEADAS
    if mapeadas:
        print("\n" + "=" * 100)
        print("✅ CAMPANHAS JÁ MAPEADAS")
        print("=" * 100)
        for info in mapeadas:
            status = "✅ MAPEADO"
            # Verificar se está exatamente no MAILING_MAP
            if info['nome'] in MAILING_MAP:
                numero_mapeado = MAILING_MAP[info['nome']]
                if numero_mapeado == info['numero']:
                    status = f"✅ MAPEADO ({numero_mapeado:06d})"
                else:
                    status = f"⚠️  CONFLITO (mapeado: {numero_mapeado:06d}, arquivo: {info['numero']:06d})"
            print(f"  {info['numero']:06d} | {info['nome']:<50} | {status}")
    
    # Mostrar campanhas NÃO MAPEADAS
    if nao_mapeadas:
        print("\n" + "=" * 100)
        print("📋 CAMPANHAS DISPONÍVEIS (NÃO MAPEADAS)")
        print("=" * 100)
        print("\nCopie e cole no config_mailing.py conforme necessário:\n")
        
        for info in nao_mapeadas:
            # Sugerir nome limpo para mapeamento
            nome_sugerido = info['nome']
            print(f'    "{nome_sugerido}": {info["numero"]},  # {info["arquivo"][:60]}')
    
    print("\n" + "=" * 100)
    print("RESUMO")
    print("=" * 100)
    print(f"  ✅ Mapeadas:     {len(mapeadas)}")
    print(f"  📋 Não mapeadas: {len(nao_mapeadas)}")
    print(f"  📁 Total:        {len(arquivos_info)}")
    print("=" * 100)

if __name__ == "__main__":
    listar_campanhas_disponiveis()
