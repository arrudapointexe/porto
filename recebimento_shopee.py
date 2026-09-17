import os
import sys
import time
import glob
import zipfile
import pandas as pd
from datetime import datetime
from playwright.sync_api import sync_playwright

# Fix encoding
sys.stdout.reconfigure(encoding='utf-8')

DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads_shopee")
USER_DATA_DIR = r"C:\PerfilBotShopee"

def limpar_pasta_downloads():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    for arquivo in glob.glob(os.path.join(DOWNLOAD_DIR, "*")):
        try: os.remove(arquivo)
        except: pass

def ler_planilha_shopee_segura(caminho):
    if caminho.endswith('.csv'):
        tentativas = [(',', 'utf-8-sig'), (',', 'utf-8'), (',', 'latin1'), (';', 'utf-8-sig'), (';', 'latin1')]
        for sep, enc in tentativas:
            try:
                df = pd.read_csv(caminho, sep=sep, encoding=enc, dtype=str)
                if len(df.columns) > 2: return df
            except: continue
    else:
        try: return pd.read_excel(caminho, dtype=str)
        except: pass
    return pd.DataFrame()

def carregar_dicionario_ceps(caminho_excel):
    try:
        df_ceps = pd.read_excel(caminho_excel, dtype=str)
        df_ceps.columns = df_ceps.columns.astype(str).str.strip()
        
        col_cep = None
        col_cidade = None
        col_bairro = None

        if 'CEPs' in df_ceps.columns and 'Responsavel' in df_ceps.columns:
            col_cep = 'CEPs'
            col_cidade = 'Responsavel' 
            if len(df_ceps.columns) >= 4:
                col_bairro = df_ceps.columns[3]
        else:
            col_cep = df_ceps.columns[0]
            col_cidade = df_ceps.columns[2]
            if len(df_ceps.columns) >= 4:
                col_bairro = df_ceps.columns[3]

        df_ceps[col_cep] = df_ceps[col_cep].astype(str).str.replace(r'\D', '', regex=True)
        
        mapa_cidades = dict(zip(df_ceps[col_cep], df_ceps[col_cidade]))
        mapa_bairros = {}
        if col_bairro:
            mapa_bairros = dict(zip(df_ceps[col_cep], df_ceps[col_bairro]))

        return mapa_cidades, mapa_bairros
    except Exception as e:
        print(f"❌ Erro ao ler a base de CEPs: {e}")
        return {}, {}

def baixar_relatorio_piso(page):
    """Navega para a exportação avançada, filtra por 'Hub_Received' e baixa o relatório."""
    try:
        print("🌐 Acessando o portal da Shopee...")
        page.goto("https://spx.shopee.com.br/#/index", wait_until="domcontentloaded")

        print("📦 Navegando para Rastreio de Pedidos...")
        page.locator("span.sub-menu-title", has_text="Pedidos").wait_for(state="visible", timeout=300000)
        page.locator("span.sub-menu-title", has_text="Pedidos").click()
        page.locator("a[title='Rastreio de pedidos']").wait_for(state="visible", timeout=10000)
        page.locator("a[title='Rastreio de pedidos']").click()

        print("⚙️ Abrindo Exportação Avançada...")
        btn_exportar = page.locator("button", has_text="Exportar")
        btn_exportar.wait_for(state="visible", timeout=60000)
        btn_exportar.hover()
        page.locator("div.ssc-dropdown-item", has_text="Exportar Pedido Avançado").click()

        status_filtro = "Hub_Received"
        print(f"🔎 Aplicando filtro de Status para '{status_filtro}'...")
        status_row = page.locator("div.s-tree-node__content").filter(
            has=page.locator(f"span.ssc-tree-node__label:text-is('{status_filtro}')")
        )
        status_row.locator("label.ssc-checkbox-wrapper").click()
        
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
        print(f"✅ Download concluído: {caminho_arquivo}")
        
        if caminho_arquivo.endswith('.zip'):
            with zipfile.ZipFile(caminho_arquivo, 'r') as zip_ref:
                zip_ref.extractall(DOWNLOAD_DIR)
            arquivos = glob.glob(os.path.join(DOWNLOAD_DIR, "*.xlsx")) + glob.glob(os.path.join(DOWNLOAD_DIR, "*.csv"))
            caminho_arquivo = arquivos[0] if arquivos else caminho_arquivo
            
        return caminho_arquivo

    except Exception as e:
        print(f"❌ Erro inesperado durante o download: {e}")
        return None

def gerar_relatorio_volumetria(caminho_arquivo):
    print("📊 Cruzando dados com a base de CEPs...")
    mapa_cidades, mapa_bairros = carregar_dicionario_ceps("base_ceps.xlsx")
    df = ler_planilha_shopee_segura(caminho_arquivo)
    
    if df.empty:
        return "❌ Falha ao processar arquivo baixado da Shopee."

    col_cep = next((c for c in df.columns if c.lower() in ['postal code', 'cep', 'c.e.p']), None)
    if not col_cep:
        col_cep = next((c for c in df.columns if 'cep' in c.lower() or 'zipcode' in c.lower()), None)
    if not col_cep:
        return "❌ Coluna de CEP não encontrada."
        
    # Identificar a coluna de data para filtrar por "Hoje"
    # A Shopee usa "Current Station Received Time" ou "Horário de Entrada" ou "Inbound Time"
    col_data = next((c for c in df.columns if 'current station received' in c.lower() or 'horário de entrada' in c.lower() or 'inbound' in c.lower() or 'entrada' in c.lower()), None)
    
    hoje_str = datetime.now().strftime("%Y-%m-%d")
    hoje_str_br = datetime.now().strftime("%d/%m/%Y")
    hoje_str_shopee = datetime.now().strftime("%d-%m-%Y") # Shopee CSV format
    
    if col_data:
        # Filtra as linhas em que a data contenha o dia de hoje
        df = df[df[col_data].astype(str).str.contains(f"{hoje_str}|{hoje_str_br}|{hoje_str_shopee}", na=False)]
    else:
        # Se não achou a coluna específica, busca em todas as colunas de tempo
        cols_tempo = [c for c in df.columns if 'time' in c.lower() or 'hora' in c.lower() or 'data' in c.lower()]
        if cols_tempo:
            mask = pd.Series(False, index=df.index)
            for c in cols_tempo:
                mask = mask | df[c].astype(str).str.contains(f"{hoje_str}|{hoje_str_br}|{hoje_str_shopee}", na=False)
            df = df[mask]
        else:
            print("⚠️ Aviso: Coluna de data não identificada. O resumo pode conter pacotes de dias anteriores.")

    if df.empty:
        return f"ℹ️ Nenhum pacote recebido hoje ({hoje_str_br}) consta no Piso (Hub Received)."

    df[col_cep] = df[col_cep].astype(str).str.replace(r'\D', '', regex=True)
    df['Cidade'] = df[col_cep].map(mapa_cidades).fillna('OUTROS CEPS')
    df['Bairro_Mot'] = df[col_cep].map(mapa_bairros).fillna('NAO MAPEADO')

    # Filtra apenas o que é da base (remove OUTROS_CEPS se quiser, ou mantém para alerta)
    df_monlevade = df[df['Cidade'].str.contains("Monlevade", case=False, na=False)]
    df_interior = df[~df['Cidade'].str.contains("Monlevade|OUTROS CEPS", case=False, na=False)]
    
    msg = f"📊 <b>VOLUMETRIA DE RECEBIMENTO</b> 📊\n"
    msg += f"📅 {datetime.now().strftime('%d/%m/%Y')}\n\n"
    
    msg += "📍 <b>JOÃO MONLEVADE (Por Bairro)</b>\n"
    if df_monlevade.empty:
        msg += "Nenhum pacote recebido.\n"
    else:
        bairros = df_monlevade['Bairro_Mot'].value_counts()
        for bairro, qtd in bairros.items():
            bairro_safe = str(bairro).replace('<', '').replace('>', '').replace('&', '')
            msg += f"▫️ {bairro_safe}: {qtd}\n"
        msg += f"<b>Total Monlevade: {len(df_monlevade)}</b>\n"
        
    msg += "\n🛣️ <b>INTERIOR (Por Cidade)</b>\n"
    if df_interior.empty:
        msg += "Nenhum pacote recebido.\n"
    else:
        cidades = df_interior['Cidade'].value_counts()
        for cidade, qtd in cidades.items():
            cidade_safe = str(cidade).replace('<', '').replace('>', '').replace('&', '')
            msg += f"▫️ {cidade_safe}: {qtd}\n"
        msg += f"<b>Total Interior: {len(df_interior)}</b>\n"
        
    fujoes = df[df['Cidade'] == 'OUTROS CEPS']
    if not fujoes.empty:
        msg += f"\n⚠️ <b>FORA DA BASE / NÃO MAPEADOS:</b> {len(fujoes)}\n"
        ceps_fujoes = fujoes[col_cep].unique()
        msg += "<i>CEPs com erro: " + ", ".join(ceps_fujoes[:10])
        if len(ceps_fujoes) > 10:
            msg += "..."
        msg += "</i>\n"
        
    msg += f"━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"📦 <b>TOTAL GERAL:</b> {len(df)}\n"
    
    return msg

def executar_recebimento_volumetria():
    limpar_pasta_downloads()
    
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR, headless=False, accept_downloads=True
        )
        page = browser.new_page()
        for p_other in browser.pages:
            if p_other != page:
                try: p_other.close()
                except: pass
        
        try:
            caminho_arquivo = baixar_relatorio_piso(page)
            if not caminho_arquivo:
                return "❌ Erro ao exportar dados do Piso (Exportação Avançada)."
                
            mensagem = gerar_relatorio_volumetria(caminho_arquivo)
            return mensagem
            
        except Exception as e:
            return f"❌ Ocorreu um erro inesperado: {e}"
        finally:
            browser.close()

if __name__ == "__main__":
    res = executar_recebimento_volumetria()
    print(res)
