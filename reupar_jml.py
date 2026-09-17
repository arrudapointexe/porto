import pandas as pd
import gspread
import sync_time_patch
from google_utils import get_gspread_client
import os
from dotenv import load_dotenv

load_dotenv()
NOME_PLANILHA = os.getenv("NOME_PLANILHA", "acareaBase")

def normalizar_codigo(codigo):
    return str(codigo or "").strip().replace(" ", "")

def reupar_dados(sigla):
    print(f"Re-upando {sigla}...")
    caminho_excel = f"Arquivos_{sigla}/dados_acareacoes_{sigla}.xlsx"
    if not os.path.exists(caminho_excel):
        print(f"Arquivo não encontrado: {caminho_excel}")
        return

    df_local = pd.read_excel(caminho_excel)
    dados_para_nuvem = [df_local.columns.values.tolist()] + df_local.fillna("").values.tolist()
    
    cliente = get_gspread_client()
    planilha_mestre = cliente.open(NOME_PLANILHA)
    
    try:
        planilha = planilha_mestre.worksheet(sigla)
    except gspread.exceptions.WorksheetNotFound:
        planilha = planilha_mestre.add_worksheet(title=sigla, rows="1000", cols="20")
    
    linhas_existentes = planilha.get_all_values()
    
    if not linhas_existentes:
        planilha.update('A1', dados_para_nuvem)
        print("Planilha estava vazia. Inserido tudo.")
    else:
        # Pegar os AWBs existentes
        awbs_existentes = set()
        for row in linhas_existentes[1:]:
            if row and str(row[0]).strip():
                awbs_existentes.add(normalizar_codigo(row[0]))
                
        linhas_finais = list(linhas_existentes)
        inseridos = 0
        for row in dados_para_nuvem[1:]:
            if not row: continue
            awb = normalizar_codigo(row[0])
            if awb and awb not in awbs_existentes:
                linhas_finais.append(row)
                awbs_existentes.add(awb)
                inseridos += 1
                
        if inseridos > 0:
            planilha.clear()
            planilha.update('A1', linhas_finais)
            print(f"Adicionados {inseridos} novos registros na aba {sigla}.")
        else:
            print(f"Nenhum registro novo para adicionar na aba {sigla}.")
            
    print("Sucesso!")

if __name__ == "__main__":
    reupar_dados("JML")
