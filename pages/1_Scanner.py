import streamlit as st
import database
from bipagem_utils import obter_indice_rota

st.set_page_config(page_title="Scanner Boticário", page_icon="📱", layout="wide")
st.logo("c:/bots/logo.png", size="large")

def injetar_estilos():
    st.markdown("""
        <style>
        .stApp {
            background-color: #021B59;
            color: #ffffff;
        }
        [data-testid="stSidebar"] {
            background-color: #01123d !important;
        }
        </style>
    """, unsafe_allow_html=True)
    
injetar_estilos()

database.setup_database()

st.title("🛍️ Scanner Boticário")
st.subheader("Registre as caixas recebidas")

rotas = ["roça", "santa barbara", "itabira", "francismar"]

if "codigo_bipagem" not in st.session_state:
    st.session_state.codigo_bipagem = ""

if "rota_bipagem" not in st.session_state:
    st.session_state.rota_bipagem = rotas[0]

# O selectbox fica fora do form para não ser resetado pelo clear_on_submit
rota_index = obter_indice_rota(rotas, st.session_state.rota_bipagem)
rota_selecionada = st.selectbox("Rota", rotas, index=rota_index, key="rota_bipagem")

import time

def tocar_som(tipo):
    timestamp = int(time.time() * 1000)
    if tipo == "sucesso":
        # Bip simples de leitor de supermercado
        url = f"https://www.myinstants.com/media/sounds/supermarket-scanner-beep.mp3?t={timestamp}"
    else:
        # Bip curto e moderno de erro (não parece despertador)
        url = f"https://assets.mixkit.co/active_storage/sfx/2954/2954-preview.mp3?t={timestamp}"
        
    st.audio(url, autoplay=True)
    # Oculta todos os players de áudio gerados pelo Streamlit na página
    st.markdown("<style>audio, [data-testid='stAudio'] { display: none !important; }</style>", unsafe_allow_html=True)

with st.form("form_bipagem", clear_on_submit=True):
    codigo = st.text_input("Código da caixa", key="codigo_bipagem")
    submitted = st.form_submit_button("Salvar")

    if submitted:
        if not codigo:
            st.error("Informe o código da caixa.")
        elif len(codigo) > 13:
            st.error(f"❌ O código '{codigo}' tem mais de 13 dígitos! Você bipou a Nota Fiscal ao invés do código da caixa.")
            tocar_som("erro")
        else:
            salvo = database.salvar_bipagem(codigo=codigo, produto="", quantidade=1, rota=rota_selecionada)
            if salvo:
                st.success(f"✅ Caixa {codigo} salva com sucesso!")
                tocar_som("sucesso")
            else:
                st.warning(f"⚠️ A caixa {codigo} já foi bipada anteriormente.")
                tocar_som("erro")

st.markdown("---")
st.subheader("Últimas bipagens")

# Exportar para Excel
bipagens_export = database.listar_bipagens(limit=5000)
if bipagens_export:
    import io
    import pandas as pd
    
    df_export = pd.DataFrame(bipagens_export)
    
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_export.to_excel(writer, index=False, sheet_name="bipagens")
    buffer.seek(0)

    st.download_button(
        label="📥 Exportar Relatório Completo (Excel)",
        data=buffer,
        file_name="boticario_conferencia.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

st.write("Exibindo as últimas 10:")
for item in bipagens_export[:10]:
    st.write(f"- {item['codigo']} | Rota: {item['rota']} | Data/Hora: {item['criado_em']}")
