import os
import time
from playwright.sync_api import sync_playwright

USER_DATA_DIR = r"C:\PerfilBotShopee"

def buscar_dados_contato_shopee(codigo):
    dados_cli = {"nome": "N/A", "tel": "N/A"}
    produto = "N/A"
    
    with sync_playwright() as p:
        try:
            # We try to use the persistent context. If it's locked, we might fail, but this is the way to be logged into Shopee.
            browser = p.chromium.launch_persistent_context(
                user_data_dir=USER_DATA_DIR, 
                headless=False,
                args=["--disable-blink-features=AutomationControlled"]
            )
            page = browser.new_page()
            for p_other in browser.pages:
                if p_other != page:
                    try: p_other.close()
                    except: pass
            
            # Go to Shopee SPX Order Detail page directly
            url_direta = f"https://spx.shopee.com.br/#/orderDetail/{codigo}/sender_info?originUrl=%2ForderTracking"
            page.goto(url_direta, wait_until="domcontentloaded")
            
            # Dá um tempo a mais para o React/Vue da Shopee carregar a página completamente
            page.wait_for_timeout(3000)
            
            # Click on 'Informações comprador/vendedor' tab
            tab_comprador = page.locator('.ssc-tabs-tab', has_text="Informações comprador/vendedor")
            if not tab_comprador.is_visible(timeout=5000):
                tab_comprador = page.locator('.ssc-tabs-tab', has_text="Buyer/Seller Info")
            
            if tab_comprador.is_visible():
                tab_comprador.click()
                page.wait_for_timeout(2000)
                
                # Extract Nome do Recebedor from title attribute
                nome_div = page.locator('label[for="buyer_name"] + div .sensitive-wrap-data').first
                if nome_div.is_visible():
                    dados_cli["nome"] = nome_div.get_attribute("title") or "N/A"
                
                # Extract Telefone from title attribute
                tel_div = page.locator('label[for="buyer_contact"] + div .sensitive-wrap-data').first
                if tel_div.is_visible():
                    dados_cli["tel"] = tel_div.get_attribute("title") or "N/A"
                
                # Extract Nome do SKU (Produto) from title attribute. It's inside a table or section with list of SKUs.
                # Find the column that contains the SKU name
                sku_div = page.locator('th:has-text("Nome do SKU"), th:has-text("SKU Name")')
                if sku_div.is_visible():
                    # The DOM structure is complex, let's just find all sensitive-wrap-data after the 'Informações do remetente e produto'
                    # Or easier: evaluate JS to find the SKU Name
                    produto = page.evaluate('''() => {
                        // Find the header for SKU Name
                        const headers = Array.from(document.querySelectorAll('th'));
                        const skuHeader = headers.find(h => h.innerText.includes('Nome do SKU') || h.innerText.includes('SKU Name'));
                        if (skuHeader) {
                            // Find the data cell in the body that corresponds to the same column index or just look for the title
                            // The SKU name is usually in a sensitive-wrap-data class inside the table body
                            const tbody = document.querySelector('.ssc-table-body tbody:not(.first-row)');
                            if (tbody) {
                                const row = tbody.querySelector('tr.ssc-table-row');
                                if (row) {
                                    // It's the 3rd cell usually (SKU ID, then SKU Name)
                                    // Just look for the one with title attribute that is not a number
                                    const cells = Array.from(row.querySelectorAll('.sensitive-wrap-data'));
                                    // The first sensitive cell in the row is usually the SKU name
                                    if (cells.length > 0) {
                                        let title = cells[0].getAttribute('title');
                                        if (title && title.includes('****')) {
                                            if (cells.length > 1) {
                                                title = cells[1].getAttribute('title');
                                            }
                                        }
                                        return title;
                                    }
                                }
                            }
                        }
                        return "N/A";
                    }''')
                    
        except Exception as e:
            print(f"Erro ao buscar contato do Rastreio Shopee {codigo}: {e}")
        finally:
            try:
                browser.close()
            except:
                pass
            
    return {
        "nome": dados_cli.get('nome', 'N/A').strip("_").strip(),
        "telefone": dados_cli.get('tel', 'N/A').strip(),
        "produto": (produto if produto else "N/A").strip()
    }

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(buscar_dados_contato_shopee(sys.argv[1]))
