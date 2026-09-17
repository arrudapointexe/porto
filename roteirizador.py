import pandas as pd
import re
import os

_cache_ceps = None

def get_base_ceps(caminho_excel=r"c:\bots\base_ceps.xlsx"):
    global _cache_ceps
    if _cache_ceps is not None:
        return _cache_ceps
    
    if not os.path.exists(caminho_excel):
        print(f"Aviso: Arquivo {caminho_excel} não encontrado.")
        return None

    try:
        # Lê a planilha, preenchendo NAs com string vazia
        df_ceps = pd.read_excel(caminho_excel, dtype=str).fillna("")
        
        # Limpa os nomes das colunas
        df_ceps.columns = df_ceps.columns.astype(str).str.strip()
        
        # Identifica as colunas (dependendo do cabeçalho que pode variar)
        col_cep = None
        col_cidade = None
        col_bairro = None
        col_entregador = None

        # Baseado no arquivo de amostra do usuário: [CEP, 'Bairro', 'Cidade', 'Entregador']
        # Pode ter cabeçalho ou não. Se tiver cabeçalho como 'CEPs', 'Responsavel', 'Bairro'...
        for col in df_ceps.columns:
            col_lower = col.lower()
            if 'cep' in col_lower:
                col_cep = col
            elif 'bairro' in col_lower:
                col_bairro = col
            elif 'cidade' in col_lower:
                col_cidade = col
            elif 'entregador' in col_lower or 'responsavel' in col_lower:
                col_entregador = col

        # Se não achou pelos nomes, tenta por índice (assumindo a ordem padrão)
        if not col_cep: col_cep = df_ceps.columns[0]
        if not col_bairro: col_bairro = df_ceps.columns[1] if len(df_ceps.columns) > 1 else None
        if not col_cidade: col_cidade = df_ceps.columns[2] if len(df_ceps.columns) > 2 else None
        if not col_entregador: col_entregador = df_ceps.columns[3] if len(df_ceps.columns) > 3 else None

        # Limpa CEP (apenas números)
        df_ceps[col_cep] = df_ceps[col_cep].astype(str).str.replace(r'\D', '', regex=True)

        # Mapeamento do "Bairro Principal" por Entregador
        # A regra será: O primeiro bairro que aparecer para aquele entregador será considerado o principal
        bairro_principal_entregador = {}
        if col_entregador and col_bairro:
            for index, row in df_ceps.iterrows():
                ent = row[col_entregador].strip()
                bairro = row[col_bairro].strip()
                if ent and ent not in bairro_principal_entregador:
                    bairro_principal_entregador[ent] = bairro

        _cache_ceps = {
            'df': df_ceps,
            'col_cep': col_cep,
            'col_bairro': col_bairro,
            'col_cidade': col_cidade,
            'col_entregador': col_entregador,
            'bairro_principal_entregador': bairro_principal_entregador
        }
        return _cache_ceps
    except Exception as e:
        print(f"Erro ao ler base de CEPs: {e}")
        return None

def obter_rota_shopee(cep):
    """Retorna o Bairro Principal (Rota) para João Monlevade, ou a Cidade para o interior."""
    cep_limpo = re.sub(r'\D', '', str(cep))
    if not cep_limpo:
        return "SEM CEP"
        
    base = get_base_ceps()
    if not base:
        return "DESCONHECIDO"
        
    df = base['df']
    
    match = df[df[base['col_cep']] == cep_limpo]
    if match.empty:
        return "OUTROS CEPS"
        
    cidade = match.iloc[0][base['col_cidade']]
    entregador = match.iloc[0][base['col_entregador']]
    
    if "Monlevade" in str(cidade):
        # Retorna o bairro principal do entregador associado a este CEP
        bairro_principal = base['bairro_principal_entregador'].get(entregador, "BAIRRO NÃO MAPEADO")
        return f"{bairro_principal} ({entregador})"
    else:
        return cidade

def obter_rota_imile(cidade, bairro_consignee):
    """
    Retorna o Bairro Principal (Rota) para João Monlevade (baseado no bairro_consignee), 
    ou a Cidade para o interior.
    """
    if "Monlevade" not in str(cidade):
        return cidade if pd.notna(cidade) else "CIDADE DESCONHECIDA"
        
    base = get_base_ceps()
    if not base or not base['col_bairro']:
        return "DESCONHECIDO"
        
    bairro_busca = str(bairro_consignee).strip().upper()
    df = base['df']
    
    # Tenta encontrar o bairro na base_ceps
    # Convertendo para upper para facilitar o match
    match = df[df[base['col_bairro']].str.upper() == bairro_busca]
    
    if match.empty:
        # Match parcial
        match = df[df[base['col_bairro']].str.upper().str.contains(bairro_busca, regex=False, na=False)]
        
    if match.empty:
        return f"ROTA DESCONHECIDA ({bairro_busca})"
        
    entregador = match.iloc[0][base['col_entregador']]
    bairro_principal = base['bairro_principal_entregador'].get(entregador, "BAIRRO NÃO MAPEADO")
    return f"{bairro_principal} ({entregador})"
