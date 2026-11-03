import os
import sys
import time
import shutil
import subprocess
from playwright.sync_api import sync_playwright
from imile_utils import login_imile

_PLAYWRIGHT_READY = False

def garantir_playwright_browsers():
    """
    Verifica e instala os navegadores do Playwright no ambiente Linux (Streamlit Cloud).
    """
    global _PLAYWRIGHT_READY
    if _PLAYWRIGHT_READY:
        return
    
    if os.name != 'nt':
        cache_dir = os.path.expanduser("~/.cache/ms-playwright")
        tem_navegador = False
        if os.path.exists(cache_dir):
            for root, dirs, files in os.walk(cache_dir):
                if any("chrome" in name or "chromium" in name for name in files + dirs):
                    tem_navegador = True
                    break
        
        if not tem_navegador:
            print("Instalando Chromium do Playwright no ambiente Linux...")
            try:
                subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
            except Exception as e:
                print(f"Aviso ao rodar 'playwright install chromium': {e}")
                
    _PLAYWRIGHT_READY = True

def _iniciar_browser(p):
    """
    Inicia o Chromium com flags essenciais para ambientes Linux/Cloud em containers.
    """
    garantir_playwright_browsers()
    
    launch_args = [
        "--disable-blink-features=AutomationControlled",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
    ]
    
    # Tentativa 1: Iniciar normalmente pelo Playwright
    try:
        return p.chromium.launch(headless=True, args=launch_args)
    except Exception as e1:
        print(f"Tentativa 1 com Playwright falhou ({e1}). Tentando 'playwright install chromium'...")
        try:
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
            return p.chromium.launch(headless=True, args=launch_args)
        except Exception as e2:
            print(f"Tentativa 2 após install falhou ({e2}). Tentando binário do sistema...")
            sys_chrome = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
            if sys_chrome:
                print(f"Usando Chromium do sistema: {sys_chrome}")
                return p.chromium.launch(executable_path=sys_chrome, headless=True, args=launch_args)
            raise RuntimeError(f"Nenhum navegador Chromium pôde ser iniciado: {e1} | {e2}")

def buscar_dados_contato_imile(codigo, usuario, senha):
    dados_cli = {"nome": "N/A", "tel": "N/A"}
    produto = "N/A"
    erro_msg = None
    browser = None
    
    try:
        with sync_playwright() as p:
            browser = _iniciar_browser(p)
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
                        except Exception:
                            continue
                    if target_f:
                        break
                    page.wait_for_timeout(1000)

                if target_f:
                    page.wait_for_timeout(3000)
                    
                    try:
                        target_f.get_by_role("tab", name="CUSTOMER INFO").first.click(force=True)
                    except Exception:
                        pass
                    page.wait_for_timeout(1000) 
                    
                    try: 
                        olho = target_f.locator('.detail-item', has_text="Customer Name").locator('svg, [role="button"]').first
                        if olho.is_visible(timeout=1000):
                            olho.click(force=True)
                            page.wait_for_timeout(1500)
                    except Exception:
                        pass

                    try: 
                        olho_tel = target_f.locator('.detail-item', has_text="Customer phone").locator('svg, [role="button"]').first
                        if olho_tel.is_visible(timeout=1000):
                            olho_tel.click(force=True)
                            page.wait_for_timeout(1500)
                    except Exception:
                        pass
                    
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
                        try:
                            target_f.get_by_role("tab", name="PRODUCT INFO").first.click(force=True)
                        except Exception:
                            target_f.get_by_text("PRODUCT INFO").first.click(force=True)
                        page.wait_for_timeout(1000) 
                        
                        try:
                            olho_prod = target_f.locator('.detail-item', has_text="Goods name").locator('svg, [role="button"]').first
                            if olho_prod.is_visible(timeout=1000):
                                olho_prod.click(force=True)
                                page.wait_for_timeout(1500)
                        except Exception:
                            pass
                        
                        produto = target_f.evaluate('''() => {
                            const buscar = (t) => {
                                const items = Array.from(document.querySelectorAll('.detail-item'));
                                const found = items.find(i => i.innerText.includes(t));
                                return found ? found.querySelector('.value').innerText.replace("****", "").trim() : "N/A";
                            };
                            return buscar("Goods name");
                        }''')
                    except Exception: 
                        produto = "N/A"
                        
            except Exception as e_inner:
                print(f"Erro durante scraping de contato do AWB {codigo}: {e_inner}")
                erro_msg = str(e_inner)
            finally:
                if browser:
                    try:
                        browser.close()
                    except Exception:
                        pass
                        
    except Exception as e_outer:
        print(f"Erro ao inicializar Playwright ou executar busca para AWB {codigo}: {e_outer}")
        erro_msg = str(e_outer)
        
    resultado = {
        "nome": dados_cli.get('nome', 'N/A'),
        "telefone": dados_cli.get('tel', 'N/A'),
        "produto": produto if produto else "N/A"
    }
    if erro_msg and (resultado["telefone"] == "N/A" or not resultado["telefone"]):
        resultado["erro"] = erro_msg
        
    return resultado
