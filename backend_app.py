import sqlite3
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import hashlib
from datetime import datetime
import os
import sys
import re

sys.path.append("c:/bots")
try:
    from shopee_at_automator import gerar_at_shopee
except ImportError:
    print("Aviso: shopee_at_automator não pode ser importado.")
    def gerar_at_shopee(codigo):
        return False, "Simulação: Backend sem o bot"

app = FastAPI(title="App Motoristas API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "c:/bots/banco_app.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS motoristas
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  nome TEXT, 
                  login TEXT UNIQUE, 
                  senha_hash TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS registro_ats
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  id_motorista INTEGER,
                  codigo_pacote TEXT,
                  numero_at TEXT,
                  data_hora TEXT,
                  status TEXT,
                  mensagem TEXT)''')
    conn.commit()
    conn.close()

init_db()

class LoginRequest(BaseModel):
    login: str
    senha: str

class RegisterRequest(BaseModel):
    nome: str
    login: str
    senha: str

class GerarATRequest(BaseModel):
    id_motorista: int
    codigo_pacote: str

def hash_senha(senha: str):
    return hashlib.sha256(senha.encode()).hexdigest()

@app.post("/register")
def register(req: RegisterRequest):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO motoristas (nome, login, senha_hash) VALUES (?, ?, ?)", 
                  (req.nome, req.login, hash_senha(req.senha)))
        conn.commit()
        return {"sucesso": True, "mensagem": "Motorista cadastrado com sucesso!"}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Login já existe.")
    finally:
        conn.close()

@app.post("/login")
def login(req: LoginRequest):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM motoristas WHERE login = ? AND senha_hash = ?", 
              (req.login, hash_senha(req.senha)))
    user = c.fetchone()
    conn.close()
    
    if user:
        return {"sucesso": True, "id_motorista": user['id'], "nome": user['nome']}
    else:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

@app.post("/gerar_at")
def endpoint_gerar_at(req: GerarATRequest):
    codigo = str(req.codigo_pacote).strip().upper()
    
    if not codigo.startswith("BR"):
        raise HTTPException(status_code=400, detail="Código inválido. Deve começar com BR.")
        
    sucesso, mensagem = gerar_at_shopee(codigo)
    
    numero_at = ""
    if sucesso:
        ats = re.findall(r'AT202\d{10,15}[A-Z]*', mensagem)
        if ats:
            numero_at = ats[0]
            
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    data_hora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    status_str = "SUCESSO" if sucesso else "ERRO"
    c.execute("INSERT INTO registro_ats (id_motorista, codigo_pacote, numero_at, data_hora, status, mensagem) VALUES (?, ?, ?, ?, ?, ?)",
              (req.id_motorista, codigo, numero_at, data_hora, status_str, mensagem))
    conn.commit()
    conn.close()
    
    return {"sucesso": sucesso, "mensagem": mensagem, "numero_at": numero_at}

@app.get("/historico/{id_motorista}")
def get_historico(id_motorista: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM registro_ats WHERE id_motorista = ? ORDER BY id DESC LIMIT 50", (id_motorista,))
    rows = c.fetchall()
    conn.close()
    return {"historico": [dict(r) for r in rows]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
