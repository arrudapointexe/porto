import os
import time
from playwright.sync_api import sync_playwright
from imile_utils import login_imile

def buscar_dados_contato_imile(codigo, usuario, senha):
    dados_cli = {"nome": "N/A", "tel": "N/A"}
    produto = "N/A"
    
    with sync_playwright() as p:
        # Executa em modo invisível (headless) para não interromper a tela
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = context.new_page()
        
        try:
            login_imile(page, usuario, senha)
            
            page.goto("https://ds.imile.com/#/DSOperation/WaybillManagement/dsTrackQuery", wait_until="domcontentloaded")
            
            target_f = None
            for _ in range(10):
                for f in page.frames:
                    try:
                        el = f.locator('.search-input input, input[placeholder*="insira"]').first
                        if el.is_visible(timeout=500):
                            el.fill(str(codigo))
                            f.locator('.search-btn, button:has-text("Pesquisar")').first.click(force=True)
                            target_f = f
                            break
                    except: continue
                if target_f: break
                page.wait_for_timeout(1000)

            if target_f:
                page.wait_for_timeout(3000)
                
                try: target_f.get_by_role("tab", name="CUSTOMER INFO").first.click(force=True)
                except: pass
                page.wait_for_timeout(1000) 
                
                try: 
                    olho = target_f.locator('.detail-item', has_text="Customer Name").locator('svg, [role="button"]').first
                    if olho.is_visible(timeout=1000):
                        olho.click(force=True)
                        page.wait_for_timeout(1500)
                except: pass

                try: 
                    olho_tel = target_f.locator('.detail-item', has_text="Customer phone").locator('svg, [role="button"]').first
                    if olho_tel.is_visible(timeout=1000):
                        olho_tel.click(force=True)
                        page.wait_for_timeout(1500)
                except: pass
                
                dados_cli = target_f.evaluate('''() => {
                    const buscar = (t) => {
                        const termos = t.split("|").map(s => s.trim().toLowerCase());
                        const items = Array.from(document.querySelectorAll('.detail-item'));
                        const found = items.find(i => {
                            const text = i.innerText.toLowerCase();
                            return termos.some(termo => text.includes(termo));
                        });
                        return found ? found.querySelector('.value').innerText.replace("****", "").trim() : "N/A";
                    };
                    return {
                        nome: buscar("Customer Name|Nome do Cliente"),
                        tel: buscar("Customer phone|Telefone do Cliente")
                    };
                }''')

                try:
                    try: target_f.get_by_role("tab", name="PRODUCT INFO").first.click(force=True)
                    except: target_f.get_by_text("PRODUCT INFO").first.click(force=True)
                    page.wait_for_timeout(1000) 
                    
                    try:
                        olho_prod = target_f.locator('.detail-item', has_text="Goods name").locator('svg, [role="button"]').first
                        if olho_prod.is_visible(timeout=1000):
                            olho_prod.click(force=True)
                            page.wait_for_timeout(1500)
                    except: pass
                    
                    produto = target_f.evaluate('''() => {
                        const buscar = (t) => {
                            const items = Array.from(document.querySelectorAll('.detail-item'));
                            const found = items.find(i => i.innerText.includes(t));
                            return found ? found.querySelector('.value').innerText.replace("****", "").trim() : "N/A";
                        };
                        return buscar("Goods name");
                    }''')
                except: 
                    produto = "N/A"
                    
        except Exception as e:
            print(f"Erro ao buscar contato do AWB {codigo}: {e}")
        finally:
            browser.close()
            
    return {
        "nome": dados_cli.get('nome', 'N/A'),
        "telefone": dados_cli.get('tel', 'N/A'),
        "produto": produto if produto else "N/A"
    }
