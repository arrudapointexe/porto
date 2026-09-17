
import sqlite3
import pandas as pd
import os
import sys

# Fix encoding para suportar emojis no Windows
sys.stdout.reconfigure(encoding='utf-8')

# --- Configurações ---
DB_FILE = "piso.db"
OUTPUT_EXCEL_FILE = "piso_exportado.xlsx"
TABLE_NAME = "piso_shopee"

def export_to_excel():
    """
    Lê os dados da tabela do banco de dados SQLite e os exporta para um arquivo Excel.
    """
    if not os.path.exists(DB_FILE):
        print(f"❌ Erro: O arquivo de banco de dados '{DB_FILE}' não foi encontrado.")
        print("Certifique-se de que o script principal 'piso_shopee.py' foi executado com sucesso primeiro.")
        return

    try:
        # Conecta ao banco de dados SQLite
        conn = sqlite3.connect(DB_FILE)
        
        # Lê a tabela inteira para um DataFrame do pandas
        # O 'SELECT *' é seguro aqui porque o schema é bem definido e controlado por nós.
        df = pd.read_sql_query(f"SELECT * FROM {TABLE_NAME}", conn)
        
        # Fecha a conexão com o banco de dados
        conn.close()
        
        if df.empty:
            print(f"⚠️ O banco de dados '{DB_FILE}' foi encontrado, mas a tabela '{TABLE_NAME}' está vazia.")
            return
            
        print(f"✅ {len(df)} registros lidos do banco de dados.")

        # Formata a coluna de data para mostrar apenas DD/MM/YYYY
        print("📅 Formatando a coluna de data...")
        df['data_recebimento'] = pd.to_datetime(df['data_recebimento'], errors='coerce').dt.strftime('%d/%m/%Y')

        # Salva o DataFrame em um arquivo Excel
        # 'index=False' para não escrever o índice do DataFrame na planilha
        df.to_excel(OUTPUT_EXCEL_FILE, index=False)
        
        print(f"🚀 Sucesso! Os dados foram exportados para '{OUTPUT_EXCEL_FILE}'.")

    except Exception as e:
        print(f"❌ Ocorreu um erro durante a exportação: {e}")

if __name__ == "__main__":
    export_to_excel()
