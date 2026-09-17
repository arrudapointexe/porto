import streamlit as st
import pandas as pd
import os

# ==========================================
# CONFIGURAÇÃO DE PÁGINA E TEMA
# ==========================================
st.set_page_config(
    page_title="Porto Guimarães Express - Dashboard",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilização CSS para as cores da empresa
st.markdown("""
    <style>
    /* Fundo da barra lateral */
    [data-testid="stSidebar"] {
        background-color: #031c3c;
    }
    /* Textos na barra lateral */
    [data-testid="stSidebar"] * {
        color: #f0f2f6;
    }
    /* Títulos principais */
    h1, h2, h3 {
        color: #031c3c !important;
    }
    /* Valores de métricas (KPIs) */
    div[data-testid="stMetricValue"] {
        color: #d32f2f;
    }
    /* Fundo da página */
    .stApp {
        background-color: #f8f9fa;
    }
    /* Ajuste de tabelas */
    .dataframe {
        font-size: 14px !important;
    }
    </style>
""", unsafe_allow_html=True)


# ==========================================
# FUNÇÕES DE DADOS
# ==========================================
@st.cache_data(ttl=600)
def carregar_dados():
    caminho = r"c:\bots\latencia_consolidada.xlsx"
    if not os.path.exists(caminho):
        return None
    try:
        # Carrega a planilha (pode levar alguns segundos se for muito grande)
        df = pd.read_excel(caminho)
        # Limpar e converter colunas conforme necessário
        if 'aging' in df.columns:
            df['aging'] = pd.to_numeric(df['aging'], errors='coerce').fillna(0)
        return df
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        return None

# ==========================================
# INTERFACE PRINCIPAL
# ==========================================
def main():
    # Header com Título (Logo opcional se estiver na mesma pasta)
    col1, col2 = st.columns([1, 4])
    with col1:
        # Tenta exibir a logo que o usuário enviou, buscando nomes comuns na pasta
        caminho_logo = r"c:\bots\logo.png"
        if os.path.exists(caminho_logo):
            st.image(caminho_logo, width=150)
        else:
            caminho_logo_jpg = r"c:\bots\logo.jpg"
            if os.path.exists(caminho_logo_jpg):
                st.image(caminho_logo_jpg, width=150)
            else:
                caminho_logo_jpeg = r"c:\bots\logo.jpeg"
                if os.path.exists(caminho_logo_jpeg):
                    st.image(caminho_logo_jpeg, width=150)
            
    with col2:
        st.title("Painel de Controle Operacional")
        st.markdown("**Porto Guimarães Express**")

    # Carregamento dos dados
    df_bruto = carregar_dados()
    if df_bruto is None or df_bruto.empty:
        st.warning("Arquivo 'latencia_consolidada.xlsx' não encontrado ou vazio. Aguardando dados...")
        return

    # ==========================================
    # BARRA LATERAL (FILTROS)
    # ==========================================
    st.sidebar.header("🔍 Filtros")

    # Tratamento para não quebrar caso as colunas estejam faltando
    colunas_disponiveis = df_bruto.columns.tolist()

    # Filtro de Base
    bases = df_bruto['Base'].dropna().unique().tolist() if 'Base' in colunas_disponiveis else []
    filtro_base = st.sidebar.multiselect("Base", options=bases, default=bases)

    # Filtro de Last Scan Type
    scan_types = df_bruto['Last scan type'].dropna().unique().tolist() if 'Last scan type' in colunas_disponiveis else []
    filtro_scan = st.sidebar.multiselect("Último Status", options=scan_types, default=scan_types)

    # Filtro de Cidade
    cidades = sorted(df_bruto['Destination City'].dropna().unique().tolist()) if 'Destination City' in colunas_disponiveis else []
    filtro_cidade = st.sidebar.multiselect("Cidade de Destino", options=cidades)

    # APLICAÇÃO DOS FILTROS
    df_filtrado = df_bruto.copy()
    if filtro_base:
        df_filtrado = df_filtrado[df_filtrado['Base'].isin(filtro_base)]
    if filtro_scan:
        df_filtrado = df_filtrado[df_filtrado['Last scan type'].isin(filtro_scan)]
    if filtro_cidade:
        df_filtrado = df_filtrado[df_filtrado['Destination City'].isin(filtro_cidade)]

    # ==========================================
    # KPIs (INDICADORES GERAIS)
    # ==========================================
    total_pacotes = len(df_filtrado)
    
    # Exemplo: Considerando atrasado se aging >= 1 (Isso pode ser configurável depois)
    total_aging = df_filtrado[df_filtrado['aging'] >= 1].shape[0] if 'aging' in df_filtrado.columns else 0
    
    # Total em rota
    total_em_rota = df_filtrado[df_filtrado['Last scan type'].astype(str).str.upper().str.contains("EM ROTA DE ENTREGA")].shape[0] if 'Last scan type' in df_filtrado.columns else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("📦 Total de Pacotes", f"{total_pacotes:,}".replace(',','.'))
    col2.metric("⚠️ Pacotes com Aging (≥1 dia)", f"{total_aging:,}".replace(',','.'))
    col3.metric("🚚 Em Rota de Entrega", f"{total_em_rota:,}".replace(',','.'))

    st.markdown("---")

    # ==========================================
    # ABAS (TABS)
    # ==========================================
    tab1, tab2 = st.tabs(["📊 Latência Geral", "📈 Aging Geral"])

    with tab1:
        st.subheader("Visão de Latência")
        st.write("Volume de pacotes por Status vs Backlog Time")
        
        if 'Last scan type' in df_filtrado.columns and 'Backlog time(Station)' in df_filtrado.columns:
            # Tabela dinâmica
            pivot_latencia = pd.pivot_table(
                df_filtrado, 
                values='Waybill No' if 'Waybill No' in df_filtrado.columns else df_filtrado.columns[0], 
                index='Last scan type', 
                columns='Backlog time(Station)', 
                aggfunc='count',
                margins=True, 
                margins_name="Total Geral"
            ).fillna(0)
            
            # Remove a linha Total Geral da pivotagem pura para criar highlight se necessário
            st.dataframe(pivot_latencia.style.format("{:.0f}").background_gradient(cmap='Blues', axis=1), use_container_width=True)
            
            # Gráfico
            st.write("### Volume por Status (Geral)")
            dist_status = df_filtrado['Last scan type'].value_counts()
            st.bar_chart(dist_status)
        else:
            st.warning("Colunas 'Last scan type' ou 'Backlog time(Station)' não encontradas.")

    with tab2:
        st.subheader("Visão de Aging")
        st.write("Volume de pacotes por Status e Cidade vs Aging")
        
        if 'Last scan type' in df_filtrado.columns and 'Destination City' in df_filtrado.columns and 'aging' in df_filtrado.columns and 'Driver Name' in df_filtrado.columns:
            # Tabela dinâmica
            pivot_aging = pd.pivot_table(
                df_filtrado, 
                values='Waybill No' if 'Waybill No' in df_filtrado.columns else df_filtrado.columns[0], 
                index=['Last scan type', 'Destination City', 'Driver Name'], 
                columns='aging', 
                aggfunc='count',
                margins=True, 
                margins_name="Total Geral"
            ).fillna(0)

            st.dataframe(pivot_aging.style.format("{:.0f}").background_gradient(cmap='Reds', axis=1), use_container_width=True)
            
            # Gráfico de Aging
            st.write("### Volume por Dia de Aging")
            dist_aging = df_filtrado['aging'].value_counts().sort_index()
            st.bar_chart(dist_aging)
        else:
            st.warning("Colunas de Status, Cidade ou Aging não encontradas.")

if __name__ == "__main__":
    main()
