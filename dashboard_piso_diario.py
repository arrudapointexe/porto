import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime

# ==========================================
# CONFIGURAÇÃO DA PÁGINA E TEMA
# ==========================================
st.set_page_config(
    page_title="Dashboard - Piso do Dia",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
    /* Estilo premium com dark mode suave e cores vibrantes */
    .stApp {
        background-color: #0f172a;
        color: #f8fafc;
        font-family: 'Inter', sans-serif;
    }
    h1, h2, h3 {
        color: #f8fafc !important;
        font-weight: 600;
    }
    .stMetric {
        background: linear-gradient(145deg, #1e293b, #0f172a);
        padding: 20px;
        border-radius: 16px;
        box-shadow: 4px 4px 10px rgba(0,0,0,0.3), -4px -4px 10px rgba(255,255,255,0.05);
        border: 1px solid #334155;
        transition: transform 0.2s ease;
    }
    .stMetric:hover {
        transform: translateY(-5px);
    }
    div[data-testid="stMetricValue"] {
        color: #38bdf8 !important;
        font-size: 2.5rem !important;
        font-weight: 700;
    }
    div[data-testid="stMetricLabel"] {
        color: #94a3b8 !important;
        font-size: 1.1rem !important;
        font-weight: 500;
    }
    /* Estilo das abas */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: transparent;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #1e293b;
        border-radius: 8px 8px 0 0;
        color: #94a3b8;
        padding: 10px 20px;
        border: none;
    }
    .stTabs [aria-selected="true"] {
        background-color: #38bdf8 !important;
        color: #0f172a !important;
        font-weight: 600;
    }
    /* Dataframes */
    [data-testid="stDataFrame"] {
        background-color: #1e293b;
        border-radius: 12px;
        padding: 10px;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# FUNÇÕES DE DADOS
# ==========================================
def carregar_dados_shopee():
    try:
        conn = sqlite3.connect("c:/bots/piso.db")
        df = pd.read_sql_query("SELECT * FROM piso_shopee", conn)
        conn.close()
        return df
    except Exception as e:
        return pd.DataFrame()

def carregar_dados_imile():
    caminho = "c:/bots/latencia_consolidada.xlsx"
    if not os.path.exists(caminho):
        return pd.DataFrame()
    try:
        df = pd.read_excel(caminho)
        return df
    except Exception as e:
        return pd.DataFrame()

# ==========================================
# COMPONENTE DE ATUALIZAÇÃO AUTOMÁTICA
# ==========================================
@st.fragment(run_every="30s")
def renderizar_dashboard():
    hoje_str = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    st.markdown(f"<p style='text-align: right; color: #94a3b8; font-size: 0.9rem;'>Última atualização: {hoje_str} (Auto-refresh a cada 30s)</p>", unsafe_allow_html=True)

    # Carrega os dados
    df_shopee = carregar_dados_shopee()
    df_imile = carregar_dados_imile()

    # ==========================================
    # FILTROS DA IMILE
    # ==========================================
    st.sidebar.header("🔍 Filtros iMile")
    if not df_imile.empty:
        bases = df_imile['Base'].dropna().unique().tolist() if 'Base' in df_imile.columns else []
        filtro_base = st.sidebar.multiselect("Base", options=bases, default=bases, key="imile_base")
        
        status_list = df_imile['Last scan type'].dropna().unique().tolist() if 'Last scan type' in df_imile.columns else []
        filtro_status = st.sidebar.multiselect("Status", options=status_list, default=status_list, key="imile_status")
        
        cidades = sorted(df_imile['Destination City'].dropna().unique().tolist()) if 'Destination City' in df_imile.columns else []
        filtro_cidade = st.sidebar.multiselect("Cidade de Destino", options=cidades, key="imile_cidade")

        if filtro_base:
            df_imile = df_imile[df_imile['Base'].isin(filtro_base)]
        if filtro_status:
            df_imile = df_imile[df_imile['Last scan type'].isin(filtro_status)]
        if filtro_cidade:
            df_imile = df_imile[df_imile['Destination City'].isin(filtro_cidade)]

    # Prepara as métricas
    total_shopee = len(df_shopee) if not df_shopee.empty else 0
    
    # Para iMile, vamos contar o volume total do arquivo como o backlog (Piso).
    total_imile = len(df_imile) if not df_imile.empty else 0
    
    # Filtro opcional: "Recebidos Hoje" para iMile
    imile_recebidos_hoje = 0
    if not df_imile.empty and 'Receive Date' in df_imile.columns:
        df_imile['Receive Date'] = pd.to_datetime(df_imile['Receive Date'], errors='coerce')
        hoje = pd.Timestamp.now().normalize()
        imile_recebidos_hoje = len(df_imile[df_imile['Receive Date'].dt.normalize() == hoje])

    # Seção de KPIs Principais
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("📦 Piso Shopee (Total)", f"{total_shopee:,}".replace(',', '.'))
    
    with col2:
        st.metric("🚚 Piso iMile (Total Backlog)", f"{total_imile:,}".replace(',', '.'))

    with col3:
        st.metric("📥 iMile Recebidos Hoje", f"{imile_recebidos_hoje:,}".replace(',', '.'))

    st.markdown("---")

    # Layout de duas colunas para detalhes
    col_shopee, col_imile = st.columns(2)

    with col_shopee:
        st.subheader("🟧 Shopee - Detalhes do Piso")
        if not df_shopee.empty:
            # Agrupar por cidade
            if 'cidade' in df_shopee.columns:
                df_shopee_cidade = df_shopee['cidade'].value_counts().reset_index()
                df_shopee_cidade.columns = ['Cidade', 'Quantidade']
                st.dataframe(df_shopee_cidade, use_container_width=True, hide_index=True)
            
            st.markdown("Amostra dos pacotes (Shopee):")
            st.dataframe(df_shopee.head(10), use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum dado encontrado no banco de dados da Shopee para o piso atual.")

    with col_imile:
        st.subheader("🟩 iMile - Detalhes do Piso")
        if not df_imile.empty:
            # Agrupar por status ou cidade
            tab_cidade, tab_status = st.tabs(["Por Cidade", "Por Status"])
            
            with tab_cidade:
                if 'Destination City' in df_imile.columns:
                    df_imile_cidade = df_imile['Destination City'].value_counts().reset_index()
                    df_imile_cidade.columns = ['Cidade de Destino', 'Quantidade']
                    st.dataframe(df_imile_cidade.head(15), use_container_width=True, hide_index=True)
                else:
                    st.write("Coluna de cidade não encontrada.")
                    
            with tab_status:
                if 'Last scan type' in df_imile.columns:
                    df_imile_status = df_imile['Last scan type'].value_counts().reset_index()
                    df_imile_status.columns = ['Status', 'Quantidade']
                    st.dataframe(df_imile_status, use_container_width=True, hide_index=True)
                else:
                    st.write("Coluna de status não encontrada.")
            
            st.markdown("Amostra dos pacotes (iMile):")
            st.dataframe(df_imile.head(10), use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum dado encontrado no arquivo consolidado da iMile.")

# ==========================================
# MAIN APP
# ==========================================
def main():
    col1, col2 = st.columns([1, 5])
    with col1:
        st.markdown("<h1 style='text-align: center; font-size: 3rem;'>🎯</h1>", unsafe_allow_html=True)
    with col2:
        st.title("Painel de Pista Diário")
        st.markdown("<h4 style='color: #94a3b8;'>Acompanhamento em tempo real do piso das operações</h4>", unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)

    # Renderiza o componente que se atualiza sozinho
    renderizar_dashboard()

if __name__ == "__main__":
    main()
