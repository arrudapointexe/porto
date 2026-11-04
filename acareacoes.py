import os
import sys
import time
import pandas as pd
import re
from dotenv import load_dotenv

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
from playwright.sync_api import sync_playwright
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from imile_utils import login_imile
from google_utils import get_gspread_client

load_dotenv()

NOME_PLANILHA = os.getenv("NOME_PLANILHA", "acareaBase")

SUBTIPOS_IGNORADOS = {
    "tt bra prioridades",
    "tt bra inquiry - prioritys",
    "tt bra inquiry - priorities",
}


def eh_subtipo_ignorado(valor) -> bool:
    texto = re.sub(r"\s+", " ", str(valor or "").strip().lower())
    if not texto:
        return False
    if texto in SUBTIPOS_IGNORADOS:
        return True
    return bool(re.search(r"tt\s*bra\s*(prioridades|inquiry\s*[-–—]?\s*priorit)", texto, re.IGNORECASE))


def normalizar_codigo(codigo):
    return str(codigo or "").strip().replace(" ", "")


def extrair_awbs_da_planilha(valores):
    awbs = set()
    if not valores:
        return awbs

    for row in valores:
        if not row:
            continue

        primeira_celula = str(row[0]).strip()
        if not primeira_celula:
            continue

        valor_normalizado = primeira_celula.lower()
        if valor_normalizado in {"awb", "waybill", "codigo", "código", "tracking", "tracking number", "motorista", "nome", "telefone", "endereço", "produto", "valor", "prazo do processo", "subtipo", "número de referência", "numero de referencia", "nº de referência", "n° de referência", "referência", "referencia"}:
            continue

        awbs.add(normalizar_codigo(primeira_celula))

    return awbs


def filtrar_itens_novos(itens, awbs_existentes):
    awbs_existentes_norm = {normalizar_codigo(awb) for awb in awbs_existentes}
    itens_novos = []
    vistos = set()

    for item in itens:
        codigo = normalizar_codigo(item.get("codigo", ""))
        if not codigo or codigo in awbs_existentes_norm or codigo in vistos:
            continue

        vistos.add(codigo)
        itens_novos.append(item)

    return itens_novos


def remover_awbs_ausentes_da_planilha(valores, awbs_ativos):
    if not valores or len(valores) <= 1:
        return valores

    header = [str(c).strip().lower() for c in valores[0]]
    idx_awb = next((i for i, h in enumerate(header) if "awb" in h), 0)
    idx_subtipo = next((i for i, h in enumerate(header) if "subtipo" in h or "sub_tipo" in h or "motivo" in h or "tipo" in h), -1)

    awbs_ativos_norm = {normalizar_codigo(awb) for awb in awbs_ativos}
    linhas_filtradas = [valores[0]]

    for row in valores[1:]:
        if not row:
            continue

        if idx_subtipo >= 0 and len(row) > idx_subtipo and eh_subtipo_ignorado(row[idx_subtipo]):
            continue

        celula_awb = str(row[idx_awb]).strip() if len(row) > idx_awb else ""
        if not celula_awb:
            linhas_filtradas.append(row)
            continue

        if normalizar_codigo(celula_awb) in awbs_ativos_norm:
            linhas_filtradas.append(row)

    return linhas_filtradas


def sincronizar_linhas_da_planilha(linhas_existentes, dados_para_nuvem, awbs_ativos):
    if not dados_para_nuvem:
        return linhas_existentes or []

    header_nuvem = [str(c).strip() for c in dados_para_nuvem[0]]

    if not linhas_existentes:
        return dados_para_nuvem

    header_existente = [str(c).strip() for c in linhas_existentes[0]]

    # Validação de segurança: o cabeçalho existente DEVE conter 'AWB' e ter pelo menos 5 colunas.
    # Caso contrário, a planilha está corrompida, vazia ou foi limpa incorretamente.
    # Nesse caso, usamos a estrutura e dados completos de 'dados_para_nuvem'.
    has_awb = any("awb" in h.lower() for h in header_existente)
    if not has_awb or len(header_existente) < 5:
        return dados_para_nuvem

    # 1. Se existir uma coluna vazia (ex: adicionada recentemente entre AWB e Motorista), nomeia como 'Número de Referência'
    if len(header_existente) > 1 and header_existente[1] == "":
        header_existente[1] = "Número de Referência"

    # 2. Se 'Número de Referência' não estiver presente no cabeçalho existente, insere logo após AWB
    has_ref = any(
        "referencia" in h.lower() or "referência" in h.lower() or "ref" in h.lower()
        for h in header_existente
    )
    if not has_ref:
        idx_awb = next((i for i, h in enumerate(header_existente) if "awb" in h.lower()), 0)
        insert_idx = idx_awb + 1
        header_existente.insert(insert_idx, "Número de Referência")
        for r in linhas_existentes[1:]:
            if len(r) > insert_idx:
                r.insert(insert_idx, "")
            else:
                r.append("")

    linhas_ativas = remover_awbs_ausentes_da_planilha(linhas_existentes, awbs_ativos)
    linhas_finais = []

    if linhas_ativas:
        linhas_finais.append(header_existente)
        linhas_finais.extend(linhas_ativas[1:])
    else:
        linhas_finais.append(header_existente)

    def criar_dict_linha(linha_valores):
        d = {}
        for idx, val in enumerate(linha_valores):
            if idx < len(header_nuvem):
                d[header_nuvem[idx]] = val
        return d

    def formatar_para_header_existente(d_valores):
        nova_linha = []
        for col_nome in header_existente:
            col_norm = col_nome.lower()
            val = ""
            if "awb" in col_norm:
                val = d_valores.get("AWB", "")
            elif "referencia" in col_norm or "referência" in col_norm or "ref" in col_norm:
                val = d_valores.get("Número de Referência", "")
            elif "motorista" in col_norm:
                val = d_valores.get("Motorista", "")
            elif "subtipo" in col_norm or "sub_tipo" in col_norm:
                val = d_valores.get("Subtipo", "")
            elif "nome" in col_norm or "cliente" in col_norm:
                val = d_valores.get("Nome", "")
            elif "telefone" in col_norm or "tel" in col_norm:
                val = d_valores.get("Telefone", "")
            elif "endereco" in col_norm or "endereço" in col_norm:
                val = d_valores.get("Endereco", "")
            elif "produto" in col_norm:
                val = d_valores.get("Produto", "")
            elif "valor" in col_norm:
                val = d_valores.get("Valor", "")
            elif "prazo" in col_norm:
                val = d_valores.get("Prazo do Processo", "")
            else:
                val = d_valores.get(col_nome, "")
            nova_linha.append(val)
        return nova_linha

    idx_awb_existente = next((i for i, h in enumerate(header_existente) if "awb" in h.lower()), 0)
    awbs_ja_na_lista = {normalizar_codigo(item[idx_awb_existente]) for item in linhas_finais[1:] if len(item) > idx_awb_existente}

    # Mapa de dados novos para atualizar referências de linhas ativas que estavam vazias
    novos_por_awb = {}
    if dados_para_nuvem[1:]:
        for linha in dados_para_nuvem[1:]:
            if not linha:
                continue
            d_linha = criar_dict_linha(linha)
            codigo = normalizar_codigo(d_linha.get("AWB", ""))
            if codigo:
                novos_por_awb[codigo] = d_linha
                if codigo not in awbs_ja_na_lista:
                    linha_formatada = formatar_para_header_existente(d_linha)
                    linhas_finais.append(linha_formatada)
                    awbs_ja_na_lista.add(codigo)

    # Preenche 'Número de Referência' nas linhas existentes caso estivesse vazio e agora tenha sido capturado
    idx_ref = next((i for i, h in enumerate(header_existente) if "referencia" in h.lower() or "referência" in h.lower() or "ref" in h.lower()), -1)
    if idx_ref >= 0:
        for r in linhas_finais[1:]:
            if len(r) > idx_awb_existente:
                awb = normalizar_codigo(r[idx_awb_existente])
                if awb in novos_por_awb:
                    val_novo = novos_por_awb[awb].get("Número de Referência", "")
                    if val_novo and val_novo != "N/A" and (idx_ref >= len(r) or not str(r[idx_ref]).strip() or str(r[idx_ref]).strip().upper() == "N/A"):
                        if idx_ref < len(r):
                            r[idx_ref] = val_novo
                        else:
                            r.extend([""] * (idx_ref - len(r)))
                            r.append(val_novo)

    # Garantir tamanho homogêneo das linhas
    max_len = len(header_existente)
    for r in linhas_finais:
        if len(r) < max_len:
            r.extend([""] * (max_len - len(r)))

    return linhas_finais


def enviar_para_google_sheets(df_final, sigla, bot=None, chat_id=None, awbs_ativos=None):
    msg = f"☁️ Enviando dados para a aba {sigla} no Google Sheets..."
    print(msg)
    if bot and chat_id: bot.send_message(chat_id, msg)
    
    MAX_TENTATIVAS = 3
    for tentativa in range(MAX_TENTATIVAS):
        try:
            cliente = get_gspread_client()
            planilha_mestre = cliente.open(NOME_PLANILHA)
            
            # Cria a aba automaticamente se não existir
            try:
                planilha = planilha_mestre.worksheet(sigla)
            except gspread.exceptions.WorksheetNotFound:
                msg_nova_aba = f"✨ Aba '{sigla}' não encontrada. Criando nova aba automaticamente..."
                print(msg_nova_aba)
                if bot and chat_id: bot.send_message(chat_id, msg_nova_aba)
                planilha = planilha_mestre.add_worksheet(title=sigla, rows="1000", cols="20")
            
            dados_para_nuvem = [df_final.columns.values.tolist()] + [
                [str(c) if c is not None else "" for c in row]
                for row in df_final.fillna("").values.tolist()
            ]
            linhas_existentes = planilha.get_all_values()
            awbs_ativos_norm = {normalizar_codigo(awb) for awb in (awbs_ativos or set())}

            if not linhas_existentes:
                planilha.update('A1', dados_para_nuvem)
            else:
                linhas_finais = sincronizar_linhas_da_planilha(linhas_existentes, dados_para_nuvem, awbs_ativos_norm)
                planilha.clear()
                if linhas_finais:
                    planilha.update('A1', linhas_finais)
            
            msg_sucesso = f"✅ SUCESSO! Dados da base {sigla} sincronizados na nuvem."
            print(msg_sucesso)
            if bot and chat_id: bot.send_message(chat_id, msg_sucesso)
            return  # Se deu certo, sai da função
            
        except Exception as e:
            msg_erro = f"⚠️ Falha na tentativa {tentativa + 1} de enviar {sigla} para a nuvem. Tentando novamente..."
            print(msg_erro)
            time.sleep(5) # Espera 5 segundos antes de tentar de novo
            
    # Se tentou 3 vezes e falhou em todas
    msg_falha = f"❌ Erro crítico: Não foi possível enviar a base {sigla} após {MAX_TENTATIVAS} tentativas."
    print(msg_falha)
    if bot and chat_id: bot.send_message(chat_id, msg_falha)


def rodar_automacao_acareacao_incremental(sigla, usuario, senha, bot=None, chat_id=None):
    return rodar_automacao_acareacao(sigla, usuario, senha, bot, chat_id, modo_incremental=True)


def rodar_automacao_acareacao(sigla, usuario, senha, bot=None, chat_id=None, modo_incremental=False):
    
    def log(msg):
        texto = f"[{sigla} - Acareação] {msg}"
        print(texto)
        if bot and chat_id:
            bot.send_message(chat_id, texto)

    log("Iniciando automação...")

    with sync_playwright() as p:
        # O argumento '--disable-blink-features=AutomationControlled' é a mágica que esconde que é um robô
        browser = p.chromium.launch(
            headless=False, 
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        # 1. CORREÇÃO DA TELA CORTADA: Forçamos 1920x1080 e idioma em Inglês
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            accept_downloads=True
        )
        page = context.new_page()

        try:
            log("Acessando o portal...")
            login_imile(page, usuario, senha)
            
           # 3. NAVEGAÇÃO BLINDADA
            log("Navegando nos menus: Ticket de reclamação...")
            page.get_by_text(re.compile(r"Service|Atendimento|Serviço", re.IGNORECASE)).first.click(force=True)
            page.wait_for_timeout(1000)
            page.get_by_text(re.compile(r"Ticket management|Gestão de tickets", re.IGNORECASE)).first.click(force=True)
            page.wait_for_timeout(1000)
            page.get_by_text(re.compile(r"Complaint ticket|Ticket de reclamação|Reclamaç", re.IGNORECASE)).first.click(force=True)
            
            # 🔥 AUMENTADO PARA 25 SEGUNDOS (O site da iMile às vezes engasga para carregar a tabela)
            page.wait_for_timeout(25000) 

            # MUDAR PAGINAÇÃO PARA 100
            log("Ajustando paginação para 100...")
            for frame in page.frames:
                try:
                    caixa_paginacao = frame.locator('.imile-pagination-options .imile-select-selector').first
                    if caixa_paginacao.is_visible(timeout=3000):
                        texto_atual = frame.locator('.imile-pagination-options .imile-select-selection-item').first.inner_text()
                        if "100" not in texto_atual:
                            caixa_paginacao.click(force=True)
                            page.wait_for_timeout(2000)
                            opcao_100 = frame.locator('div[title="100 / página"], div[title="100 / page"]').first
                            if opcao_100.is_visible(timeout=4000):
                                opcao_100.click(force=True)
                                log("Paginação alterada! Aguardando site carregar as 100 linhas...")
                                # 🔥 AUMENTADO PARA 30 SEGUNDOS
                                page.wait_for_timeout(30000) 
                        break 
                except: continue
            
            # Mais uma folguinha extra antes de ler
            page.wait_for_timeout(8000)

            # BUSCA DE CÓDIGOS EM PROCESSING
            log("Buscando códigos em Processing...")
            codigos_prazos = []
            for index, frame in enumerate(page.frames):
                try:
                    if "Ticket" in frame.content() or "ticket" in frame.content() or "Reclama" in frame.content() or "AWB" in frame.content():
                        res = frame.evaluate(r'''() => {
                            try {
                                const itens = [];
                                const rows = document.querySelectorAll("tbody tr");
                                const headers = Array.from(document.querySelectorAll("thead th")).map(h => h.textContent.trim());

                                const awbIndex = headers.findIndex(h => h.includes("Related AWB") || h.includes("Waybill") || h.includes("AWB"));
                                const prazoIndex = headers.findIndex(h => h.includes("Deadline Process Time") || h.includes("Prazo"));
                                const statusIndex = headers.findIndex(h => h.includes("Handling Status") || h.includes("Status") || h.includes("Estado"));
                                const subTypeIndex = headers.findIndex(h => h.includes("Ticket Sub Type") || h.includes("Sub Type") || h.includes("Subtipo"));

                                rows.forEach(row => {
                                    const cells = Array.from(row.querySelectorAll("td"));
                                    if (!cells || cells.length === 0) return;

                                    let status = "";
                                    if (statusIndex >= 0 && cells[statusIndex]) {
                                        status = cells[statusIndex].textContent.trim();
                                    }
                                    if (!status || !status.includes("Processing")) {
                                        status = cells.some(c => c.textContent.trim().includes("Processing")) ? "Processing" : status;
                                    }

                                    if (status.includes("Processing")) {
                                        let codigo = "";
                                        let prazo = "N/A";
                                        let sub_tipo = "N/A";

                                        if (awbIndex >= 0 && cells[awbIndex]) {
                                            codigo = cells[awbIndex].textContent.trim();
                                        } 
                                        
                                        // Fallback robusto se codigo estiver vazio ou apenas espacos
                                        if (!codigo || codigo.length < 5) {
                                            const match = cells.map(c => c.textContent.trim()).join(' ').match(/\b\d{13,15}\b/);
                                            if (match) codigo = match[0];
                                        }

                                        if (prazoIndex >= 0 && cells[prazoIndex]) {
                                            prazo = cells[prazoIndex].textContent.trim();
                                        }
                                        
                                        if (subTypeIndex >= 0 && cells[subTypeIndex]) {
                                            sub_tipo = cells[subTypeIndex].textContent.trim();
                                        }

                                        if (codigo) itens.push({ codigo, prazo, sub_tipo });
                                    }
                                });
                                return { sucesso: true, itens: itens };
                            } catch(e) {
                                return { sucesso: false, error: e.message };
                            }
                        }''')
                        if res and res.get('sucesso'): 
                            codigos_prazos.extend(res.get('itens', []))
                        elif res and not res.get('sucesso'):
                            log(f"⚠️ Erro ao extrair dados no JS: {res.get('error')}")
                except: continue

            codigos_map = {}
            for item in codigos_prazos:
                if eh_subtipo_ignorado(item.get('sub_tipo', '')):
                    continue
                codigo = str(item.get('codigo', '')).strip()
                if codigo: codigos_map[codigo] = item

            codigos_finais = list(codigos_map.values())
            log(f"Total de códigos Processing capturados: {len(codigos_finais)}")

            if modo_incremental:
                try:
                    cliente = get_gspread_client()
                    planilha_mestre = cliente.open(NOME_PLANILHA)
                    try:
                        planilha = planilha_mestre.worksheet(sigla)
                    except gspread.exceptions.WorksheetNotFound:
                        planilha = planilha_mestre.add_worksheet(title=sigla, rows="1000", cols="20")

                    awbs_existentes = extrair_awbs_da_planilha(planilha.get_all_values())
                except Exception as e:
                    log(f"Não foi possível consultar a planilha para filtrar itens já existentes: {e}")
                    awbs_existentes = set()

                awbs_ativos = {normalizar_codigo(item.get("codigo", "")) for item in codigos_finais}
                codigos_finais = filtrar_itens_novos(codigos_finais, awbs_existentes)
                log(f"Códigos novos para detalhar após checagem na planilha: {len(codigos_finais)}")

                if not codigos_finais:
                    log("Nenhum código novo para detalhar. Finalizando sem gastar descriptografia adicional...")
                    browser.close()
                    return None
            else:
                awbs_ativos = {normalizar_codigo(item.get("codigo", "")) for item in codigos_finais}

            log("Iniciando consultas detalhadas (isso pode demorar um pouco)...")
            page.goto("https://ds.imile.com/#/DSOperation/WaybillManagement/dsTrackQuery", wait_until="domcontentloaded")
            
            dados_finais_excel = []

            for item in codigos_finais:
                codigo = item['codigo']
                prazo_da_linha = item['prazo']
                sub_tipo_da_linha = item.get('sub_tipo', 'N/A') # 👇 NOVO: Puxando o subtipo
                target_f = None
                
                for _ in range(10):
                    for f in page.frames:
                        try:
                            el = f.locator('.search-input input, input[placeholder*="insira"], input[placeholder*="Please"], input[placeholder*="please"], textarea').first
                            if el.is_visible(timeout=500):
                                el.fill(str(codigo))
                                f.locator('.search-btn, button:has-text("Pesquisar"), button:has-text("Search"), button:has-text("Query")').first.click(force=True)
                                target_f = f
                                break
                        except: continue
                    if target_f: break
                    page.wait_for_timeout(1000)

                if target_f:
                    page.wait_for_timeout(3000)
                    
                    # 1. ABA INFORMAÇÃO BÁSICA / BASIC INFO -> Extrair Número de Referência
                    num_referencia = "N/A"
                    try:
                        try: target_f.get_by_role("tab", name=re.compile(r"BASIC INFO|INFORMAÇÃO BÁSICA|INFORMAÇÕES BÁSICAS|INFORMAÇÃO BASICA", re.IGNORECASE)).first.click(force=True)
                        except: target_f.get_by_text(re.compile(r"BASIC INFO|INFORMAÇÃO BÁSICA|INFORMAÇÕES BÁSICAS|INFORMAÇÃO BASICA", re.IGNORECASE)).first.click(force=True)
                        page.wait_for_timeout(1000)
                    except: pass

                    try:
                        olho_ref = target_f.locator('.detail-item', has_text=re.compile(r"referência|referencia|reference", re.IGNORECASE)).locator('svg, [role="button"]').first
                        if olho_ref.is_visible(timeout=800):
                            olho_ref.click(force=True)
                            page.wait_for_timeout(1000)
                    except: pass

                    try:
                        num_referencia = target_f.evaluate('''() => {
                            const termos = ["nº de referência", "n° de referência", "no de referencia", "número de referência", "numero de referencia", "reference no", "reference number", "ref no", "referência", "referencia", "reference"];
                            
                            // 1. Tentar por .detail-item
                            const items = Array.from(document.querySelectorAll('.detail-item'));
                            for (const item of items) {
                                const text = (item.innerText || "").toLowerCase();
                                if (termos.some(t => text.includes(t))) {
                                    const valEl = item.querySelector('.value');
                                    if (valEl && valEl.innerText.trim()) {
                                        const v = valEl.innerText.replace(/\\*\\*\\*\\*/g, "").trim();
                                        if (v && v !== "-") return v;
                                    }
                                    const lines = item.innerText.split('\\n').map(l => l.trim()).filter(Boolean);
                                    if (lines.length > 1) {
                                        const v = lines[lines.length - 1].replace(/\\*\\*\\*\\*/g, "").trim();
                                        if (v && v !== "-" && !termos.some(t => v.toLowerCase().includes(t))) return v;
                                    }
                                }
                            }
                            
                            // 2. Tentar por elementos genéricos
                            const allNodes = Array.from(document.querySelectorAll('.ant-descriptions-item, .ant-form-item, div, tr, li'));
                            for (const node of allNodes) {
                                if (node.innerText && node.innerText.length < 150) {
                                    const text = node.innerText.toLowerCase();
                                    if (termos.some(t => text.includes(t))) {
                                        const valEl = node.querySelector('.ant-descriptions-item-content, .value, dd, span:last-child');
                                        if (valEl && valEl.innerText.trim()) {
                                            const v = valEl.innerText.replace(/\\*\\*\\*\\*/g, "").trim();
                                            if (v && v !== "-" && !termos.some(t => v.toLowerCase().includes(t))) return v;
                                        }
                                        const lines = node.innerText.split('\\n').map(l => l.trim()).filter(Boolean);
                                        if (lines.length > 1) {
                                            const v = lines[lines.length - 1].replace(/\\*\\*\\*\\*/g, "").trim();
                                            if (v && v !== "-" && !termos.some(t => v.toLowerCase().includes(t))) return v;
                                        }
                                    }
                                }
                            }
                            return "N/A";
                        }''')
                    except Exception as e:
                        num_referencia = "N/A"

                    # 2. ABA INFORMAÇÕES DO CLIENTE
                    try: 
                        try: target_f.get_by_role("tab", name=re.compile(r"CUSTOMER INFO|INFORMAÇÃO DO CLIENTE|INFORMAÇÕES DO CLIENTE", re.IGNORECASE)).first.click(force=True)
                        except: target_f.get_by_text(re.compile(r"CUSTOMER INFO|INFORMAÇÃO DO CLIENTE|INFORMAÇÕES DO CLIENTE", re.IGNORECASE)).first.click(force=True)
                        page.wait_for_timeout(1000)
                    except: pass
                    
                    try: 
                        olho = target_f.locator('.detail-item', has_text=re.compile(r"Customer Name|Nome do Cliente", re.IGNORECASE)).locator('svg, [role="button"]').first
                        if olho.is_visible(timeout=1000):
                            olho.click(force=True)
                            page.wait_for_timeout(1500)
                    except: pass

                    try: 
                        olho_tel = target_f.locator('.detail-item', has_text=re.compile(r"Customer phone|Telefone do Cliente|Telefone", re.IGNORECASE)).locator('svg, [role="button"]').first
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
                            tel: buscar("Customer phone|Telefone do Cliente"),
                            end: buscar("Address|Endereço"),
                            bairro: buscar("Customer District|Bairro"),
                            cidade: buscar("Recipient City|Cidade do Destinatário")
                        };
                    }''')

                    # 3. ABA INFORMAÇÕES DO PRODUTO
                    try:
                        try: target_f.get_by_role("tab", name=re.compile(r"PRODUCT INFO|INFORMAÇÃO DO PRODUTO|INFORMAÇÕES DO PRODUTO|PRODUTO", re.IGNORECASE)).first.click(force=True)
                        except: target_f.get_by_text(re.compile(r"PRODUCT INFO|INFORMAÇÃO DO PRODUTO|INFORMAÇÕES DO PRODUTO|PRODUTO", re.IGNORECASE)).first.click(force=True)
                        page.wait_for_timeout(1000) 
                        
                        try:
                            olho_prod = target_f.locator('.detail-item', has_text=re.compile(r"Goods name|mercadoria|produto", re.IGNORECASE)).locator('svg, [role="button"]').first
                            if olho_prod.is_visible(timeout=1000):
                                olho_prod.click(force=True)
                                page.wait_for_timeout(1500)
                        except: pass

                        try:
                            olho_val = target_f.locator('.detail-item', has_text=re.compile(r"Declared Value|valor", re.IGNORECASE)).locator('svg, [role="button"]').first
                            if olho_val.is_visible(timeout=1000):
                                olho_val.click(force=True)
                                page.wait_for_timeout(1500)
                        except: pass
                        
                        dados_prod = target_f.evaluate('''() => {
                            const buscar = (t) => {
                                const termos = t.split("|").map(s => s.trim().toLowerCase());
                                const items = Array.from(document.querySelectorAll('.detail-item'));
                                const found = items.find(i => {
                                    const text = i.innerText.toLowerCase();
                                    return termos.some(termo => text.includes(termo));
                                });
                                return found ? found.querySelector('.value').innerText.replace("****", "").trim() : "N/A";
                            };
                            return { produto: buscar("Goods name|mercadoria|produto"), valor: buscar("Declared Value|valor declarado|valor") };
                        }''')
                        produto = dados_prod['produto']
                        valor = dados_prod['valor']
                    except: 
                        produto = "N/A"
                        valor = "0.00"

                    # 4. ABA OPERAÇÃO (MOTORISTA)
                    prazo = prazo_da_linha if prazo_da_linha else "N/A"
                    try:
                        try: target_f.get_by_role("tab", name=re.compile(r"OPS INFO|OPERAÇÃO|OPERACOES|INFORMAÇÃO DE OPERAÇÃO", re.IGNORECASE)).first.click(force=True)
                        except: target_f.get_by_text(re.compile(r"OPS INFO|OPERAÇÃO|OPERACOES|INFORMAÇÃO DE OPERAÇÃO", re.IGNORECASE)).first.click(force=True)
                        page.wait_for_timeout(1000)
                        
                        motorista = target_f.evaluate('''() => {
                            const items = Array.from(document.querySelectorAll('.detail-item'));
                            const found = items.find(i => i.innerText.includes("DA"));
                            return found ? found.querySelector('.value').innerText.replace("****", "").trim() : "N/A";
                        }''')
                    except: motorista = "N/A"

                    endereco_completo = f"{dados_cli['end']}, {dados_cli['bairro']}, {dados_cli['cidade']}".replace(", N/A", "").replace("N/A, ", "")

                    dados_finais_excel.append({
                        "AWB": codigo,
                        "Número de Referência": num_referencia,
                        "Motorista": motorista,
                        "Subtipo": sub_tipo_da_linha, 
                        "Nome": dados_cli['nome'],
                        "Telefone": dados_cli['tel'],
                        "Endereco": endereco_completo,
                        "Produto": produto,
                        "Valor": valor,
                        "Prazo do Processo": prazo
                    })

            if dados_finais_excel:
                # ==========================================
                # NOVO: SEPARA OS ARQUIVOS POR PASTA (DRIVES)
                # ==========================================
                pasta_base = f"Arquivos_{sigla}"
                os.makedirs(pasta_base, exist_ok=True) # Cria a pasta da base se não existir
                
                df_final = pd.DataFrame(dados_finais_excel)
                # Salva o arquivo dentro da pasta correspondente
                nome_arquivo = os.path.join(pasta_base, f"dados_acareacoes_{sigla}.xlsx")
                df_final.to_excel(nome_arquivo, index=False)
                
                log(f"Planilha local gerada na pasta '{pasta_base}', subindo para a nuvem...")
                enviar_para_google_sheets(df_final, sigla, bot, chat_id, awbs_ativos=awbs_ativos)
                
                # ==========================================
                # MENSAGEM COM O RESUMO DOS MOTORISTAS (LIMPO)
                # ==========================================
                if bot and chat_id:
                    contagem_motoristas = df_final['Motorista'].value_counts()
                    msg_resumo = f"🚚 *MOTORISTAS COM ACAREAÇÕES - {sigla}*\n\n"
                    
                    for mot_completo, qtd in contagem_motoristas.items():
                        nome_limpo = re.sub(r'\(.*?\)', '', str(mot_completo)).strip()
                        nome_limpo = nome_limpo.split('-')[0].strip()
                        primeiro_nome = nome_limpo.split(' ')[0].strip().upper()
                        
                        msg_resumo += f"👤 {primeiro_nome}: {qtd} pacote(s)\n"
                        
                    msg_resumo += f"\n📦 *Total: {len(df_final)} acareação(ões)*"
                    bot.send_message(chat_id, msg_resumo, parse_mode="Markdown")
                
                return nome_arquivo
            else:
                return None

        except Exception as e:
            log(f"❌ Erro crítico: {e}")
            return None
        finally:
            browser.close()