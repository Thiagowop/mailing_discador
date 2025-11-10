"""
Mapeamento entre campanhas do 3C Plus e números de mailing.

Os números correspondem aos IDs dos mailings nos arquivos CSV.
Formato do arquivo: "Mailing XXXXXX - NOME - YYYY-MM-DD.csv"

Exemplo:
    "RSF Judicial": 32  →  busca "Mailing 000032 - RSF Judicial - *.csv"

IMPORTANTE: Apenas campanhas que existem ativamente no 3C Plus são mapeadas aqui.
"""

MAILING_MAP = {
    # Campanhas ativas no 3C Plus (26 campanhas confirmadas)
    "Tenda": 31,
    "Cyrela - Pré Empreendimentos": 80,
    "Deva Veículos": 27,
    "Longitude": 73,
    "RSF Judicial": 32,
    "Direcional Extrajudicial": 43,
    "Direcional Judicial": 44,
    "VIC Extrajudicial": 1,  # Vic Extra
    "VIC Judicial": 2,
    "EMCCAMP Extrajudicial": 41,
    "EMCCAMP Judicial": 65,
    "Tabelionato": 78,
    "Cyrela Extrajudicial": 19,
    "Cyrela Judicial": 34,
    "Sobrosa Mello": 84,
    "Movida Extrajudicial": 5,  # Movida Extra
    "Movida Judicial": 6,
    "Foco Aluguel": 76,
    "Arbore Extrajudicial": 56,
    "Arbore Judicial": 61,
    "LCM": 85,
    "Vila Brasil Extrajudicial": 13,
    "CredAluga": 81,  # Credaluga - Ocupado
    "Jerônimo": 75,
    "Sempre Editora": 26,
    "São José": 74,
}
