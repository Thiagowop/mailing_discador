"""
Script de análise para verificar se as 27 campanhas do 3C Plus conseguiriam
encontrar seus arquivos de mailing locais correspondentes.

Simula o processo de busca de arquivo que o sistema faria e identifica:
1. Campanhas que conseguiriam encontrar arquivo (OK)
2. Campanhas que NÃO encontrariam arquivo (ERRO)
3. Campanhas com múltiplas correspondências (AMBIGUIDADE)
"""

import os
from pathlib import Path
import re
from difflib import SequenceMatcher

# Campanhas disponíveis no 3C Plus (conforme lista fornecida)
CAMPANHAS_3C_PLUS = [
    "Tenda",
    "Cyrela - Pré Empreendimentos",
    "Deva Veículos",
    "Longitude",
    "RSF Judicial",
    "Campanha teste",
    "Direcional Extrajudicial",
    "Direcional Judicial",
    "VIC Extrajudicial",
    "VIC Judicial",
    "EMCCAMP Extrajudicial",
    "EMCCAMP Judicial",
    "Tabelionato",
    "Cyrela Extrajudicial",
    "Cyrela Judicial",
    "Sobrosa Mello",
    "Movida Extrajudicial",
    "Movida Judicial",
    "Foco Aluguel",
    "Arbore Extrajudicial",
    "Arbore Judicial",
    "LCM",
    "Vila Brasil Extrajudicial",
    "CredAluga",
    "Jerônimo",
    "Sempre Editora",
    "São José"
]

def extrair_nome_campanha_do_arquivo(nome_arquivo):
    """Extrai o nome da campanha do nome do arquivo de mailing.
    
    Formato esperado: "Mailing XXXXXX - NOME_CAMPANHA - YYYY-MM-DD.csv"
    """
    # Remove extensão
    nome = nome_arquivo.replace('.csv', '')
    
    # Padrão: Mailing XXXXXX - NOME - DATA
    match = re.match(r'Mailing\s+\d+\s+-\s+(.+?)\s+-\s+\d{4}-\d{2}-\d{2}', nome)
    if match:
        return match.group(1).strip()
    return None

def normalizar_nome(nome):
    """Normaliza nome para comparação (minúscula, sem acentos, espaços normalizados)."""
    import unicodedata
    # Remove acentos
    nome = ''.join(c for c in unicodedata.normalize('NFD', nome)
                   if unicodedata.category(c) != 'Mn')
    # Minúscula e normaliza espaços
    return ' '.join(nome.lower().split())

def calcular_similaridade(str1, str2):
    """Calcula similaridade entre duas strings (0.0 a 1.0)."""
    return SequenceMatcher(None, str1, str2).ratio()

def buscar_arquivo_para_campanha(nome_campanha, arquivos_disponiveis):
    """
    Simula a busca de arquivo de mailing para uma campanha do 3C Plus.
    
    Retorna:
        - ('OK', arquivo, similaridade) se encontrou correspondência exata ou muito próxima
        - ('PARCIAL', [arquivos], similaridades) se encontrou correspondências parciais
        - ('ERRO', None, None) se não encontrou correspondência
    """
    nome_norm = normalizar_nome(nome_campanha)
    
    # 1. Busca exata
    for arquivo, campanha_arquivo in arquivos_disponiveis.items():
        if normalizar_nome(campanha_arquivo) == nome_norm:
            return ('OK', arquivo, 1.0)
    
    # 2. Busca por similaridade alta (>= 0.8)
    correspondencias = []
    for arquivo, campanha_arquivo in arquivos_disponiveis.items():
        similaridade = calcular_similaridade(nome_norm, normalizar_nome(campanha_arquivo))
        if similaridade >= 0.8:
            correspondencias.append((arquivo, campanha_arquivo, similaridade))
    
    if len(correspondencias) == 1:
        return ('OK', correspondencias[0][0], correspondencias[0][2])
    elif len(correspondencias) > 1:
        return ('AMBIGUIDADE', correspondencias, None)
    
    # 3. Busca por palavras-chave principais
    palavras_campanha = set(nome_norm.split())
    
    # Remove palavras comuns que não ajudam
    palavras_ignorar = {'de', 'da', 'do', 'das', 'dos', 'e', 'o', 'a', '-'}
    palavras_campanha = palavras_campanha - palavras_ignorar
    
    if palavras_campanha:
        correspondencias_parciais = []
        for arquivo, campanha_arquivo in arquivos_disponiveis.items():
            palavras_arquivo = set(normalizar_nome(campanha_arquivo).split()) - palavras_ignorar
            palavras_comuns = palavras_campanha & palavras_arquivo
            
            if palavras_comuns:
                taxa_match = len(palavras_comuns) / len(palavras_campanha)
                if taxa_match >= 0.6:  # Pelo menos 60% das palavras em comum
                    correspondencias_parciais.append((arquivo, campanha_arquivo, taxa_match))
        
        if len(correspondencias_parciais) == 1:
            return ('PARCIAL', correspondencias_parciais[0][0], correspondencias_parciais[0][2])
        elif len(correspondencias_parciais) > 1:
            return ('AMBIGUIDADE', correspondencias_parciais, None)
    
    return ('ERRO', None, None)

def analisar_campanhas():
    """Analisa se cada campanha do 3C Plus conseguiria encontrar seu arquivo local."""
    
    # Diretório de campanhas
    dir_campanhas = Path(__file__).parent / 'data' / 'campanhas'
    
    if not dir_campanhas.exists():
        print(f"❌ Diretório não encontrado: {dir_campanhas}")
        return
    
    # Mapear arquivos locais
    arquivos_disponiveis = {}
    for arquivo in os.listdir(dir_campanhas):
        if arquivo.endswith('.csv'):
            nome_campanha = extrair_nome_campanha_do_arquivo(arquivo)
            if nome_campanha:
                arquivos_disponiveis[arquivo] = nome_campanha
    
    print("=" * 100)
    print("ANÁLISE DE MAPEAMENTO: CAMPANHAS 3C PLUS → ARQUIVOS LOCAIS")
    print("=" * 100)
    print(f"\nTotal de campanhas no 3C Plus: {len(CAMPANHAS_3C_PLUS)}")
    print(f"Total de arquivos locais disponíveis: {len(arquivos_disponiveis)}")
    print("\n" + "=" * 100)
    
    # Contadores
    ok_count = 0
    erro_count = 0
    ambiguidade_count = 0
    parcial_count = 0
    
    # Listas para categorizar
    campanhas_ok = []
    campanhas_erro = []
    campanhas_ambiguidade = []
    campanhas_parcial = []
    
    # Testar cada campanha
    for i, campanha in enumerate(CAMPANHAS_3C_PLUS, 1):
        status, resultado, score = buscar_arquivo_para_campanha(campanha, arquivos_disponiveis)
        
        if status == 'OK':
            ok_count += 1
            campanhas_ok.append((campanha, resultado, score))
        elif status == 'PARCIAL':
            parcial_count += 1
            campanhas_parcial.append((campanha, resultado, score))
        elif status == 'AMBIGUIDADE':
            ambiguidade_count += 1
            campanhas_ambiguidade.append((campanha, resultado))
        else:  # ERRO
            erro_count += 1
            campanhas_erro.append(campanha)
    
    # Exibir resultados categorizados
    
    # 1. Campanhas OK
    if campanhas_ok:
        print("\n✅ CAMPANHAS QUE ENCONTRARIAM ARQUIVO (OK)")
        print("=" * 100)
        for campanha, arquivo, score in campanhas_ok:
            score_pct = int(score * 100)
            print(f"  [{score_pct:3d}%] {campanha}")
            print(f"         → {arquivo}")
    
    # 2. Campanhas com correspondência parcial
    if campanhas_parcial:
        print("\n⚠️  CAMPANHAS COM CORRESPONDÊNCIA PARCIAL")
        print("=" * 100)
        for campanha, arquivo, score in campanhas_parcial:
            score_pct = int(score * 100)
            print(f"  [{score_pct:3d}%] {campanha}")
            print(f"         → {arquivo}")
            print(f"         💡 Verificar se a correspondência está correta")
    
    # 3. Campanhas com ambiguidade
    if campanhas_ambiguidade:
        print("\n⚠️  CAMPANHAS COM MÚLTIPLAS CORRESPONDÊNCIAS (AMBIGUIDADE)")
        print("=" * 100)
        for campanha, correspondencias in campanhas_ambiguidade:
            print(f"\n  ❓ {campanha}")
            print(f"     Múltiplos arquivos encontrados:")
            for arquivo, nome, score in correspondencias:
                score_pct = int(score * 100)
                print(f"       [{score_pct:3d}%] {arquivo}")
            print(f"     ⚠️  Sistema não saberá qual arquivo usar!")
    
    # 4. Campanhas com ERRO
    if campanhas_erro:
        print("\n❌ CAMPANHAS QUE NÃO ENCONTRARIAM ARQUIVO (ERRO)")
        print("=" * 100)
        for campanha in campanhas_erro:
            print(f"  ❌ {campanha}")
            
            # Tentar sugerir arquivos similares
            sugestoes = []
            nome_norm = normalizar_nome(campanha)
            for arquivo, nome_arquivo in arquivos_disponiveis.items():
                sim = calcular_similaridade(nome_norm, normalizar_nome(nome_arquivo))
                if sim >= 0.3:  # Pelo menos 30% similar
                    sugestoes.append((arquivo, nome_arquivo, sim))
            
            if sugestoes:
                sugestoes.sort(key=lambda x: x[2], reverse=True)
                print(f"     💡 Possíveis arquivos similares:")
                for arquivo, nome, sim in sugestoes[:3]:  # Top 3
                    sim_pct = int(sim * 100)
                    print(f"        [{sim_pct:2d}%] {arquivo}")
            else:
                print(f"     ⚠️  Nenhum arquivo similar encontrado!")
    
    # Resumo final
    print("\n" + "=" * 100)
    print("📊 RESUMO FINAL")
    print("=" * 100)
    print(f"""
  Total de campanhas analisadas: {len(CAMPANHAS_3C_PLUS)}
  
  ✅ OK (encontrou arquivo):           {ok_count:2d} ({ok_count*100//len(CAMPANHAS_3C_PLUS):2d}%)
  ⚠️  Parcial (correspondência ~):     {parcial_count:2d} ({parcial_count*100//len(CAMPANHAS_3C_PLUS):2d}%)
  ⚠️  Ambiguidade (múltiplos arquivos): {ambiguidade_count:2d} ({ambiguidade_count*100//len(CAMPANHAS_3C_PLUS):2d}%)
  ❌ ERRO (não encontrou):             {erro_count:2d} ({erro_count*100//len(CAMPANHAS_3C_PLUS):2d}%)
  """)
    
    if erro_count > 0 or ambiguidade_count > 0:
        print("⚠️  ATENÇÃO: Algumas campanhas terão problemas na exportação!")
        print("\nAções necessárias:")
        if erro_count > 0:
            print(f"  • Criar ou renomear {erro_count} arquivo(s) de mailing")
        if ambiguidade_count > 0:
            print(f"  • Resolver {ambiguidade_count} ambiguidade(s) de nomenclatura")
    else:
        print("✅ Todas as campanhas conseguiriam encontrar seus arquivos!")
    
    print("\n" + "=" * 100)

if __name__ == "__main__":
    analisar_campanhas()
