import os
import sqlite3
import sys

# Fix encoding
sys.stdout.reconfigure(encoding='utf-8')

DB_FILE = "boticario.db"


def setup_database():
    # Cria a tabela se nao existir
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS bipagens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL,
            produto TEXT,
            quantidade INTEGER,
            rota TEXT,
            status TEXT DEFAULT 'PENDENTE',
            criado_em TEXT DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )
    conn.commit()
    conn.close()


def salvar_bipagem(codigo, produto="", quantidade=1, rota=""):
    from datetime import datetime
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM bipagens WHERE codigo = ?", (codigo,))
    if cursor.fetchone():
        conn.close()
        return False

    data_hoje = datetime.now().strftime("%d/%m/%Y")

    cursor.execute(
        """
        INSERT INTO bipagens (codigo, produto, quantidade, rota, status, criado_em)
        VALUES (?, ?, ?, ?, 'PENDENTE', ?)
        """,
        (codigo, produto, quantidade, rota, data_hoje),
    )
    conn.commit()
    conn.close()
    return True


def listar_bipagens(limit=100):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, codigo, produto, quantidade, rota, status, criado_em FROM bipagens ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def atualizar_rota(item_id, rota):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("UPDATE bipagens SET rota = ? WHERE id = ?", (rota, item_id))
    conn.commit()
    conn.close()
