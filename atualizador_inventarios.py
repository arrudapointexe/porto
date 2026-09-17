import time
import subprocess
import sys
from datetime import datetime
import os

# Fix encoding
sys.stdout.reconfigure(encoding='utf-8')

def run_script(script_name):
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Iniciando {script_name}...")
    try:
        # Run using the same python executable to ensure venv is used
        result = subprocess.run([sys.executable, script_name], capture_output=True, text=True, encoding='utf-8', check=True)
        print(f"✅ {script_name} finalizado com sucesso.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Erro ao rodar {script_name}: {e}")
        print("--- Output do Erro ---")
        print(e.stderr)

def main():
    intervalo_segundos = 360  # 6 minutos
    print("="*50)
    print("🤖 Atualizador Automático de Inventários (Shopee e iMile)")
    print(f"⏳ Intervalo configurado: {intervalo_segundos / 60} minutos")
    print("="*50)
    
    # Muda o diretório atual para onde os scripts estão (para evitar erros de caminho relativo)
    os.chdir(r"c:\bots")
    
    while True:
        print(f"\n--- Nova Rodada de Atualização: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} ---")
        
        # 1. Atualizar Shopee
        run_script("recebimento_shopee.py")
        
        # 2. Atualizar iMile
        run_script("atualizar_latencia_imile.py")
        
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Rodada finalizada. Aguardando {intervalo_segundos/60} minutos para a próxima...")
        
        # Escreve a data da última atualização para o dashboard poder ler
        with open("ultima_atualizacao_inventario.txt", "w", encoding="utf-8") as f:
            f.write(datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
            
        time.sleep(intervalo_segundos)

if __name__ == "__main__":
    main()
