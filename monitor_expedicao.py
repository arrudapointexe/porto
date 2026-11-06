import streamlit as st
import pandas as pd
import os
import io
import re
import json
import urllib.parse
from datetime import datetime, timedelta, date
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

try:
    from aba_backlog import render_aba_backlog
except Exception as _e_bk:
    print(f"Aviso: aba_backlog indisponível: {_e_bk}")
    render_aba_backlog = None

# ==========================================
# CONFIGURAÇÃO DA PÁGINA STREAMLIT
# ==========================================
st.set_page_config(
    page_title="Monitor de Expedição — Porto Guimarães",
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
    
    /* Badges */
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
    .badge-base { background-color: rgba(56, 189, 248, 0.2); color: #38bdf8; border: 1px solid #0284c7; }
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
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #0f172a;
        border-right: 1px solid #1e293b;
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
        'Fnix': 'Fênix', 'Estao': 'Estação', 'Estao': 'Estação', 'Cssia': 'Cássia', 'gua': 'Água',
        'Itamb': 'Itambé', 'Antnio': 'Antônio', 'Gonalo': 'Gonçalo', 'Sebastio': 'Sebastião',
        'Passabm': 'Passabém', 'Carmsia': 'Carmésia', 'Suau': 'Suaçuí', 'Manhuau': 'Manhuaçu',
        'Brbara': 'Bárbara', 'Abboras': 'Abóboras', 'Efignia': 'Efigênia', 'Par': 'Pará',
        'Esperana': 'Esperança', 'Gois': 'Goiás', 'Nmero': 'Número', 'Ibituruna': 'Ibituruna'
    }
    for errado, correto in substituicoes.items():
        s = s.replace(errado, correto)
    s = s.replace('', '')
    return s.strip()

def obter_credenciais_base(sigla_base):
    """Retorna credenciais do config.py ou st.secrets de acordo com a base do pacote."""
    sigla = str(sigla_base or '').strip().upper()
    try:
        u_sec = st.secrets.get(f"IMILE_{sigla}_USER")
        s_sec = st.secrets.get(f"IMILE_{sigla}_PASS") or st.secrets.get(f"{sigla}_IMILE_PASS")
        if u_sec and s_sec:
            return u_sec, s_sec
    except Exception:
        pass
    if config and hasattr(config, 'BASES_SLA'):
        for b, u, s in config.BASES_SLA:
            if str(b).strip().upper() == sigla and u and s:
                return u, s
    # Fallback para ITR ou JML
    return os.getenv("IMILE_ITR_USER"), os.getenv("ITR_IMILE_PASS")

def formatar_telefone(tel):
    """Higieniza número de telefone para o formato padrão internacional 55+DDD+NUM."""
    tel_limpo = ''.join(filter(str.isdigit, str(tel)))
    if not tel_limpo:
        return ""
    if not tel_limpo.startswith('55') and len(tel_limpo) <= 11:
        tel_limpo = f"55{tel_limpo}"
    return tel_limpo

def gerar_link_whatsapp(telefone, nome, awb, endereco, base_sigla="", produto=""):
    """Gera link wa.me com mensagem profissional pré-formatada."""
    tel = formatar_telefone(telefone)
    if not tel:
        return None
    nome_fmt = nome if nome and nome != "N/A" else "Cliente"
    prod_fmt = f"\n📦 *Produto:* {produto}" if produto and produto != "N/A" else ""
    end_fmt = f"\n📍 *Endereço:* {endereco}" if endereco and endereco != "N/A" else ""
    base_info = f" (Base {base_sigla})" if base_sigla else ""
    
    msg = (
        f"Olá {nome_fmt}, sou da equipe de entregas da *Porto Guimarães Express*{base_info}.\n"
        f"Estamos acompanhando seu pedido:{prod_fmt}\n"
        f"🔖 *Rastreio:* {awb}{end_fmt}\n\n"
        f"Gostaria de confirmar se você já recebeu esta encomenda ou se precisa de auxílio com a entrega?"
    )
    msg_enc = urllib.parse.quote(msg)
    return f"https://wa.me/{tel}?text={msg_enc}"

def gerar_texto_grupo_whatsapp(df_subset, base_nome, formato="completo", filtro_regiao="TODOS"):
    """Gera texto formatado com o resumo dos motoristas para colar no grupo de WhatsApp, com suporte a separação LOC / INT."""
    agora_str = datetime.now().strftime("%d/%m/%Y às %H:%M")
    
    if filtro_regiao == "LOC":
        df_target = df_subset[df_subset['Regiao_Motorista'] == 'LOC'] if 'Regiao_Motorista' in df_subset.columns else df_subset
        sufixo_tit = " — LOC (LOCAL / URBANO)"
    elif filtro_regiao == "INT":
        df_target = df_subset[df_subset['Regiao_Motorista'] == 'INT'] if 'Regiao_Motorista' in df_subset.columns else df_subset
        sufixo_tit = " — INT (INTERIOR / SATÉLITES)"
    else:
        df_target = df_subset
        sufixo_tit = ""

    total_pacotes = len(df_target)
    mots_unicos = df_target['Motorista_Limpo'].nunique() if 'Motorista_Limpo' in df_target.columns else 0
    total_atraso = len(df_target[df_target['aging'] >= 1]) if 'aging' in df_target.columns else 0
    total_d0 = len(df_target[df_target['aging'] == 0]) if 'aging' in df_target.columns else 0
    base_header = base_nome if base_nome else "Todas as Bases"

    def formatar_linhas(df_dados_mots, prefixar_tag=False):
        contagem = df_dados_mots['Motorista_Limpo'].value_counts() if 'Motorista_Limpo' in df_dados_mots.columns else pd.Series()
        linhas = []
        for mot, total_m in contagem.items():
            df_m = df_dados_mots[df_dados_mots['Motorista_Limpo'] == mot]
            atraso_m = len(df_m[df_m['aging'] >= 1]) if 'aging' in df_m.columns else 0
            d0_m = len(df_m[df_m['aging'] == 0]) if 'aging' in df_m.columns else 0
            d1_m = len(df_m[df_m['aging'] == 1]) if 'aging' in df_m.columns else 0
            d2_m = len(df_m[df_m['aging'] >= 2]) if 'aging' in df_m.columns else 0
            base_m = df_m['Base'].iloc[0] if not df_m.empty and 'Base' in df_m.columns else ""
            reg_m = df_m['Regiao_Motorista'].iloc[0] if not df_m.empty and 'Regiao_Motorista' in df_m.columns else ""
            
            tag_str = ""
            if prefixar_tag:
                if reg_m and base_header != "Todas as Bases":
                    tag_str = f"[{reg_m}] "
                elif base_m and reg_m:
                    tag_str = f"[{base_m} {reg_m}] "
                elif base_m:
                    tag_str = f"[{base_m}] "

            if formato == "simplificado":
                linhas.append(f"👤 *{tag_str}{mot}:* {total_m} pacote(s)")
            elif formato == "atrasados":
                if atraso_m > 0:
                    detalhes_atr = []
                    if d1_m > 0: detalhes_atr.append(f"{d1_m} D1")
                    if d2_m > 0: detalhes_atr.append(f"{d2_m} D2+")
                    txt_atr = f" ({' + '.join(detalhes_atr)})" if detalhes_atr else ""
                    linhas.append(f"⚠️ *{tag_str}{mot}:* {atraso_m} em atraso{txt_atr} | Total: {total_m}")
            else: # completo
                if atraso_m == 0:
                    status_txt = "✅ 100% no prazo"
                else:
                    detalhes_atr = []
                    if d1_m > 0: detalhes_atr.append(f"{d1_m} D1")
                    if d2_m > 0: detalhes_atr.append(f"{d2_m} D2+")
                    suf_atr = f" ({', '.join(detalhes_atr)})" if detalhes_atr else ""
                    status_txt = f"{d0_m} D0 | ⚠️ {atraso_m} em atraso{suf_atr}"
                linhas.append(f"👤 *{tag_str}{mot}:* {total_m} pacotes ({status_txt})")
        return linhas

    if filtro_regiao == "SEPARADO" and 'Regiao_Motorista' in df_subset.columns:
        df_loc = df_subset[df_subset['Regiao_Motorista'] == 'LOC']
        df_int = df_subset[df_subset['Regiao_Motorista'] == 'INT']
        
        linhas_loc = formatar_linhas(df_loc)
        linhas_int = formatar_linhas(df_int)
        
        bloco_loc = "\n".join(linhas_loc) if linhas_loc else "Nenhum motorista LOC com pacotes."
        bloco_int = "\n".join(linhas_int) if linhas_int else "Nenhum motorista INT com pacotes."
        
        corpo = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏙️ *ENTREGADORES LOC (LOCAL / URBANO) — {len(df_loc)} pacotes ({df_loc['Motorista_Limpo'].nunique()} mot.):*\n\n"
            f"{bloco_loc}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏞️ *ENTREGADORES INT (INTERIOR / CIDADES) — {len(df_int)} pacotes ({df_int['Motorista_Limpo'].nunique()} mot.):*\n\n"
            f"{bloco_int}"
        )
    else:
        linhas = formatar_linhas(df_target, prefixar_tag=(filtro_regiao == "TODOS"))
        if formato == "atrasados" and not linhas:
            corpo = "✅ Parabéns equipe! Nenhum entregador com pacotes em atraso no momento! 🎉"
        else:
            corpo = "\n".join(linhas) if linhas else "Nenhum pacote em rota."

    texto = (
        f"🚚 *RESUMO DE EXPEDIÇÃO EM ROTA{sufixo_tit}*\n"
        f"🏢 *Base:* {base_header}\n"
        f"📅 *Atualizado:* {agora_str}\n\n"
        f"📦 *Total em Rota:* {total_pacotes} pacotes\n"
        f"👨‍✈️ *Entregadores:* {mots_unicos} motoristas\n"
        f"🟢 *No Prazo (D0):* {total_d0} pacotes\n"
        f"⚠️ *Em Atraso (≥ D1):* {total_atraso} pacotes\n\n"
        f"{corpo}\n\n"
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
# PROCESSAMENTO DOS DADOS (COMUM LOCAL / NUVEM)
# ==========================================
def processar_dataframe_todas_bases(df):
    if df is None or df.empty:
        return pd.DataFrame()
        
    df = df.copy()
    df.columns = df.columns.astype(str).str.strip()
    
    if df.empty:
        return df
        
    # Normalização de Base
    if 'Base' in df.columns:
        df['Base'] = df['Base'].astype(str).str.strip().str.upper()
    else:
        df['Base'] = "DESCONHECIDA"
        
    # Normalização de Aging
    if 'aging' in df.columns:
        df['aging'] = pd.to_numeric(df['aging'], errors='coerce').fillna(0).astype(int)
    else:
        df['aging'] = 0

    # Normalização de Datas de Operação e Recebimento
    hoje_dt = datetime.now().date()
    if 'Receive Date' in df.columns:
        dt_raw = pd.to_datetime(df['Receive Date'], errors='coerce')
        dt_series = dt_raw.dt.date
    else:
        dt_raw = pd.Series(pd.NaT, index=df.index)
        dt_series = pd.Series(None, index=df.index)

    fallback_dt = df['aging'].apply(
        lambda ag: hoje_dt - timedelta(days=int(ag)) if pd.notna(ag) else hoje_dt
    )
    df['Data_Operacao'] = dt_series.fillna(fallback_dt)

    def formatar_data_display(row):
        raw = row.get('Receive Date')
        if pd.notna(raw) and str(raw).strip() and str(raw).lower() != 'nan':
            try:
                dt = pd.to_datetime(raw)
                return dt.strftime('%d/%m/%Y %H:%M')
            except:
                pass
        d_op = row.get('Data_Operacao')
        if pd.notna(d_op):
            try:
                return d_op.strftime('%d/%m/%Y')
            except:
                return str(d_op)
        return "N/A"

    df['Data_Display'] = df.apply(formatar_data_display, axis=1)
        
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
    
    # Motorista Amigável (remove prefixos tipo '(ITR LOC) ', '(JML INT) ', etc.)
    def resolver_motorista(val):
        m = str(val).strip()
        if not m or m.lower() in ['nan', 'none', '']:
            return "Não Atribuído"
        return re.sub(r'^\([A-Za-z0-9_]+\s+(LOC|INT)\)\s*', '', m).strip()
        
    if 'Driver Name' in df.columns:
        df['Motorista_Limpo'] = df['Driver Name'].apply(resolver_motorista)
    else:
        df['Motorista_Limpo'] = "Não Atribuído"
        
    # Classificação de Localidade
    def resolver_tipo_localidade(row):
        abrangencia = str(row.get('abrangencia', '1')).strip()
        if abrangencia == '0':
            return "⚠️ Fora de Rota (Inversão)"
            
        cidade = str(row.get('Destination City', '')).strip().upper()
        base = str(row.get('Base', '')).strip().upper()
        
        cidades_polo = {
            'ITR': 'ITABIRA',
            'JML': 'JOAO MONLEVADE',
            'SNB': 'SANTA BARBARA'
        }
        polo = cidades_polo.get(base, '')
        if polo and polo in cidade:
            return "🏙️ Cidade Polo (Urbano)"
        return "🏞️ Interior Satélite"
        
    df['Tipo_Localidade'] = df.apply(resolver_tipo_localidade, axis=1)
    
    # Classificação do Entregador: LOC (Local / Urbano) vs INT (Interior / Satélite)
    def resolver_regiao_motorista(row):
        d_name = str(row.get('Driver Name', '')).strip().upper()
        if re.search(r'\bINT\b', d_name):
            return "INT"
        if re.search(r'\bLOC\b', d_name):
            return "LOC"
        tipo_loc = str(row.get('Tipo_Localidade', ''))
        if 'Polo' in tipo_loc or 'Urbano' in tipo_loc:
            return "LOC"
        elif 'Interior' in tipo_loc:
            return "INT"
        return "LOC"

    df['Regiao_Motorista'] = df.apply(resolver_regiao_motorista, axis=1)
    
    return df

@st.cache_data(show_spinner=False)
def _carregar_dados_todas_bases_local_cached(mtime):
    caminho = "c:/bots/latencia_consolidada.xlsx"
    if not os.path.exists(caminho):
        return pd.DataFrame(), ""
    try:
        df = pd.read_excel(caminho)
        att_str = datetime.fromtimestamp(mtime).strftime("%d/%m/%Y às %H:%M:%S")
        return processar_dataframe_todas_bases(df), att_str
    except Exception as e:
        print(f"Erro ao ler Excel local: {e}")
        return pd.DataFrame(), ""

@st.cache_data(ttl=60, show_spinner=False)
def _carregar_dados_todas_bases_sheets_cached():
    try:
        creds = obter_credenciais_google()
        if not creds:
            return pd.DataFrame(), "Sem credenciais Google"
        cliente = gspread.authorize(creds)
        planilha = cliente.open("acareaBase").worksheet("Expedicao_Geral")
        dados = planilha.get_all_values()
        if not dados or len(dados) < 2:
            return pd.DataFrame(), "Aba vazia"
        df_raw = pd.DataFrame(dados[1:], columns=dados[0])
        att_str = "Recentemente"
        if 'Atualizado_Em' in df_raw.columns and not df_raw['Atualizado_Em'].empty:
            att_str = str(df_raw['Atualizado_Em'].iloc[0]).strip()
        return processar_dataframe_todas_bases(df_raw), att_str
    except Exception as e:
        print(f"Erro ao carregar do Google Sheets: {e}")
        return pd.DataFrame(), "Erro Sheets"

def carregar_dados_todas_bases():
    # 1. Tenta carregar do arquivo local se existir (modo desktop)
    caminho_local = "c:/bots/latencia_consolidada.xlsx"
    if os.path.exists(caminho_local):
        try:
            mtime = os.path.getmtime(caminho_local)
            df, att_str = _carregar_dados_todas_bases_local_cached(mtime)
            if df is not None and not df.empty:
                st.session_state['expedicao_origem_dados'] = "Computador Local"
                st.session_state['expedicao_ultima_att'] = att_str
                st.session_state['last_all_bases_df'] = df
                return df
        except Exception:
            pass

    # 2. Modo Nuvem (Google Sheets acareaBase > Expedicao_Geral)
    df, att_str = _carregar_dados_todas_bases_sheets_cached()
    if df is not None and not df.empty:
        st.session_state['expedicao_origem_dados'] = "Google Sheets (acareaBase)"
        st.session_state['expedicao_ultima_att'] = att_str
        st.session_state['last_all_bases_df'] = df
        return df

    return st.session_state.get('last_all_bases_df', pd.DataFrame())

def exportar_para_excel(df, nome_arquivo):
    """Gera buffer de bytes para download em Excel."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Expedicao')
    return output.getvalue()

# ==========================================
# CABEÇALHO GLOBAL & STATUS DO ROBÔ
# ==========================================
def render_header():
    ultima_att_str = st.session_state.get('expedicao_ultima_att', 'Recentemente')
    origem_dados = st.session_state.get('expedicao_origem_dados', 'Google Sheets')
            
    col_t1, col_t2 = st.columns([6, 4])
    with col_t1:
        st.markdown("""
            <div style='display: flex; align-items: center; gap: 14px;'>
                <span style='font-size: 2.8rem;'>📦</span>
                <div>
                    <h1 style='margin: 0; font-size: 1.9rem;'>Monitor de Expedição — Painel Geral</h1>
                    <p style='margin: 2px 0 0 0; color: #94a3b8; font-size: 0.95rem;'>
                        Porto Guimarães Express | Gestão em Tempo Real de Rota e Piso
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
    df_raw = carregar_dados_todas_bases()
    
    if df_raw.empty:
        st.warning("⚠️ Nenhum dado de expedição encontrado no momento. O robô pode estar sincronizando neste momento.")
        if st.button("🔄 Forçar Recarregamento"):
            st.rerun()
        return

    # Filtros Superiores: Base e Data
    bases_disponiveis = ["Todas as Bases"] + sorted(df_raw['Base'].dropna().unique().tolist())
    
    # Calcular datas mínimas e máximas dos dados
    datas_validas = df_raw['Data_Operacao'].dropna()
    hoje = datetime.now().date()
    min_data_disp = datas_validas.min() if not datas_validas.empty else hoje
    max_data_disp = datas_validas.max() if not datas_validas.empty else hoje

    col_sel_base, col_modo_data, col_picker = st.columns([3, 3, 4])
    with col_sel_base:
        base_selecionada = st.selectbox("🏢 Base Operacional:", bases_disponiveis, key="filtro_base_global")
        
    with col_modo_data:
        opcoes_data = [
            "Todas as Datas (Geral)",
            "🟢 Hoje",
            "🟡 Ontem",
            "📆 Últimos 3 dias",
            "📆 Últimos 7 dias",
            "📆 Últimos 15 dias",
            "📆 Mês Atual",
            "🎯 Data Específica",
            "🗓️ Intervalo Personalizado"
        ]
        modo_data_selecionado = st.selectbox("📅 Filtro de Data (Entrada):", opcoes_data, key="filtro_modo_data_global")

    data_inicio = None
    data_fim = None
    texto_periodo = "Todo o período"

    with col_picker:
        if modo_data_selecionado == "🎯 Data Específica":
            val_especifica = st.date_input(
                "Selecione o Dia:",
                value=max_data_disp,
                min_value=min_data_disp,
                max_value=max(max_data_disp, hoje),
                format="DD/MM/YYYY",
                key="filtro_data_especifica"
            )
            data_inicio = val_especifica
            data_fim = val_especifica
            texto_periodo = f"Dia {val_especifica.strftime('%d/%m/%Y')}"
            
        elif modo_data_selecionado == "🗓️ Intervalo Personalizado":
            val_intervalo = st.date_input(
                "Selecione o Período (De / Até):",
                value=(max(min_data_disp, hoje - timedelta(days=7)), max_data_disp),
                min_value=min_data_disp,
                max_value=max(max_data_disp, hoje),
                format="DD/MM/YYYY",
                key="filtro_data_intervalo"
            )
            if isinstance(val_intervalo, (tuple, list)):
                if len(val_intervalo) == 2:
                    data_inicio = val_intervalo[0]
                    data_fim = val_intervalo[1]
                    texto_periodo = f"{data_inicio.strftime('%d/%m/%Y')} até {data_fim.strftime('%d/%m/%Y')}"
                elif len(val_intervalo) == 1:
                    data_inicio = val_intervalo[0]
                    data_fim = val_intervalo[0]
                    texto_periodo = f"{data_inicio.strftime('%d/%m/%Y')}"
        elif modo_data_selecionado == "🟢 Hoje":
            data_inicio = hoje
            data_fim = hoje
            texto_periodo = f"Hoje ({hoje.strftime('%d/%m/%Y')})"
            st.markdown(f"<div style='padding-top: 30px; color: #4ade80; font-weight: 600; font-size: 0.9rem;'>🟢 Filtrando: Hoje ({hoje.strftime('%d/%m/%Y')})</div>", unsafe_allow_html=True)
        elif modo_data_selecionado == "🟡 Ontem":
            data_inicio = hoje - timedelta(days=1)
            data_fim = hoje - timedelta(days=1)
            texto_periodo = f"Ontem ({data_inicio.strftime('%d/%m/%Y')})"
            st.markdown(f"<div style='padding-top: 30px; color: #fde047; font-weight: 600; font-size: 0.9rem;'>🟡 Filtrando: Ontem ({data_inicio.strftime('%d/%m/%Y')})</div>", unsafe_allow_html=True)
        elif modo_data_selecionado == "📆 Últimos 3 dias":
            data_inicio = hoje - timedelta(days=3)
            data_fim = hoje
            texto_periodo = f"{data_inicio.strftime('%d/%m/%Y')} até {data_fim.strftime('%d/%m/%Y')}"
            st.markdown(f"<div style='padding-top: 30px; color: #38bdf8; font-weight: 600; font-size: 0.9rem;'>📆 {data_inicio.strftime('%d/%m')} até {data_fim.strftime('%d/%m')} (3 dias)</div>", unsafe_allow_html=True)
        elif modo_data_selecionado == "📆 Últimos 7 dias":
            data_inicio = hoje - timedelta(days=7)
            data_fim = hoje
            texto_periodo = f"{data_inicio.strftime('%d/%m/%Y')} até {data_fim.strftime('%d/%m/%Y')}"
            st.markdown(f"<div style='padding-top: 30px; color: #38bdf8; font-weight: 600; font-size: 0.9rem;'>📆 {data_inicio.strftime('%d/%m')} até {data_fim.strftime('%d/%m')} (7 dias)</div>", unsafe_allow_html=True)
        elif modo_data_selecionado == "📆 Últimos 15 dias":
            data_inicio = hoje - timedelta(days=15)
            data_fim = hoje
            texto_periodo = f"{data_inicio.strftime('%d/%m/%Y')} até {data_fim.strftime('%d/%m/%Y')}"
            st.markdown(f"<div style='padding-top: 30px; color: #38bdf8; font-weight: 600; font-size: 0.9rem;'>📆 {data_inicio.strftime('%d/%m')} até {data_fim.strftime('%d/%m')} (15 dias)</div>", unsafe_allow_html=True)
        elif modo_data_selecionado == "📆 Mês Atual":
            data_inicio = hoje.replace(day=1)
            data_fim = hoje
            texto_periodo = f"{data_inicio.strftime('%d/%m/%Y')} até {data_fim.strftime('%d/%m/%Y')}"
            st.markdown(f"<div style='padding-top: 30px; color: #38bdf8; font-weight: 600; font-size: 0.9rem;'>📆 Mês Atual ({hoje.strftime('%m/%Y')})</div>", unsafe_allow_html=True)
        else: # Todas as Datas
            st.markdown("<div style='padding-top: 30px; color: #94a3b8; font-size: 0.9rem;'>Mostrando todo o inventário ativo sem filtro de data</div>", unsafe_allow_html=True)

    # Filtrar pelo escopo de Base selecionado
    if base_selecionada != "Todas as Bases":
        df_dados = df_raw[df_raw['Base'] == base_selecionada].copy()
    else:
        df_dados = df_raw.copy()

    # Filtrar pela Data selecionada
    if data_inicio and data_fim:
        df_dados = df_dados[(df_dados['Data_Operacao'] >= data_inicio) & (df_dados['Data_Operacao'] <= data_fim)].copy()

    if df_dados.empty:
        st.warning(f"⚠️ Nenhum pacote encontrado para a base **{base_selecionada}** com o filtro de data **{texto_periodo}**.")
        return

    # Divisão dos dados
    df_rota = df_dados[df_dados['is_rota']].copy()
    df_piso = df_dados[~df_dados['is_rota']].copy()

    # Métricas Gerais
    total_vol = len(df_dados)
    total_rota = len(df_rota)
    total_piso = len(df_piso)
    
    rota_atraso = len(df_rota[df_rota['aging'] >= 1])
    motoristas_ativos = df_rota['Motorista_Limpo'].nunique()

    # Cards Principais no Topo
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">📦 Inventário Total</div>
                <div class="metric-value text-sky">{total_vol}</div>
                <div class="metric-sub">{base_selecionada} | {texto_periodo}</div>
            </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">🚚 Em Rota</div>
                <div class="metric-value text-sky">{total_rota}</div>
                <div class="metric-sub">{(total_rota/total_vol*100):.1f}% do volume</div>
            </div>
        """, unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-label">🏢 No Piso</div>
                <div class="metric-value text-orange">{total_piso}</div>
                <div class="metric-sub">{(total_piso/total_vol*100):.1f}% aguardando rota</div>
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

    # Abas Principais
    tab_rota, tab_piso, tab_backlog, tab_busca = st.tabs([
        "🚚 Aging em Rota (Entregadores)",
        "🏢 Piso por Bairro & Região",
        "📊 Status por Backlog",
        "🔍 Consulta Rápida (AWB)"
    ])

    with tab_rota:
        render_aba_rota(df_rota, base_selecionada)

    with tab_piso:
        render_aba_piso(df_piso, base_selecionada)

    with tab_backlog:
        if render_aba_backlog:
            render_aba_backlog(df_dados, base_selecionada, key_prefix="bk_gen")
        else:
            st.error("Módulo aba_backlog.py não encontrado.")

    with tab_busca:
        render_aba_busca(df_dados)

# ==========================================
# RENDERIZAÇÃO DA ABA 1: AGING EM ROTA
# ==========================================
def render_aba_rota(df_rota, base_contexto):
    if df_rota.empty:
        st.success("🎉 Não há pacotes em rota no momento para o filtro selecionado!")
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

    modo_layout_graf = st.radio(
        "📐 Visualização dos Gráficos:",
        ["📸 Modo Print WhatsApp (Tela Cheia / Números Grandes)", "📐 Lado a Lado (Compacto)"],
        index=0,
        horizontal=True,
        key="modo_layout_graf_rota_gen"
    )
    tela_cheia = "Modo Print" in modo_layout_graf

    def _render_graf_dist_gen():
        st.markdown("##### 📊 Distribuição do Aging em Rota")
        tot_dist = max(len(df_rota), 1)
        df_dist = pd.DataFrame({
            'Faixa': ['<b>D0 (No Prazo)</b>', '<b>D1 (Atenção)</b>', '<b>D2 (Alerta)</b>', '<b>D3+ (Crítico)</b>'],
            'Volume': [d0, d1, d2, d3],
            'Rotulo': [
                f"<b>{v}</b> ({v / tot_dist * 100:.0f}%)" if v > 0 else "<b>0</b>"
                for v in [d0, d1, d2, d3]
            ]
        })
        max_vol_dist = max(int(df_dist['Volume'].max()), 1)
        fig_dist = px.bar(
            df_dist, x='Faixa', y='Volume', text='Rotulo',
            color='Faixa',
            color_discrete_map={
                '<b>D0 (No Prazo)</b>': '#16a34a',
                '<b>D1 (Atenção)</b>': '#eab308',
                '<b>D2 (Alerta)</b>': '#f97316',
                '<b>D3+ (Crítico)</b>': '#dc2626'
            }
        )
        fig_dist.update_traces(
            textposition='outside',
            textfont=dict(size=16, color='#ffffff', family='Arial Black, Inter, sans-serif'),
            cliponaxis=False
        )
        fig_dist.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0f172a",
            plot_bgcolor="#0f172a",
            margin=dict(t=35, b=20, l=20, r=20),
            showlegend=False,
            height=290 if tela_cheia else 320,
            xaxis=dict(title="", tickfont=dict(size=14, color='#f8fafc')),
            yaxis=dict(
                title="Pacotes",
                range=[0, max_vol_dist * 1.35],
                tickfont=dict(size=13, color='#cbd5e1'),
                gridcolor="rgba(148, 163, 184, 0.15)"
            )
        )
        st.plotly_chart(fig_dist, use_container_width=True, config={
            'toImageButtonOptions': {
                'format': 'png',
                'filename': f'distribuicao_aging_rota_{base_contexto}',
                'height': 420,
                'width': 900,
                'scale': 3
            }
        })

    def _render_graf_mot_gen():
        col_c_tit, col_c_reg, col_c_qtd, col_c_ord = st.columns([4, 2, 2, 2])
        with col_c_tit:
            st.markdown("##### 👨‍✈️ Entregadores em Rota (Volume vs Prazos)")
        with col_c_reg:
            opcoes_reg_graf = ["Todos", "LOC (Local)", "INT (Interior)"]
            filtro_reg_graf = st.selectbox(
                "Equipe:",
                opcoes_reg_graf,
                key="filtro_reg_graf_rota",
                label_visibility="collapsed"
            )
        with col_c_qtd:
            opcoes_qtd_graf = ["Top 12", "Top 20", "Top 35", "Todos"]
            filtro_qtd_graf = st.selectbox(
                "Quantidade:",
                opcoes_qtd_graf,
                index=1,
                key="filtro_qtd_graf_rota",
                label_visibility="collapsed"
            )
        with col_c_ord:
            opcoes_ord_graf = ["Maior Volume", "Mais Atrasados", "Menor Volume"]
            filtro_ord_graf = st.selectbox(
                "Ordenar:",
                opcoes_ord_graf,
                index=0,
                key="filtro_ord_graf_rota",
                label_visibility="collapsed"
            )

        df_rota_chart = df_rota.copy()
        if filtro_reg_graf == "LOC (Local)" and 'Regiao_Motorista' in df_rota_chart.columns:
            df_rota_chart = df_rota_chart[df_rota_chart['Regiao_Motorista'] == 'LOC']
        elif filtro_reg_graf == "INT (Interior)" and 'Regiao_Motorista' in df_rota_chart.columns:
            df_rota_chart = df_rota_chart[df_rota_chart['Regiao_Motorista'] == 'INT']

        if not df_rota_chart.empty:
            df_mot = df_rota_chart.groupby(['Motorista_Limpo', df_rota_chart['aging'] >= 1]).size().unstack(fill_value=0).reset_index()
            df_mot.columns = ['Motorista', 'No_Prazo', 'Atrasado'] if len(df_mot.columns) == 3 else ['Motorista', 'No_Prazo']
            if 'Atrasado' not in df_mot.columns:
                df_mot['Atrasado'] = 0

            df_mot['Total'] = df_mot['No_Prazo'] + df_mot['Atrasado']

            if filtro_ord_graf == "Mais Atrasados":
                df_mot = df_mot.sort_values(by=['Atrasado', 'Total'], ascending=[True, True])
            elif filtro_ord_graf == "Menor Volume":
                df_mot = df_mot.sort_values(by=['Total', 'Atrasado'], ascending=[False, False])
            else:
                df_mot = df_mot.sort_values(by=['Total', 'Atrasado'], ascending=[True, True])

            if filtro_qtd_graf == "Top 12":
                df_mot = df_mot.tail(12)
            elif filtro_qtd_graf == "Top 20":
                df_mot = df_mot.tail(20)
            elif filtro_qtd_graf == "Top 35":
                df_mot = df_mot.tail(35)

            max_tot = max(int(df_mot['Total'].max()), 1)
            limiar_interno = max(max_tot * 0.055, 1.5)
            df_mot['Motorista_Bold'] = df_mot['Motorista'].apply(lambda m: f"<b>{m}</b>")

            def _rotulo_externo(r):
                tot = int(r['Total'])
                np_v = int(r['No_Prazo'])
                at_v = int(r['Atrasado'])
                if at_v > 0 and np_v > 0:
                    return f"  <b>{tot}</b>  <span style='color:#86efac'><b>🟢{np_v}</b></span> <span style='color:#fca5a5'><b>🔴{at_v}</b></span>"
                elif at_v > 0:
                    return f"  <b>{tot}</b>  <span style='color:#fca5a5'><b>🔴{at_v} atr.</b></span>"
                return f"  <b>{tot}</b>  <span style='color:#86efac'><b>✅ D0</b></span>"

            rotulos_externos = df_mot.apply(_rotulo_externo, axis=1)
            altura_grafico = max(380, min(2000, len(df_mot) * 42 + 125))

            tot_c = len(df_rota_chart)
            d0_c = len(df_rota_chart[df_rota_chart['aging'] == 0])
            atr_c = len(df_rota_chart[df_rota_chart['aging'] >= 1])
            agora_graf = datetime.now().strftime("%d/%m %H:%M")

            fig_mot = go.Figure()
            fig_mot.add_trace(go.Bar(
                y=df_mot['Motorista_Bold'],
                x=df_mot['No_Prazo'],
                name='🟢 No Prazo (D0)',
                orientation='h',
                marker_color='#16a34a',
                text=df_mot['No_Prazo'].apply(lambda v: f"<b>{int(v)}</b>" if v >= limiar_interno else ''),
                textposition='inside',
                insidetextanchor='middle',
                textfont=dict(size=15, color='#ffffff', family='Arial Black, Inter, sans-serif')
            ))
            fig_mot.add_trace(go.Bar(
                y=df_mot['Motorista_Bold'],
                x=df_mot['Atrasado'],
                name='🔴 Em Atraso (≥ D1)',
                orientation='h',
                marker_color='#dc2626',
                text=df_mot['Atrasado'].apply(lambda v: f"<b>{int(v)}</b>" if v >= limiar_interno else ''),
                textposition='inside',
                insidetextanchor='middle',
                textfont=dict(size=15, color='#ffffff', family='Arial Black, Inter, sans-serif')
            ))
            fig_mot.add_trace(go.Scatter(
                y=df_mot['Motorista_Bold'],
                x=df_mot['Total'],
                mode='text',
                text=rotulos_externos,
                textposition='middle right',
                textfont=dict(size=15, color='#ffffff', family='Inter, Arial, sans-serif'),
                showlegend=False,
                hoverinfo='skip',
                cliponaxis=False
            ))
            fig_mot.update_layout(
                barmode='stack',
                bargap=0.20,
                uniformtext=dict(minsize=14, mode='show'),
                template="plotly_dark",
                paper_bgcolor="#0f172a",
                plot_bgcolor="#0f172a",
                title=dict(
                    text=(
                        f"<b>🚚 AGING EM ROTA — {base_contexto} ({filtro_reg_graf}) • {agora_graf}</b>"
                        f"<br><span style='font-size:13px;color:#cbd5e1;'>"
                        f"📦 Total: <b>{tot_c}</b> pac.  |  🟢 No Prazo (D0): <b>{d0_c}</b>  |  🔴 Em Atraso (≥ D1): <b>{atr_c}</b>"
                        f"</span>"
                    ),
                    x=0.01,
                    y=0.98,
                    font=dict(size=16, color='#f8fafc', family='Inter, Arial, sans-serif')
                ),
                margin=dict(t=75, b=20, l=15, r=30),
                height=altura_grafico,
                xaxis=dict(
                    range=[0, max_tot * 1.36],
                    tickfont=dict(size=13, color='#cbd5e1'),
                    gridcolor="rgba(148, 163, 184, 0.15)",
                    title=""
                ),
                yaxis=dict(
                    tickfont=dict(size=14, color='#f8fafc', family='Inter, Arial, sans-serif'),
                    automargin=True,
                    title=""
                ),
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.01,
                    xanchor="right",
                    x=1,
                    font=dict(size=13, color='#f8fafc')
                )
            )
            st.plotly_chart(fig_mot, use_container_width=True, config={
                'toImageButtonOptions': {
                    'format': 'png',
                    'filename': f'grafico_expedicao_{base_contexto}_{filtro_reg_graf}',
                    'height': altura_grafico,
                    'width': 1250,
                    'scale': 3
                }
            })
            st.caption("📸 **Para mandar no WhatsApp:** Clique no ícone da câmera 📷 no canto superior direito do gráfico para baixar em **Alta Definição (3x)** ou tire print direto da tela.")
        else:
            st.info(f"Nenhum motorista {filtro_reg_graf} em rota no momento.")

    if tela_cheia:
        _render_graf_mot_gen()
        with st.expander("📊 Ver Gráfico de Distribuição por Faixa (D0, D1, D2, D3+)", expanded=False):
            _render_graf_dist_gen()
    else:
        col_g1, col_g2 = st.columns([3.5, 6.5])
        with col_g1:
            _render_graf_dist_gen()
        with col_g2:
            _render_graf_mot_gen()

    st.markdown("#### 🔍 Filtros da Rota")
    f_col1, f_col2, f_col3, f_col4 = st.columns([2, 2, 2, 3])
    
    with f_col1:
        opcoes_aging = ["Todos", "🟢 No Prazo (D0)", "⚠️ Em Atraso (≥ D1)", "🔥 Críticos (≥ D2)"]
        filtro_aging = st.selectbox("Status de Aging:", opcoes_aging, key="f_aging_rota_gen")
        
    with f_col2:
        motoristas = ["Todos"] + sorted(df_rota['Motorista_Limpo'].unique().tolist())
        filtro_mot = st.selectbox("Motorista:", motoristas, key="f_mot_rota_gen")
        
    with f_col3:
        cidades = ["Todas"] + sorted(df_rota['Destination City'].unique().tolist())
        filtro_cid = st.selectbox("Cidade:", cidades, key="f_cid_rota_gen")
        
    with f_col4:
        busca_rota = st.text_input("Buscar Waybill, Bairro ou Endereço:", key="f_busca_rota_gen", placeholder="Ex: 3320..., Centro, etc.")

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
        cols_export = ['Base', 'Waybill No', 'Data_Display', 'aging', 'Motorista_Limpo', 'Destination City', 'Bairro_Display', 'Endereco_Display', 'Receive Date']
        cols_export_existentes = [c for c in cols_export if c in df_view.columns]
        excel_bytes = exportar_para_excel(df_view[cols_export_existentes], "pacotes_em_rota.xlsx")
        st.download_button(
            label="📥 Baixar Pacotes Filtrados (Excel)",
            data=excel_bytes,
            file_name=f"expedicao_em_rota_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_rota_gen"
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
        base_m = df_m['Base'].iloc[0] if not df_m.empty and 'Base' in df_m.columns else ""
        reg_m = df_m['Regiao_Motorista'].iloc[0] if not df_m.empty and 'Regiao_Motorista' in df_m.columns else "LOC"
        pct_no_prazo = round((d0_m / total_m * 100), 1) if total_m > 0 else 100.0
        status_geral = "🟢 100% no prazo" if atraso_m == 0 else f"⚠️ {atraso_m} em atraso"
        
        resumo_mots_tabela.append({
            "Base": base_m,
            "Equipe": reg_m,
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
        st.markdown("Gere a mensagem formatada para colar no grupo. **Dica:** Separe entre **LOC** e **INT** para a mensagem não ficar gigante!")
        
        c_reg1, c_fmt1 = st.columns([5, 5])
        with c_reg1:
            sel_divisao = st.radio(
                "Divisão de Equipe (Grupo WhatsApp):",
                ["🏢 Todos os Motoristas", "🏙️ Apenas LOC (Local / Urbano)", "🏞️ Apenas INT (Interior / Satélites)", "📑 Separar em Blocos (LOC + INT)"],
                horizontal=True,
                key="tipo_divisao_wpp_rota_gen"
            )
        with c_fmt1:
            tipo_relatorio = st.radio(
                "Formato das Informações:",
                ["Completo (Total + Prazos D0/Atraso)", "Simplificado (Apenas Nome e Total)", "⚠️ Apenas Motoristas com Atraso (≥ D1)"],
                horizontal=True,
                key="tipo_rel_wpp_rota_gen"
            )
        
        modo_fmt = "completo"
        if "Simplificado" in tipo_relatorio:
            modo_fmt = "simplificado"
        elif "Apenas Motoristas com Atraso" in tipo_relatorio:
            modo_fmt = "atrasados"

        filtro_reg = "TODOS"
        if "Apenas LOC" in sel_divisao:
            filtro_reg = "LOC"
        elif "Apenas INT" in sel_divisao:
            filtro_reg = "INT"
        elif "Separar em Blocos" in sel_divisao:
            filtro_reg = "SEPARADO"

        texto_wpp = gerar_texto_grupo_whatsapp(df_view, base_contexto, formato=modo_fmt, filtro_regiao=filtro_reg)
        
        st.code(texto_wpp, language="text")
        
        col_btn_w1, col_btn_w2 = st.columns([3, 7])
        with col_btn_w1:
            msg_url = urllib.parse.quote(texto_wpp)
            nome_botao = "📲 Enviar no WhatsApp"
            if filtro_reg == "LOC":
                nome_botao = "📲 Enviar no Grupo LOC"
            elif filtro_reg == "INT":
                nome_botao = "📲 Enviar no Grupo INT"
            st.link_button(nome_botao, f"https://api.whatsapp.com/send?text={msg_url}")
        with col_btn_w2:
            st.caption("💡 Clique no ícone de cópia no canto superior direito do quadro de texto para copiar para a área de transferência.")

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
        base_mot = df_m['Base'].iloc[0] if not df_m.empty else ""
        aviso_txt = f"⚠️ {atrasados_m} em atraso" if atrasados_m > 0 else "✅ 100% no prazo"
        
        with st.expander(f"👨‍✈️ [{base_mot}] {mot} — {qtd} pacotes ({aviso_txt})", expanded=(qtd > 0 and atrasados_m > 0)):
            if qtd > 120:
                st.warning("Volume alto. Exibindo em tabela interativa:")
                tabela_cols = ['Base', 'Waybill No', 'Data_Display', 'aging', 'Destination City', 'Bairro_Display', 'Endereco_Display']
                st.dataframe(df_m[tabela_cols], width="stretch", hide_index=True)
            else:
                h1, h2, h3, h4, h5 = st.columns([2, 1, 3, 3, 2])
                h1.markdown("**Waybill (Rastreio)**")
                h2.markdown("**Aging**")
                h3.markdown("**Bairro / Cidade**")
                h4.markdown("**Endereço / Data**")
                h5.markdown("**Ação Imediata**")
                
                for _, row in df_m.iterrows():
                    awb = str(row['Waybill No'])
                    ag = int(row['aging'])
                    bairro = row['Bairro_Display']
                    cidade = row['Destination City']
                    endereco = row['Endereco_Display']
                    base_pkg = row.get('Base', 'ITR')
                    
                    if ag == 0:
                        badge_html = "<span class='badge badge-d0'>D0 (Hoje)</span>"
                    elif ag == 1:
                        badge_html = "<span class='badge badge-d1'>D1 (1 dia)</span>"
                    elif ag == 2:
                        badge_html = "<span class='badge badge-d2'>D2 (2 dias)</span>"
                    else:
                        badge_html = f"<span class='badge badge-d3'>D{ag} (Crítico)</span>"
                        
                    r1, r2, r3, r4, r5 = st.columns([2, 1, 3, 3, 2])
                    r1.write(f"`{awb}` <span class='badge badge-base'>{base_pkg}</span>", unsafe_allow_html=True)
                    r2.markdown(badge_html, unsafe_allow_html=True)
                    r3.write(f"**{bairro}** ({cidade})")
                    r4.markdown(f"{endereco}<br><small style='color: #94a3b8;'>📅 Entrada: <b>{row.get('Data_Display', 'N/A')}</b></small>", unsafe_allow_html=True)
                    
                    btn_ph = r5.empty()
                    key_link = f"wpp_gen_{awb}"
                    
                    if key_link in st.session_state:
                        btn_ph.markdown(st.session_state[key_link], unsafe_allow_html=True)
                    else:
                        if btn_ph.button("📱 WhatsApp", key=f"btn_r_gen_{awb}"):
                            u, s = obter_credenciais_base(base_pkg)
                            if not u or not s:
                                btn_ph.error(f"Sem credenciais {base_pkg}.")
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
                                        awb, endereco, base_pkg, res.get('produto', '')
                                    )
                                    if link:
                                        html = f'<a href="{link}" target="_blank" class="wpp-btn">Abrir WhatsApp</a>'
                                        st.session_state[key_link] = html
                                        btn_ph.markdown(html, unsafe_allow_html=True)

# ==========================================
# RENDERIZAÇÃO DA ABA 2: PISO POR BAIRRO
# ==========================================
def render_aba_piso(df_piso, base_contexto):
    if df_piso.empty:
        st.success("🎉 O piso está totalmente limpo para o filtro selecionado!")
        return

    total_piso = len(df_piso)
    total_bairros = df_piso['Bairro_Display'].nunique()
    
    df_loc = df_piso[df_piso['Tipo_Localidade'] == '🏙️ Cidade Polo (Urbano)']
    df_int = df_piso[df_piso['Tipo_Localidade'] == '🏞️ Interior Satélite']
    df_fora = df_piso[df_piso['Tipo_Localidade'] == '⚠️ Fora de Rota (Inversão)']
    
    p1, p2, p3, p4, p5 = st.columns(5)
    p1.metric("🏢 Total no Piso", f"{total_piso}")
    p2.metric("📍 Bairros Distintos", f"{total_bairros}")
    p3.metric("🏙️ Cidades Polo", f"{len(df_loc)}")
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
        tipos_loc = ["Todos", "🏙️ Cidade Polo (Urbano)", "🏞️ Interior Satélite", "⚠️ Fora de Rota (Inversão)"]
        filtro_loc = st.selectbox("Localidade:", tipos_loc, key="f_loc_piso_gen")
        
    with pf2:
        status_list = ["Todos"] + sorted(df_piso['Last scan type'].dropna().unique().tolist())
        filtro_status_piso = st.selectbox("Status Scan:", status_list, key="f_status_piso_gen")
        
    with pf3:
        opcoes_ordem_piso = [
            "🔥 Mais Antigo Primeiro (Maior Aging)",
            "🌱 Mais Novo Primeiro (Menor Aging)",
            "📊 Maior Volume Primeiro",
            "🔤 Alfabética"
        ]
        ordem = st.selectbox("Ordenar Bairros e Pacotes:", opcoes_ordem_piso, index=0, key="f_ordem_piso_gen")
        
    with pf4:
        busca_piso = st.text_input("Buscar Bairro, Cidade ou Waybill:", key="f_busca_piso_gen", placeholder="Ex: Centro, 610...")

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
        df_piso_view = df_piso_view.sort_values(by=['aging', 'Base', 'Bairro_Display'], ascending=[aging_asc, True, True])

    rotulo_ordem = "do menor para o maior aging (mais novos primeiro)" if aging_asc else "do maior para o menor aging (mais antigos primeiro)"
    st.markdown(f"<div style='margin-top: 15px;'><b>Exibindo {len(df_piso_view)} pacotes no piso (ordenados {rotulo_ordem})</b></div>", unsafe_allow_html=True)

    if not df_piso_view.empty:
        cols_piso_exp = ['Base', 'Waybill No', 'aging', 'Data_Display', 'Last scan type', 'Destination City', 'Bairro_Display', 'Endereco_Display', 'Tipo_Localidade', 'Receive Date']
        cols_piso_exp_existentes = [c for c in cols_piso_exp if c in df_piso_view.columns]
        excel_piso_bytes = exportar_para_excel(df_piso_view[cols_piso_exp_existentes], "inventario_piso.xlsx")
        st.download_button(
            label="📥 Baixar Piso por Bairro (Excel)",
            data=excel_piso_bytes,
            file_name=f"piso_bairros_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_piso_gen"
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
        base_b = df_b['Base'].iloc[0] if not df_b.empty else ""
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
        titulo_expander = f"{icone} [{base_b}] {bairro_nome} ({cidade_b}) — {qtd_bairro} pacotes | {tag_ref}: {badge_ag_txt}"
        
        with st.expander(titulo_expander, expanded=(qtd_bairro >= 5 or (not aging_asc and ref_ag >= 2))):
            if qtd_bairro > 80:
                st.warning(f"Volume alto neste bairro. Exibindo em tabela direta ({rotulo_ordem}):")
                cols_grid = [c for c in ['Base', 'Waybill No', 'aging', 'Data_Display', 'Last scan type', 'Endereco_Display', 'Receive Date'] if c in df_b.columns]
                st.dataframe(df_b[cols_grid], width="stretch", hide_index=True)
            else:
                p_cols_h = st.columns([2, 1, 2, 3, 2])
                p_cols_h[0].markdown("**Waybill (Rastreio)**")
                p_cols_h[1].markdown("**Aging**")
                p_cols_h[2].markdown("**Status no Piso**")
                p_cols_h[3].markdown("**Endereço / Data**")
                p_cols_h[4].markdown("**Ação / WhatsApp**")
                
                for _, row in df_b.iterrows():
                    awb = str(row['Waybill No'])
                    scan = row['Last scan type']
                    end = row['Endereco_Display']
                    base_pkg = row.get('Base', 'ITR')
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
                    pr1.write(f"`{awb}` <span class='badge badge-base'>{base_pkg}</span>", unsafe_allow_html=True)
                    pr2.markdown(badge_html, unsafe_allow_html=True)
                    pr3.markdown(f"<span class='badge badge-piso'>{scan}</span>", unsafe_allow_html=True)
                    pr4.markdown(f"{end}<br><small style='color: #94a3b8;'>📅 Entrada: <b>{row.get('Data_Display', 'N/A')}</b></small>", unsafe_allow_html=True)
                    
                    btn_ph = pr5.empty()
                    k_link = f"wpp_piso_gen_{awb}"
                    if k_link in st.session_state:
                        btn_ph.markdown(st.session_state[k_link], unsafe_allow_html=True)
                    else:
                        if btn_ph.button("📱 Contato", key=f"btn_p_gen_{awb}"):
                            u, s = obter_credenciais_base(base_pkg)
                            if not u or not s:
                                btn_ph.error(f"Sem credenciais {base_pkg}")
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
                                        awb, end, base_pkg, res.get('produto', '')
                                    )
                                    if link:
                                        html = f'<a href="{link}" target="_blank" class="wpp-btn">Abrir WhatsApp</a>'
                                        st.session_state[k_link] = html
                                        btn_ph.markdown(html, unsafe_allow_html=True)

# ==========================================
# RENDERIZAÇÃO DA ABA 3: CONSULTA WAYBILL
# ==========================================
def render_aba_busca(df_dados):
    st.markdown("#### 🔎 Localizador Universal de Pacote (Todas as Bases)")
    st.write("Digite ou bipe o número da Waybill para ver imediatamente status, base, entregador, aging e dados de contato.")
    
    codigo_busca = st.text_input("Código de Rastreio (Waybill No):", placeholder="Ex: 3320176083220, 6101626606010...", key="busca_universal_awb_gen")
    
    if codigo_busca:
        cd = codigo_busca.strip()
        match = df_dados[df_dados['Waybill No'].astype(str).str.contains(cd, na=False)]
        
        if match.empty:
            st.error(f"❌ Pacote `{cd}` não foi encontrado no inventário ativo.")
        else:
            st.success(f"Encontrado(s) {len(match)} registro(s) correspondente(s):")
            for _, r in match.iterrows():
                awb = str(r['Waybill No'])
                is_r = r['is_rota']
                base_pkg = r.get('Base', 'ITR')
                status_txt = "🚚 EM ROTA COM MOTORISTA" if is_r else f"🏢 NO PISO DA BASE ({r['Last scan type']})"
                cor_status = "#38bdf8" if is_r else "#f97316"
                
                with st.container():
                    st.markdown(f"""
                        <div style='background: #1e293b; border-left: 5px solid {cor_status}; border-radius: 8px; padding: 16px; margin-bottom: 12px;'>
                            <div style='display: flex; justify-content: space-between; align-items: center;'>
                                <span style='font-size: 1.2rem; font-weight: 800; color: #f8fafc;'>
                                    Waybill: {awb} <span class='badge badge-base'>{base_pkg}</span>
                                </span>
                                <span style='font-weight: 700; color: {cor_status};'>{status_txt}</span>
                            </div>
                            <hr style='border-color: #334155; margin: 10px 0;'>
                            <div style='display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; color: #cbd5e1;'>
                                <div><b>Base:</b> {base_pkg}</div>
                                <div><b>Data Entrada:</b> {r.get('Data_Display', 'N/A')}</div>
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
                        if st.button("📱 Pesquisar WhatsApp", key=f"univ_wpp_gen_{awb}"):
                            u, s = obter_credenciais_base(base_pkg)
                            if not u or not s:
                                st.error(f"Sem credenciais {base_pkg}.")
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
                                        awb, r['Endereco_Display'], base_pkg, res.get('produto', '')
                                    )
                                    if link:
                                        st.markdown(f'<a href="{link}" target="_blank" class="wpp-btn">Abrir WhatsApp com {res.get("nome", "Cliente")}</a>', unsafe_allow_html=True)

# ==========================================
# FUNÇÃO PRINCIPAL
# ==========================================
def main():
    if os.path.exists("c:/bots/logo.png"):
        st.logo("c:/bots/logo.png", size="large")
    elif os.path.exists("logo.png"):
        st.logo("logo.png", size="large")
        
    render_header()
    st.markdown("<hr style='border-color: #334155; margin: 16px 0 24px 0;'>", unsafe_allow_html=True)
    render_dashboard()

if __name__ == "__main__":
    main()
