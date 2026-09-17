import os
import glob
import time
import zipfile
import pandas as pd
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
import sys

# Fix encoding para suportar emojis no Windows
sys.stdout.reconfigure(encoding='utf-8')

# ==========================================
# CONFIGURAÇÕES
# ==========================================
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads_shopee")
USER_DATA_DIR = r"C:\PerfilBotShopee"
CACHE_FILE = "piso_cache_shopee.xlsx"

def limpar_pasta_downloads():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    for arquivo in glob.glob(os.path.join(DOWNLOAD_DIR, "*")):
        try: os.remove(arquivo)
        except: pass

def ler_planilha_shopee_segura(caminho):
    """Lê CSV ou Excel de forma robusta."""
    if caminho.endswith('.csv'):
        tentativas = [
            (',', 'utf-8-sig'), (',', 'utf-8'), (',', 'latin1'),
            (';', 'utf-8-sig'), (';', 'latin1')
        ]
        for sep, enc in tentativas:
            try:
                df = pd.read_csv(caminho, sep=sep, encoding=enc, dtype=str)
                if len(df.columns) > 2:
                    return df
            except:
                continue
    else:
        try: return pd.read_excel(caminho, dtype=str)
        except: pass
    return pd.DataFrame()

# ==========================================
# LEITURA DA BASE DE CEPS
# ==========================================
def carregar_dicionario_ceps_com_motorista(caminho_excel):
    print("Lendo base de CEPs (Sua planilha amarela)...")
    try:
        df_ceps = pd.read_excel(caminho_excel, dtype=str)
        df_ceps.columns = df_ceps.columns.astype(str).str.strip()
        
        col_cep = None
        col_cidade = None
        col_motorista = None

        if 'CEPs' in df_ceps.columns and 'Responsavel' in df_ceps.columns:
            col_cep = 'CEPs'
            col_cidade = 'Responsavel' 
            if len(df_ceps.columns) >= 4:
                col_motorista = df_ceps.columns[3]
        else:
            col_cep = df_ceps.columns[0]
            col_cidade = df_ceps.columns[2]
            if len(df_ceps.columns) >= 4:
                col_motorista = df_ceps.columns[3]

        df_ceps[col_cep] = df_ceps[col_cep].astype(str).str.replace(r'\D', '', regex=True)
        
        mapa_cidades = dict(zip(df_ceps[col_cep], df_ceps[col_cidade]))
        mapa_motoristas = {}
        if col_motorista:
            mapa_motoristas = dict(zip(df_ceps[col_cep], df_ceps[col_motorista]))
        else:
            print("⚠️ Coluna D (Motorista) não encontrada na planilha base_ceps.xlsx.")

        print(f"✅ Base de CEPs carregada com {len(mapa_cidades)} cidades e {len(mapa_motoristas)} motoristas!")
        return mapa_cidades, mapa_motoristas
    except Exception as e:
        print(f"❌ Erro ao ler a base de CEPs: {e}")
        return {}, {}

# ==========================================
# ROTINA MATINAL: CACHE & PRINT DO PISO
# ==========================================
def baixar_relatorio_piso(page):
    """Baixa o relatório avançado filtrando por Hub_Received"""
    print("📦 Navegando para Rastreio de Pedidos (Piso)...")
    page.goto("https://spx.shopee.com.br/#/index", wait_until="domcontentloaded")

    menu_pedidos = page.locator("span.sub-menu-title", has_text="Pedidos")
    menu_pedidos.wait_for(state="visible", timeout=60000)
    menu_pedidos.click()
    
    submenu_rastreio = page.locator("a[title='Rastreio de pedidos']")
    submenu_rastreio.wait_for(state="visible", timeout=10000)
    submenu_rastreio.click()

    print("⚙️ Abrindo Exportação Avançada...")
    btn_exportar = page.locator("button", has_text="Exportar")
    btn_exportar.wait_for(state="visible", timeout=60000)
    btn_exportar.hover()
    
    page.locator("div.ssc-dropdown-item", has_text="Exportar Pedido Avançado").click()

    print("🔎 Aplicando filtro de Status (Hub_Received)...")
    linha_status = page.locator("div.s-tree-node__content").filter(
        has=page.locator("span.ssc-tree-node__label:text-is('Hub_Received')")
    )
    linha_status.locator("label.ssc-checkbox-wrapper").click()

    print("👤 Aplicando filtro de Conta (All)...")
    conta_pedido_div = page.locator("div.ssc-form-item", has_text="Conta do pedido:")
    conta_pedido_div.locator("span.ssc-tree-node__label", has_text="All").first.click()

    page.locator("button.ssc-btn-type-primary", has_text="Confirmar").click()

    print("⏳ Aguardando o processamento do relatório no servidor...")
    tarefa_row = page.locator("div.task-row", has_text="Forward Order").first
    botao_baixar = tarefa_row.locator("button", has_text="Baixar")
    botao_baixar.wait_for(state="visible", timeout=300000) 
    
    print("⬇️ Baixando arquivo...")
    with page.expect_download() as download_info:
        botao_baixar.click()
    
    download = download_info.value
    caminho_arquivo = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
    download.save_as(caminho_arquivo)
    
    if caminho_arquivo.endswith('.zip'):
        with zipfile.ZipFile(caminho_arquivo, 'r') as zip_ref:
            zip_ref.extractall(DOWNLOAD_DIR)
        arquivos = glob.glob(os.path.join(DOWNLOAD_DIR, "*.xlsx")) + glob.glob(os.path.join(DOWNLOAD_DIR, "*.csv"))
        caminho_arquivo = arquivos[0] if arquivos else caminho_arquivo

    return caminho_arquivo

def rotina_matinal():
    """
    1. Baixa planilha do piso (Hub_Received).
    2. Cruza com base_ceps.xlsx para pegar Cidade e Motorista.
    3. Salva em cache.
    4. Gera e retorna imagem (Pivot Table) com total de pacotes por motorista.
    """
    print(f"\n{'='*70}")
    print(f"🌅 ROTINA MATINAL SHOPEE - PISO (HUB RECEIVED)")
    print(f"{'='*70}")

    limpar_pasta_downloads()

    caminho_base_ceps = "base_ceps.xlsx"
    if not os.path.exists(caminho_base_ceps):
        return ["❌ Arquivo base_ceps.xlsx não encontrado!"], []
    
    mapa_cidades, mapa_motoristas = carregar_dicionario_ceps_com_motorista(caminho_base_ceps)

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR, headless=False, accept_downloads=True
        )
        page = browser.pages[0]
        try:
            caminho_piso = baixar_relatorio_piso(page)
        except Exception as e:
            print(f"❌ Erro na extração da Shopee: {e}")
            browser.close()
            return [f"❌ Erro na extração da Shopee: {e}"], []
        finally:
            browser.close()

    if not caminho_piso:
        return ["❌ Falha ao baixar a planilha do piso."], []

    df = ler_planilha_shopee_segura(caminho_piso)
    if df.empty:
        return ["❌ A planilha baixada do piso está vazia ou não pôde ser lida."], []

    # Ajuste de Colunas
    col_station = next((c for c in df.columns if 'station' in c.lower() or 'estação' in c.lower() or 'estacao' in c.lower()), None)
    col_cep = next((c for c in df.columns if 'zipcode' in c.lower() or 'cep' in c.lower()), None)
    col_tracking = next((c for c in df.columns if 'tracking number' in c.lower() or 'rastreamento' in c.lower()), None)
    
    if not all([col_station, col_cep, col_tracking]):
        return ["❌ Colunas essenciais (Estação, CEP ou Rastreamento) não encontradas no arquivo."], []

    # Filtrar apenas Monlevade/JML
    df = df[df[col_station].astype(str).str.contains('Monlevade|JML', na=False, case=False)].copy()
    
    if df.empty:
        return ["✅ Nenhum pacote no piso para a base de Monlevade (JML)."], []

    # Cruzar Dados
    df[col_cep] = df[col_cep].astype(str).str.replace(r'\D', '', regex=True)
    df['Cidade'] = df[col_cep].map(mapa_cidades).fillna('OUTROS_CEPS')
    df['Motorista'] = df[col_cep].map(mapa_motoristas).fillna('SEM MOTORISTA')
    
    # Padronizar nomes para o cache
    df_cache = df[[col_tracking, 'Cidade', 'Motorista']].copy()
    df_cache.columns = ['Tracking Number', 'Cidade', 'Motorista']
    df_cache['Status'] = 'Hub_Received' # Status inicial da manhã
    df_cache['Data_Cache'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    df_cache.to_excel(CACHE_FILE, index=False)
    print(f"✅ Cache matinal salvo em {CACHE_FILE} com {len(df_cache)} pacotes.")

    # ---------------------------------------------
    # GERAR IMAGEM (PIVOT TABLE)
    # ---------------------------------------------
    mensagens = ["✅ *Shopee:* Resumo do Piso gerado com sucesso."]
    imagens_geradas = []

    rotas_shopee = {
        "Joao_Monlevade": ['João Monlevade'],
        "Barao_SB_Catas": ['Barão de Cocais', 'Santa Bárbara', 'Catas Altas'],
        "Interior": ['Nova Era', 'Bela Vista de Minas', 'São Gonçalo do Rio Abaixo', 'Rio Piracicaba', 'São Domingos do Prata', 'São José do Goiabal', 'Dionísio'],
        "Problemas_CEP": ['OUTROS_CEPS']
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        for nome_rota, cidades in rotas_shopee.items():
            df_rota = df_cache[df_cache['Cidade'].str.upper().isin([c.upper() for c in cidades])]
            if df_rota.empty:
                continue

            pt = pd.pivot_table(
                df_rota, values='Tracking Number', 
                index=['Cidade', 'Motorista'], 
                aggfunc='count', fill_value=0
            ).rename(columns={'Tracking Number': 'Total Piso'})

            # HTML Builder
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ background: #002030; margin: 0; padding: 20px; font-family: Calibri, Arial, sans-serif; }}
                    #print-shopee {{ display: inline-block; background: #87CEFA; padding: 2px; border: 2px solid black; }}
                    table {{ border-collapse: collapse; font-size: 14px; width: 500px; }}
                    th {{ color: white; padding: 6px; text-align: center; border: 1px solid #555; background: #002030; }}
                    th.titulo {{ color: red; font-size: 20px; text-align: left; border: none; padding-bottom: 10px; }}
                    td {{ padding: 4px 6px; border: 1px solid #777; text-align: center; color: black; font-weight: bold; }}
                    td.left {{ text-align: left; }}
                    tr.city td {{ background: #A9D0F5; font-weight: bold; }}
                    tr.mot td {{ background: #87CEFA; font-weight: normal; }}
                    tr.total td {{ background: #002030; color: white; font-weight: bold; }}
                </style>
            </head>
            <body>
                <div id="print-shopee">
                    <table>
                        <tr><th colspan="2" class="titulo">Shopee - Piso ({nome_rota.replace('_', ' ')})</th></tr>
                        <tr><th style="text-align: left;">Responsavel</th><th>Pacotes no Piso</th></tr>
            """

            total_absoluto = 0
            for cidade in df_rota['Cidade'].unique():
                df_cid = df_rota[df_rota['Cidade'] == cidade]
                tot_cid = len(df_cid)
                total_absoluto += tot_cid

                html += f"<tr class='city'><td class='left'>⊟ {cidade}</td><td>{tot_cid}</td></tr>"

                if cidade in pt.index.get_level_values('Cidade'):
                    mots = df_cid.groupby('Motorista').size().sort_values(ascending=False)
                    for mot, tot_mot in mots.items():
                        html += f"<tr class='mot'><td class='left' style='padding-left: 20px;'>{mot}</td><td>{tot_mot}</td></tr>"

            html += f"<tr class='total'><td class='left'>Total Geral</td><td>{total_absoluto}</td></tr>"
            html += "</table></div></body></html>"

            caminho_imagem = f"Print_Piso_Shopee_{nome_rota}.png"
            page.set_content(html)
            page.locator("#print-shopee").wait_for(state="visible")
            page.locator("#print-shopee").screenshot(path=caminho_imagem)

            imagens_geradas.append(caminho_imagem)
            mensagens.append(f"📦 *Piso Shopee:* {nome_rota.replace('_', ' ')}")

        browser.close()

    ceps_fujoes = df[df['Cidade'] == 'OUTROS_CEPS'][col_cep].dropna().unique().tolist()
    if ceps_fujoes:
        lista = "\n".join([f"- {cep}" for cep in ceps_fujoes])
        mensagens.append(f"⚠️ CEPs SEM CIDADE DEFINIDA NA BASE:\n{lista}")

    return mensagens, imagens_geradas

# ==========================================
# ROTINA CONSULTA: PESQUISA EM LOTE
# ==========================================
def realizar_pesquisa_lote(page, rastreios):
    print("📦 Navegando para Rastreio de Pedidos...")
    page.goto("https://spx.shopee.com.br/#/index", wait_until="domcontentloaded")

    menu_pedidos = page.locator("span.sub-menu-title", has_text="Pedidos")
    menu_pedidos.wait_for(state="visible", timeout=60000)
    menu_pedidos.click()
    
    submenu_rastreio = page.locator("a[title='Rastreio de pedidos']")
    submenu_rastreio.wait_for(state="visible", timeout=10000)
    submenu_rastreio.click()
    
    print("🔍 Clicando em Pesquisa em lote...")
    btn_lote = page.locator("button.batch-search-button")
    btn_lote.wait_for(state="visible", timeout=30000)
    btn_lote.click()

    print(f"✍️ Inserindo {len(rastreios)} rastreios no campo...")
    textarea = page.locator("textarea.ssc-textarea")
    textarea.wait_for(state="visible", timeout=10000)
    
    texto_rastreios = "\n".join(rastreios)
    textarea.evaluate(f"(el) => el.value = `{texto_rastreios}`")
    textarea.press("Enter")
    time.sleep(1)

    print("⚙️ Clicando em Exportar e Exportar pedidos pesquisados...")
    btn_exportar = page.locator("button.batch-actions-btn", has_text="Exportar")
    btn_exportar.wait_for(state="visible", timeout=10000)
    btn_exportar.hover()
    
    dropdown_item = page.locator("div.ssc-dropdown-item", has_text="Exportar pedidos pesquisados")
    dropdown_item.wait_for(state="visible", timeout=10000)
    dropdown_item.click()

    print("⏳ Aguardando processamento do arquivo atualizado...")
    tarefa_row = page.locator("div.task-row").first
    botao_baixar = tarefa_row.locator("button", has_text="Baixar")
    botao_baixar.wait_for(state="visible", timeout=300000) 
    
    print("⬇️ Baixando arquivo da pesquisa em lote...")
    with page.expect_download() as download_info:
        botao_baixar.click()
    
    download = download_info.value
    caminho_arquivo = os.path.join(DOWNLOAD_DIR, download.suggested_filename)
    download.save_as(caminho_arquivo)
    
    if caminho_arquivo.endswith('.zip'):
        with zipfile.ZipFile(caminho_arquivo, 'r') as zip_ref:
            zip_ref.extractall(DOWNLOAD_DIR)
        arquivos = glob.glob(os.path.join(DOWNLOAD_DIR, "*.xlsx")) + glob.glob(os.path.join(DOWNLOAD_DIR, "*.csv"))
        caminho_arquivo = arquivos[0] if arquivos else caminho_arquivo

    return caminho_arquivo

def rotina_consulta():
    """
    1. Abre o piso_cache_shopee.xlsx.
    2. Realiza pesquisa em lote na Shopee para pegar o status atual dos pacotes.
    3. Cruza os dados e gera resumo de quantos foram "Delivered".
    """
    print(f"\n{'='*70}")
    print(f"⏰ ROTINA DE CONSULTA SHOPEE - PESQUISA EM LOTE")
    print(f"{'='*70}")

    if not os.path.exists(CACHE_FILE):
        msg = "⚠️ Cache do piso (piso_cache_shopee.xlsx) não encontrado. Execute a Rotina Matinal primeiro."
        print(msg)
        return {"mensagem": msg}

    try:
        df_cache = pd.read_excel(CACHE_FILE, dtype=str)
    except Exception as e:
        msg = f"❌ Erro ao ler cache: {e}"
        print(msg)
        return {"mensagem": msg}

    if df_cache.empty or 'Tracking Number' not in df_cache.columns:
        msg = "⚠️ O cache não possui códigos de rastreamento válidos."
        print(msg)
        return {"mensagem": msg}

    rastreios_validos = df_cache['Tracking Number'].dropna().unique().tolist()
    
    if len(rastreios_validos) > 10000:
        print("⚠️ Mais de 10.000 pacotes. Selecionando apenas os 10.000 primeiros.")
        rastreios_validos = rastreios_validos[:10000]

    limpar_pasta_downloads()

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR, headless=False, accept_downloads=True
        )
        page = browser.pages[0]
        try:
            caminho_atualizado = realizar_pesquisa_lote(page, rastreios_validos)
        except Exception as e:
            msg = f"❌ Erro na consulta em lote: {e}"
            print(msg)
            browser.close()
            return {"mensagem": msg}
        finally:
            browser.close()

    if not caminho_atualizado:
        return {"mensagem": "❌ Falha ao baixar o arquivo atualizado."}

    df_atualizado = ler_planilha_shopee_segura(caminho_atualizado)
    
    col_tracking = next((c for c in df_atualizado.columns if 'tracking number' in c.lower() or 'rastreamento' in c.lower()), None)
    col_status = next((c for c in df_atualizado.columns if 'status' in c.lower()), None)

    if not col_tracking or not col_status:
        return {"mensagem": "❌ Colunas de rastreamento ou status não encontradas no arquivo atualizado."}

    mapa_status = dict(zip(df_atualizado[col_tracking], df_atualizado[col_status]))
    
    df_cache['Status_Atual'] = df_cache['Tracking Number'].map(mapa_status).fillna('Desconhecido')
    df_cache.to_excel(CACHE_FILE, index=False)

    entregues_keywords = ['delivered', 'entregue', 'completed']
    
    df_cache['Finalizado'] = df_cache['Status_Atual'].astype(str).str.lower().apply(
        lambda x: any(k in x for k in entregues_keywords)
    )

    msg = f"📊 *ATUALIZAÇÃO DE ENTREGAS SHOPEE (Pacotes do Piso)* 📊\n"
    msg += f"━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"⏰ {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"

    total_entregues_geral = df_cache['Finalizado'].sum()
    total_pacotes_geral = len(df_cache)

    for motorista in sorted(df_cache['Motorista'].unique()):
        df_mot = df_cache[df_cache['Motorista'] == motorista]
        total_mot = len(df_mot)
        entregues_mot = df_mot['Finalizado'].sum()
        pendentes_mot = total_mot - entregues_mot
        
        msg += f"🚚 *{motorista}*: {entregues_mot} entregues de {total_mot} (Restam {pendentes_mot})\n"

    msg += f"━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"📦 *TOTAL DO DIA:* {total_entregues_geral} entregues de {total_pacotes_geral} (Restam {total_pacotes_geral - total_entregues_geral})\n"

    print(msg)
    
    return {
        "mensagem": msg,
        "arquivo": CACHE_FILE
    }

def executar_rotina_shopee_do_bot(tipo="consulta"):
    if tipo == "matinal":
        mensagens, imagens = rotina_matinal()
        return {"mensagens": mensagens, "imagens": imagens}
    elif tipo == "consulta":
        resultado = rotina_consulta()
        return resultado
    return None

if __name__ == "__main__":
    # rotina_matinal()
    # rotina_consulta()
    pass
