import streamlit as st
import pandas as pd
import os
import io
import json
import urllib.parse
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials

try:
    import sync_time_patch
except ImportError:
    pass

try:
    import config
except ImportError:
    config = None

try:
    from scraper_contato import buscar_dados_contato_imile
except Exception:
    buscar_dados_contato_imile = None

# ==========================================
# CONFIGURAÇÃO DA PÁGINA STREAMLIT
# ==========================================
st.set_page_config(
    page_title="Monitor ITR - Expedição & Piso",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================================
# ESTILOS CSS CUSTOMIZADOS (TEMA PORTO GUIMARÃES DARK)
# ==========================================
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    .stApp {
        background-color: #0b1120;
        color: #f8fafc;
    }
    
    /* Headers */
    h1, h2, h3, h4 {
        color: #f8fafc !important;
        font-weight: 700 !important;
        letter-spacing: -0.02em;
    }
    
    /* Cards de Métricas Principais */
    .metric-card {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid #334155;
        border-radius: 14px;
        padding: 16px 20px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        text-align: center;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .metric-card:hover {
        transform: translateY(-3px);
        box-shadow: 0 8px 20px rgba(56, 189, 248, 0.15);
    }
    .metric-value {
        font-size: 2.2rem;
        font-weight: 800;
        line-height: 1.1;
        margin-top: 4px;
    }
    .metric-label {
        font-size: 0.95rem;
        font-weight: 600;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .metric-sub {
        font-size: 0.8rem;
        color: #64748b;
        margin-top: 4px;
    }
    
    /* Cores de Métricas */
    .text-sky { color: #38bdf8 !important; }
    .text-green { color: #22c55e !important; }
    .text-yellow { color: #eab308 !important; }
    .text-orange { color: #f97316 !important; }
    .text-red { color: #ef4444 !important; }
    .text-purple { color: #a855f7 !important; }
    
    /* Badges de Aging */
    .badge {
        display: inline-block;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 0.78rem;
        font-weight: 700;
        text-align: center;
        margin-right: 5px;
    }
    .badge-d0 { background-color: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid #22c55e; }
    .badge-d1 { background-color: rgba(234, 179, 8, 0.2); color: #fde047; border: 1px solid #eab308; }
    .badge-d2 { background-color: rgba(249, 115, 22, 0.2); color: #fdba74; border: 1px solid #f97316; }
    .badge-d3 { background-color: rgba(239, 68, 68, 0.2); color: #fca5a5; border: 1px solid #ef4444; }
    .badge-piso { background-color: rgba(56, 189, 248, 0.2); color: #7dd3fc; border: 1px solid #38bdf8; }
    .badge-aviso { background-color: rgba(168, 85, 247, 0.2); color: #d8b4fe; border: 1px solid #a855f7; }
    
    /* Estilo das Abas */
    .stTabs [data-baseweb="tab-list"] {
        gap: 12px;
        background-color: transparent;
        border-bottom: 2px solid #1e293b;
        padding-bottom: 4px;
        margin-bottom: 20px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #1e293b;
        border-radius: 10px 10px 0 0;
        color: #94a3b8;
        padding: 12px 24px;
        font-weight: 600;
        font-size: 1.05rem;
        border: 1px solid #334155;
        border-bottom: none;
        transition: all 0.2s ease;
    }
    .stTabs [data-baseweb="tab"]:hover {
        color: #f8fafc;
        background-color: #273549;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(180deg, #0284c7 0%, #0369a1 100%) !important;
        color: #ffffff !important;
        border-color: #38bdf8 !important;
        box-shadow: 0 4px 12px rgba(56, 189, 248, 0.25);
    }
    
    /* Botoes de WhatsApp */
    .wpp-btn {
        background-color: #25D366;
        color: white !important;
        padding: 6px 14px;
        border-radius: 6px;
        text-decoration: none;
        font-size: 0.85rem;
        font-weight: 700;
        display: inline-block;
        transition: opacity 0.2s;
    }
    .wpp-btn:hover {
        opacity: 0.9;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# FUNÇÕES AUXILIARES DE LIMPEZA E FORMATAÇÃO
# ==========================================
def limpar_texto(txt):
    """Corrige caracteres corrompidos comuns em planilhas iMile (mojibake)."""
    if pd.isna(txt) or not str(txt).strip():
        return ""
    s = str(txt).strip()
    substituicoes = {
        'rea': 'Área', 'Poo': 'Poço', 'So': 'São', 'Marlia': 'Marília',
        'Fnix': 'Fênix', 'Estao': 'Estação', 'Cssia': 'Cássia', 'gua': 'Água',
        'Itamb': 'Itambé', 'Antnio': 'Antônio', 'Gonalo': 'Gonçalo', 'Sebastio': 'Sebastião',
        'Passabm': 'Passabém', 'Carmsia': 'Carmésia', 'Suau': 'Suaçuí', 'Manhuau': 'Manhuaçu',
        'Brbara': 'Bárbara', 'Abboras': 'Abóboras', 'Efignia': 'Efigênia', 'Par': 'Pará',
        'Esperana': 'Esperança', 'Gois': 'Goiás', 'Nmero': 'Número'
    }
    for errado, correto in substituicoes.items():
        s = s.replace(errado, correto)
    s = s.replace('', '')
    return s.strip()

def obter_credenciais_itr():
    """Busca credenciais específicas da base de ITR no config ou secrets."""
    try:
        if "IMILE_ITR_USER" in st.secrets and "ITR_IMILE_PASS" in st.secrets:
            return st.secrets["IMILE_ITR_USER"], st.secrets["ITR_IMILE_PASS"]
    except Exception:
        pass
    if config and hasattr(config, 'BASES_SLA'):
        for b, u, s in config.BASES_SLA:
            if str(b).strip().upper() == "ITR" and u and s:
                return u, s
    return os.getenv("IMILE_ITR_USER"), os.getenv("ITR_IMILE_PASS")

def formatar_telefone(tel):
    """Higieniza número de telefone para o formato padrão internacional 55+DDD+NUM."""
    tel_limpo = ''.join(filter(str.isdigit, str(tel)))
    if not tel_limpo:
        return ""
    if not tel_limpo.startswith('55') and len(tel_limpo) <= 11:
        tel_limpo = f"55{tel_limpo}"
    return tel_limpo

def gerar_link_whatsapp(telefone, nome, awb, endereco, produto=""):
    """Gera link wa.me com mensagem profissional pré-formatada para a base ITR."""
    tel = formatar_telefone(telefone)
    if not tel:
        return None
    nome_fmt = nome if nome and nome != "N/A" else "Cliente"
    prod_fmt = f"\n📦 *Produto:* {produto}" if produto and produto != "N/A" else ""
    end_fmt = f"\n📍 *Endereço:* {endereco}" if endereco and endereco != "N/A" else ""
    
    msg = (
        f"Olá {nome_fmt}, sou da equipe de entregas da *Porto Guimarães Express* (Base Itabira / iMile).\n"
        f"Estamos acompanhando seu pedido:{prod_fmt}\n"
        f"🔖 *Rastreio:* {awb}{end_fmt}\n\n"
        f"Gostaria de confirmar se você já recebeu esta encomenda ou se precisa de auxílio com a entrega?"
    )
    msg_enc = urllib.parse.quote(msg)
    return f"https://wa.me/{tel}?text={msg_enc}"

def gerar_texto_grupo_whatsapp(df_subset, base_nome="ITR", formato="completo"):
    """Gera texto formatado com o resumo dos motoristas para colar no grupo de WhatsApp."""
    agora_str = datetime.now().strftime("%d/%m/%Y às %H:%M")
    total_pacotes = len(df_subset)
    mots_unicos = df_subset['Motorista_Limpo'].nunique() if 'Motorista_Limpo' in df_subset.columns else 0
    total_atraso = len(df_subset[df_subset['aging'] >= 1]) if 'aging' in df_subset.columns else 0
    total_d0 = len(df_subset[df_subset['aging'] == 0]) if 'aging' in df_subset.columns else 0

    contagem = df_subset['Motorista_Limpo'].value_counts() if 'Motorista_Limpo' in df_subset.columns else pd.Series()
    
    linhas_mots = []
    for mot, total_m in contagem.items():
        df_m = df_subset[df_subset['Motorista_Limpo'] == mot]
        atraso_m = len(df_m[df_m['aging'] >= 1]) if 'aging' in df_m.columns else 0
        d0_m = len(df_m[df_m['aging'] == 0]) if 'aging' in df_m.columns else 0
        d1_m = len(df_m[df_m['aging'] == 1]) if 'aging' in df_m.columns else 0
        d2_m = len(df_m[df_m['aging'] >= 2]) if 'aging' in df_m.columns else 0
        
        if formato == "simplificado":
            linhas_mots.append(f"👤 *{mot}:* {total_m} pacote(s)")
        elif formato == "atrasados":
            if atraso_m > 0:
                detalhes_atr = []
                if d1_m > 0: detalhes_atr.append(f"{d1_m} D1")
                if d2_m > 0: detalhes_atr.append(f"{d2_m} D2+")
                txt_atr = f" ({' + '.join(detalhes_atr)})" if detalhes_atr else ""
                linhas_mots.append(f"⚠️ *{mot}:* {atraso_m} em atraso{txt_atr} | Total: {total_m}")
        else: # completo
            if atraso_m == 0:
                status_txt = "✅ 100% no prazo"
            else:
                detalhes_atr = []
                if d1_m > 0: detalhes_atr.append(f"{d1_m} D1")
                if d2_m > 0: detalhes_atr.append(f"{d2_m} D2+")
                suf_atr = f" ({', '.join(detalhes_atr)})" if detalhes_atr else ""
                status_txt = f"{d0_m} D0 | ⚠️ {atraso_m} em atraso{suf_atr}"
            linhas_mots.append(f"👤 *{mot}:* {total_m} pacotes ({status_txt})")

    if formato == "atrasados" and not linhas_mots:
        corpo_mots = "✅ Parabéns equipe! Nenhum entregador com pacotes em atraso no momento! 🎉"
    else:
        corpo_mots = "\n".join(linhas_mots) if linhas_mots else "Nenhum pacote em rota."

    texto = (
        f"🚚 *RESUMO DE EXPEDIÇÃO EM ROTA — BASE ITR*\n"
        f"🏢 *Base:* {base_nome}\n"
        f"📅 *Atualizado:* {agora_str}\n\n"
        f"📦 *Total em Rota:* {total_pacotes} pacotes\n"
        f"👨‍✈️ *Entregadores:* {mots_unicos} motoristas\n"
        f"🟢 *No Prazo (D0):* {total_d0} pacotes\n"
        f"⚠️ *Em Atraso (≥ D1):* {total_atraso} pacotes\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 *DISTRIBUIÇÃO POR ENTREGADOR:*\n\n"
        f"{corpo_mots}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ *Favor atentar para as baixas dentro do horário e devolução de insucessos à base!*"
    )
    return texto

# ==========================================
# CREDENCIAIS GOOGLE & FUNÇÕES DE APOIO
# ==========================================
def obter_credenciais_google():
    """Obtém credenciais da conta de serviço Google (arquivo local ou secrets)."""
    caminho_cred = os.path.join(os.path.dirname(__file__), 'credenciais.json')
    if os.path.exists(caminho_cred):
        try:
            with open(caminho_cred, encoding='utf-8') as f:
                info = json.load(f)
            escopo = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
            return Credentials.from_service_account_info(info, scopes=escopo)
        except Exception:
            pass
    try:
        chave_str = st.secrets["chave_google"].strip()
        info = json.loads(chave_str)
        escopo = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        return Credentials.from_service_account_info(info, scopes=escopo)
    except Exception as e:
        print(f"Credenciais Google não disponíveis: {e}")
        return None

# ==========================================
# PROCESSAMENTO DE DADOS (COMUM LOCAL / NUVEM)
# ==========================================
def processar_dataframe_itr(df):
    if df is None or df.empty:
        return pd.DataFrame()
        
    df = df.copy()
    df.columns = df.columns.astype(str).str.strip()
    
    # Filtro estrito: APENAS BASE ITR
    if 'Base' in df.columns:
        df = df[df['Base'].astype(str).str.upper() == 'ITR'].copy()
    else:
        return pd.DataFrame()
        
    if df.empty:
        return df
        
    # Normalização de Aging
    if 'aging' in df.columns:
        df['aging'] = pd.to_numeric(df['aging'], errors='coerce').fillna(0).astype(int)
    else:
        df['aging'] = 0
        
    # Limpeza de Textos Principais
    for col in ['Destination City', 'Consignee Area', 'Consignee Address_y', 'Consignee Address_x', 'Driver Name', 'Last scan type']:
        if col in df.columns:
            df[col] = df[col].apply(limpar_texto)
            
    # Definir se está Em Rota ou no Piso
    if 'Last scan type' in df.columns:
        df['is_rota'] = df['Last scan type'].str.upper() == 'OUT FOR DELIVERY'
    else:
        df['is_rota'] = False
        
    # Bairro Consolidado / Display
    def resolver_bairro(row):
        area = str(row.get('Consignee Area', '')).strip()
        cidade = str(row.get('Destination City', '')).strip()
        if area and area.lower() not in ['nan', 'none', '']:
            return area
        if cidade and cidade.lower() not in ['nan', 'none', '']:
            return f"{cidade} (Centro/Sede)"
        return "Bairro Não Informado"
        
    df['Bairro_Display'] = df.apply(resolver_bairro, axis=1)
    
    # Endereço Consolidado
    def resolver_endereco(row):
        y = str(row.get('Consignee Address_y', '')).strip()
        if y and y.lower() not in ['nan', 'none', '']:
            return y
        x = str(row.get('Consignee Address_x', '')).strip()
        if x and x.lower() not in ['nan', 'none', '']:
            return x
        return "Endereço não informado"
        
    df['Endereco_Display'] = df.apply(resolver_endereco, axis=1)
    
    # Motorista Amigável
    def resolver_motorista(val):
        m = str(val).strip()
        if not m or m.lower() in ['nan', 'none', '']:
            return "Não Atribuído"
        return m.replace('(ITR LOC) ', '').replace('(ITR INT) ', '').strip()
        
    if 'Driver Name' in df.columns:
        df['Motorista_Limpo'] = df['Driver Name'].apply(resolver_motorista)
    else:
        df['Motorista_Limpo'] = "Não Atribuído"
        
    # Classificação de Localidade
    def resolver_tipo_localidade(row):
        cidade = str(row.get('Destination City', '')).strip().upper()
        abrangencia = str(row.get('abrangencia', '1')).strip()
        if abrangencia == '0':
            return "⚠️ Fora de Rota (Inversão)"
        if "ITABIRA" in cidade:
            return "🏙️ Itabira (Urbano)"
        return "🏞️ Interior Satélite"
        
    df['Tipo_Localidade'] = df.apply(resolver_tipo_localidade, axis=1)
    
    return df

@st.cache_data(show_spinner=False)
def _carregar_dados_itr_local_cached(mtime):
    caminho = "c:/bots/latencia_consolidada.xlsx"
    if not os.path.exists(caminho):
        return pd.DataFrame(), ""
    try:
        df = pd.read_excel(caminho)
        att_str = datetime.fromtimestamp(mtime).strftime("%d/%m/%Y às %H:%M:%S")
        return processar_dataframe_itr(df), att_str
    except Exception as e:
        print(f"Erro ao ler Excel local: {e}")
        return pd.DataFrame(), ""

@st.cache_data(ttl=60, show_spinner=False)
def _carregar_dados_itr_sheets_cached():
    try:
        creds = obter_credenciais_google()
        if not creds:
            return pd.DataFrame(), "Sem credenciais Google"
        cliente = gspread.authorize(creds)
        planilha = cliente.open("acareaBase").worksheet("ITR_Expedicao")
        dados = planilha.get_all_values()
        if not dados or len(dados) < 2:
            return pd.DataFrame(), "Aba vazia"
        df_raw = pd.DataFrame(dados[1:], columns=dados[0])
        att_str = "Recentemente"
        if 'Atualizado_Em' in df_raw.columns and not df_raw['Atualizado_Em'].empty:
            att_str = str(df_raw['Atualizado_Em'].iloc[0]).strip()
        return processar_dataframe_itr(df_raw), att_str
    except Exception as e:
        print(f"Erro ao carregar ITR do Google Sheets: {e}")
        return pd.DataFrame(), "Erro Sheets"

def carregar_dados_itr():
    # 1. Tenta carregar do arquivo local se existir (modo desktop/desenvolvimento)
    caminho_local = "c:/bots/latencia_consolidada.xlsx"
    if os.path.exists(caminho_local):
        try:
            mtime = os.path.getmtime(caminho_local)
            df, att_str = _carregar_dados_itr_local_cached(mtime)
            if df is not None and not df.empty:
                st.session_state['itr_origem_dados'] = "Computador Local"
                st.session_state['itr_ultima_att'] = att_str
                st.session_state['last_itr_dedicated_df'] = df
                return df
        except Exception:
            pass

    # 2. Modo Nuvem (Google Sheets acareaBase > ITR_Expedicao)
    df, att_str = _carregar_dados_itr_sheets_cached()
    if df is not None and not df.empty:
        st.session_state['itr_origem_dados'] = "Google Sheets (acareaBase)"
        st.session_state['itr_ultima_att'] = att_str
        st.session_state['last_itr_dedicated_df'] = df
        return df

    return st.session_state.get('last_itr_dedicated_df', pd.DataFrame())

def exportar_para_excel(df, nome_arquivo):
    """Gera buffer de bytes para download em Excel."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='ITR_Monitor')
    return output.getvalue()

# ==========================================
# CABEÇALHO GLOBAL & STATUS DO ROBÔ
# ==========================================
def render_header(df_itr):
    ultima_att_str = st.session_state.get('itr_ultima_att', 'Recentemente')
    origem_dados = st.session_state.get('itr_origem_dados', 'Google Sheets')
            
    col_t1, col_t2 = st.columns([6, 4])
    with col_t1:
        st.markdown("""
            <div style='display: flex; align-items: center; gap: 14px;'>
                <span style='font-size: 2.8rem;'>📦</span>
                <div>
                    <h1 style='margin: 0; font-size: 1.9rem;'>Monitor de Expedição — Base ITR</h1>
                    <p style='margin: 2px 0 0 0; color: #94a3b8; font-size: 0.95rem;'>
                        Painel Exclusivo da Base de Itabira | Inventário em Rota e Piso
                    </p>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
    with col_t2:
        st.markdown(f"""
            <div style='background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 10px 16px; text-align: right;'>
                <div style='color: #94a3b8; font-size: 0.8rem;'>🤖 Sincronização Robô iMile</div>
                <div style='color: #38bdf8; font-weight: 700; font-size: 0.95rem;'>{ultima_att_str}</div>
                <div style='color: #64748b; font-size: 0.75rem;'>🌐 Fonte: {origem_dados}</div>
            </div>
        """, unsafe_allow_html=True)

# ==========================================
# FRAGMENTO DE EXECUÇÃO EM TEMPO REAL
# ==========================================
@st.fragment(run_every="30s")
def render_dashboard():
    df_itr = carregar_dados_itr()
    
    if df_itr.empty:
        st.warning("⚠️ Nenhum dado encontrado para a base ITR no momento. O robô pode estar sincronizando neste momento.")
        if st.button("🔄 Forçar Recarregamento"):
            st.rerun()
        return

    # Divisão dos dados
    df_rota = df_itr[df_itr['is_rota']].copy()
    df_piso = df_itr[~df_itr['is_rota']].copy()

    # Métricas Gerais
    total_itr = len(df_itr)
    total_rota = len(df_rota)
    total_piso = len(df_piso)
    
    rota_d0 = len(df_rota[df_rota['aging'] == 0])
    rota_atraso = len(df_rota[df_rota['aging'] >= 1])
    motoristas_ativos = df_rota['Motorista_Limpo'].nunique()

    # Cards Principais no Topo
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">📦 Inventário ITR</div>
                <div class="metric-value text-sky">{total_itr}</div>
                <div class="metric-sub">Base Itabira Total</div>
            </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">🚚 Em Rota</div>
                <div class="metric-value text-sky">{total_rota}</div>
                <div class="metric-sub">{(total_rota/total_itr*100):.1f}% do inventário</div>
            </div>
        """, unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">🏢 No Piso</div>
                <div class="metric-value text-orange">{total_piso}</div>
                <div class="metric-sub">{(total_piso/total_itr*100):.1f}% aguardando rota</div>
            </div>
        """, unsafe_allow_html=True)
    with c4:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">⚠️ Rota em Atraso</div>
                <div class="metric-value text-red">{rota_atraso}</div>
                <div class="metric-sub">Aging ≥ 1 dia</div>
            </div>
        """, unsafe_allow_html=True)
    with c5:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">👨‍✈️ Entregadores</div>
                <div class="metric-value text-green">{motoristas_ativos}</div>
                <div class="metric-sub">Em rota hoje</div>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='margin-bottom: 25px;'></div>", unsafe_allow_html=True)

    # Abas
    tab_rota, tab_piso, tab_busca = st.tabs([
        "🚚 Aging em Rota (Entregadores)",
        "🏢 Piso por Bairro (Base Itabira)",
        "🔍 Consulta Rápida (AWB)"
    ])

    with tab_rota:
        render_aba_rota(df_rota)

    with tab_piso:
        render_aba_piso(df_piso)

    with tab_busca:
        render_aba_busca(df_itr)

# ==========================================
# RENDERIZAÇÃO DA ABA 1: AGING EM ROTA
# ==========================================
def render_aba_rota(df_rota):
    if df_rota.empty:
        st.success("🎉 Não há pacotes em rota no momento para a base ITR!")
        return

    d0 = len(df_rota[df_rota['aging'] == 0])
    d1 = len(df_rota[df_rota['aging'] == 1])
    d2 = len(df_rota[df_rota['aging'] == 2])
    d3 = len(df_rota[df_rota['aging'] >= 3])
    max_aging = int(df_rota['aging'].max())

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("🟢 D0 (No Prazo)", f"{d0}")
    k2.metric("🟡 D1 (Atenção)", f"{d1}")
    k3.metric("🟠 D2 (Alerta)", f"{d2}")
    k4.metric("🔴 D3+ (Crítico)", f"{d3}")
    k5.metric("🔥 Aging Máximo", f"{max_aging} dias")

    st.markdown("<hr style='border-color: #1e293b; margin: 15px 0;'>", unsafe_allow_html=True)

    col_g1, col_g2 = st.columns([4, 6])
    with col_g1:
        st.markdown("##### 📊 Distribuição do Aging em Rota")
        df_dist = pd.DataFrame({
            'Faixa': ['D0 (No Prazo)', 'D1 (Atenção)', 'D2 (Alerta)', 'D3+ (Crítico)'],
            'Volume': [d0, d1, d2, d3]
        })
        fig_dist = px.bar(
            df_dist, x='Faixa', y='Volume', text='Volume',
            color='Faixa',
            color_discrete_map={
                'D0 (No Prazo)': '#22c55e',
                'D1 (Atenção)': '#eab308',
                'D2 (Alerta)': '#f97316',
                'D3+ (Crítico)': '#ef4444'
            }
        )
        fig_dist.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=20, b=20, l=20, r=20),
            showlegend=False,
            height=280
        )
        st.plotly_chart(fig_dist, use_container_width=True)

    with col_g2:
        st.markdown("##### 👨‍✈️ Volume por Motorista (No Prazo vs Atrasado)")
        df_mot = df_rota.groupby(['Motorista_Limpo', df_rota['aging'] >= 1]).size().unstack(fill_value=0).reset_index()
        df_mot.columns = ['Motorista', 'No_Prazo', 'Atrasado'] if len(df_mot.columns) == 3 else ['Motorista', 'No_Prazo']
        if 'Atrasado' not in df_mot.columns:
            df_mot['Atrasado'] = 0
            
        df_mot['Total'] = df_mot['No_Prazo'] + df_mot['Atrasado']
        df_mot = df_mot.sort_values(by='Total', ascending=True)

        fig_mot = go.Figure()
        fig_mot.add_trace(go.Bar(y=df_mot['Motorista'], x=df_mot['No_Prazo'], name='No Prazo (D0)', orientation='h', marker_color='#22c55e'))
        fig_mot.add_trace(go.Bar(y=df_mot['Motorista'], x=df_mot['Atrasado'], name='Em Atraso (≥ D1)', orientation='h', marker_color='#ef4444'))
        fig_mot.update_layout(
            barmode='stack',
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=20, b=20, l=20, r=20),
            height=280,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_mot, use_container_width=True)

    st.markdown("#### 🔍 Filtros da Rota")
    f_col1, f_col2, f_col3, f_col4 = st.columns([2, 2, 2, 3])
    
    with f_col1:
        opcoes_aging = ["Todos", "🟢 No Prazo (D0)", "⚠️ Em Atraso (≥ D1)", "🔥 Críticos (≥ D2)"]
        filtro_aging = st.selectbox("Status de Aging:", opcoes_aging, key="f_aging_rota_itr")
        
    with f_col2:
        motoristas = ["Todos"] + sorted(df_rota['Motorista_Limpo'].unique().tolist())
        filtro_mot = st.selectbox("Motorista:", motoristas, key="f_mot_rota_itr")
        
    with f_col3:
        cidades = ["Todas"] + sorted(df_rota['Destination City'].unique().tolist())
        filtro_cid = st.selectbox("Cidade:", cidades, key="f_cid_rota_itr")
        
    with f_col4:
        busca_rota = st.text_input("Buscar Waybill, Bairro ou Endereço:", key="f_busca_rota_itr", placeholder="Ex: 3320..., Centro, etc.")

    df_view = df_rota.copy()
    if filtro_aging == "🟢 No Prazo (D0)":
        df_view = df_view[df_view['aging'] == 0]
    elif filtro_aging == "⚠️ Em Atraso (≥ D1)":
        df_view = df_view[df_view['aging'] >= 1]
    elif filtro_aging == "🔥 Críticos (≥ D2)":
        df_view = df_view[df_view['aging'] >= 2]
        
    if filtro_mot != "Todos":
        df_view = df_view[df_view['Motorista_Limpo'] == filtro_mot]
        
    if filtro_cid != "Todas":
        df_view = df_view[df_view['Destination City'] == filtro_cid]
        
    if busca_rota:
        termo = busca_rota.strip().lower()
        cond_awb = df_view['Waybill No'].astype(str).str.lower().str.contains(termo, na=False)
        cond_bai = df_view['Bairro_Display'].astype(str).str.lower().str.contains(termo, na=False)
        cond_end = df_view['Endereco_Display'].astype(str).str.lower().str.contains(termo, na=False)
        df_view = df_view[cond_awb | cond_bai | cond_end]

    st.markdown(f"<div style='margin-top: 15px;'><b>Exibindo {len(df_view)} pacotes em rota</b></div>", unsafe_allow_html=True)
    
    if not df_view.empty:
        cols_export = ['Waybill No', 'aging', 'Motorista_Limpo', 'Destination City', 'Bairro_Display', 'Endereco_Display', 'Receive Date']
        cols_export_existentes = [c for c in cols_export if c in df_view.columns]
        excel_bytes = exportar_para_excel(df_view[cols_export_existentes], "pacotes_em_rota_itr.xlsx")
        st.download_button(
            label="📥 Baixar Pacotes Filtrados (Excel)",
            data=excel_bytes,
            file_name=f"itr_em_rota_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_rota_itr"
        )

    motoristas_view = df_view['Motorista_Limpo'].value_counts()
    
    # Construção da Tabela Consolidada de Motoristas
    resumo_mots_tabela = []
    for mot, total_m in motoristas_view.items():
        df_m = df_view[df_view['Motorista_Limpo'] == mot]
        atraso_m = len(df_m[df_m['aging'] >= 1]) if 'aging' in df_m.columns else 0
        d0_m = len(df_m[df_m['aging'] == 0]) if 'aging' in df_m.columns else 0
        d1_m = len(df_m[df_m['aging'] == 1]) if 'aging' in df_m.columns else 0
        d2_m = len(df_m[df_m['aging'] >= 2]) if 'aging' in df_m.columns else 0
        pct_no_prazo = round((d0_m / total_m * 100), 1) if total_m > 0 else 100.0
        status_geral = "🟢 100% no prazo" if atraso_m == 0 else f"⚠️ {atraso_m} em atraso"
        
        resumo_mots_tabela.append({
            "Motorista": mot,
            "Total": total_m,
            "D0 (Hoje)": d0_m,
            "D1 (Atenção)": d1_m,
            "D2+ (Crítico)": d2_m,
            "Em Atraso": atraso_m,
            "% No Prazo": f"{pct_no_prazo}%",
            "Situação": status_geral
        })
    df_resumo_mots = pd.DataFrame(resumo_mots_tabela)

    # ==============================================================
    # 📢 GERADOR DE RELATÓRIO FORMATADO PARA O GRUPO DO WHATSAPP
    # ==============================================================
    with st.expander("📢 Copiar Resumo dos Motoristas para o Grupo do WhatsApp", expanded=True if not df_view.empty else False):
        st.markdown("Copie o relatório pronto e agrupado para enviar no grupo de entregas da equipe ITR:")
        
        c_fmt1, c_fmt2 = st.columns([7, 3])
        with c_fmt1:
            tipo_relatorio = st.radio(
                "Formato do Resumo:",
                ["Completo (Total + Prazos D0/Atraso)", "Simplificado (Apenas Nome e Total)", "⚠️ Apenas Motoristas com Atraso (≥ D1)"],
                horizontal=True,
                key="tipo_rel_wpp_rota_itr"
            )
        
        modo_fmt = "completo"
        if "Simplificado" in tipo_relatorio:
            modo_fmt = "simplificado"
        elif "Apenas Motoristas com Atraso" in tipo_relatorio:
            modo_fmt = "atrasados"

        texto_wpp = gerar_texto_grupo_whatsapp(df_view, "ITR", formato=modo_fmt)
        
        st.code(texto_wpp, language="text")
        
        col_btn_w1, col_btn_w2 = st.columns([3, 7])
        with col_btn_w1:
            msg_url = urllib.parse.quote(texto_wpp)
            st.link_button("📲 Enviar direto no WhatsApp", f"https://api.whatsapp.com/send?text={msg_url}")
        with col_btn_w2:
            st.caption("💡 Você também pode clicar no ícone de cópia no canto superior direito do texto acima.")

    # ==============================================================
    # 📋 VISÃO CONSOLIDADA EM TABELA (TODOS OS MOTORISTAS AGRUPADOS)
    # ==============================================================
    with st.expander(f"📋 Tabela Consolidada de Todos os Entregadores ({len(df_resumo_mots)} motoristas)", expanded=False):
        if not df_resumo_mots.empty:
            st.dataframe(df_resumo_mots, width="stretch", hide_index=True)

    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
    for mot, qtd in motoristas_view.items():
        df_m = df_view[df_view['Motorista_Limpo'] == mot].sort_values(by='aging', ascending=False)
        atrasados_m = len(df_m[df_m['aging'] >= 1])
        aviso_txt = f"⚠️ {atrasados_m} em atraso" if atrasados_m > 0 else "✅ 100% no prazo"
        
        with st.expander(f"👨‍✈️ {mot} — {qtd} pacotes ({aviso_txt})", expanded=(qtd > 0 and atrasados_m > 0)):
            if qtd > 120:
                st.warning("Volume alto. Exibindo em tabela direta:")
                tabela_cols = ['Waybill No', 'aging', 'Destination City', 'Bairro_Display', 'Endereco_Display']
                st.dataframe(df_m[tabela_cols], width="stretch", hide_index=True)
            else:
                h1, h2, h3, h4, h5 = st.columns([2, 1, 3, 3, 2])
                h1.markdown("**Waybill (Rastreio)**")
                h2.markdown("**Aging**")
                h3.markdown("**Bairro / Cidade**")
                h4.markdown("**Endereço**")
                h5.markdown("**Ação Imediata**")
                
                for _, row in df_m.iterrows():
                    awb = str(row['Waybill No'])
                    ag = int(row['aging'])
                    bairro = row['Bairro_Display']
                    cidade = row['Destination City']
                    endereco = row['Endereco_Display']
                    
                    if ag == 0:
                        badge_html = "<span class='badge badge-d0'>D0 (Hoje)</span>"
                    elif ag == 1:
                        badge_html = "<span class='badge badge-d1'>D1 (1 dia)</span>"
                    elif ag == 2:
                        badge_html = "<span class='badge badge-d2'>D2 (2 dias)</span>"
                    else:
                        badge_html = f"<span class='badge badge-d3'>D{ag} (Crítico)</span>"
                        
                    r1, r2, r3, r4, r5 = st.columns([2, 1, 3, 3, 2])
                    r1.write(f"`{awb}`")
                    r2.markdown(badge_html, unsafe_allow_html=True)
                    r3.write(f"**{bairro}** ({cidade})")
                    r4.write(endereco)
                    
                    btn_ph = r5.empty()
                    key_link = f"wpp_link_itr_ded_{awb}"
                    
                    if key_link in st.session_state:
                        btn_ph.markdown(st.session_state[key_link], unsafe_allow_html=True)
                    else:
                        if btn_ph.button("📱 WhatsApp", key=f"btn_r_itr_{awb}"):
                            u, s = obter_credenciais_itr()
                            if not u or not s:
                                btn_ph.error("Sem credenciais ITR.")
                            elif not buscar_dados_contato_imile:
                                btn_ph.error("Módulo de busca de contato não disponível.")
                            else:
                                with st.spinner("Buscando telefone..."):
                                    try:
                                        res = buscar_dados_contato_imile(awb, u, s)
                                    except Exception as e_err:
                                        res = {"erro": str(e_err), "telefone": "N/A"}
                                
                                if not res.get('telefone') or res['telefone'] == "N/A":
                                    msg_err = res.get('erro', 'Telefone não achado')
                                    btn_ph.warning(f"⚠️ {msg_err}")
                                    btn_ph.markdown(
                                        f'<a href="https://ds.imile.com/#/DSOperation/WaybillManagement/dsTrackQuery" target="_blank" style="color: #38bdf8; font-size: 0.8rem; text-decoration: underline;">🔗 Abrir iMile ({awb})</a>',
                                        unsafe_allow_html=True
                                    )
                                else:
                                    link = gerar_link_whatsapp(
                                        res['telefone'], res.get('nome', ''),
                                        awb, endereco, res.get('produto', '')
                                    )
                                    if link:
                                        html = f'<a href="{link}" target="_blank" class="wpp-btn">Abrir WhatsApp</a>'
                                        st.session_state[key_link] = html
                                        btn_ph.markdown(html, unsafe_allow_html=True)

# ==========================================
# RENDERIZAÇÃO DA ABA 2: PISO POR BAIRRO
# ==========================================
def render_aba_piso(df_piso):
    if df_piso.empty:
        st.success("🎉 O piso da base ITR está totalmente limpo! Nenhum pacote pendente de expedição.")
        return

    total_piso = len(df_piso)
    total_bairros = df_piso['Bairro_Display'].nunique()
    
    df_loc = df_piso[df_piso['Tipo_Localidade'] == '🏙️ Itabira (Urbano)']
    df_int = df_piso[df_piso['Tipo_Localidade'] == '🏞️ Interior Satélite']
    df_fora = df_piso[df_piso['Tipo_Localidade'] == '⚠️ Fora de Rota (Inversão)']
    
    p1, p2, p3, p4, p5 = st.columns(5)
    p1.metric("🏢 Total no Piso", f"{total_piso}")
    p2.metric("📍 Bairros Distintos", f"{total_bairros}")
    p3.metric("🏙️ Itabira Urbana", f"{len(df_loc)}")
    p4.metric("🏞️ Interior Satélite", f"{len(df_int)}")
    p5.metric("⚠️ Fora de Rota", f"{len(df_fora)}")

    st.markdown("<hr style='border-color: #1e293b; margin: 15px 0;'>", unsafe_allow_html=True)

    col_chart, col_status = st.columns([7, 3])
    with col_chart:
        st.markdown("##### 📍 Top 15 Bairros com Maior Volume no Piso")
        top_bairros = df_piso['Bairro_Display'].value_counts().head(15).reset_index()
        top_bairros.columns = ['Bairro', 'Volume']
        top_bairros = top_bairros.sort_values(by='Volume', ascending=True)

        fig_piso = px.bar(
            top_bairros, x='Volume', y='Bairro', orientation='h', text='Volume',
            color='Volume', color_continuous_scale="Blues"
        )
        fig_piso.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=20, b=20, l=20, r=20),
            coloraxis_showscale=False,
            height=320
        )
        st.plotly_chart(fig_piso, use_container_width=True)

    with col_status:
        st.markdown("##### 🏷️ Status do Scan no Piso")
        status_counts = df_piso['Last scan type'].value_counts().reset_index()
        status_counts.columns = ['Status', 'Qtd']
        fig_status = px.pie(
            status_counts, names='Status', values='Qtd', hole=0.45,
            color_discrete_sequence=px.colors.qualitative.Pastel
        )
        fig_status.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=20, b=20, l=20, r=20),
            height=320,
            showlegend=True,
            legend=dict(orientation="h", y=-0.1)
        )
        st.plotly_chart(fig_status, use_container_width=True)

    st.markdown("#### 🔍 Filtros do Piso")
    pf1, pf2, pf3, pf4 = st.columns([2, 2, 2, 3])
    
    with pf1:
        tipos_loc = ["Todos", "🏙️ Itabira (Urbano)", "🏞️ Interior Satélite", "⚠️ Fora de Rota (Inversão)"]
        filtro_loc = st.selectbox("Localidade:", tipos_loc, key="f_loc_piso_itr")
        
    with pf2:
        status_list = ["Todos"] + sorted(df_piso['Last scan type'].dropna().unique().tolist())
        filtro_status_piso = st.selectbox("Status Scan:", status_list, key="f_status_piso_itr")
        
    with pf3:
        opcoes_ordem_piso = [
            "🔥 Mais Antigo Primeiro (Maior Aging)",
            "🌱 Mais Novo Primeiro (Menor Aging)",
            "📊 Maior Volume Primeiro",
            "🔤 Alfabética"
        ]
        ordem = st.selectbox("Ordenar Bairros e Pacotes:", opcoes_ordem_piso, index=0, key="f_ordem_piso_itr")
        
    with pf4:
        busca_piso = st.text_input("Buscar Bairro, Cidade ou Waybill:", key="f_busca_piso_itr", placeholder="Ex: Centro, Pará, 610...")

    df_piso_view = df_piso.copy()
    if filtro_loc != "Todos":
        df_piso_view = df_piso_view[df_piso_view['Tipo_Localidade'] == filtro_loc]
        
    if filtro_status_piso != "Todos":
        df_piso_view = df_piso_view[df_piso_view['Last scan type'] == filtro_status_piso]
        
    if busca_piso:
        t = busca_piso.strip().lower()
        c_awb = df_piso_view['Waybill No'].astype(str).str.lower().str.contains(t, na=False)
        c_bai = df_piso_view['Bairro_Display'].astype(str).str.lower().str.contains(t, na=False)
        c_cid = df_piso_view['Destination City'].astype(str).str.lower().str.contains(t, na=False)
        df_piso_view = df_piso_view[c_awb | c_bai | c_cid]

    # Determina a direção de ordenação do Aging (True = Menor pro Maior, False = Maior pro Menor)
    aging_asc = True if "Menor Aging" in ordem or "Mais Novo" in ordem else False

    # Ordena a visão do piso pelo aging conforme escolha
    if 'aging' in df_piso_view.columns:
        df_piso_view = df_piso_view.sort_values(by=['aging', 'Bairro_Display'], ascending=[aging_asc, True])

    rotulo_ordem = "do menor para o maior aging (mais novos primeiro)" if aging_asc else "do maior para o menor aging (mais antigos primeiro)"
    st.markdown(f"<div style='margin-top: 15px;'><b>Exibindo {len(df_piso_view)} pacotes no piso (ordenados {rotulo_ordem})</b></div>", unsafe_allow_html=True)

    if not df_piso_view.empty:
        cols_piso_exp = ['Waybill No', 'aging', 'Last scan type', 'Destination City', 'Bairro_Display', 'Endereco_Display', 'Tipo_Localidade', 'Receive Date']
        cols_piso_exp_existentes = [c for c in cols_piso_exp if c in df_piso_view.columns]
        excel_piso_bytes = exportar_para_excel(df_piso_view[cols_piso_exp_existentes], "inventario_piso_itr.xlsx")
        st.download_button(
            label="📥 Baixar Piso por Bairro (Excel)",
            data=excel_piso_bytes,
            file_name=f"itr_piso_bairros_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_piso_itr"
        )

    if "Maior Aging" in ordem or "Mais Antigo" in ordem:
        # Bairros com pacotes mais antigos no topo
        resumo_bairros = df_piso_view.groupby('Bairro_Display').agg(
            ag_metric=('aging', 'max'),
            qtd=('Waybill No', 'count')
        ).sort_values(by=['ag_metric', 'qtd'], ascending=[False, False])
        bairros_lista = resumo_bairros.index.tolist()
    elif "Menor Aging" in ordem or "Mais Novo" in ordem:
        # Bairros com pacotes mais novos no topo
        resumo_bairros = df_piso_view.groupby('Bairro_Display').agg(
            ag_metric=('aging', 'min'),
            qtd=('Waybill No', 'count')
        ).sort_values(by=['ag_metric', 'qtd'], ascending=[True, False])
        bairros_lista = resumo_bairros.index.tolist()
    elif "Volume" in ordem:
        bairros_lista = df_piso_view['Bairro_Display'].value_counts().index.tolist()
    else:
        bairros_lista = sorted(df_piso_view['Bairro_Display'].unique().tolist())

    for bairro_nome in bairros_lista:
        df_b = df_piso_view[df_piso_view['Bairro_Display'] == bairro_nome].copy()
        qtd_bairro = len(df_b)
        
        # Ordenação rigorosa dos pacotes no bairro
        if 'aging' in df_b.columns:
            df_b = df_b.sort_values(by=['aging', 'Waybill No'], ascending=[aging_asc, True])

        cidade_b = df_b['Destination City'].iloc[0] if not df_b.empty else ""
        tipo_loc_b = df_b['Tipo_Localidade'].iloc[0] if not df_b.empty else ""
        
        if aging_asc:
            ref_ag = int(df_b['aging'].min()) if 'aging' in df_b.columns and not df_b.empty else 0
            tag_ref = "Mais novo"
        else:
            ref_ag = int(df_b['aging'].max()) if 'aging' in df_b.columns and not df_b.empty else 0
            tag_ref = "Mais antigo"

        if ref_ag == 0:
            badge_ag_txt = "🟢 D0 (Hoje)"
        elif ref_ag == 1:
            badge_ag_txt = "⚠️ D1 (1 dia)"
        elif ref_ag == 2:
            badge_ag_txt = "🔥 D2 (2 dias)"
        else:
            badge_ag_txt = f"🚨 D{ref_ag} ({ref_ag} dias)"
            
        icone = "⚠️" if "Fora de Rota" in tipo_loc_b else "📍"
        titulo_expander = f"{icone} {bairro_nome} ({cidade_b}) — {qtd_bairro} pacotes | {tag_ref}: {badge_ag_txt}"
        
        with st.expander(titulo_expander, expanded=(qtd_bairro >= 5 or (not aging_asc and ref_ag >= 2))):
            if qtd_bairro > 80:
                st.warning(f"Volume alto neste bairro. Exibindo em tabela direta ({rotulo_ordem}):")
                cols_grid = [c for c in ['Waybill No', 'aging', 'Last scan type', 'Endereco_Display', 'Receive Date'] if c in df_b.columns]
                st.dataframe(df_b[cols_grid], width="stretch", hide_index=True)
            else:
                p_cols_h = st.columns([2, 1, 2, 3, 2])
                p_cols_h[0].markdown("**Waybill (Rastreio)**")
                p_cols_h[1].markdown("**Aging**")
                p_cols_h[2].markdown("**Status no Piso**")
                p_cols_h[3].markdown("**Endereço de Entrega**")
                p_cols_h[4].markdown("**Ação / WhatsApp**")
                
                for _, row in df_b.iterrows():
                    awb = str(row['Waybill No'])
                    scan = row['Last scan type']
                    end = row['Endereco_Display']
                    ag = int(row.get('aging', 0))
                    
                    if ag == 0:
                        badge_html = "<span class='badge badge-d0'>D0</span>"
                    elif ag == 1:
                        badge_html = "<span class='badge badge-d1'>D1</span>"
                    elif ag == 2:
                        badge_html = "<span class='badge badge-d2'>D2</span>"
                    else:
                        badge_html = f"<span class='badge badge-d3'>D{ag}</span>"
                        
                    pr1, pr2, pr3, pr4, pr5 = st.columns([2, 1, 2, 3, 2])
                    pr1.write(f"`{awb}`")
                    pr2.markdown(badge_html, unsafe_allow_html=True)
                    pr3.markdown(f"<span class='badge badge-piso'>{scan}</span>", unsafe_allow_html=True)
                    pr4.write(end)
                    
                    btn_ph = pr5.empty()
                    k_link = f"wpp_piso_itr_{awb}"
                    if k_link in st.session_state:
                        btn_ph.markdown(st.session_state[k_link], unsafe_allow_html=True)
                    else:
                        if btn_ph.button("📱 Contato", key=f"btn_p_itr_{awb}"):
                            u, s = obter_credenciais_itr()
                            if not u or not s:
                                btn_ph.error("Sem credenciais")
                            elif not buscar_dados_contato_imile:
                                btn_ph.error("Módulo de busca de contato não disponível.")
                            else:
                                with st.spinner("Buscando dados de contato na iMile..."):
                                    try:
                                        res = buscar_dados_contato_imile(awb, u, s)
                                    except Exception as e_err:
                                        res = {"erro": str(e_err), "telefone": "N/A"}
                                
                                if not res.get('telefone') or res['telefone'] == "N/A":
                                    msg_err = res.get('erro', 'Telefone não achado')
                                    btn_ph.warning(f"⚠️ {msg_err}")
                                    btn_ph.markdown(
                                        f'<a href="https://ds.imile.com/#/DSOperation/WaybillManagement/dsTrackQuery" target="_blank" style="color: #38bdf8; font-size: 0.8rem; text-decoration: underline;">🔗 Abrir iMile ({awb})</a>',
                                        unsafe_allow_html=True
                                    )
                                else:
                                    link = gerar_link_whatsapp(
                                        res['telefone'], res.get('nome', ''),
                                        awb, end, res.get('produto', '')
                                    )
                                    if link:
                                        html = f'<a href="{link}" target="_blank" class="wpp-btn">Abrir WhatsApp</a>'
                                        st.session_state[k_link] = html
                                        btn_ph.markdown(html, unsafe_allow_html=True)

# ==========================================
# RENDERIZAÇÃO DA ABA 3: CONSULTA WAYBILL
# ==========================================
def render_aba_busca(df_itr):
    st.markdown("#### 🔎 Localizador Universal de Pacote (Base ITR)")
    st.write("Digite ou bipe o número da Waybill para ver imediatamente status, entregador, aging e dados de contato.")
    
    codigo_busca = st.text_input("Código de Rastreio (Waybill No):", placeholder="Ex: 3320176083220, 6101626606010...", key="busca_universal_awb_itr")
    
    if codigo_busca:
        cd = codigo_busca.strip()
        match = df_itr[df_itr['Waybill No'].astype(str).str.contains(cd, na=False)]
        
        if match.empty:
            st.error(f"❌ Pacote `{cd}` não foi encontrado no inventário ativo da base ITR.")
        else:
            st.success(f"Encontrado(s) {len(match)} registro(s) correspondente(s):")
            for _, r in match.iterrows():
                awb = str(r['Waybill No'])
                is_r = r['is_rota']
                status_txt = "🚚 EM ROTA COM MOTORISTA" if is_r else f"🏢 NO PISO DA BASE ({r['Last scan type']})"
                cor_status = "#38bdf8" if is_r else "#f97316"
                
                with st.container():
                    st.markdown(f"""
                        <div style='background: #1e293b; border-left: 5px solid {cor_status}; border-radius: 8px; padding: 16px; margin-bottom: 12px;'>
                            <div style='display: flex; justify-content: space-between; align-items: center;'>
                                <span style='font-size: 1.2rem; font-weight: 800; color: #f8fafc;'>Waybill: {awb}</span>
                                <span style='font-weight: 700; color: {cor_status};'>{status_txt}</span>
                            </div>
                            <hr style='border-color: #334155; margin: 10px 0;'>
                            <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; color: #cbd5e1;'>
                                <div><b>Motorista:</b> {r['Motorista_Limpo']}</div>
                                <div><b>Aging:</b> {r['aging']} dias</div>
                                <div><b>Cidade:</b> {r['Destination City']}</div>
                                <div><b>Bairro:</b> {r['Bairro_Display']}</div>
                                <div style='grid-column: 1 / -1;'><b>Endereço:</b> {r['Endereco_Display']}</div>
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    col_b1, col_b2 = st.columns([2, 8])
                    with col_b1:
                        if st.button("📱 Pesquisar WhatsApp", key=f"univ_wpp_itr_{awb}"):
                            u, s = obter_credenciais_itr()
                            if not u or not s:
                                st.error("Sem credenciais ITR.")
                            elif not buscar_dados_contato_imile:
                                st.error("Módulo de busca de contato não disponível.")
                            else:
                                with st.spinner("Buscando dados de contato na iMile..."):
                                    try:
                                        res = buscar_dados_contato_imile(awb, u, s)
                                    except Exception as e_err:
                                        res = {"erro": str(e_err), "telefone": "N/A"}
                                
                                if not res.get('telefone') or res['telefone'] == "N/A":
                                    msg_err = res.get('erro', 'Telefone não achado no sistema.')
                                    st.warning(f"⚠️ {msg_err}")
                                    st.markdown(
                                        f'<a href="https://ds.imile.com/#/DSOperation/WaybillManagement/dsTrackQuery" target="_blank" style="color: #38bdf8; font-size: 0.85rem; text-decoration: underline;">🔗 Abrir consulta direta no portal iMile ({awb})</a>',
                                        unsafe_allow_html=True
                                    )
                                else:
                                    link = gerar_link_whatsapp(
                                        res['telefone'], res.get('nome', ''),
                                        awb, r['Endereco_Display'], res.get('produto', '')
                                    )
                                    if link:
                                        st.markdown(f'<a href="{link}" target="_blank" class="wpp-btn">Abrir WhatsApp com {res.get("nome", "Cliente")}</a>', unsafe_allow_html=True)

# ==========================================
# FUNÇÃO PRINCIPAL
# ==========================================
def main():
    if os.path.exists("c:/bots/logo.png"):
        st.logo("c:/bots/logo.png", size="large")
        
    df_itr = carregar_dados_itr()
    render_header(df_itr)
    
    st.markdown("<hr style='border-color: #334155; margin: 16px 0 24px 0;'>", unsafe_allow_html=True)
    
    render_dashboard()

if __name__ == "__main__":
    main()
