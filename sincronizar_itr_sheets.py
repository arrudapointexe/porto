import os
import sys
import json
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

NOME_PLANILHA_MESTRE = "acareaBase"
NOME_ABA_ITR = "ITR_Expedicao"

def obter_credenciais_sheets():
    """Obtém credenciais da conta de serviço Google (arquivo local ou secrets)."""
    caminho_cred = os.path.join(os.path.dirname(__file__), "credenciais.json")
    if os.path.exists(caminho_cred):
        with open(caminho_cred, encoding="utf-8") as f:
            info = json.load(f)
    else:
        try:
            import streamlit as st
            info = json.loads(st.secrets["chave_google"].strip())
        except Exception as e:
            raise RuntimeError(f"Credenciais Google não encontradas: {e}")

    escopo = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    return Credentials.from_service_account_info(info, scopes=escopo)


def sincronizar_itr_para_sheets(caminho_excel=None, df_fornecido=None):
    """
    Filtra os pacotes da base ITR e faz upload direto para a aba 'ITR_Expedicao'
    dentro da planilha mestre 'acareaBase' no Google Sheets.
    """
    try:
        # 1. Obter dados
        if df_fornecido is not None and not df_fornecido.empty:
            df = df_fornecido.copy()
        else:
            if not caminho_excel:
                caminho_excel = os.path.join(os.path.dirname(__file__), "latencia_consolidada.xlsx")
            if not os.path.exists(caminho_excel):
                print(f"WARN: Arquivo '{caminho_excel}' não encontrado para sincronização.")
                return False, "Arquivo não encontrado"
            df = pd.read_excel(caminho_excel)

        if df.empty or 'Base' not in df.columns:
            print("WARN: Planilha de latência vazia ou sem coluna 'Base'.")
            return False, "Planilha vazia ou sem coluna Base"

        # 2. Filtrar estritamente base ITR
        df_itr = df[df['Base'].astype(str).str.strip().str.upper() == 'ITR'].copy()
        total_itr = len(df_itr)
        
        if total_itr == 0:
            print("INFO: Nenhum pacote da base ITR para sincronizar.")
            return True, "Zero pacotes ITR"

        # 3. Adicionar carimbo de data/hora da sincronização
        agora_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        df_itr['Atualizado_Em'] = agora_str

        # 4. Limpar valores para envio seguro ao Google Sheets (strings e vazios)
        df_itr_envio = df_itr.fillna('')
        for col in df_itr_envio.columns:
            df_itr_envio[col] = df_itr_envio[col].astype(str).str.strip()

        cabecalho = df_itr_envio.columns.tolist()
        valores = df_itr_envio.values.tolist()
        dados_completos = [cabecalho] + valores

        # 5. Conectar ao Google Sheets
        creds = obter_credenciais_sheets()
        cliente = gspread.authorize(creds)
        planilha_mestre = cliente.open(NOME_PLANILHA_MESTRE)

        # 6. Obter ou criar a aba ITR_Expedicao
        try:
            ws = planilha_mestre.worksheet(NOME_ABA_ITR)
        except gspread.exceptions.WorksheetNotFound:
            ws = planilha_mestre.add_worksheet(
                title=NOME_ABA_ITR,
                rows=max(1000, len(dados_completos) + 100),
                cols=len(cabecalho) + 5
            )
            print(f"INFO: Aba '{NOME_ABA_ITR}' criada com sucesso na planilha '{NOME_PLANILHA_MESTRE}'.")

        # 7. Atualizar os dados
        ws.clear()
        ws.update(range_name='A1', values=dados_completos, value_input_option='USER_ENTERED')
        
        msg_sucesso = f"✅ Sincronizados {total_itr} pacotes ITR para '{NOME_PLANILHA_MESTRE} > {NOME_ABA_ITR}' ({agora_str})"
        print(msg_sucesso)
        return True, msg_sucesso

    except Exception as e:
        msg_erro = f"❌ Falha ao sincronizar ITR para o Google Sheets: {e}"
        print(msg_erro)
        return False, msg_erro


if __name__ == "__main__":
    print("Iniciando sincronização manual de ITR para Google Sheets...")
    sucesso, msg = sincronizar_itr_para_sheets()
    print(msg)
