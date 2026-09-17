import streamlit as st
import pandas as pd
import os
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(
    page_title="Dashboard Operacional",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilos CSS Customizados Premium (Modo Escuro)
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    /* Fundo principal e barra lateral */
    .stApp {
        background-color: #0b1120;
    }
    [data-testid="stSidebar"] {
        background-color: #0f172a;
    }
    [data-testid="stSidebar"] * {
        color: #cbd5e1;
    }
    
    /* Textos em geral */
    .stMarkdown p, .stMarkdown span {
        color: #cbd5e1 !important;
    }
    
    /* Títulos */
    h1 {
        color: #f8fafc !important;
        font-weight: 800 !important;
    }
    h2, h3 {
        color: #e2e8f0 !important;
        font-weight: 600 !important;
    }
    
    /* Cards de Métricas */
    div[data-testid="metric-container"] {
        background-color: #1e293b;
        border-radius: 15px;
        padding: 20px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.4), 0 2px 4px -1px rgba(0, 0, 0, 0.2);
        border: 1px solid #334155;
        transition: transform 0.2s ease-in-out;
    }
    div[data-testid="metric-container"]:hover {
        transform: translateY(-5px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.6), 0 4px 6px -2px rgba(0, 0, 0, 0.4);
    }
    
    /* Estilo dos rótulos das métricas */
    div[data-testid="metric-container"] > div {
        color: #94a3b8;
        font-weight: 600;
        font-size: 1.1rem;
    }
    /* Estilo dos valores numéricos */
    div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
        color: #f1f5f9;
        font-weight: 800;
        font-size: 2.2rem;
    }
    
    /* Checkbox/Multiselect styling pra fundo escuro (Streamlit lida razoavelmente com o tema) */
    </style>
""", unsafe_allow_html=True)

col_logo, col_title = st.columns([1, 6])
with col_logo:
    caminho_logo = r"c:\bots\logo.png"
    if os.path.exists(caminho_logo):
        st.image(caminho_logo, width=120)
with col_title:
    st.title("Painel Operacional: Visão de Aging 🚀")
    st.markdown("Acompanhamento interativo do status de entregas e latência.")

# ==========================================
# DADOS
# ==========================================
caminho = r"c:\bots\latencia_consolidada.xlsx"
if not os.path.exists(caminho):
    st.error(f"Arquivo não encontrado: {caminho}")
    st.stop()

@st.cache_data(ttl=60)
def load_data():
    df = pd.read_excel(caminho)
    if 'aging' in df.columns:
        df['aging'] = pd.to_numeric(df['aging'], errors='coerce').fillna(0).astype(int)
    # Preencher vazios para não quebrar gráficos de hierarquia
    df.fillna({'Last scan type': 'Sem Status', 'Destination City': 'Não Informada', 'Driver Name': 'Não Informado'}, inplace=True)
    return df

with st.spinner('Analisando dados...'):
    df_bruto = load_data()

if df_bruto.empty:
    st.warning("O arquivo está vazio.")
    st.stop()

colunas_necessarias = ['Last scan type', 'Destination City', 'Driver Name', 'aging']
for col in colunas_necessarias:
    if col not in df_bruto.columns:
        st.error(f"Coluna ausente no arquivo: {col}")
        st.stop()

# ==========================================
# FILTROS
# ==========================================
st.sidebar.markdown("## 🔍 Filtros Inteligentes")
bases = df_bruto['Base'].dropna().unique().tolist() if 'Base' in df_bruto.columns else []
filtro_base = st.sidebar.multiselect("Bases Operacionais", options=bases, default=bases)

status_list = df_bruto['Last scan type'].dropna().unique().tolist()
filtro_status = st.sidebar.multiselect("Status do Pacote", options=status_list, default=status_list)

df_filtrado = df_bruto.copy()
if filtro_base:
    df_filtrado = df_filtrado[df_filtrado['Base'].isin(filtro_base)]
if filtro_status:
    df_filtrado = df_filtrado[df_filtrado['Last scan type'].isin(filtro_status)]

# Se a coluna 'Waybill No' não existir, cria uma dummy para contagem
col_count = 'Waybill No' if 'Waybill No' in df_filtrado.columns else df_filtrado.columns[0]

# ==========================================
# KPIs PREMIUM
# ==========================================
st.markdown("<br>", unsafe_allow_html=True)
total_geral = len(df_filtrado)
total_aging = df_filtrado[df_filtrado['aging'] >= 1].shape[0]
aging_max = df_filtrado['aging'].max() if total_geral > 0 else 0

c1, c2, c3, c4 = st.columns(4)
c1.metric("📦 Volume Total", f"{total_geral:,}".replace(',', '.'))
c2.metric("✅ No Prazo (Aging 0)", f"{total_geral - total_aging:,}".replace(',', '.'))
c3.metric("⚠️ Em Atraso (Aging ≥ 1)", f"{total_aging:,}".replace(',', '.'))
c4.metric("🔥 Aging Máximo", f"{int(aging_max)} dias")

st.markdown("<hr style='border:1px solid #334155'>", unsafe_allow_html=True)

# ==========================================
# GRÁFICOS INTERATIVOS (PLOTLY)
# ==========================================

# 1. Distribuição de Aging Geral
st.subheader("📊 Distribuição de Aging por Status")
df_aging_dist = df_filtrado.groupby(['aging', 'Last scan type'])[col_count].count().reset_index()
df_aging_dist.rename(columns={col_count: 'Volume'}, inplace=True)

fig1 = px.bar(
    df_aging_dist, 
    x='aging', 
    y='Volume', 
    color='Last scan type',
    text_auto=True,
    labels={'aging': 'Dias de Aging (0 = No prazo)', 'Volume': 'Quantidade de Pacotes'},
    color_discrete_sequence=px.colors.qualitative.Plotly
)
fig1.update_layout(
    template="plotly_dark",
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(tickmode='linear', tick0=0, dtick=1),
    font=dict(family="Inter", size=14, color="#cbd5e1"),
    margin=dict(t=20, l=20, r=20, b=20),
    legend_title_text="Status"
)
st.plotly_chart(fig1, use_container_width=True)

# Layout em duas colunas para gráficos menores
col_chart1, col_chart2 = st.columns(2)

with col_chart1:
    st.subheader("📍 Volume por Cidade")
    df_cidade = df_filtrado['Destination City'].value_counts().reset_index()
    df_cidade.columns = ['Cidade', 'Volume']
    fig2 = px.pie(
        df_cidade.head(10), 
        names='Cidade', 
        values='Volume',
        hole=0.4,
        color_discrete_sequence=px.colors.sequential.Teal
    )
    fig2.update_traces(textposition='inside', textinfo='percent+label')
    fig2.update_layout(
        template="plotly_dark",
        plot_bgcolor="rgba(0,0,0,0)", 
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=20, b=20, l=20, r=20),
        showlegend=False,
        font=dict(color="#cbd5e1")
    )
    st.plotly_chart(fig2, use_container_width=True)

with col_chart2:
    st.subheader("⚠️ Top 10 Motoristas (Pacotes em Atraso)")
    # Filtrar apenas quem tem aging > 0
    df_atraso = df_filtrado[df_filtrado['aging'] >= 1]
    if not df_atraso.empty:
        df_motoristas = df_atraso.groupby('Driver Name')[col_count].count().reset_index()
        df_motoristas.columns = ['Motorista', 'Volume em Atraso']
        df_motoristas = df_motoristas.sort_values(by='Volume em Atraso', ascending=True).tail(10)
        
        fig3 = px.bar(
            df_motoristas, 
            x='Volume em Atraso', 
            y='Motorista', 
            orientation='h',
            text='Volume em Atraso',
            color='Volume em Atraso',
            color_continuous_scale="Reds"
        )
        fig3.update_layout(
            template="plotly_dark",
            plot_bgcolor="rgba(0,0,0,0)", 
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=20, b=20, l=20, r=20),
            coloraxis_showscale=False,
            font=dict(family="Inter", size=13, color="#cbd5e1")
        )
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.success("🎉 Nenhum motorista com pacotes em atraso (Aging ≥ 1)!")

# ==========================================
# MAPA DE ÁRVORE (TREEMAP HIERÁRQUICO)
# ==========================================
st.markdown("<br>", unsafe_allow_html=True)
st.subheader("🗺️ Visão Hierárquica: Status > Cidade > Motorista")
st.markdown("Navegue clicando nos blocos para aprofundar na hierarquia que você usava na planilha.")

# Prepara dados para Treemap
df_tree = df_filtrado.groupby(['Last scan type', 'Destination City', 'Driver Name'])[col_count].count().reset_index()
df_tree.columns = ['Status', 'Cidade', 'Motorista', 'Volume']
# Adiciona uma raiz constante
df_tree['Total'] = 'Porto Guimarães Express'

fig_tree = px.treemap(
    df_tree, 
    path=['Total', 'Status', 'Cidade', 'Motorista'], 
    values='Volume',
    color='Volume',
    color_continuous_scale='Blues',
)
fig_tree.update_traces(root_color="#1e293b")
fig_tree.update_layout(
    template="plotly_dark",
    margin=dict(t=20, l=20, r=20, b=20),
    font=dict(family="Inter", size=14, color="#cbd5e1"),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)"
)
st.plotly_chart(fig_tree, use_container_width=True)

# Opcional: Dados Brutos ocultos caso precisem consultar a tabela
with st.expander("Ver dados detalhados (estilo Planilha)"):
    st.dataframe(df_filtrado, use_container_width=True)

