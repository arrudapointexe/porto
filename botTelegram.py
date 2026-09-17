import telebot
import subprocess
import sys
import os
from playwright.sync_api import sync_playwright
import re
from dotenv import load_dotenv
import schedule
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import sync_time_patch  #offset time do googlinho

load_dotenv()

#omports
from gerar_perdas import extrair_relatorio_diario_completo
from SLAimile import atualizar_bd_manha, extrair_e_comparar_sla
from acareacoes import rodar_automacao_acareacao, rodar_automacao_acareacao_incremental
from shopee import carregar_dicionario_ceps, baixar_planilha_shopee, gerar_relatorio_shopee
from SLAShopee_novo import executar_rotina_shopee_do_bot
from recebimento_shopee import executar_recebimento_volumetria
from SLA_Arrival import executar_rotina_sla_arrival
from config import CHAT_ID_ALVO, BASES_ACAREACOES, BASES_SLA, ITR_LOC_CITIES, ITR_INT_CITIES, JML_LOC_CITIES, JML_INT_CITIES
from shopee_at_automator import extrair_codigo_barras, gerar_at_shopee
from ranking_entregas import rotina_ranking_entregas



TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)

#sla e lat
def executar_fluxo_sla(sigla, usuario, senha, chat_id):
    bot.send_message(chat_id, f"⏳ Iniciando extração e comparação de SLA da base {sigla} com o BD de hoje...")
    
    cidades_loc = JML_LOC_CITIES if sigla == "JML" else ITR_LOC_CITIES
    cidades_int = JML_INT_CITIES if sigla == "JML" else ITR_INT_CITIES
    
    img_path, msg = extrair_e_comparar_sla(usuario, senha, sigla, cidades_loc, cidades_int)
    
    if img_path and msg and "❌ Erro" not in msg:
        try:
            with open(img_path, 'rb') as foto:
                bot.send_photo(chat_id, foto, caption=msg, parse_mode="Markdown")
            bot.send_message(chat_id, f"✅ Processo SLA {sigla} finalizado com sucesso!")
        except Exception as e:
            bot.send_message(chat_id, f"❌ Erro ao enviar imagem SLA {sigla}: {e}")
    else:
        bot.send_message(chat_id, msg if msg else f"🚨 Erro crítico na base {sigla}.")

#arrival e oc
def executar_fluxo_arrival(sigla, usuario, senha, chat_id):
    bot.send_message(chat_id, f"⏳ Iniciando extração de SLA Arrival da base {sigla}...")
    try:
        img_path, msg = executar_rotina_sla_arrival(sigla, usuario, senha)
        if img_path:
            with open(img_path, 'rb') as foto:
                bot.send_photo(chat_id, foto, caption=msg, parse_mode="Markdown")
            bot.send_message(chat_id, f"✅ Processo Arrival {sigla} finalizado com sucesso!")
        else:
            bot.send_message(chat_id, msg)
    except Exception as e:
        bot.send_message(chat_id, f"❌ Erro fatal ao executar Arrival de {sigla}: {e}")

#acareações e resumo
def executar_fluxo_acareacao(sigla, usuario, senha, chat_id):
    arquivo_gerado = rodar_automacao_acareacao(sigla, usuario, senha, bot, chat_id)
    
    if arquivo_gerado and os.path.exists(arquivo_gerado):
        try:
            with open(arquivo_gerado, 'rb') as doc:
                bot.send_document(chat_id, doc, caption=f"📦 Planilha de Acareações {sigla} extraída e enviada ao Drive com sucesso!")
        except Exception as e:
            bot.send_message(chat_id, f"⚠️ A automação rodou, mas falhou ao enviar o Excel aqui no Telegram: {e}")
    else:
        bot.send_message(chat_id, f"✅ Processo de acareação da {sigla} finalizado, mas nenhum dado novo precisou ser salvo.")

def executar_fluxo_acareacao_incremental(sigla, usuario, senha, chat_id):
    arquivo_gerado = rodar_automacao_acareacao_incremental(sigla, usuario, senha, bot, chat_id)
    
    if arquivo_gerado and os.path.exists(arquivo_gerado):
        try:
            with open(arquivo_gerado, 'rb') as doc:
                bot.send_document(chat_id, doc, caption=f"📦 Planilha de Acareações {sigla} extraída e enviada ao Drive com sucesso!")
        except Exception as e:
            bot.send_message(chat_id, f"⚠️ A automação rodou, mas falhou ao enviar o Excel aqui no Telegram: {e}")
    else:
        bot.send_message(chat_id, f"✅ Processo de acareação da {sigla} finalizado, mas nenhum dado novo precisou ser salvo.")

def calcular_resumo_base(caminho_excel):
    from datetime import datetime, timedelta
    import pandas as pd
    if not caminho_excel or not os.path.exists(caminho_excel):
        return 0, 0
    try:
        df = pd.read_excel(caminho_excel)
        total = len(df)
        urgentes = 0
        agora = datetime.now()
        limite_5h = agora + timedelta(hours=5)
        
        if 'Prazo do Processo' in df.columns:
            for prazo_texto in df['Prazo do Processo'].dropna().astype(str):
                try:
                    try:
                        prazo_dt = datetime.strptime(prazo_texto.strip(), "%Y-%m-%d %H:%M:%S")
                    except:
                        prazo_dt = datetime.strptime(prazo_texto.strip()[:16], "%Y-%m-%d %H:%M")
                    
                    if prazo_dt <= limite_5h:
                        urgentes += 1
                except: pass
        return total, urgentes
    except:
        return 0, 0

# ==============================================================
# COMANDOS PRINCIPAIS DO BOT
# ==============================================================
@bot.message_handler(commands=['ajuda', 'start'])
def send_welcome(message):
    texto = (
        "Olá! Escolha um comando abaixo:\n\n"
        "🚚 *SHOPEE:*\n"
        "/shopee - Gerar Tabela Dinâmica de Vencimentos\n\n"
        "📊 *Relatórios:*\n"
        "/kpi - Atualiza o Dashboard Mensal\n"
        "/perdas - Relatório diário de inventários\n\n"
        "📈 *SLA e Latência (Automático 12, 15, 18 e 21h):*\n"
        "/bd_manha - Baixar o Inventário BD Matinal (iMile)\n"
        "/vencimento - Tabela dinâmica de aging (Latência Consolidada)\n"
        "/bd_manha_shopee - 🆕 Cache Matinal do Piso (Shopee)\n"
        "/consulta_shopee - 🆕 Pesquisa em Lote de Entregues (Shopee)\n"
        "/recebimento_shopee - 🆕 Volumetria de Recebimento do dia (Shopee)\n"
        "/jml - Checar SLA Atual JML\n"
        "/itr - Checar SLA Atual ITR\n"
        "/ctg - Checar SLA Atual CTG\n\n"
        "📦 *Automação de Acareações:*\n"
        "/acarea - Rodar todas as bases no Modo Turbo\n"
        "/acareajml - Buscar e subir acareações JML\n"
        "/acareaitr - Buscar e subir acareações ITR\n"
        "/acareactg - Buscar e subir acareações CTG\n"
        "/acareaatualjml - Atualizar apenas novas acareações JML\n"
        "/acareaatualitr - Atualizar apenas novas acareações ITR\n"
    )
    bot.reply_to(message, texto, parse_mode="Markdown")

@bot.message_handler(commands=['shopee'])
def command_shopee(message):
    bot.send_message(message.chat.id, "🔍 Iniciando a extração do Export Forward no portal da Shopee. Aguarde...")
    caminho_forward = baixar_planilha_shopee()
    if not caminho_forward or not os.path.exists(caminho_forward):
        bot.send_message(message.chat.id, "❌ Erro ao baixar o arquivo da Shopee. Verifique o portal ou o login.")
        return

    caminho_ceps = "base_ceps.xlsx"
    mapa_ceps = carregar_dicionario_ceps(caminho_ceps)
    if not mapa_ceps:
        bot.send_message(message.chat.id, "⚠️ Aviso: Base de CEPs vazia. Alguns pacotes ficarão sem cidade.")

    bot.send_message(message.chat.id, "📊 Planilha baixada! Gerando as imagens por rota...")
    mensagens, imagens = gerar_relatorio_shopee(caminho_forward, mapa_ceps)
    
    if not imagens: 
        for msg in mensagens:
            bot.send_message(message.chat.id, msg)
    else:
        for i, img in enumerate(imagens):
            if os.path.exists(img):
                with open(img, 'rb') as foto:
                    bot.send_photo(message.chat.id, foto, caption=mensagens[i], parse_mode="Markdown")
        if len(mensagens) > len(imagens):
            for aviso_extra in mensagens[len(imagens):]:
                bot.send_message(message.chat.id, aviso_extra)

@bot.message_handler(commands=['bd_manha_shopee'])
def command_bd_manha_shopee(message):
    bot.send_message(message.chat.id, "🌅 Iniciando Cache Matinal da Shopee (Piso)... Isso pode levar alguns minutos.")
    resultado = executar_rotina_shopee_do_bot("matinal")
    if resultado and resultado.get('mensagens'):
        mensagens = resultado['mensagens']
        imagens = resultado['imagens']
        for i, img in enumerate(imagens):
            if os.path.exists(img):
                with open(img, 'rb') as foto:
                    bot.send_photo(message.chat.id, foto, caption=mensagens[i] if i < len(mensagens) else "", parse_mode="Markdown")
        if len(mensagens) > len(imagens):
            for aviso in mensagens[len(imagens):]:
                bot.send_message(message.chat.id, aviso)
    else:
         bot.send_message(message.chat.id, "❌ Falha ao executar rotina matinal da Shopee.")

@bot.message_handler(commands=['consulta_shopee'])
def command_consulta_shopee(message):
    bot.send_message(message.chat.id, "🔍 Iniciando Pesquisa em Lote da Shopee para atualizar status...")
    resultado = executar_rotina_shopee_do_bot("consulta")
    if resultado and 'mensagem' in resultado:
        bot.send_message(message.chat.id, resultado['mensagem'], parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "❌ Falha ao realizar a consulta em lote da Shopee.")

@bot.message_handler(commands=['recebimento_shopee'])
def command_recebimento_shopee(message):
    bot.send_message(message.chat.id, "📦 Iniciando extração da volumetria de recebimento de hoje da Shopee. Isso pode levar 1 minuto...")
    resultado = executar_recebimento_volumetria()
    if resultado:
        bot.send_message(message.chat.id, resultado, parse_mode="HTML")
    else:
        bot.send_message(message.chat.id, "❌ Falha ao extrair a volumetria de recebimento.")

@bot.message_handler(commands=['meuid'])
def descobrir_id(message):
    bot.reply_to(message, f"O ID deste chat é: `{message.chat.id}`", parse_mode="Markdown")

@bot.message_handler(commands=['kpi'])
def extrair_kpi_comando(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, "📊 *Iniciando Extração de KPI!*\nO robô está varrendo a iMile para calcular as métricas. Isso leva alguns minutos...", parse_mode="Markdown")
    try:
        caminho_python = sys.executable
        caminho_script = "c:/bots/kpi_mensal.py"
        subprocess.run([caminho_python, caminho_script], check=True)
        bot.send_message(chat_id, "✅ *KPI Atualizado com Sucesso!*\nOs dados já estão disponíveis no seu Dashboard no site.", parse_mode="Markdown")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Ocorreu um erro ao extrair o KPI: {e}")

@bot.message_handler(commands=['perdas'])
def command_perdas(message):
    bot.send_message(message.chat.id, "🔍 A iniciar a extração diária. A descarregar novos inventários e gerar tabelas...")
    try:
        user_jml = os.getenv("IMILE_JML_USER")
        user_itr = os.getenv("IMILE_ITR_USER")
        pass_geral = os.getenv("IMILE_PASS")
        
        if not user_jml or not user_itr or not pass_geral:
            bot.send_message(message.chat.id, "⚠️ Credenciais de JML ou ITR ausentes no .env.")
            return

        msg_perdas, img_itr, img_jml = extrair_relatorio_diario_completo(user_jml, pass_geral, user_itr, pass_geral)
        
        if img_itr and os.path.exists(img_itr):
            with open(img_itr, 'rb') as f_itr:
                bot.send_photo(message.chat.id, f_itr)
        if img_jml and os.path.exists(img_jml):
            with open(img_jml, 'rb') as f_jml:
                bot.send_photo(message.chat.id, f_jml)
                
        bot.send_message(message.chat.id, msg_perdas)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ocorreu um erro na extração completa: {e}")

@bot.message_handler(commands=['vencimento'])
def command_vencimento(message):
    bot.send_message(message.chat.id, "📊 Gerando as tabelas de latência consolidadas. Isso pode levar alguns instantes...")
    try:
        from gerar_vencimentos import gerar_imagens_vencimentos
        imagens, msg = gerar_imagens_vencimentos()
        if imagens:
            for img in imagens:
                if os.path.exists(img):
                    with open(img, 'rb') as foto:
                        bot.send_photo(message.chat.id, foto)
            bot.send_message(message.chat.id, "✅ Tabelas geradas com sucesso!")
        else:
            bot.send_message(message.chat.id, f"❌ Não foi possível gerar as tabelas: {msg}")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ocorreu um erro ao gerar as tabelas: {e}")


    #sla 
@bot.message_handler(commands=['bd_manha'])
def command_bd_manha(message):
    bot.send_message(message.chat.id, "🌅 Iniciando a atualização do BD Matinal para ITR e JML. Isso levará alguns minutos...")
    user_jml = os.getenv("IMILE_JML_USER")
    user_itr = os.getenv("IMILE_ITR_USER")
    pw = os.getenv("IMILE_PASS")

    if atualizar_bd_manha(user_itr, pw, "ITR"):
        bot.send_message(message.chat.id, "✅ BD de ITR atualizado com sucesso!")
    else:
        bot.send_message(message.chat.id, "❌ Falha ao atualizar BD de ITR.")

    if atualizar_bd_manha(user_jml, pw, "JML"):
        bot.send_message(message.chat.id, "✅ BD de JML atualizado com sucesso!")
    else:
        bot.send_message(message.chat.id, "❌ Falha ao atualizar BD de JML.")
    bot.send_message(message.chat.id, "🎉 Processo de BD Matinal finalizado!")

@bot.message_handler(commands=['ctg'])
def command_sla_ctg(message):
    user = os.getenv("IMILE_CTG_USER")
    pw = os.getenv("IMILE_PASS")
    bot.send_message(message.chat.id, "⚠️ O fluxo do SLA CTG precisa de lista de cidades (LOC/INT) configuradas no bot.")

@bot.message_handler(commands=['jml'])
def command_sla_jml(message):
    user = os.getenv("IMILE_JML_USER")
    pw = os.getenv("IMILE_PASS")
    executar_fluxo_sla("JML", user, pw, message.chat.id)

@bot.message_handler(commands=['itr'])
def command_sla_itr(message):
    user = os.getenv("IMILE_ITR_USER")
    pw = os.getenv("IMILE_PASS")
    executar_fluxo_sla("ITR", user, pw, message.chat.id)

@bot.message_handler(commands=['arrival_jml'])
def command_arrival_jml(message):
    user = os.getenv("IMILE_JML_USER")
    pw = os.getenv("IMILE_PASS")
    executar_fluxo_arrival("JML", user, pw, message.chat.id)

@bot.message_handler(commands=['arrival_itr'])
def command_arrival_itr(message):
    user = os.getenv("IMILE_ITR_USER")
    pw = os.getenv("IMILE_PASS")
    executar_fluxo_arrival("ITR", user, pw, message.chat.id)

@bot.message_handler(commands=['arrival_snb'])
def command_arrival_snb(message):
    user = os.getenv("IMILE_SNB_USER")
    pw = os.getenv("IMILE_PASS")
    executar_fluxo_arrival("SNB", user, pw, message.chat.id)

# ----------------- COMANDOS DE ACAREAÇÕES MANUAIS -----------------
@bot.message_handler(commands=['acareactg'])
def command_acarea_ctg(message):
    user = os.getenv("IMILE_CTG_USER")
    pw = os.getenv("IMILE_PASS")
    executar_fluxo_acareacao("CTG", user, pw, message.chat.id)

@bot.message_handler(commands=['acareajml'])
def command_acarea_jml(message):
    user = os.getenv("IMILE_JML_USER")
    pw = os.getenv("IMILE_PASS")
    executar_fluxo_acareacao("JML", user, pw, message.chat.id)

@bot.message_handler(commands=['acareaitr'])
def command_acarea_itr(message):
    user = os.getenv("IMILE_ITR_USER")
    pw = os.getenv("IMILE_PASS")
    executar_fluxo_acareacao("ITR", user, pw, message.chat.id)

@bot.message_handler(commands=['acareaatualjml'])
def command_acarea_atual_jml(message):
    user = os.getenv("IMILE_JML_USER")
    pw = os.getenv("IMILE_PASS")
    executar_fluxo_acareacao_incremental("JML", user, pw, message.chat.id)

@bot.message_handler(commands=['acareaatualbim'])
def command_acarea_atual_bim(message):
    user = os.getenv("IMILE_BIM_USER")
    pw = os.getenv("IMILE_PASS")
    executar_fluxo_acareacao_incremental("BIM", user, pw, message.chat.id)

@bot.message_handler(commands=['acareaatualitr'])
def command_acarea_atual_itr(message):
    user = os.getenv("IMILE_ITR_USER")
    pw = os.getenv("IMILE_PASS")
    executar_fluxo_acareacao_incremental("ITR", user, pw, message.chat.id)

@bot.message_handler(commands=['acareaatualsnb'])
def command_acarea_atual_snb(message):
    user = os.getenv("IMILE_SNB_USER")
    pw = os.getenv("IMILE_PASS")
    executar_fluxo_acareacao_incremental("SNB", user, pw, message.chat.id)

@bot.message_handler(commands=['acareaatualctp'])
def command_acarea_atual_ctp(message):
    user = os.getenv("IMILE_CTP_USER")
    pw = os.getenv("IMILE_PASS")
    executar_fluxo_acareacao_incremental("CTP", user, pw, message.chat.id)

@bot.message_handler(commands=['acareactp'])
def command_acarea_ctp(message):
    user = os.getenv("IMILE_CTP_USER")
    pw = os.getenv("IMILE_PASS")
    executar_fluxo_acareacao("CTP", user, pw, message.chat.id)

@bot.message_handler(commands=['acareagvr'])
def command_acarea_gvr(message):
    user = os.getenv("IMILE_GVR_USER")
    pw = os.getenv("IMILE_PASS")
    executar_fluxo_acareacao("GVR", user, pw, message.chat.id)

@bot.message_handler(commands=['acareagnh'])
def command_acarea_gnh(message):
    user = os.getenv("IMILE_GNH_USER")
    pw = os.getenv("IMILE_PASS")
    executar_fluxo_acareacao("GNH", user, pw, message.chat.id)

@bot.message_handler(commands=['acareamnt'])
def command_acarea_mnt(message):
    user = os.getenv("IMILE_MNT_USER")
    pw = os.getenv("IMILE_PASS")
    executar_fluxo_acareacao("MNT", user, pw, message.chat.id)

@bot.message_handler(commands=['acareactp'])
def command_acarea_ctp(message):
    user = os.getenv("IMILE_CTP_USER")
    pw = os.getenv("IMILE_PASS")
    executar_fluxo_acareacao("CTP", user, pw, message.chat.id)

@bot.message_handler(commands=['acareaqhg'])
def command_acarea_qhg(message):
    user = os.getenv("IMILE_QHG_USER")
    pw = os.getenv("IMILE_PASS")
    executar_fluxo_acareacao("QHG", user, pw, message.chat.id)

@bot.message_handler(commands=['acarea'])
def acarea_todas(message):
    chat_id = message.chat.id
    bot.send_message(chat_id, "🚀 *A iniciar varredura geral (MODO TURBO)!*\nO robô vai extrair as acareações de *TODAS* as bases a rodar de 2 em 2...", parse_mode="Markdown")

    bases_para_rodar = BASES_ACAREACOES

    resumos = {}

    def processar_base_manual(sigla, usuario, senha):
        if not usuario or not senha:
            bot.send_message(chat_id, f"⚠️ Credenciais da base {sigla} ausentes no .env. A saltar...")
            return sigla, None
        bot.send_message(chat_id, f"⏳ *A iniciar base: {sigla} (Login: {usuario})*...", parse_mode="Markdown")
        try:
            caminho_file = rodar_automacao_acareacao(sigla, usuario, senha, bot, chat_id)
            return sigla, caminho_file
        except Exception as e:
            bot.send_message(chat_id, f"❌ Erro ao processar a base {sigla}: {e}")
            return sigla, None

    with ThreadPoolExecutor(max_workers=2) as executor:
        futuros = [executor.submit(processar_base_manual, b[0], b[1], b[2]) for b in bases_para_rodar]
        for futuro in as_completed(futuros):
            sigla, caminho_file = futuro.result()
            if caminho_file:
                total, urgentes = calcular_resumo_base(caminho_file)
                resumos[sigla] = {"total": total, "urgentes": urgentes}
            else:
                resumos[sigla] = {"total": 0, "urgentes": 0}

    msg_analistas = "📊 *CONSOLIDADO DE ACAREAÇÕES POR BASE* 📊\n━━━━━━━━━━━━━━━━━━━━━━\nOlá equipa, segue o balanço pendente:\n\n"
    total_rede = 0
    for sigla in [b[0] for b in bases_para_rodar]:
        if sigla in resumos:
            tot = resumos[sigla]["total"]
            urg = resumos[sigla]["urgentes"]
            total_rede += tot
            txt_urg = f"_(🚨 {urg} CRÍTICOS < 5H)_" if urg > 0 else "_(✅ Sem urgências)_"
            msg_analistas += f"🏢 *{sigla}:* {tot} pacote(s) {txt_urg}\n"
    msg_analistas += f"━━━━━━━━━━━━━━━━━━━━━━\n📦 *TOTAL DA REDE:* {total_rede} acareações pendentes."
    bot.send_message(chat_id, msg_analistas, parse_mode="Markdown")

#AT SHOPEE
last_photo_by_chat = {}

@bot.message_handler(content_types=['photo'])
def handle_photo_shopee(message):
    chat_id = message.chat.id
    caption = message.caption or ""
    
    last_photo_by_chat[chat_id] = {
        'message': message,
        'time': time.time()
    }
    
    if re.search(r'\bat\b', caption, re.IGNORECASE):
        processar_foto_at(message)
        last_photo_by_chat.pop(chat_id, None)

@bot.message_handler(func=lambda msg: msg.text and re.search(r'\bat\b', msg.text, re.IGNORECASE))
def handle_text_reply_at(message):
    chat_id = message.chat.id
    
    if message.reply_to_message and message.reply_to_message.content_type == 'photo':
        processar_foto_at(message.reply_to_message, message)
        return
        
    last_photo_info = last_photo_by_chat.get(chat_id)
    if last_photo_info and (time.time() - last_photo_info['time']) < 120:
        processar_foto_at(last_photo_info['message'], message)
        last_photo_by_chat.pop(chat_id, None)

def processar_foto_at(foto_msg, chat_msg=None):
    target_msg = chat_msg if chat_msg else foto_msg
    bot.reply_to(target_msg, "🔍 Processando foto para gerar AT Shopee...")
    try:
        file_info = bot.get_file(foto_msg.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        file_path = f"temp_{foto_msg.photo[-1].file_id}.jpg"
        with open(file_path, 'wb') as new_file:
            new_file.write(downloaded_file)
            
        codigo = extrair_codigo_barras(file_path)
        if os.path.exists(file_path):
            os.remove(file_path)
        
        if not codigo:
            bot.reply_to(target_msg, "⚠️ Não foi possível ler o código de barras (BR...S). Mande uma msg para mim no telegram e eu mesmo faço o tratamento manual!")
            return
            
        bot.reply_to(target_msg, f"📦 Código lido: `{codigo}`. Acessando SPX...")
        sucesso, msg_retorno = gerar_at_shopee(codigo)
        
        bot.reply_to(target_msg, msg_retorno, parse_mode="Markdown")
        
    except Exception as e:
        bot.reply_to(target_msg, f"❌ Erro ao processar a imagem: {e}")

#despertadores

def rotina_automatica_acareacoes():
    bot.send_message(CHAT_ID_ALVO, "⏰ *HORÁRIO ATINGIDO! Iniciando varredura automática (Modo Turbo)*", parse_mode="Markdown")
    
    bases_para_rodar = BASES_ACAREACOES

    resumos = {}
    def processar_base_auto(sigla, usuario, senha):
        if not usuario or not senha: return sigla, None
        bot.send_message(CHAT_ID_ALVO, f"⏳ *Iniciando base: {sigla} (Login: {usuario})*...", parse_mode="Markdown")
        try:
            caminho_file = rodar_automacao_acareacao(sigla, usuario, senha, bot, CHAT_ID_ALVO)
            return sigla, caminho_file
        except:
            return sigla, None

    with ThreadPoolExecutor(max_workers=2) as executor:
        futuros = [executor.submit(processar_base_auto, b[0], b[1], b[2]) for b in bases_para_rodar]
        for futuro in as_completed(futuros):
            sigla, caminho_file = futuro.result()
            if caminho_file:
                total, urgentes = calcular_resumo_base(caminho_file)
                resumos[sigla] = {"total": total, "urgentes": urgentes}
            else:
                resumos[sigla] = {"total": 0, "urgentes": 0}

    msg_analistas = "📊 *CONSOLIDADO (AUTOMÁTICO)* 📊\n━━━━━━━━━━━━━━━━━━━━━━\nBalanço pendente:\n\n"
    total_rede = 0
    for sigla in [b[0] for b in bases_para_rodar]:
        if sigla in resumos:
            tot = resumos[sigla]["total"]
            urg = resumos[sigla]["urgentes"]
            total_rede += tot
            txt_urg = f"_(🚨 {urg} CRÍTICOS < 5H)_" if urg > 0 else "_(✅ Sem urgências)_"
            msg_analistas += f"🏢 *{sigla}:* {tot} pacote(s) {txt_urg}\n"
    msg_analistas += f"━━━━━━━━━━━━━━━━━━━━━━\n📦 *TOTAL DA REDE:* {total_rede} acareações."
    bot.send_message(CHAT_ID_ALVO, msg_analistas, parse_mode="Markdown")

def rotina_automatica_sla():
    bot.send_message(CHAT_ID_ALVO, "⏰ *HORÁRIO ATINGIDO! Extração de SLA (Latência)...*", parse_mode="Markdown")
    
    bases_sla = BASES_SLA

    def processar_sla_auto(sigla, usuario, senha):
        if not usuario or not senha: return
        try: executar_fluxo_sla(sigla, usuario, senha, CHAT_ID_ALVO)
        except Exception as e: bot.send_message(CHAT_ID_ALVO, f"❌ Erro SLA {sigla}: {e}")
            
    def processar_arrival_auto(sigla, usuario, senha):
        if not usuario or not senha: return
        try: executar_fluxo_arrival(sigla, usuario, senha, CHAT_ID_ALVO)
        except Exception as e: bot.send_message(CHAT_ID_ALVO, f"❌ Erro Arrival {sigla}: {e}")

    with ThreadPoolExecutor(max_workers=2) as executor:
        futuros = [executor.submit(processar_sla_auto, b[0], b[1], b[2]) for b in bases_sla]
        futuros_arrival = [executor.submit(processar_arrival_auto, b[0], b[1], b[2]) for b in bases_sla]
        for futuro in as_completed(futuros + futuros_arrival): pass
        
    try:
        resultado_shopee = executar_rotina_shopee_do_bot("consulta")
        if resultado_shopee and 'mensagem' in resultado_shopee:
            bot.send_message(CHAT_ID_ALVO, resultado_shopee['mensagem'], parse_mode="Markdown")
    except Exception as e:
        bot.send_message(CHAT_ID_ALVO, f"❌ Erro na consulta automática da Shopee: {e}")

def rotina_automatica_atualizar_latencia_20m():
    def _run():
        try:
            from atualizar_latencia_imile import main as atualizar_latencia
            atualizar_latencia()

        except Exception as e:
            bot.send_message(CHAT_ID_ALVO, f"❌ Erro na atualização de latência (20m): {e}")
            
    import threading
    threading.Thread(target=_run, daemon=True).start()

def relogio_do_bot():
    while True:
        schedule.run_pending()
        time.sleep(10)

# Configurando os horários fixos
#schedule.every().day.at("08:00").do(rotina_automatica_acareacoes)
#schedule.every().day.at("10:00").do(rotina_automatica_acareacoes)
#schedule.every().day.at("12:00").do(rotina_automatica_acareacoes)
#schedule.every().day.at("14:00").do(rotina_automatica_acareacoes)
#schedule.every().day.at("16:00").do(rotina_automatica_acareacoes)
#schedule.every().day.at("18:00").do(rotina_automatica_acareacoes)
#schedule.every().day.at("20:00").do(rotina_automatica_acareacoes)

schedule.every().day.at("12:00").do(rotina_automatica_sla)
schedule.every().day.at("15:00").do(rotina_automatica_sla)
schedule.every().day.at("18:00").do(rotina_automatica_sla)
schedule.every().day.at("21:00").do(rotina_automatica_sla)

schedule.every(20).minutes.do(rotina_automatica_atualizar_latencia_20m)


# ==============================================================
# INICIALIZAÇÃO (SEMPRE AQUI NO FINAL)
# ==============================================================
threading.Thread(target=relogio_do_bot, daemon=True).start()
print("⏰ Relógio interno ativado! Rotinas agendadas.")
print("🤖 Bot iniciado e aguardando comandos manuais...")

bot.infinity_polling()