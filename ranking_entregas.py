import pandas as pd
import os
import json
import glob
from datetime import datetime
import telebot
import subprocess
import sys
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
bot = telebot.TeleBot(TOKEN)
from config import CHAT_ID_ALVO

ESTADO_ARQUIVO = "c:/bots/estado_entregas.json"

def carregar_estado():
    if os.path.exists(ESTADO_ARQUIVO):
        try:
            with open(ESTADO_ARQUIVO, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {
        "data": datetime.now().strftime("%Y-%m-%d"),
        "scores": {"imile": {}, "shopee": {}},
        "active_awbs": {"imile": {}, "shopee": {}}
    }

def salvar_estado(estado):
    with open(ESTADO_ARQUIVO, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=4)

def ler_imile_atual():
    caminho = "c:/bots/latencia_consolidada.xlsx"
    if not os.path.exists(caminho):
        return {}
    try:
        df = pd.read_excel(caminho)
        df.columns = df.columns.astype(str).str.strip()
        
        if 'Driver Name' not in df.columns or 'Waybill No' not in df.columns:
            return {}
            
        df_validos = df.dropna(subset=['Driver Name', 'Waybill No'])
        df_validos = df_validos[df_validos['Driver Name'].astype(str).str.strip() != ""]
        df_validos = df_validos[df_validos['Driver Name'].astype(str).str.strip().str.lower() != "nan"]
        
        return dict(zip(df_validos['Waybill No'].astype(str), df_validos['Driver Name'].astype(str)))
    except Exception as e:
        print(f"Erro ao ler iMile no ranking: {e}")
        return {}

def ler_shopee_atual():
    dir_downloads = "c:/bots/downloads_shopee"
    if not os.path.exists(dir_downloads):
        return {}
        
    arquivos = glob.glob(os.path.join(dir_downloads, "*.xlsx")) + glob.glob(os.path.join(dir_downloads, "*.csv"))
    if not arquivos:
        return {}
        
    caminho = max(arquivos, key=os.path.getmtime)
    try:
        if caminho.endswith('.csv'):
            df = None
            for sep, enc in [(',', 'utf-8-sig'), (',', 'utf-8'), (',', 'latin1'), (';', 'utf-8-sig'), (';', 'latin1')]:
                try:
                    tmp_df = pd.read_csv(caminho, sep=sep, encoding=enc, dtype=str)
                    if len(tmp_df.columns) > 2: 
                        df = tmp_df
                        break
                except: continue
            if df is None: return {}
        else:
            df = pd.read_excel(caminho, dtype=str)
            
        col_tracking = next((c for c in df.columns if 'tracking' in c.lower()), None)
        col_driver = next((c for c in df.columns if 'driver name' in c.lower() or 'entregador' in c.lower()), None)
        
        if not col_tracking or not col_driver:
            return {}
            
        df_validos = df.dropna(subset=[col_driver, col_tracking])
        df_validos = df_validos[df_validos[col_driver].astype(str).str.strip() != ""]
        df_validos = df_validos[df_validos[col_driver].astype(str).str.strip().str.lower() != "nan"]
        
        return dict(zip(df_validos[col_tracking].astype(str), df_validos[col_driver].astype(str)))
    except Exception as e:
        print(f"Erro ao ler Shopee no ranking: {e}")
        return {}

def processar_mudancas(ativos_atuais, ativos_anteriores, scores):
    for awb, motorista in ativos_anteriores.items():
        if awb not in ativos_atuais:
            motorista_nome = motorista.title().strip()
            if motorista_nome not in scores:
                scores[motorista_nome] = 0
            scores[motorista_nome] += 1
    return scores

def formatar_ranking(scores_imile, scores_shopee):
    msg = "🏆 *RANKING DE ENTREGAS DE HOJE* 🏆\n\n"
    
    if scores_imile:
        msg += "🟩 *Top 10 - iMile:*\n"
        ranking_imile = sorted(scores_imile.items(), key=lambda x: x[1], reverse=True)
        for i, (mot, pts) in enumerate(ranking_imile[:10]):
            medalha = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "🏅"
            msg += f"{medalha} {mot} - {pts} pacotes\n"
        msg += "\n"
        
    if scores_shopee:
        msg += "🟧 *Top 10 - Shopee:*\n"
        ranking_shopee = sorted(scores_shopee.items(), key=lambda x: x[1], reverse=True)
        for i, (mot, pts) in enumerate(ranking_shopee[:10]):
            medalha = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "🏅"
            msg += f"{medalha} {mot} - {pts} pacotes\n"
            
    if not scores_imile and not scores_shopee:
        msg += "Nenhuma entrega registrada ainda. Acelera equipe! 🚀"
        
    return msg

def forcar_atualizacao_inventarios():
    print("Baixando planilhas atualizadas (Shopee e iMile) antes de rodar o ranking...")
    try:
        subprocess.run([sys.executable, "c:/bots/recebimento_shopee.py"], capture_output=True)
        subprocess.run([sys.executable, "c:/bots/atualizar_latencia_imile.py"], capture_output=True)
        print("Downloads concluídos com sucesso.")
    except Exception as e:
        print(f"Erro ao baixar inventários: {e}")

def rotina_ranking_entregas():
    print("Executando rotina de ranking de entregas...")
    
    # 1. Atualiza os inventários para ter a versão mais recente
    forcar_atualizacao_inventarios()
    
    estado = carregar_estado()
    hoje = datetime.now().strftime("%Y-%m-%d")
    
    if estado["data"] != hoje:
        estado = {
            "data": hoje,
            "scores": {"imile": {}, "shopee": {}},
            "active_awbs": {"imile": {}, "shopee": {}}
        }
        
    ativos_imile_atual = ler_imile_atual()
    ativos_shopee_atual = ler_shopee_atual()
    
    estado["scores"]["imile"] = processar_mudancas(ativos_imile_atual, estado["active_awbs"].get("imile", {}), estado["scores"].get("imile", {}))
    estado["scores"]["shopee"] = processar_mudancas(ativos_shopee_atual, estado["active_awbs"].get("shopee", {}), estado["scores"].get("shopee", {}))
    
    estado["active_awbs"]["imile"] = ativos_imile_atual
    estado["active_awbs"]["shopee"] = ativos_shopee_atual
    
    salvar_estado(estado)
    
    mensagem = formatar_ranking(estado["scores"]["imile"], estado["scores"]["shopee"])
    
    try:
        bot.send_message(CHAT_ID_ALVO, mensagem, parse_mode="Markdown")
        print("Ranking enviado com sucesso para o Telegram.")
    except Exception as e:
        print(f"Erro ao enviar ranking: {e}")

if __name__ == "__main__":
    rotina_ranking_entregas()
