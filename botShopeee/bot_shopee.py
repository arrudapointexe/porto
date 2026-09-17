import os
import cv2
import time
from pyzbar.pyzbar import decode
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# === CONFIGURAÇÕES ===
# Caminho da pasta que você criou no Passo 3. 
# O robô salvará seu login da Shopee aqui.
USER_DATA_DIR = r"C:\PerfilBotShopee" 

def ler_qr_code_da_imagem(caminho_imagem):
    """Lê a imagem do pacote e extrai o código de rastreio."""
    print(f"👁️ Escaneando imagem: {caminho_imagem}")
    try:
        img = cv2.imread(caminho_imagem)
        codigos = decode(img)
        
        for qrcode in codigos:
            texto = qrcode.data.decode('utf-8')
            if "BR" in texto or len(texto) > 10:
                print(f"✅ Código extraído: {texto}")
                return texto
                
        print("❌ Nenhum QR Code válido encontrado.")
        return None
    except Exception as e:
        print(f"❌ Erro na leitura da imagem: {e}")
        return None

def processar_pacote_na_shopee(codigo):
    """Abre a Shopee, verifica o status e, se necessário, cria a Tarefa de Atribuição."""
    
    with sync_playwright() as p:
        # headless=False faz o navegador aparecer na tela para você ver a mágica acontecer.
        browser = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR, 
            headless=False, 
            slow_mo=300 # Deixa os cliques um pouco mais lentos para a Shopee não bloquear
        )
        page = browser.pages[0]
        
        try:
            print(f"🌐 Consultando pedido {codigo}...")
            page.goto("https://spx.shopee.com.br/#/orderDetail/search", wait_until="domcontentloaded")
            
            # --- PAUSA PARA LOGIN MANUAL (APENAS NA PRIMEIRA VEZ) ---
            # Se for a primeira vez rodando, o script vai esperar você fazer login.
            if page.locator("input[placeholder*='E-mail']").is_visible() or "login" in page.url:
                print("⚠️ ATENÇÃO: Faça o login manualmente no navegador que abriu.")
                print("O robô vai aguardar 60 segundos para você fazer o login e passar pelo Captcha...")
                page.wait_for_url("**/orderDetail/search**", timeout=60000)
                print("✅ Login detectado! Retomando automação...")
            
            # 1. Pesquisa o Código
            search_input = page.locator("input[placeholder*='Número de Rastreamento']")
            search_input.wait_for(state="visible", timeout=15000)
            search_input.fill(codigo)
            search_input.press("Enter")
            
            time.sleep(3) # Aguarda o DOM carregar a resposta
            
            # 2. Captura o Status
            status_locator = page.locator("span.order-status span.ssc-tag-content").first
            status_locator.wait_for(state="visible", timeout=10000)
            status = status_locator.inner_text().strip().lower()
            print(f"📦 Status capturado: {status.upper()}")
            
            # 3. REGRA DE NEGÓCIO
            if "interceptado" in status:
                mensagem = f"🚨 *ATENÇÃO!* O pacote `{codigo}` está *INTERCEPTADO*.\nFavor devolver imediatamente."
            
            elif "hub_sorting" in status or "hub_received" in status or "recebido" in status:
                print("🛠️ Status validado. Iniciando criação de Tarefa de Atribuição (AT)...")
                
                # Navega para a tela de AT
                page.goto("https://spx.shopee.com.br/#/delivery-assignment/list", wait_until="domcontentloaded")
                
                # Clica em Criar Tarefa
                page.locator("button", has_text="Criar tarefa de atribuição").wait_for(state="visible", timeout=15000)
                page.locator("button", has_text="Criar tarefa de atribuição").click()
                
                # Clica em Enviar no modal
                page.locator("div.ssc-react-modal-buttons button.ssc-react-button-primary", has_text="Enviar").wait_for(state="visible", timeout=10000)
                page.locator("div.ssc-react-modal-buttons button.ssc-react-button-primary").click()
                
                time.sleep(2)
                
                # Digita o código do pacote na AT
                input_codigo = page.locator("input[placeholder='Por favor, escaneie ou insira SPX TN/TO']")
                input_codigo.wait_for(state="visible", timeout=15000)
                input_codigo.click()
                input_codigo.fill(codigo)
                input_codigo.press("Enter")
                
                time.sleep(3) # Aguarda o pacote ser registrado
                
                # Captura o ID da AT gerada
                id_tarefa = page.locator("div.task-id span").nth(1).inner_text().strip()
                
                mensagem = f"✅ Pacote `{codigo}` processado com sucesso.\n📝 *Tarefa de Atribuição criada:* `{id_tarefa}`."
                
            elif "entregue" in status:
                mensagem = f"📦 O pacote `{codigo}` já consta como *ENTREGUE* no sistema."
                
            else:
                mensagem = f"🔎 Pacote `{codigo}` verificado.\nStatus atual: *{status.upper()}*."
                
            return mensagem
            
        except PlaywrightTimeoutError:
            print("⚠️ Erro: Demora no carregamento da página ou elemento não encontrado.")
            return f"❌ Tentativa de automação para `{codigo}` falhou por lentidão no site."
        except Exception as e:
            print(f"❌ Erro crítico: {e}")
            return f"❌ Erro interno ao processar `{codigo}`."
        finally:
            browser.close()

# === TESTE LOCAL ===
if __name__ == "__main__":
    imagem_teste = "foto_teste.jpg" # O arquivo precisa estar na mesma pasta
    
    if os.path.exists(imagem_teste):
        codigo = ler_qr_code_da_imagem(imagem_teste)
        
        if codigo:
            resposta_final = processar_pacote_na_shopee(codigo)
            print("\n" + "="*50)
            print("💬 MENSAGEM QUE O BOT ENVIARIA NO WHATSAPP:")
            print(resposta_final)
            print("="*50)
    else:
        print(f"❌ Coloque uma foto com QR Code nomeada como '{imagem_teste}' na pasta do script para testar.")