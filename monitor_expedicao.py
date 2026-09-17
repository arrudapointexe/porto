import streamlit as st
import pandas as pd
import os
import glob
import zipfile
from datetime import datetime, timedelta
import urllib.parse
import config
from scraper_contato import buscar_dados_contato_imile
import roteirizador

st.set_page_config(
    page_title="Monitor de Expedição",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Estilo Premium
st.markdown("""
    <style>
    .stApp { background-color: #0f172a; color: #f8fafc; font-family: 'Inter', sans-serif; }
    h1, h2, h3 { color: #f8fafc !important; font-weight: 600; }
    .metric-card {
        background: linear-gradient(145deg, #1e293b, #0f172a);
        padding: 20px;
        border-radius: 16px;
        box-shadow: 4px 4px 10px rgba(0,0,0,0.3), -4px -4px 10px rgba(255,255,255,0.05);
        border: 1px solid #334155;
        text-align: center;
        margin-bottom: 20px;
    }
    .metric-value { color: #38bdf8; font-size: 2.5rem; font-weight: 700; }
    .metric-label { color: #94a3b8; font-size: 1.1rem; font-weight: 500; }
    .route-header {
        background-color: #1e293b; padding: 10px 15px; border-radius: 8px;
        margin-top: 10px; font-weight: bold; color: #38bdf8;
    }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; background-color: transparent; }
    .stTabs [data-baseweb="tab"] { background-color: #1e293b; border-radius: 8px 8px 0 0; color: #94a3b8; padding: 10px 20px; border: none; }
    .stTabs [aria-selected="true"] { background-color: #38bdf8 !important; color: #0f172a !important; font-weight: 600; }
    </style>
""", unsafe_allow_html=True)

@st.cache_data(show_spinner=False)
def _carregar_dados_imile_cached(mtime):
    caminho = "c:/bots/latencia_consolidada.xlsx"
    if not os.path.exists(caminho):
        return pd.DataFrame()
    try:
        df = pd.read_excel(caminho)
        # Limpar espaços nos nomes das colunas
        df.columns = df.columns.astype(str).str.strip()
        
        # Filtrar por "Arrive" (No piso)
        if 'Last scan type' in df.columns:
            df = df[df['Last scan type'].astype(str).str.upper() == 'ARRIVE']
            
        # Filtro de Abrangência (Excluir fora de rota)
        if 'abrangencia' in df.columns and 'Destination City' in df.columns:
            cond_abrangencia = df['abrangencia'].astype(str) == '1'
            cond_sao_goncalo = df['Destination City'].astype(str).str.upper().str.contains('SÃO GONÇALO DO RIO ABAIXO', na=False)
            df = df[cond_abrangencia | cond_sao_goncalo]
            
        # Aplicar Roteirização
        if not df.empty and 'Destination City' in df.columns and 'Consignee Area' in df.columns:
            df['Rota'] = df.apply(lambda row: roteirizador.obter_rota_imile(row['Destination City'], row['Consignee Area']), axis=1)
        else:
            df['Rota'] = "DESCONHECIDO"
            
        return df
    except Exception as e:
        return None

def carregar_dados_imile():
    caminho = "c:/bots/latencia_consolidada.xlsx"
    mtime = os.path.getmtime(caminho) if os.path.exists(caminho) else 0
    df = _carregar_dados_imile_cached(mtime)
    if df is not None:
        st.session_state['last_imile_df'] = df
        return df
    return st.session_state.get('last_imile_df', pd.DataFrame())

@st.cache_data(show_spinner=False)
def _carregar_dados_imile_inventariados_cached(mtime):
    caminho = "c:/bots/latencia_consolidada.xlsx"
    if not os.path.exists(caminho):
        return pd.DataFrame()
    try:
        df = pd.read_excel(caminho)
        df.columns = df.columns.astype(str).str.strip()
        
        # Filtrar por "Inventory Scan"
        if 'Last scan type' in df.columns:
            df = df[df['Last scan type'].astype(str).str.upper() == 'INVENTORY SCAN']
            
        # Filtro de Abrangência (Excluir fora de rota)
        if 'abrangencia' in df.columns and 'Destination City' in df.columns:
            cond_abrangencia = df['abrangencia'].astype(str) == '1'
            cond_sao_goncalo = df['Destination City'].astype(str).str.upper().str.contains('SÃO GONÇALO DO RIO ABAIXO', na=False)
            df = df[cond_abrangencia | cond_sao_goncalo]
            
        # Aplicar Roteirização
        if not df.empty and 'Destination City' in df.columns and 'Consignee Area' in df.columns:
            df['Rota'] = df.apply(lambda row: roteirizador.obter_rota_imile(row['Destination City'], row['Consignee Area']), axis=1)
        else:
            df['Rota'] = "DESCONHECIDO"
            
        return df
    except Exception as e:
        return None

def carregar_dados_imile_inventariados():
    caminho = "c:/bots/latencia_consolidada.xlsx"
    mtime = os.path.getmtime(caminho) if os.path.exists(caminho) else 0
    df = _carregar_dados_imile_inventariados_cached(mtime)
    if df is not None:
        st.session_state['last_imile_inv_df'] = df
        return df
    return st.session_state.get('last_imile_inv_df', pd.DataFrame())

@st.cache_data(show_spinner=False)
def _carregar_dados_shopee_cached(caminho, mtime):
    try:
        if caminho.endswith('.csv'):
            df = None
            for sep, enc in [(',', 'utf-8-sig'), (',', 'utf-8'), (',', 'latin1'), (';', 'utf-8-sig'), (';', 'latin1')]:
                try:
                    tmp_df = pd.read_csv(caminho, sep=sep, encoding=enc, dtype=str)
                    if len(tmp_df.columns) > 2: 
                        df = tmp_df
                        break
                except: continue
            if df is None: return None
        else:
            df = pd.read_excel(caminho, dtype=str)

        # Filtro de status Hub_Received (Opcional, pois normalmente o export já é filtrado)
        # Algumas planilhas tem coluna "Status"
        col_status = next((c for c in df.columns if 'status' in c.lower()), None)
        if col_status:
            df = df[df[col_status].astype(str).str.contains("Hub_Received|Recebido no hub", case=False, na=False)]

        # Aplicar Roteirização
        col_cep = next((c for c in df.columns if c.lower() in ['postal code', 'cep', 'c.e.p'] or 'cep' in c.lower() or 'zipcode' in c.lower()), None)
        if col_cep and not df.empty:
            df['Rota'] = df[col_cep].apply(roteirizador.obter_rota_shopee)
        else:
            df['Rota'] = "SEM CEP"
            
        return df
    except Exception as e:
        return None

def carregar_dados_shopee():
    dir_downloads = "c:/bots/downloads_shopee"
    if not os.path.exists(dir_downloads):
        return pd.DataFrame()
        
    # Pega o arquivo mais recente
    arquivos = glob.glob(os.path.join(dir_downloads, "*.xlsx")) + glob.glob(os.path.join(dir_downloads, "*.csv"))
    if not arquivos:
        return pd.DataFrame()
        
    caminho = max(arquivos, key=os.path.getmtime)
    mtime = os.path.getmtime(caminho)
    
    df = _carregar_dados_shopee_cached(caminho, mtime)
    if df is not None:
        st.session_state['last_shopee_df'] = df
        return df
    return st.session_state.get('last_shopee_df', pd.DataFrame())

@st.fragment(run_every="30s")
def render_header_kpis():
    # Ler arquivo de última atualização
    caminho_txt = "c:/bots/ultima_atualizacao_inventario.txt"
    ultima_att_str = "Desconhecido"
    proxima_att_str = "Desconhecido"
    
    if os.path.exists(caminho_txt):
        try:
            with open(caminho_txt, "r", encoding="utf-8") as f:
                ultima_att_str = f.read().strip()
                ultima_dt = datetime.strptime(ultima_att_str, "%d/%m/%Y %H:%M:%S")
                proxima_dt = ultima_dt + timedelta(minutes=6)
                proxima_att_str = proxima_dt.strftime("%H:%M:%S")
        except:
            pass
            
    st.markdown(f"<p style='text-align: right; color: #94a3b8;'>🤖 Última verificação do robô: <b>{ultima_att_str}</b> | Próxima: <b>~{proxima_att_str}</b></p>", unsafe_allow_html=True)
    
    df_imile = carregar_dados_imile()
    df_shopee = carregar_dados_shopee()
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">🟩 Faltam Bipar (iMile)</div>
            <div class="metric-value">{len(df_imile)}</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">🟧 Faltam Bipar (Shopee)</div>
            <div class="metric-value">{len(df_shopee)}</div>
        </div>
        """, unsafe_allow_html=True)

@st.fragment(run_every="30s")
def render_tab_imile():
    df_imile = carregar_dados_imile()
    
    col_filtro, col_di, col_df = st.columns([2, 1, 1])
    with col_filtro:
        tipo_filtro = st.selectbox("📅 Filtro de Data (iMile):", ["Todos", "Filtrar por Período"], key="tipo_filtro_imile")
    
    if tipo_filtro == "Filtrar por Período":
        with col_di:
            data_inicio = st.date_input("Data Inicial", key="di_imile")
        with col_df:
            data_fim = st.date_input("Data Final", key="df_imile")
            
        if not df_imile.empty:
            col_backlog = next((c for c in df_imile.columns if 'backlog' in c.lower()), None)
            if col_backlog:
                hoje = datetime.now().date()
                
                # Backlog 1 = Hoje, Backlog 2 = Ontem, etc.
                # Então, Data Final (mais recente) tem um backlog MENOR.
                backlog_min = (hoje - data_fim).days + 1
                backlog_max = (hoje - data_inicio).days + 1
                
                # Evita problemas se a pessoa inverter as datas
                b_min, b_max = min(backlog_min, backlog_max), max(backlog_min, backlog_max)
                
                dias_backlog = pd.to_numeric(df_imile[col_backlog], errors='coerce')
                df_imile = df_imile[(dias_backlog >= b_min) & (dias_backlog <= b_max)]
            else:
                st.warning("⚠️ Coluna de Backlog não encontrada para aplicar o filtro.")
            
    if df_imile.empty:
        st.success("Tudo bipado! Nenhum pacote pendente no piso (Arrive) para o filtro selecionado.")
    else:
        rotas = df_imile['Rota'].value_counts()
        
        col_bairro = 'Consignee Area' if 'Consignee Area' in df_imile.columns else None
        col_endereco = 'Consignee Address_y' if 'Consignee Address_y' in df_imile.columns else None
        
        if col_bairro: df_imile[col_bairro] = df_imile[col_bairro].fillna('N/A')
        if col_endereco: df_imile[col_endereco] = df_imile[col_endereco].fillna('N/A')
        
        cols_to_show = ['Waybill No']
        if col_bairro: cols_to_show.append(col_bairro)
        if col_endereco: cols_to_show.append(col_endereco)
        
        for rota, qtd in rotas.items():
            with st.expander(f"📦 {rota} - {qtd} pacotes", expanded=(qtd > 0)):
                df_rota = df_imile[df_imile['Rota'] == rota]
                
                if qtd > 150:
                    st.warning("Muitos pacotes nesta rota. Exibindo como tabela simples para não travar o navegador.")
                    st.dataframe(df_rota[cols_to_show], hide_index=True, use_container_width=True)
                else:
                    hcols = st.columns([2, 3, 3, 2])
                    hcols[0].markdown("**Waybill No**")
                    if col_bairro: hcols[1].markdown("**Bairro**")
                    if col_endereco: hcols[2].markdown("**Endereço**")
                    hcols[3].markdown("**Ação**")
                    
                    for _, row in df_rota.iterrows():
                        awb = row['Waybill No']
                        bairro = row.get(col_bairro, 'N/A') if col_bairro else 'N/A'
                        endereco = row.get(col_endereco, 'N/A') if col_endereco else 'N/A'
                        base = row.get('Base', 'JML')
                        
                        rcols = st.columns([2, 3, 3, 2])
                        rcols[0].write(awb)
                        if col_bairro: rcols[1].write(bairro)
                        if col_endereco: rcols[2].write(endereco)
                        
                        btn_placeholder = rcols[3].empty()
                        link_key = f"wpp_link_{awb}"
                        
                        if link_key in st.session_state:
                            btn_placeholder.markdown(st.session_state[link_key], unsafe_allow_html=True)
                        else:
                            if btn_placeholder.button("Pesquisar", key=f"btn_{awb}"):
                                import config
                                import urllib.parse
                                from scraper_contato import buscar_dados_contato_imile
                                
                                usuario, senha = None, None
                                for b, u, s in config.BASES_SLA:
                                    if b == base:
                                        usuario, senha = u, s
                                        break
                                        
                                if not usuario:
                                    btn_placeholder.error("Sem credenciais.")
                                else:
                                    with st.spinner("Buscando..."):
                                        resultado = buscar_dados_contato_imile(awb, usuario, senha)
                                        
                                    if resultado['telefone'] == "N/A" or not resultado['telefone']:
                                        try: btn_placeholder.error("Telefone não achado")
                                        except: pass
                                    else:
                                        tel_limpo = ''.join(filter(str.isdigit, resultado['telefone']))
                                        if not tel_limpo.startswith('55') and len(tel_limpo) <= 11:
                                            tel_limpo = f"55{tel_limpo}"
                                        msg = f"Olá {resultado['nome']}, sou responsável pelas entregas da Shein/Tiktok, gostaria de confirmar se vc recebeu o seguinte pedido:\n\n📦 Produto: {resultado['produto']}\n🔖 Código: {awb}"
                                        msg_encoded = urllib.parse.quote(msg)
                                        link_wpp = f"https://wa.me/{tel_limpo}?text={msg_encoded}"
                                        html_link = f'<a href="{link_wpp}" target="_blank" style="background-color: #25D366; color: white; padding: 5px 10px; border-radius: 5px; text-decoration: none; font-size: 12px;">📱 WhatsApp</a>'
                                        st.session_state[link_key] = html_link
                                        try:
                                            btn_placeholder.markdown(html_link, unsafe_allow_html=True)
                                        except:
                                            pass

@st.fragment(run_every="30s")
def render_tab_shopee():
    df_shopee = carregar_dados_shopee()
    
    col_filtro, col_di, col_df = st.columns([2, 1, 1])
    with col_filtro:
        tipo_filtro = st.selectbox("📅 Filtro de Data (Shopee):", ["Todos", "Filtrar por Período"], key="tipo_filtro_shopee")
    
    if tipo_filtro == "Filtrar por Período":
        with col_di:
            data_inicio = st.date_input("Data Inicial", key="di_shopee")
        with col_df:
            data_fim = st.date_input("Data Final", key="df_shopee")
            
        if not df_shopee.empty:
            col_data = next((c for c in df_shopee.columns if 'current station received' in c.lower() or 'horário de entrada' in c.lower() or 'inbound' in c.lower() or 'entrada' in c.lower()), None)
            if col_data:
                # O formato do Shopee pode variar, to_datetime lida com a maioria. dayfirst=True ajuda com dd/mm/yyyy
                datas = pd.to_datetime(df_shopee[col_data], errors='coerce', dayfirst=True).dt.date
                df_shopee = df_shopee[(datas >= data_inicio) & (datas <= data_fim)]
            else:
                st.warning("⚠️ Coluna de data não encontrada para aplicar o filtro.")

    if df_shopee.empty:
        st.success("Tudo bipado! Nenhum pacote pendente no piso hoje.")
    else:
        rotas = df_shopee['Rota'].value_counts()
        
        col_tracking = next((c for c in df_shopee.columns if 'tracking' in c.lower() or 'rastreamento' in c.lower() or 'rastreio' in c.lower()), None)
        
        cols_to_show = []
        if col_tracking: cols_to_show.append(col_tracking)
        
        col_comprador = next((c for c in df_shopee.columns if 'buyer' in c.lower() or 'comprador' in c.lower()), None)
        col_cidade = next((c for c in df_shopee.columns if 'cidade' in c.lower() or 'city' in c.lower()), None)
        col_bairro = next((c for c in df_shopee.columns if 'bairro' in c.lower() or 'district' in c.lower()), None)
        
        if not col_comprador and len(df_shopee.columns) >= 8:
            col_comprador = df_shopee.columns[7]

        if col_comprador: cols_to_show.append(col_comprador)
        if col_cidade: cols_to_show.append(col_cidade)
        if col_bairro: cols_to_show.append(col_bairro)
        
        if not cols_to_show:
            cols_to_show = df_shopee.columns.tolist()
            
        for rota, qtd in rotas.items():
            with st.expander(f"📦 {rota} - {qtd} pacotes", expanded=(qtd > 0)):
                df_rota = df_shopee[df_shopee['Rota'] == rota]
                
                header_cols = st.columns([2, 3, 3, 2])
                header_cols[0].markdown("**Rastreio**")
                header_cols[1].markdown("**Comprador / Bairro**")
                header_cols[2].markdown("**Cidade**")
                header_cols[3].markdown("**Contato Direto**")
                
                for _, row in df_rota.iterrows():
                    tracking = row.get(col_tracking, 'N/A') if col_tracking else 'N/A'
                    comprador = row.get(col_comprador, '') if col_comprador else ''
                    bairro = row.get(col_bairro, '') if col_bairro else ''
                    cidade = row.get(col_cidade, 'N/A') if col_cidade else 'N/A'
                    
                    comp_bairro = f"{comprador} - {bairro}".strip(" -")
                    if not comp_bairro:
                        comp_bairro = "N/A"
                    
                    rcols = st.columns([2, 3, 3, 2])
                    rcols[0].write(tracking)
                    rcols[1].write(comp_bairro)
                    rcols[2].write(cidade)
                    
                    btn_placeholder = rcols[3].empty()
                    link_key = f"wpp_link_shopee_{tracking}"
                    
                    if link_key in st.session_state:
                        btn_placeholder.markdown(st.session_state[link_key], unsafe_allow_html=True)
                    else:
                        if tracking != 'N/A' and btn_placeholder.button("Pesquisar", key=f"btn_shp_{tracking}"):
                            import urllib.parse
                            from scraper_contato_shopee import buscar_dados_contato_shopee
                            
                            with st.spinner("Buscando..."):
                                resultado = buscar_dados_contato_shopee(tracking)
                                
                            if resultado['telefone'] == "N/A" or not resultado['telefone']:
                                try: btn_placeholder.error("Telefone não achado")
                                except: pass
                            else:
                                tel_limpo = ''.join(filter(str.isdigit, resultado['telefone']))
                                if not tel_limpo.startswith('55') and len(tel_limpo) <= 11:
                                    tel_limpo = f"55{tel_limpo}"
                                msg = f"Olá {resultado['nome']}, sou responsável pelas entregas da Shopee, gostaria de confirmar se vc recebeu o seguinte pedido:\n\n📦 Produto: {resultado['produto']}\n🔖 Código: {tracking}"
                                msg_encoded = urllib.parse.quote(msg)
                                link_wpp = f"https://wa.me/{tel_limpo}?text={msg_encoded}"
                                html_link = f'<a href="{link_wpp}" target="_blank" style="background-color: #25D366; color: white; padding: 5px 10px; border-radius: 5px; text-decoration: none; font-size: 12px;">📱 WhatsApp</a>'
                                st.session_state[link_key] = html_link
                                try:
                                    btn_placeholder.markdown(html_link, unsafe_allow_html=True)
                                except:
                                    pass

def injetar_estilos():
    st.markdown("""
        <style>
        /* Cores da empresa: Azul Marinho (#021B59) e Vermelho (#E30613) */
        .stApp {
            background-color: #021B59;
            color: #ffffff;
        }
        [data-testid="stSidebar"] {
            background-color: #01123d !important;
        }
        .metric-card {
            background-color: #042573 !important;
            border-left: 4px solid #E30613 !important;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 10px;
        }
        .metric-label {
            font-size: 14px;
            color: #d1d5db;
        }
        .metric-value {
            font-size: 28px;
            font-weight: bold;
            color: #ffffff;
        }
        /* Corrigir abas */
        .stTabs [data-baseweb="tab-list"] {
            gap: 10px;
        }
        .stTabs [data-baseweb="tab"] {
            background-color: #042573;
            border-radius: 4px 4px 0 0;
            padding: 10px 20px;
        }
        .stTabs [aria-selected="true"] {
            background-color: #E30613 !important;
            color: #ffffff !important;
        }
        </style>
    """, unsafe_allow_html=True)

@st.fragment(run_every="30s")
def render_tab_imile_inventariados():
    df_imile = carregar_dados_imile_inventariados()
    
    col_filtro, col_di, col_df = st.columns([2, 1, 1])
    with col_filtro:
        tipo_filtro = st.selectbox("📅 Filtro de Data (Inventariados):", ["Todos", "Filtrar por Período"], key="tipo_filtro_inv")
    
    if tipo_filtro == "Filtrar por Período":
        with col_di:
            data_inicio = st.date_input("Data Inicial", key="di_inv")
        with col_df:
            data_fim = st.date_input("Data Final", key="df_inv")
            
        if not df_imile.empty:
            col_backlog = next((c for c in df_imile.columns if 'backlog' in c.lower()), None)
            if col_backlog:
                hoje = datetime.now().date()
                backlog_min = (hoje - data_fim).days + 1
                backlog_max = (hoje - data_inicio).days + 1
                b_min, b_max = min(backlog_min, backlog_max), max(backlog_min, backlog_max)
                dias_backlog = pd.to_numeric(df_imile[col_backlog], errors='coerce')
                df_imile = df_imile[(dias_backlog >= b_min) & (dias_backlog <= b_max)]
            else:
                st.warning("⚠️ Coluna de Backlog não encontrada para aplicar o filtro.")
            
    if df_imile.empty:
        st.info("Nenhum pacote com status 'Inventory Scan' no momento.")
    else:
        st.success(f"Total de pacotes inventariados: {len(df_imile)}")
        rotas = df_imile['Rota'].value_counts()
        
        col_bairro = 'Consignee Area' if 'Consignee Area' in df_imile.columns else None
        col_endereco = 'Consignee Address_y' if 'Consignee Address_y' in df_imile.columns else None
        
        if col_bairro: df_imile[col_bairro] = df_imile[col_bairro].fillna('N/A')
        if col_endereco: df_imile[col_endereco] = df_imile[col_endereco].fillna('N/A')
        
        cols_to_show = ['Waybill No']
        if col_bairro: cols_to_show.append(col_bairro)
        if col_endereco: cols_to_show.append(col_endereco)
        
        for rota, qtd in rotas.items():
            with st.expander(f"📦 {rota} - {qtd} pacotes", expanded=False):
                df_rota = df_imile[df_imile['Rota'] == rota]
                
                if qtd > 150:
                    st.warning("Muitos pacotes nesta rota. Exibindo como tabela simples para não travar o navegador.")
                    st.dataframe(df_rota[cols_to_show], hide_index=True, use_container_width=True)
                else:
                    hcols = st.columns([2, 3, 3, 2])
                    hcols[0].markdown("**Waybill No**")
                    if col_bairro: hcols[1].markdown("**Bairro**")
                    if col_endereco: hcols[2].markdown("**Endereço**")
                    hcols[3].markdown("**Ação**")
                    
                    for _, row in df_rota.iterrows():
                        awb = row['Waybill No']
                        bairro = row.get(col_bairro, 'N/A') if col_bairro else 'N/A'
                        endereco = row.get(col_endereco, 'N/A') if col_endereco else 'N/A'
                        base = row.get('Base', 'JML')
                        
                        rcols = st.columns([2, 3, 3, 2])
                        rcols[0].write(awb)
                        if col_bairro: rcols[1].write(bairro)
                        if col_endereco: rcols[2].write(endereco)
                        
                        btn_placeholder = rcols[3].empty()
                        link_key = f"wpp_link_inv_{awb}"
                        
                        if link_key in st.session_state:
                            btn_placeholder.markdown(st.session_state[link_key], unsafe_allow_html=True)
                        else:
                            if btn_placeholder.button("Pesquisar", key=f"btn_inv_{awb}"):
                                import config
                                import urllib.parse
                                from scraper_contato import buscar_dados_contato_imile
                                
                                usuario, senha = None, None
                                for b, u, s in config.BASES_SLA:
                                    if b == base:
                                        usuario, senha = u, s
                                        break
                                        
                                if not usuario:
                                    btn_placeholder.error("Sem credenciais.")
                                else:
                                    with st.spinner("Buscando..."):
                                        resultado = buscar_dados_contato_imile(awb, usuario, senha)
                                        
                                    if resultado['telefone'] == "N/A" or not resultado['telefone']:
                                        try: btn_placeholder.error("Telefone não achado")
                                        except: pass
                                    else:
                                        tel_limpo = ''.join(filter(str.isdigit, resultado['telefone']))
                                        if not tel_limpo.startswith('55') and len(tel_limpo) <= 11:
                                            tel_limpo = f"55{tel_limpo}"
                                        msg = f"Olá {resultado['nome']}, sou responsável pelas entregas da Shein/Tiktok, gostaria de confirmar se vc recebeu o seguinte pedido:\n\n📦 Produto: {resultado['produto']}\n🔖 Código: {awb}"
                                        msg_encoded = urllib.parse.quote(msg)
                                        link_wpp = f"https://wa.me/{tel_limpo}?text={msg_encoded}"
                                        html_link = f'<a href="{link_wpp}" target="_blank" style="background-color: #25D366; color: white; padding: 5px 10px; border-radius: 5px; text-decoration: none; font-size: 12px;">📱 WhatsApp</a>'
                                        st.session_state[link_key] = html_link
                                        try:
                                            btn_placeholder.markdown(html_link, unsafe_allow_html=True)
                                        except:
                                            pass

def main():
    st.set_page_config(page_title="Painel de Expedição", page_icon="🎯", layout="wide")
    st.logo("c:/bots/logo.png", size="large")
    injetar_estilos()
    
    col1, col2 = st.columns([1, 8])
    with col1:
        st.markdown("<h1 style='font-size: 3rem;'>🎯</h1>", unsafe_allow_html=True)
    with col2:
        st.title("Painel de Expedição")
        st.markdown("<h4 style='color: #94a3b8;'>Acompanhamento de Bipagem (Pacotes Faltantes no App)</h4>", unsafe_allow_html=True)
        
    st.markdown("---")
    
    render_header_kpis()
    
    tab_imile, tab_shopee, tab_inventario = st.tabs(["🟩 Monitor iMile", "🟧 Monitor Shopee", "📋 Inventariados"])
    
    with tab_imile:
        render_tab_imile()
        
    with tab_shopee:
        render_tab_shopee()
        
    with tab_inventario:
        st.subheader("📋 Lista de Pacotes Inventariados (iMile)")
        st.write("Pacotes que estão com o status **Inventory Scan** na planilha da iMile.")
        render_tab_imile_inventariados()

if __name__ == "__main__":
    main()
