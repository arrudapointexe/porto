import pandas as pd
import numpy as np
import os
from playwright.sync_api import sync_playwright
import unicodedata
from config import ITR_LOC_CITIES, ITR_INT_CITIES, JML_LOC_CITIES, JML_INT_CITIES, SNB_LOC_CITIES, SNB_INT_CITIES

TODAS_CIDADES = ITR_LOC_CITIES + ITR_INT_CITIES + JML_LOC_CITIES + JML_INT_CITIES + SNB_LOC_CITIES + SNB_INT_CITIES

def unvowel(t):
    if pd.isna(t): return ""
    t = str(t).upper().replace('\ufffd', '')
    for v in 'AEIOUÁÉÍÓÚÀÈÌÒÙÂÊÎÔÛÃÕÄËÏÖÜ':
        t = t.replace(v, '')
    return ''.join(c for c in t if c.isalnum())

MAPA_CIDADES = {unvowel(c): c for c in TODAS_CIDADES}

def normalizar_cidade(texto):
    if pd.isna(texto): return ""
    k = unvowel(texto)
    return MAPA_CIDADES.get(k, str(texto).strip().upper())

def gerar_tabela_html(df, titulo="AGING GERAL IMILE"):
    # Filtra e agrupa dados
    if df.empty:
        return ""
    
    # Colunas de aging disponíveis
    agings = sorted([c for c in df['aging'].dropna().unique() if isinstance(c, (int, float))])
    agings = [int(x) for x in agings if x > 0] # Filtra apenas aging > 0 se necessário, ou inclui 0? O usuário não especificou, assumimos todos ou apenas >=1? A imagem mostra 1, 2, 3.
    # vamos pegar todos os agings que existem no df
    
    html = f"""
    <div style="background-color: white; width: 600px; font-family: Calibri, sans-serif; padding: 10px;">
        <div style="background-color: #002060; color: white; padding: 10px; font-size: 20px; font-weight: bold; display: flex; align-items: center;">
            <img src="logo.png" style="height: 40px; margin-right: 15px;" onerror="this.style.display='none'"> 
            {titulo}
        </div>
        <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
            <thead>
                <tr style="background-color: #002060; color: white; text-align: right;">
                    <th style="text-align: left; padding: 5px;">STATUS/CIDADE/MOTORISTA</th>
    """
    for ag in agings:
        html += f"<th style='padding: 5px; width: 40px;'>{ag}</th>"
    html += "<th style='padding: 5px; width: 80px;'>Total Geral</th></tr></thead><tbody>"
    
    # Agrupamento
    # Para simular tabela dinâmica modo compacto
    grouped = df.groupby(['Waybill Status', 'City', 'Driver Name', 'aging']).size().reset_index(name='count')
    
    total_geral_agings = {ag: 0 for ag in agings}
    total_geral_tudo = 0
    
    for status in df['Waybill Status'].dropna().unique():
        df_status = grouped[grouped['Waybill Status'] == status]
        if df_status.empty: continue
        
        status_tot = df_status['count'].sum()
        html += f"<tr style='background-color: #d9e1f2; font-weight: bold;'><td style='padding: 3px; padding-left: 5px;'>[-] {status}</td>"
        for ag in agings:
            val = df_status[df_status['aging'] == ag]['count'].sum()
            total_geral_agings[ag] += val
            html += f"<td style='text-align: right; padding: 3px;'>{val if val > 0 else ''}</td>"
        total_geral_tudo += status_tot
        html += f"<td style='text-align: right; padding: 3px;'>{status_tot}</td></tr>"
        
        for cidade in df_status['City'].unique():
            df_cidade = df_status[df_status['City'] == cidade]
            if df_cidade.empty: continue
            
            cidade_tot = df_cidade['count'].sum()
            html += f"<tr style='background-color: #eaeff7;'><td style='padding: 3px; padding-left: 20px; font-weight: bold;'>[-] {cidade}</td>"
            for ag in agings:
                val = df_cidade[df_cidade['aging'] == ag]['count'].sum()
                html += f"<td style='text-align: right; padding: 3px; font-weight: bold;'>{val if val > 0 else ''}</td>"
            html += f"<td style='text-align: right; padding: 3px; font-weight: bold;'>{cidade_tot}</td></tr>"
            
            for motorista in df_cidade['Driver Name'].unique():
                df_mot = df_cidade[df_cidade['Driver Name'] == motorista]
                if df_mot.empty: continue
                
                mot_tot = df_mot['count'].sum()
                html += f"<tr style='background-color: #eaeff7;'><td style='padding: 3px; padding-left: 40px;'>{motorista}</td>"
                for ag in agings:
                    val = df_mot[df_mot['aging'] == ag]['count'].sum()
                    html += f"<td style='text-align: right; padding: 3px;'>{val if val > 0 else ''}</td>"
                html += f"<td style='text-align: right; padding: 3px;'>{mot_tot}</td></tr>"
    
    # Linha Total Geral
    html += "<tr style='background-color: #002060; color: white; font-weight: bold;'><td style='padding: 5px;'>Total Geral</td>"
    for ag in agings:
        html += f"<td style='text-align: right; padding: 5px;'>{total_geral_agings[ag] if total_geral_agings[ag] > 0 else ''}</td>"
    html += f"<td style='text-align: right; padding: 5px;'>{total_geral_tudo}</td></tr>"
    
    html += "</tbody></table></div>"
    return html

TRADUCOES_STATUS = {
    "assign da": "ATRIBUÍDO",
    "assigned": "ATRIBUÍDO",
    "atribuido": "ATRIBUÍDO",
    "atribuído": "ATRIBUÍDO",
    "out for delivery": "EM ROTA",
    "em rota de entrega": "EM ROTA",
    "delivering": "EM ROTA",
    "driver inventory": "Driver Inventory",
    "arrive": "Recebido no DS",
    "arrived at delivery station": "Recebido no DS",
    "arrived at ds": "Recebido no DS",
    "receive": "Recebido",
    "received": "Recebido",
    "offloading": "Descarregado",
    "unloaded": "Descarregado",
    "back to warehouse": "Return",
    "return": "Return",
    "returned": "Return"
}

def formatar_status(st):
    st_lower = str(st).lower().strip()
    return TRADUCOES_STATUS.get(st_lower, str(st).title())

def gerar_imagens_vencimentos(caminho_excel="c:/bots/latencia_consolidada.xlsx"):
    if not os.path.exists(caminho_excel):
        return None, "Arquivo latencia_consolidada.xlsx não encontrado."
    
    df = pd.read_excel(caminho_excel)
    
    # Usa 'Last scan type' ou 'Last Scan Type' ou cai para 'Waybill Status'
    col_status = next((c for c in df.columns if 'last scan type' in c.lower()), None)
    if not col_status:
        col_status = 'Waybill Status'
        
    if 'aging' not in df.columns or col_status not in df.columns or 'Driver Name' not in df.columns:
        return None, "Colunas necessárias não encontradas na planilha."
        
    # Usa Consignee City, e se for nulo cai para Destination City
    if 'Consignee City' in df.columns and 'Destination City' in df.columns:
        df['City'] = df['Consignee City'].fillna(df['Destination City'])
    elif 'Destination City' in df.columns:
        df['City'] = df['Destination City']
    elif 'Consignee City' in df.columns:
        df['City'] = df['Consignee City']
    else:
        return None, "Nenhuma coluna de cidade encontrada."
        
    df['City'] = df['City'].apply(normalizar_cidade)
    
    # Filtra apenas os pacotes 'Not Closed' (ativos)
    if 'Type' in df.columns:
        df = df[df['Type'].astype(str).str.upper() != 'CLOSED']
    
    # Corrige a coluna aging para numérico
    df['aging'] = pd.to_numeric(df['aging'], errors='coerce')
    df = df[df['aging'] > 0] # Filtramos apenas para aging >= 1 (1, 2, 3...)
    
    df['Waybill Status'] = df[col_status].apply(formatar_status)
    
    # Grupos de cidades
    grupos = {
        "Santa Barbara, Catas Altas e Barao de Cocais": [normalizar_cidade(c) for c in SNB_LOC_CITIES + SNB_INT_CITIES],
        "Cidade D0 JML": [normalizar_cidade(c) for c in JML_LOC_CITIES],
        "Cidade D0 ITR": [normalizar_cidade(c) for c in ITR_LOC_CITIES],
        "Cidades D1 JML": [normalizar_cidade(c) for c in JML_INT_CITIES],
        "Cidades D1 ITR": [normalizar_cidade(c) for c in ITR_INT_CITIES]
    }
    
    imagens_geradas = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        for nome_grupo, lista_cidades in grupos.items():
            df_grupo = df[df['City'].isin(lista_cidades)]
            if df_grupo.empty:
                continue
                
            html = gerar_tabela_html(df_grupo, titulo=f"AGING - {nome_grupo.upper()}")
            if not html: continue
            
            full_html = f"<!DOCTYPE html><html><body style='margin:0; padding:0;'>{html}</body></html>"
            page.set_content(full_html)
            
            nome_arquivo = f"aging_{nome_grupo.replace(' ', '_').replace(',', '')}.png"
            page.locator("div").first.screenshot(path=nome_arquivo)
            imagens_geradas.append(nome_arquivo)
            
        browser.close()
        
    return imagens_geradas, "Sucesso"

if __name__ == "__main__":
    imgs, msg = gerar_imagens_vencimentos()
    print(imgs)
    print(msg)
