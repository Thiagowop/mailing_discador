# Pasta de Testes

Arquivos utilitários para teste e validação do sistema de mapeamento de campanhas.

## 📋 Arquivos

### `analise_campanhas.py`
Analisa se as 27 campanhas do 3C Plus conseguiriam encontrar seus arquivos de mailing locais correspondentes.

**Uso:**
```bash
python testes/analise_campanhas.py
```

**Funcionalidades:**
- Verifica correspondência entre nomes de campanhas e arquivos
- Identifica ambiguidades (múltiplos arquivos para mesma campanha)
- Detecta campanhas sem arquivo correspondente
- Sugere possíveis matches por similaridade

---

### `testar_mapeamento.py`
Testa o mapeamento configurado em `src/config_mailing.py`.

**Uso:**
```bash
python testes/testar_mapeamento.py
```

**Funcionalidades:**
- Valida se cada campanha mapeada encontra seu arquivo
- Usa o número do mailing para busca precisa
- Gera relatório de sucesso/falha

---

### `mapear_campanhas_faltantes.py`
Lista todas as campanhas disponíveis nos arquivos locais e identifica quais ainda não foram mapeadas.

**Uso:**
```bash
python testes/mapear_campanhas_faltantes.py
```

**Funcionalidades:**
- Lista arquivos de mailing disponíveis
- Compara com campanhas já mapeadas
- Gera código pronto para copiar no config_mailing.py

---

### `listar_campanhas_3cplus.py`
Conecta ao 3C Plus e lista todas as campanhas e suas listas de mailing.

**Uso:**
```bash
python testes/listar_campanhas_3cplus.py > testes/resultado_3cplus.txt
```

**Funcionalidades:**
- Autentica no 3C Plus
- Lista campanhas ativas
- Mostra listas existentes em cada campanha
- Salva resultado em arquivo de texto

---

### `resultado_3cplus.txt`
Resultado da última execução do `listar_campanhas_3cplus.py`.

---

## 🎯 Fluxo de uso típico

1. **Verificar campanhas no 3C Plus:**
   ```bash
   python testes/listar_campanhas_3cplus.py > testes/resultado_3cplus.txt
   ```

2. **Identificar campanhas sem mapeamento:**
   ```bash
   python testes/mapear_campanhas_faltantes.py
   ```

3. **Adicionar mapeamento em `src/config_mailing.py`**

4. **Validar mapeamento:**
   ```bash
   python testes/testar_mapeamento.py
   ```

5. **Análise detalhada (se necessário):**
   ```bash
   python testes/analise_campanhas.py
   ```
