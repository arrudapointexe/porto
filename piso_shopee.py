
import os
import glob
import sqlite3
import pandas as pd
import time
import sys
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# Fix encoding para suportar emojis no Windows
sys.stdout.reconfigure(encoding='utf-8')

# --- Configurações ---
USER_DATA_DIR = r"C:\PerfilBotShopee"
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads_shopee")
DB_FILE = "piso.db"
# NOTA: O texto do status pode variar. Verifique no site se é 'Hub Received', 'Recebido no hub', etc.
STATUS_TO_FILTER = "Hub_Received" 

# --- Funções Auxiliares ---
def limpar_pasta_downloads():
    """Cria ou limpa o diretório de downloads."""
    print("🧹 Limpando downloads antigos...")
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    for arquivo in glob.glob(os.path.join(DOWNLOAD_DIR, "*")):
        try:
            os.remove(arquivo)
        except Exception as e:
            print(f"  - Não foi possível remover {arquivo}: {e}")

def setup_database():
    """Cria o banco de dados e a tabela se não existirem."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS piso_shopee (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL UNIQUE,
            rua TEXT,
            cidade TEXT,
            bairro TEXT,
            data_recebimento TEXT
        )
    """)
    conn.commit()
    conn.close()
    print(f"🗃️ Banco de dados '{DB_FILE}' configurado.")

def insert_data(codigo, rua, cidade, bairro, data_recebimento):
    """Insere ou atualiza um registro no banco de dados."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO piso_shopee (codigo, rua, cidade, bairro, data_recebimento)
        VALUES (?, ?, ?, ?, ?)
    """, (codigo, rua, cidade, bairro, data_recebimento))
    conn.commit()
    conn.close()

def ler_planilha_segura(caminho):
    """Lê um arquivo .csv ou .xlsx de forma robusta, tentando diferentes separadores e encodings."""
    print(f"📄 Lendo o arquivo baixado: {os.path.basename(caminho)}")
    if caminho.endswith('.csv'):
        tentativas = [
            (',', 'utf-8-sig'), (',', 'utf-8'), (',', 'latin1'),
            (';', 'utf-8-sig'), (';', 'latin1')
        ]
        for sep, enc in tentativas:
            try:
                df = pd.read_csv(caminho, sep=sep, encoding=enc, dtype=str, on_bad_lines='warn')
                # A good CSV should have a reasonable number of columns
                if len(df.columns) > 5:
                    print(f"✅ Arquivo CSV lido com sucesso (sep='{sep}', encoding='{enc}').")
                    return df
            except Exception:
                continue
    elif caminho.endswith('.xlsx'):
        try:
            df = pd.read_excel(caminho, dtype=str)
            print("✅ Arquivo XLSX lido com sucesso.")
            return df
        except Exception as e:
            print(f"❌ Erro ao ler arquivo XLSX: {e}")
            pass
        
    print("❌ Não foi possível ler a planilha com as configurações testadas.")
    return pd.DataFrame()

# --- Funções Principais com Playwright ---
def download_floor_report(page):
    """Navega para a exportação avançada, filtra por 'Hub Received' e baixa o relatório."""
    try:
        print("🌐 Acessando o portal da Shopee...")
        page.goto("https://spx.shopee.com.br/#/index", wait_until="domcontentloaded")

        print("📦 Navegando para Rastreio de Pedidos...")
        page.locator("span.sub-menu-title", has_text="Pedidos").wait_for(state="visible", timeout=60000)
        page.locator("span.sub-menu-title", has_text="Pedidos").click()
        page.locator("a[title='Rastreio de pedidos']").wait_for(state="visible", timeout=10000)
        page.locator("a[title='Rastreio de pedidos']").click()

        print("⚙️ Abrindo Exportação Avançada...")
        btn_exportar = page.locator("button", has_text="Exportar")
        btn_exportar.wait_for(state="visible", timeout=60000)
        btn_exportar.hover()
        page.locator("div.ssc-dropdown-item", has_text="Exportar Pedido Avançado").click()

        print(f"🔎 Aplicando filtro de Status para '{STATUS_TO_FILTER}'...")
        status_row = page.locator("div.s-tree-node__content").filter(
            has=page.locator(f"span.ssc-tree-node__label:text-is('{STATUS_TO_FILTER}')")
        )
        status_row.locator("label.ssc-checkbox-wrapper").click()
        
        conta_pedido_div = page.locator("div.ssc-form-item", has_text="Conta do pedido:")
        conta_pedido_div.locator("span.ssc-tree-node__label", has_text="All").first.click()

        page.locator("button.ssc-btn-type-primary", has_text="Confirmar").click()

        print("⏳ Aguardando o processamento do relatório no servidor (pode levar alguns minutos)...")
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
        return caminho_arquivo

    except PlaywrightTimeoutError as e:
        print(f"❌ Erro de Timeout: um elemento não apareceu a tempo. {e}")
        return None
    except Exception as e:
        print(f"❌ Erro inesperado durante o download: {e}")
        return None

def get_order_details(page, codigo):
    """Busca um código, clica na aba de informações e extrai endereço, cidade e bairro."""
    try:
        search_input = page.locator("input[placeholder*='Número de Rastreamento']")
        search_input.fill(codigo)
        search_input.press("Enter")
        time.sleep(2) # Pausa para a página de detalhes do pedido carregar

        # Clica na aba "Informações comprador/vendedor" para revelar os detalhes
        try:
            info_tab = page.locator("div.ssc-tabs-tab", has_text="Informações comprador/vendedor")
            info_tab.wait_for(state="visible", timeout=5000)
            info_tab.click()
            time.sleep(1) # Pausa para o conteúdo da aba carregar
        except PlaywrightTimeoutError:
            print(f"  - Aviso: Não foi possível encontrar a aba 'Informações comprador/vendedor' para o código {codigo}. Tentando continuar.")
            pass

        details = {}
        fields_to_extract = {
            "rua": "Endereço do comprador",
            "cidade": "Cidade",
            "bairro": "Bairro"
        }

        for key, label_text in fields_to_extract.items():
            try:
                label = page.locator(f"label:has-text('{label_text}')")
                base_container = page.locator("div.ssc-form-item", has=label).first
                
                eye_icon = base_container.locator("svg.sensitive-wrap-icon")
                eye_icon.wait_for(state="visible", timeout=5000)
                eye_icon.click()

                # Pausa para esperar a descriptografia
                time.sleep(0.5)
                
                data_div = base_container.locator("div.sensitive-wrap-data")
                details[key] = data_div.inner_text()
            except PlaywrightTimeoutError:
                print(f"  - Não foi possível encontrar ou revelar o campo '{label_text}' para o código {codigo}.")
                details[key] = None
        
        return details.get("rua"), details.get("cidade"), details.get("bairro")
    except Exception as e:
        print(f"  - Erro ao processar o código {codigo}: {e}")
        return None, None, None

def get_city_from_cep(cep):
    """Mapeia um CEP para uma cidade com base nas regras fornecidas."""
    if not isinstance(cep, str):
        return "Cidade Desconhecida"
    
    cep = ''.join(filter(str.isdigit, cep))
    
    cep_map = {
        '35930': 'João Monlevade', '35931': 'João Monlevade', '35932': 'João Monlevade',
        '35920': 'Nova Era',
        '35935': 'São Gonçalo do Rio Abaixo',
        '35980': 'Bela Vista de Minas',
        '35940': 'Rio Piracicaba', '35943': 'Rio Piracicaba', '35945': 'Rio Piracicaba',
        '35960': 'Santa Bárbara', '35961': 'Santa Bárbara', '35963': 'Santa Bárbara', '35966': 'Santa Bárbara',
        '35969': 'Catas Altas',
        '35970': 'Barão de Cocais', '35975': 'Barão de Cocais',
        '35984': 'Dionísio', '35985': 'Dionísio',
        '35986': 'São José do Goiabal',
        '35993': 'São Domingos do Prata', '35995': 'São Domingos do Prata', '35997': 'São Domingos do Prata',
    }

    for prefix, city in cep_map.items():
        if cep.startswith(prefix):
            return city
            
    return "Cidade Desconhecida"

def main():
    """Função principal que orquestra todo o processo."""
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
        print(f"♻️ Banco de dados antigo '{DB_FILE}' removido.")

    setup_database()
    limpar_pasta_downloads()

    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR, headless=False, accept_downloads=True, slow_mo=50
        )
        page = browser.pages[0]

        report_file_path = download_floor_report(page)
        if not report_file_path:
            print("❌ Falha ao baixar o relatório. Abortando script.")
            browser.close()
            return

        df = ler_planilha_segura(report_file_path)
        if df.empty:
            print("❌ O DataFrame está vazio. Abortando.")
            browser.close()
            return

        col_tracking = next((c for c in df.columns if 'tracking number' in c.lower()), None)
        col_date = df.columns[16] if len(df.columns) > 16 else None
        col_cep = df.columns[6] if len(df.columns) > 6 else None # Coluna G

        if not all([col_tracking, col_date, col_cep]):
            print(f"❌ Colunas essenciais não encontradas. Código:'{col_tracking}', Data:'{col_date}', CEP:'{col_cep}'.")
            browser.close()
            return

        print(f"✅ Colunas encontradas: Código='{col_tracking}', Data='{col_date}', CEP='{col_cep}'")
        
        # --- FILTRO DE DATA ---
        print("🔎 Filtrando pacotes recebidos no dia de hoje...")
        today = pd.Timestamp.now().normalize()
        df[col_date] = pd.to_datetime(df[col_date], format='%d-%m-%Y %H:%M', errors='coerce')
        original_count = len(df)
        df = df[df[col_date].dt.normalize() == today].copy()
        print(f"✅ Filtro de data aplicado. Pacotes de hoje: {len(df)} (de {original_count} no total).")
        if df.empty:
            print("ℹ️ Nenhum pacote de hoje no relatório. Encerrando.")
            browser.close()
            return

        # --- FILTRO DE CIDADE POR CEP ---
        print("🔎 Mapeando cidades pelo CEP e aplicando filtros...")
        df['cidade_mapeada'] = df[col_cep].apply(get_city_from_cep)
        
        # 1. Manter apenas as cidades que foram mapeadas com sucesso
        pre_filter_count = len(df)
        df = df[df['cidade_mapeada'] != 'Cidade Desconhecida'].copy()
        print(f"✅ Mapeamento concluído. Cidades conhecidas: {len(df)} (de {pre_filter_count}).")

        # 2. Excluir as cidades indesejadas
        excluded_cities = ['Santa Bárbara', 'Catas Altas', 'Barão de Cocais']
        pre_exclusion_count = len(df)
        df = df[~df['cidade_mapeada'].isin(excluded_cities)].copy()
        print(f"✅ Filtro de exclusão aplicado. Pacotes restantes: {len(df)} (de {pre_exclusion_count}).")

        if df.empty:
            print("ℹ️ Nenhum pacote restante após todos os filtros. Encerrando.")
            browser.close()
            return
        
        # --- INÍCIO DA BUSCA INDIVIDUAL ---
        print("\n🚚 Iniciando a processamento dos detalhes de cada pedido...")
        page.goto("https://spx.shopee.com.br/#/orderDetail/search", wait_until="domcontentloaded")

        for index, row in df.iterrows():
            codigo = str(row[col_tracking]).strip()
            data_recebimento = row[col_date]

            if not codigo or pd.isna(codigo) or 'BR' not in codigo:
                continue

            data_str = pd.to_datetime(data_recebimento).strftime('%d/%m/%Y %H:%M:%S') if pd.notna(data_recebimento) else ""
            cidade_mapeada = row['cidade_mapeada']
            
            print(f"\nProcessing {index + 1}/{len(df)}: {codigo} (Cidade Mapeada: {cidade_mapeada})")
            
            # Pesquisa detalhada apenas para João Monlevade
            if cidade_mapeada == 'João Monlevade':
                rua, cidade, bairro = get_order_details(page, codigo)
                if rua or cidade or bairro:
                    insert_data(codigo, rua, cidade, bairro, data_str)
                    print(f"  - ✔️ Sucesso! Rua: {rua}, Cidade: {cidade}, Bairro: {bairro}. Dados salvos.")
                else:
                    print(f"  - ❌ Falha ao extrair informações para o código {codigo}.")
                    insert_data(codigo, 'N/A', cidade_mapeada, 'N/A', data_str)
            else:
                # Para outras cidades, pula a pesquisa detalhada para economizar tempo
                print(f"  - ⏭️ Pulando pesquisa detalhada para {cidade_mapeada}.")
                insert_data(codigo, 'N/A', cidade_mapeada, 'N/A', data_str)

        print("\n🎉 Processo concluído com sucesso!")
        browser.close()

if __name__ == "__main__":
    while True:
        print("\n" + "="*50)
        print(f"🕒 Iniciando varredura do Piso Shopee: {time.strftime('%d/%m/%Y %H:%M:%S')}")
        print("="*50)
        try:
            main()
        except Exception as e:
            print(f"❌ Erro na execução principal: {e}")
        
        print("\n⏳ Aguardando 15 minutos para a próxima varredura...")
        time.sleep(900) # Aguarda 15 minutos (900 segundos)
