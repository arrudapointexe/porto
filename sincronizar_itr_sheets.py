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
NOME_ABA_GERAL = "Expedicao_Geral"

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


def _preparar_dados_para_envio(df, agora_str):
    df_envio = df.copy()
    df_envio['Atualizado_Em'] = agora_str
    df_clean = df_envio.fillna('')
    for col in df_clean.columns:
        df_clean[col] = df_clean[col].astype(str).str.strip()
    cabecalho = df_clean.columns.tolist()
    valores = df_clean.values.tolist()
    return [cabecalho] + valores


def sincronizar_expedicao_completa(caminho_excel=None, df_fornecido=None):
    """
    Sincroniza simultaneamente:
    1. A aba 'Expedicao_Geral' (todas as bases: JML, ITR, SNB) para o monitor_expedicao.py online.
    2. A aba 'ITR_Expedicao' (apenas ITR) para o monitor_itr.py online.
    """
    try:
        if df_fornecido is not None and not df_fornecido.empty:
            df = df_fornecido.copy()
        else:
            if not caminho_excel:
                caminho_excel = os.path.join(os.path.dirname(__file__), "latencia_consolidada.xlsx")
            if not os.path.exists(caminho_excel):
                print(f"WARN: Arquivo '{caminho_excel}' não encontrado.")
                return False, "Arquivo não encontrado"
            df = pd.read_excel(caminho_excel)

        if df.empty or 'Base' not in df.columns:
            print("WARN: Planilha de latência vazia ou sem coluna 'Base'.")
            return False, "Planilha vazia ou sem coluna Base"

        agora_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        creds = obter_credenciais_sheets()
        cliente = gspread.authorize(creds)
        planilha_mestre = cliente.open(NOME_PLANILHA_MESTRE)

        # 1. Sincronizar Expedicao_Geral (Todas as Bases)
        dados_geral = _preparar_dados_para_envio(df, agora_str)
        try:
            ws_geral = planilha_mestre.worksheet(NOME_ABA_GERAL)
        except gspread.exceptions.WorksheetNotFound:
            ws_geral = planilha_mestre.add_worksheet(
                title=NOME_ABA_GERAL,
                rows=max(2000, len(dados_geral) + 100),
                cols=len(dados_geral[0]) + 5
            )
        ws_geral.clear()
        ws_geral.update(range_name='A1', values=dados_geral, value_input_option='USER_ENTERED')
        print(f"✅ Sincronizados {len(df)} pacotes para '{NOME_PLANILHA_MESTRE} > {NOME_ABA_GERAL}' ({agora_str})")

        # 2. Sincronizar ITR_Expedicao (Apenas base ITR)
        df_itr = df[df['Base'].astype(str).str.strip().str.upper() == 'ITR'].copy()
        if not df_itr.empty:
            dados_itr = _preparar_dados_para_envio(df_itr, agora_str)
            try:
                ws_itr = planilha_mestre.worksheet(NOME_ABA_ITR)
            except gspread.exceptions.WorksheetNotFound:
                ws_itr = planilha_mestre.add_worksheet(
                    title=NOME_ABA_ITR,
                    rows=max(1000, len(dados_itr) + 100),
                    cols=len(dados_itr[0]) + 5
                )
            ws_itr.clear()
            ws_itr.update(range_name='A1', values=dados_itr, value_input_option='USER_ENTERED')
            print(f"✅ Sincronizados {len(df_itr)} pacotes para '{NOME_PLANILHA_MESTRE} > {NOME_ABA_ITR}' ({agora_str})")

        return True, f"Sincronização completa realizada com sucesso às {agora_str}"

    except Exception as e:
        msg_erro = f"❌ Falha na sincronização completa: {e}"
        print(msg_erro)
        return False, msg_erro


def sincronizar_itr_para_sheets(caminho_excel=None, df_fornecido=None):
    """Mantido para compatibilidade reversa."""
    return sincronizar_expedicao_completa(caminho_excel, df_fornecido)


if __name__ == "__main__":
    print("Iniciando sincronização manual de ITR para Google Sheets...")
    sucesso, msg = sincronizar_itr_para_sheets()
    print(msg)
