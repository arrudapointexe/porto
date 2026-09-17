import os
import sys
import time
from datetime import datetime

# Força o print a usar UTF-8 no Windows para suportar emojis
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import cv2
import zxingcpp
from playwright.sync_api import sync_playwright

USER_DATA_DIR = r"C:\PerfilBotShopee"

def extrair_codigo_barras(caminho_imagem):
    try:
        imagem = cv2.imread(caminho_imagem)
        if imagem is None: return None
        
        def validar_texto(texto):
            return texto.startswith("BR") and len(texto) > 10

        # Tentativa 1: Zxing original
        for res in zxingcpp.read_barcodes(imagem):
            if validar_texto(res.text): return res.text
            
        # Transformações para facilitar a leitura se a imagem original falhou
        gray = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)
        
        # Tentativa 2: Zxing em Escala de Cinza
        for res in zxingcpp.read_barcodes(gray):
            if validar_texto(res.text): return res.text
            
        # Tentativa 3: Limiarização (Threshold Otsu)
        _, thresh = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        for res in zxingcpp.read_barcodes(thresh):
            if validar_texto(res.text): return res.text
            
        # Tentativa 4: Redimensionar imagem
        scale_percent = 50
        width = int(gray.shape[1] * scale_percent / 100)
        height = int(gray.shape[0] * scale_percent / 100)
        resized = cv2.resize(gray, (width, height), interpolation=cv2.INTER_AREA)
        for res in zxingcpp.read_barcodes(resized):
            if validar_texto(res.text): return res.text

        # Tentativa 5: OpenCV Barcode Detector Nativo
        try:
            bd = cv2.barcode.BarcodeDetector()
            retval, decoded_info, decoded_type, points = bd.detectAndDecode(imagem)
            if retval and decoded_info:
                for info in decoded_info:
                    if validar_texto(info): return info
                    
            retval, decoded_info, decoded_type, points = bd.detectAndDecode(gray)
            if retval and decoded_info:
                for info in decoded_info:
                    if validar_texto(info): return info
        except:
            pass

        # Falhou em todas as tentativas
        return None
    except Exception as e:
        print(f"Erro ao extrair código de barras: {e}")
        return None

def gerar_at_shopee(codigo_rastreio):
    """
    Retorna (sucesso_booleano, mensagem_para_o_usuario)
    """
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            accept_downloads=True
        )
        page = browser.pages[0]
        try:
            page.goto(f"https://spx.shopee.com.br/#/orderDetail/{codigo_rastreio}/sender_info?originUrl=%2ForderTracking&module=am_hubDeliveryManagement&stationType=AM_HUB", wait_until="domcontentloaded")
            
            try:
                page.locator(".order-tracking-box").wait_for(state="visible", timeout=15000)
            except:
                pass

            page.wait_for_timeout(3000)
            
            status = ""
            texto_pagina = page.content()
            if "SOC_LHTransported" in texto_pagina or "SOC_LHTransporting" in texto_pagina:
                status = "Transporte"
            elif "Entregue" in texto_pagina:
                status = "Entregue"
            elif "Atribuído" in texto_pagina or "Allocated" in texto_pagina or "Assigned" in texto_pagina:
                status = "Atribuído"
            elif "Entrega" in texto_pagina or "Hub_Received" in texto_pagina:
                status = "Recebido no Hub"
            
            import re
            if status == "Transporte":
                return False, f"⚠️ O pacote `{codigo_rastreio}` está em transporte. Receba na base primeiro e tente novamente!"
            elif status == "Atribuído":
                ats = re.findall(r'AT202\d{10,15}[A-Z]*', texto_pagina)
                at_existente = ats[0] if ats else "outra tarefa"
                return False, f"⚠️ O pacote `{codigo_rastreio}` JÁ ESTÁ na {at_existente}! Você precisa receber na base (Hub Receive) para retirá-lo dessa AT antes de criar uma nova."
            elif status == "":
                return False, f"⚠️ Não foi possível confirmar se o pacote `{codigo_rastreio}` está Recebido no Hub. Faça o tratamento manual."
            
            page.goto("https://spx.shopee.com.br/#/delivery-assignment/list", wait_until="domcontentloaded")
            
            btn_criar_at = page.locator("button", has_text="Criar tarefa de atribuição")
            btn_criar_at.wait_for(state="visible", timeout=15000)
            btn_criar_at.click()
            
            page.wait_for_timeout(1000) # Aguarda o pop-up abrir
            
            # Clicar direto no botão Enviar sem mexer na data
            btn_enviar = page.locator("button.ssc-react-button-primary", has_text="Enviar").last
            btn_enviar.wait_for(state="visible", timeout=10000)
            btn_enviar.click(force=True)
            
            input_new_order = page.locator("input[placeholder='Por favor, escaneie ou insira SPX TN/TO']").first
            input_new_order.wait_for(state="visible", timeout=15000)
            input_new_order.fill(codigo_rastreio)
            input_new_order.press("Enter")
            
            page.wait_for_timeout(3000)
            
            # Verifica se o código foi adicionado verificando se ainda existe uma mensagem de erro
            texto_modal = page.content()
            if "erro" in texto_modal.lower() or "already" in texto_modal.lower() or "vinculado" in texto_modal.lower() or "não pode ser" in texto_modal.lower():
                return False, f"⚠️ O Shopee recusou o pacote `{codigo_rastreio}` na criação da AT (pode não estar na base ou já estar em outra AT). AT cancelada."
            
            # Checar se o código de rastreio está na tabela
            if page.locator(f"text={codigo_rastreio}").count() == 0:
                return False, f"⚠️ O pacote `{codigo_rastreio}` não foi adicionado à AT pelo Shopee. AT cancelada para evitar AT vazia."
            
            btn_concluido = page.locator("button", has_text="Concluído").first
            btn_concluido.click()
            
            page.wait_for_timeout(2000)
            
            try:
                txt_tarefa = page.locator("span", has_text="ID de tarefa atribuída:").locator("..").inner_text()
                at_code = txt_tarefa.split(":")[-1].strip()
                if at_code.startswith("AT"):
                    return True, f"✅ SUCESSO! O pacote `{codigo_rastreio}` foi colocado na tarefa {at_code}"
            except:
                pass
            
            texto_pagina = page.content()
            ats = re.findall(r'AT202\d{10,15}[A-Z]*', texto_pagina)
            if ats:
                return True, f"✅ SUCESSO! O pacote `{codigo_rastreio}` foi colocado na tarefa {ats[0]}"

            return False, f"⚠️ A tarefa foi criada para o pacote `{codigo_rastreio}`, mas não consegui capturar o código AT. Verifique no sistema."

        except Exception as e:
            return False, f"❌ Ocorreu um erro no robô ao tentar gerar AT para `{codigo_rastreio}`."
        finally:
            browser.close()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        caminho_img = sys.argv[1]
        codigo = extrair_codigo_barras(caminho_img)
        if not codigo:
            print("ERRO: Não foi possível ler o código de barras (BR...S). Faça o tratamento manual.")
        else:
            sucesso, msg = gerar_at_shopee(codigo)
            print(msg)
    else:
        print("Forneça o caminho da imagem como argumento.")
