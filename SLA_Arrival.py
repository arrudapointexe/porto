import os
import re
import pandas as pd
import unicodedata
from datetime import datetime, timedelta
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from imile_utils import login_imile
from config import ITR_LOC_CITIES, ITR_INT_CITIES, JML_LOC_CITIES, JML_INT_CITIES, BASES_SLA

load_dotenv()

# ==============================================================
# DICIONÁRIOS E MAPEAMENTOS
# ==============================================================
MAPA_CIDADES = {
    "ITR": {"LOC": ITR_LOC_CITIES, "INT": ITR_INT_CITIES},
    "JML": {"LOC": JML_LOC_CITIES, "INT": JML_INT_CITIES}
}

STATUS_MAP = {
    'atribuído': 'ATRIBUIDO',
    'em rota de entrega': 'EM ROTA',
    'entregue': 'ENTREGUE',
    'leitura do inventário': 'IVENTARIO',
    'recebido no ds': 'NA BASE',
    'retorno de insucesso': 'VOLTO PRA BASE',
    'seal vehicle': 'X',
    'transferência concluída': 'X'
}

OCORRENCIA_MAP = {
    'danificado - irrecuperável': 'AVARIA',
    'embalagem externa danificada, item interno danificado': 'AVARIA',
    'embalagem externa danificada, item interno intacto': 'AVARIA',
    'embalagem externa intacta, item interno com barulho': 'AVARIA',
    'embalagem vazia': 'AVARIA',
    'encomenda extraviada': 'EXTRAVIO'
    # O restante (que não for Avaria ou Extravio) será tratado como "EM ROTA" via default
}

# ==============================================================
# FUNÇÕES DE NEGÓCIO (LÓGICA DO EXCEL)
# ==============================================================
def get_prazo_e_base(cidade_nome, sigla_padrao):
    """
    Retorna a (Base, Prazo) para uma cidade.
    O prazo é 0 se for LOC, 1 se for INT.
    """
    if pd.isna(cidade_nome) or not str(cidade_nome).strip():
        return sigla_padrao, 1
    
    # Normalização básica
    cidade_norm = str(cidade_nome).strip().lower()
    cidade_norm = ''.join(c for c in unicodedata.normalize('NFD', cidade_norm) if unicodedata.category(c) != 'Mn')
    
    # Procurar na sigla atual primeiro
    cidades_map = MAPA_CIDADES.get(sigla_padrao, {})
    loc_cidades = [''.join(c for c in unicodedata.normalize('NFD', str(c).strip().lower()) if unicodedata.category(c) != 'Mn') for c in cidades_map.get("LOC", [])]
    int_cidades = [''.join(c for c in unicodedata.normalize('NFD', str(c).strip().lower()) if unicodedata.category(c) != 'Mn') for c in cidades_map.get("INT", [])]
    
    if cidade_norm in loc_cidades:
        return sigla_padrao, 0
    elif cidade_norm in int_cidades:
        return sigla_padrao, 1
    
    # Se não achou na sigla padrão, procura em todas (para caso a planilha retorne uma cidade que é de outra base)
    for s, cmap in MAPA_CIDADES.items():
        locs = [''.join(c for c in unicodedata.normalize('NFD', str(c).strip().lower()) if unicodedata.category(c) != 'Mn') for c in cmap.get("LOC", [])]
        ints = [''.join(c for c in unicodedata.normalize('NFD', str(c).strip().lower()) if unicodedata.category(c) != 'Mn') for c in cmap.get("INT", [])]
        if cidade_norm in locs:
            return s, 0
        elif cidade_norm in ints:
            return s, 1
            
    return sigla_padrao, 1 # Padrão INT

def unificar_status(status_str):
    if pd.isna(status_str):
        return ""
    return STATUS_MAP.get(str(status_str).strip().lower(), str(status_str))

def unificar_ocorrencia(ocorrencia_str):
    if pd.isna(ocorrencia_str) or not str(ocorrencia_str).strip():
        return "EM ROTA"
    return OCORRENCIA_MAP.get(str(ocorrencia_str).strip().lower(), "EM ROTA")

def calcular_vencimento(data_recebimento, prazo):
    """
    Simula a fórmula do Excel:
    =EG2+EH2+SE(DIA.DA.SEMANA(EG2;2)=7;1;0)+SE(OU(DIA.DA.SEMANA(EG2+EH2+SE(DIA.DA.SEMANA(EG2;2)=7;1;0);2)=6;DIA.DA.SEMANA(EG2+EH2+SE(DIA.DA.SEMANA(EG2;2)=7;1;0);2)=7);1;0)
    """
    if pd.isna(data_recebimento):
        return pd.NaT
    
    # Remover horas
    dt_base = data_recebimento.normalize()
    
    # SE(DIA.DA.SEMANA(EG2;2)=7;1;0) -> No Excel, 2=Segunda(1) a Domingo(7).
    # Em Python, weekday(): 0=Segunda ... 6=Domingo.
    adicional_1 = 1 if dt_base.weekday() == 6 else 0
    
    # Ajuste 1: EG2 + EH2 + Adicional 1
    dt_adj1 = dt_base + timedelta(days=prazo + adicional_1)
    
    # SE(OU(DIA.DA.SEMANA(Ajuste 1;2)=6; DIA.DA.SEMANA(Ajuste 1;2)=7); 1; 0)
    # Se Ajuste 1 for Sábado (5) ou Domingo (6), adiciona 1 dia.
    adicional_2 = 1 if dt_adj1.weekday() in [5, 6] else 0
    
    dt_final = dt_adj1 + timedelta(days=adicional_2)
    return dt_final

# ==============================================================
# FUNÇÕES DE AUTOMAÇÃO
# ==============================================================

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def baixar_arrival_scan(sigla, usuario, senha):
    """
    Acessa ds.imile.com ScanQuery?listType=Arrival, filtra últimos 7 dias, exporta e baixa o arquivo.
    """
    log(f"📥 BAIXANDO ARRIVAL SCAN - {sigla}")
    arquivo_cache = f"arrival_scan_{sigla}.xlsx"
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        
        try:
            log(f"[{sigla}] Fazendo login na iMile DS...")
            login_imile(page, usuario, senha)
            
            # Remove pop-ups que interceptam cliques
            try:
                page.evaluate("document.querySelectorAll('.fireWrap, .overlay, .MuiBackdrop-root, .el-dialog__wrapper').forEach(e => e.remove())")
                page.wait_for_timeout(500)
            except: pass
            
            # Mudar idioma para português no DS (se estiver em inglês)
            lang_btn = page.locator('.ProTopbar-ActionItem-text:has-text("English")').first
            if lang_btn.is_visible(timeout=5000):
                log(f"[{sigla}] Mudando idioma para Português...")
                lang_btn.click(force=True)
                page.wait_for_timeout(1000)
                page.locator('li:has-text("Português")').first.click(force=True)
                page.wait_for_timeout(3000)
            
            # Remover de novo caso algo tenha carregado depois
            try:
                page.evaluate("document.querySelectorAll('.fireWrap, .overlay, .MuiBackdrop-root, .el-dialog__wrapper').forEach(e => e.remove())")
            except: pass
            
            # Navegar para Scan Management > Scan Query > Arrival
            log(f"[{sigla}] Acessando Scan Management...")
            page.goto("https://ds.imile.com/#/DSOperation/ScanManagement/ScanQuery?listType=Arrival")
            page.wait_for_timeout(5000)
            
            # Filtro de data: Últimos 7 dias
            log(f"[{sigla}] Configurando filtro de data (últimos 7 dias)...")
            # Busca diretamente pela classe raiz do componente de calendário
            calendario_container = page.locator('.RangeDatePicker-root').first
            
            if calendario_container.is_visible(timeout=15000):
                # Clica na div inteira do calendário
                calendario_container.click(force=True)
                page.wait_for_timeout(1000)
                
                # Selecionar a primeira opção de filtro rápido (The Last Week / Última Semana)
                preset_7_days = page.locator('.StaticDayRangePicker-left span.item, .ImileBox-root span.item').first
                if preset_7_days.is_visible():
                    preset_7_days.click(force=True)
                else:
                    log("Aviso: Opção de semana não visível no calendário.")
            else:
                log("Aviso: Não encontrou o campo de data!")
            page.wait_for_timeout(2000)
            
            # Clicar em Pesquisar
            log(f"[{sigla}] Pesquisando...")
            btn_pesquisar = page.locator('.ImileActionButton-root:has-text("consulta"), .ImileActionButton-root:has-text("Search"), .scene-query').first
            btn_pesquisar.click(force=True)
            page.wait_for_timeout(5000)
            
            # ==========================================
            # IDÊNTICO AO ATUALIZAR_LATENCIA_IMILE.PY
            # ==========================================
            log(f"[{sigla}] Solicitando exportação...")
            # Como em Arrival (Português) muitas vezes o botão é apenas o ícone, vamos buscar por ele primeiro
            btn_export = page.locator('.ImileActionButton-root:has(svg path[d^="M7.13 2.58"])').first
            if btn_export.is_visible(timeout=5000):
                btn_export.click(force=True)
            else:
                page.locator('.ImileActionButton-root:has-text("Export"), .ImileActionButton-root:has-text("Exportar")').first.click(force=True)
            page.wait_for_timeout(1000)
            
            page.locator('li.ImileMenuItem-root:has-text("Export All"), li.ImileMenuItem-root:has-text("Exportar tudo")').first.click(force=True)
            page.wait_for_timeout(1000)
            
            # Clica no botão de confirmação dentro do modal de exportação, usando o seletor de classe mais robusto
            page.locator('.export-button').first.click(force=True)
            
            log(f"[{sigla}] Aguardando a iMile gerar o arquivo (isso pode demorar)...")
            page.wait_for_timeout(15000) # Espera estendida para a geração
            
            log(f"[{sigla}] Abrindo a central de downloads para baixar o arquivo...")
            # O ícone de download na barra de navegação superior
            page.locator('span.Imile-ButtonIcon-root svg path[d*="M8 0C3.57"]').locator('..').first.click(force=True)
            
            # Espera o último botão de download aparecer na lista
            btn_baixar = page.locator('button:has-text("download"), button:has-text("Baixar")').last
            btn_baixar.wait_for(state="visible", timeout=30000)
            
            # Inicia o download
            log(f"[{sigla}] Baixando o arquivo...")
            with page.expect_download(timeout=120000) as download_info:
                btn_baixar.click(force=True)
            
            download = download_info.value
            download.save_as(arquivo_cache)
            log(f"✅ [{sigla}] Arrival Scan baixado: {arquivo_cache}")
            return arquivo_cache
            
        except Exception as e:
            log(f"❌ Erro ao baixar Arrival Scan de {sigla}: {e}")
            return None
        finally:
            browser.close()

def filtrar_awbs_por_data(arquivo_excel):
    """
    Lê o Excel de Arrival e extrai os AWBs dos últimos 3 dias (Hoje, D-1, D-2).
    """
    if not arquivo_excel or not os.path.exists(arquivo_excel):
        return []
    
    log("Filtando AWBs por data (D-0, D-1, D-2)...")
    try:
        df = pd.read_excel(arquivo_excel)
        # O Arrival Scan costuma ter Coluna A = Scan Time e Coluna B = Waybill No.
        # Vamos buscar pelos nomes prováveis para evitar erros se as colunas mudarem de ordem
        
        col_scan_time = None
        col_awb = None
        for col in df.columns:
            col_str = str(col).lower()
            if 'scan time' in col_str or 'hora' in col_str or 'tempo' in col_str:
                if not col_scan_time: col_scan_time = col
            if 'waybill' in col_str or 'awb' in col_str or 'etiqueta' in col_str:
                if not col_awb: col_awb = col
                
        # Fallback para colunas A e B
        if not col_scan_time: col_scan_time = df.columns[0]
        if not col_awb: col_awb = df.columns[1]
        
        df[col_scan_time] = pd.to_datetime(df[col_scan_time], errors='coerce')
        
        # Obter datas alvo
        hoje = datetime.now().date()
        d_1 = hoje - timedelta(days=1)
        d_2 = hoje - timedelta(days=2)
        datas_alvo = [hoje, d_1, d_2]
        
        # Filtrar
        df_filtrado = df[df[col_scan_time].dt.date.isin(datas_alvo)]
        awbs = df_filtrado[col_awb].dropna().astype(str).tolist()
        
        # Limpar espaços
        df_filtrado = df_filtrado.copy()
        df_filtrado[col_awb] = df_filtrado[col_awb].astype(str).str.strip()
        df_filtrado.rename(columns={col_awb: 'AWB_CHAVE', col_scan_time: 'DATA DO RECEBIMENTO'}, inplace=True)
        
        awbs = df_filtrado['AWB_CHAVE'].dropna().unique().tolist()
        log(f"Encontrados {len(awbs)} AWBs nos últimos 3 dias.")
        return df_filtrado
    except Exception as e:
        log(f"❌ Erro ao filtrar AWBs do Excel: {e}")
        return None

def consultar_oc_lote(usuario, senha, awbs, sigla):
    """
    Acessa oc.imile.com CentralWaybillQuery, consulta lote de AWBs e extrai a tabela.
    """
    if not awbs:
        return None
        
    log(f"🔍 CONSULTANDO LOTE DE {len(awbs)} WAYBILLS - {sigla}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        
        try:
            log(f"[{sigla}] Fazendo login na iMile OC...")
            login_imile(page, usuario, senha)
            
            # Remove pop-ups que interceptam cliques
            try:
                page.evaluate("document.querySelectorAll('.fireWrap, .overlay, .MuiBackdrop-root, .el-dialog__wrapper').forEach(e => e.remove())")
                page.wait_for_timeout(500)
            except: pass
            
            page.goto("https://oc.imile.com/#/CenterOperation/CenterWaybillmanagement/CentralWaybillQuery")
            page.wait_for_timeout(5000)
            
            # Mudar idioma para português
            lang_btn = page.locator('.ProTopbar-ActionItem-text:has-text("English")').first
            if lang_btn.is_visible(timeout=3000):
                log("Mudando idioma para Português...")
                lang_btn.click(force=True)
                page.wait_for_timeout(1000)
                page.locator('li:has-text("Português")').first.click(force=True)
                page.wait_for_timeout(3000)
                
            # Remover de novo caso algo tenha carregado depois
            try:
                page.evaluate("document.querySelectorAll('.fireWrap, .overlay, .MuiBackdrop-root, .el-dialog__wrapper').forEach(e => e.remove())")
            except: pass
            
            log(f"[{sigla}] Inserindo todos os AWBs no campo de pesquisa...")
            awbs_str = " ".join(awbs)
            input_campo = page.locator('input[placeholder*="insira"], input[placeholder*="Por favor"], input[placeholder*="Waybill"]').first
            input_campo.click(force=True)
            input_campo.fill(awbs_str)
            page.wait_for_timeout(500)
            
            # Clicar Consulta
            page.locator('.ImileActionButton-text:has-text("consulta"), .ImileActionButton-text:has-text("Search")').first.click(force=True)
            
            log(f"[{sigla}] Aguardando tabela...")
            page.wait_for_timeout(8000) 
            
            # Exportar tudo!
            log(f"[{sigla}] Solicitando exportação no OC...")
            btn_export = page.locator('.ImileActionButton-root:has(svg path[d^="M7.13 2.58"])').first
            if btn_export.is_visible(timeout=5000):
                btn_export.click(force=True)
            else:
                page.locator('.ImileActionButton-root:has-text("Export"), .ImileActionButton-root:has-text("Exportar")').first.click(force=True)
            page.wait_for_timeout(1000)
            
            page.locator('li.ImileMenuItem-root:has-text("Export All"), li.ImileMenuItem-root:has-text("Exportar tudo")').first.click(force=True)
            page.wait_for_timeout(1000)
            
            page.locator('.export-button').first.click(force=True)
            
            log(f"[{sigla}] Aguardando a iMile gerar o arquivo OC (15s)...")
            page.wait_for_timeout(15000)
            
            log(f"[{sigla}] Abrindo centro de downloads do OC...")
            page.locator('span.Imile-ButtonIcon-root svg path[d*="M8 0C3.57"]').locator('..').first.click(force=True)
            
            btn_baixar = page.locator('button:has-text("download"), button:has-text("Baixar")').last
            btn_baixar.wait_for(state="visible", timeout=30000)
            
            log(f"[{sigla}] Baixando arquivo do OC...")
            with page.expect_download(timeout=120000) as download_info:
                btn_baixar.click(force=True)
                
            download = download_info.value
            arquivo_oc = f"cache_oc_{sigla}.xlsx"
            download.save_as(arquivo_oc)
            
            log(f"✅ Arquivo OC salvo: {arquivo_oc}")
            return arquivo_oc
            
        except Exception as e:
            log(f"❌ Erro ao consultar OC de {sigla}: {e}")
            return None
        finally:
            browser.close()

def processar_logica_excel(df_oc, sigla_padrao):
    """
    Aplica as regras de Vencimento, Status e SLA na tabela de dados brutos (pandas df_oc).
    """
    if df_oc is None or df_oc.empty:
        return pd.DataFrame()
        
    df = df_oc.copy()
    log(f"Processando lógica do Excel para {len(df)} linhas...")
    
    # Identificar colunas importantes
    col_awb = None
    col_cidade = None
    col_status = None
    col_excecao = None
    
    # A coluna BW (índice 74) é a data de recebimento no OC
    col_data_rec = df.columns[74] if len(df.columns) > 74 else None
    
    for col in df.columns:
        c_lower = str(col).lower()
        if 'etiqueta' in c_lower or 'awb' in c_lower or 'waybill' in c_lower: col_awb = col
        if 'cidade destinatária' in c_lower or 'consignee city' in c_lower: col_cidade = col
        if 'último status' in c_lower or 'last status' in c_lower: col_status = col
        if 'motivo da exceção' in c_lower or 'exception reason' in c_lower: col_excecao = col

    # Fallbacks se não achar o nome exato (se a extração em PT-BR falhar e ficar em EN)
    if not col_cidade: col_cidade = 'Cidade destinatária'
    if not col_status: col_status = 'Último status'
    if not col_excecao: col_excecao = 'Motivo da exceção'
    
    # Garantir que as colunas existem
    for c in [col_cidade, col_status, col_excecao]:
        if c not in df.columns:
            df[c] = ""
            
    if not col_data_rec:
        df['DATA_REC_FALLBACK'] = ""
        col_data_rec = 'DATA_REC_FALLBACK'
            
    # Regra A: Prazo e Base
    df[['BASE', 'PRAZO']] = df.apply(lambda row: pd.Series(get_prazo_e_base(row[col_cidade], sigla_padrao)), axis=1)
    
    # Regra B: Datas
    df[col_data_rec] = pd.to_datetime(df[col_data_rec], errors='coerce')
    df['DATA DO VENCIMENTO'] = df.apply(lambda row: calcular_vencimento(row[col_data_rec], row['PRAZO']), axis=1)
    
    hoje = pd.Timestamp(datetime.now().date())
    
    def calc_nomenclatura(dt_venc):
        if pd.isna(dt_venc): return "Inválido"
        
        # Exceção de sábado: A fórmula joga os vencimentos de Sábado para Domingo.
        # Portanto, se hoje for Sábado (weekday == 5), pacotes vencendo amanhã (Domingo) 
        # são considerados "Vencimentos" do dia.
        if hoje.weekday() == 5 and dt_venc == (hoje + pd.Timedelta(days=1)):
            return "Vencimentos"
            
        if dt_venc > hoje: return "No Prazo"
        elif dt_venc == hoje: return "Vencimentos"
        else: return "Vencidos"
        
    df['NOMECLATURA DE VENCIMENTO'] = df['DATA DO VENCIMENTO'].apply(calc_nomenclatura)
    
    # Regra C: Status Unificado
    df['STATUS UNIFICADO'] = df[col_status].apply(unificar_status)
    
    # Regra D: Ocorrência (Exceção)
    df['OCORRENCIA REMOÇAO'] = df[col_excecao].apply(unificar_ocorrencia)
    
    # FILTRO: Apenas os pacotes que VENCEM HOJE (Vencimentos)
    df_vencimentos = df[df['NOMECLATURA DE VENCIMENTO'] == 'Vencimentos'].copy()
    
    # FILTRO 2: Ignorar pacotes que foram transferidos/seal vehicle ('X')
    df_vencimentos = df_vencimentos[df_vencimentos['STATUS UNIFICADO'] != 'X']
    
    # Tabela Dinâmica
    if df_vencimentos.empty:
        log("Nenhum pacote vencendo hoje após os filtros.")
        return pd.DataFrame()
        
    # Agrupar por Base e Cidade, pivotar Status Unificado
    tabela = pd.crosstab(
        index=[df_vencimentos['BASE'], df_vencimentos[col_cidade]],
        columns=df_vencimentos['STATUS UNIFICADO'],
        margins=True,
        margins_name='Total Geral'
    )
    
    # Ordenar colunas: NA BASE, INVENTARIO, EM ROTA, ENTREGUE
    ordem_colunas = ['NA BASE', 'INVENTARIO', 'EM ROTA', 'ENTREGUE']
    for col in ordem_colunas:
        if col not in tabela.columns:
            tabela[col] = 0
            
    colunas_finais = [c for c in ordem_colunas if c in tabela.columns]
    if 'Total Geral' in tabela.columns:
        colunas_finais.append('Total Geral')
        
    tabela = tabela[colunas_finais].fillna(0).astype(int)
    
    # Opcional: Remover o MultiIndex das linhas para ficar mais fácil
    tabela = tabela.reset_index()
    
    log("Tabela Dinâmica gerada com sucesso.")
    return tabela

def gerar_resumo_telegram_e_imagem(tabela, sigla):
    if tabela is None or tabela.empty:
        return None, f"⚠️ Nenhum pacote vencendo hoje na SLA Arrival para {sigla}."
        
    msg = f"📊 *VENCIMENTOS HOJE (Arrival) - {sigla}* 📊\n"
    msg += f"━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"⏰ {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
    
    # Prepara dados totais
    if 'Total Geral' in tabela['BASE'].values:
        idx_total = tabela[tabela['BASE'] == 'Total Geral'].index[0]
        row_total = tabela.loc[idx_total]
        tabela_linhas = tabela.drop(idx_total)
    else:
        row_total = tabela.sum(numeric_only=True)
        tabela_linhas = tabela

    # Preparar a renderização do HTML para ficar IDENTICO ao Excel
    def fmt_num(val):
        v = int(val)
        return str(v) if v > 0 else ""

    def fmt_sla(entregue, total):
        if total == 0:
            return "0,00%", "sla-grey"
        pct = (entregue / total) * 100
        pct_str = f"{pct:.2f}%".replace('.', ',')
        if pct == 0:
            return pct_str, "sla-grey"
        elif pct < 100:
            return pct_str, "sla-red"
        else:
            return pct_str, "sla-green"

    # Calcula totais da base (linha com o [-] SIGLA)
    total_geral_valor = int(row_total.get('Total Geral', 0))
    t_na_base = int(row_total.get('NA BASE', 0))
    t_inventario = int(row_total.get('INVENTARIO', 0) + row_total.get('INVENTARIO', 0))
    t_em_rota = int(row_total.get('EM ROTA', 0))
    t_entregue = int(row_total.get('ENTREGUE', 0))
    t_geral = total_geral_valor
    
    sla_base_str, sla_base_cls = fmt_sla(t_entregue, t_geral)

    linhas_html = ""
    for idx, row in tabela_linhas.iterrows():
        base = row['BASE']
        cidade = row.get('Cidade destinatária', 'Desconhecida')
        
        total = int(row.get('Total Geral', 0))
        if total > 0:
            msg += f"🏙️ *{cidade}* ({base}): {total} pacotes\n"
            
        na_base = int(row.get('NA BASE', 0))
        inventario = int(row.get('INVENTARIO', 0) + row.get('IVENTARIO', 0))
        em_rota = int(row.get('EM ROTA', 0))
        entregue = int(row.get('ENTREGUE', 0))
        
        sla_str, sla_cls = fmt_sla(entregue, total)
        
        # Cores alternadas para as linhas (imitando o excel)
        bg_class = "city-row-0" if idx % 2 == 0 else "city-row-1"
        
        linhas_html += f"""
        <tr class="{bg_class}">
            <td class="left" style="padding-left: 25px;">{cidade}</td>
            <td>{fmt_num(na_base)}</td>
            <td>{fmt_num(inventario)}</td>
            <td>{fmt_num(em_rota)}</td>
            <td>{fmt_num(entregue)}</td>
            <td>{fmt_num(total)}</td>
            <td class="{sla_cls}">{sla_str}</td>
        </tr>
        """
            
    msg += f"━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"📦 *TOTAL:* {total_geral_valor} pacotes\n"
    
    # SLA Calc
    if 'ENTREGUE' in row_total and total_geral_valor > 0:
        entregues = row_total['ENTREGUE']
        sla_pct = (entregues / total_geral_valor) * 100
        msg += f"🎯 *SLA:* {sla_pct:.2f}%\n"

    # GERAR IMAGEM HTML IDÊNTICA AO EXCEL
    html_unico = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ background: white; margin: 0; padding: 10px; font-family: 'Calibri', Arial, sans-serif; font-size: 15px; }}
            #print-sla {{ display: inline-flex; flex-direction: column; width: 850px; background: white; border: none; }}
            
            .header-top {{ background-color: #002060; color: white; padding: 8px 15px; display: flex; justify-content: space-between; align-items: flex-end; }}
            .header-top .title {{ font-size: 32px; font-weight: bold; line-height: 1; }}
            .header-top .subtitle {{ font-size: 15px; font-weight: bold; line-height: 1; padding-bottom: 4px; }}
            
            table {{ border-collapse: collapse; width: 100%; }}
            th {{ background: #002060; color: white; text-align: center; padding: 4px 10px; font-weight: bold; border-right: 1px solid white; }}
            th.left {{ text-align: right; padding-right: 10px; border-right: none; }}
            th.sla-header {{ border-left: 1px solid black; border-right: 1px solid black; }}
            
            td {{ padding: 2px 10px; text-align: center; border-right: 1px solid white; border-left: 1px solid white; color: black; }}
            td.left {{ text-align: left; border-left: none; }}
            
            /* Filtros (quadradinhos com funil) */
            .filter-icon {{ display: inline-block; background: #E7E6E6; color: black; font-size: 10px; padding: 0px 3px; border: 1px solid #B2B2B2; margin-left: 5px; vertical-align: middle; box-shadow: 1px 1px 1px rgba(0,0,0,0.2); }}
            
            /* Linha da Base (-) */
            .ds-row {{ background-color: #E2EBF5; font-weight: bold; border-top: 1px solid #8EA9DB; border-bottom: 1px solid #8EA9DB; }}
            .ds-row td {{ text-align: center; }}
            .ds-row td.left {{ display: flex; align-items: center; gap: 5px; border-right: none; }}
            .collapse-icon {{ font-size: 10px; border: 1px solid #8EA9DB; padding: 0px 3px; display: inline-block; background: white; color: black; line-height: 10px; }}
            
            /* Linhas das cidades (alternadas) */
            .city-row-0 {{ background-color: #B4C6E7; }}
            .city-row-1 {{ background-color: #D9E1F2; }}
            
            /* Total Geral */
            .footer-row {{ background-color: #002060; color: white; font-weight: bold; border-top: 2px solid white; }}
            .footer-row td {{ color: white; border-right: 1px solid white; }}
            .footer-row td.left {{ border-right: none; padding-left: 5px; }}
            
            /* SLA Cells */
            .sla-red {{ background-color: #FFC7CE; color: #9C0006; font-weight: bold; border-left: 1px solid black !important; border-right: 1px solid black !important; }}
            .sla-green {{ background-color: #C6EFCE; color: #006100; font-weight: bold; border-left: 1px solid black !important; border-right: 1px solid black !important; }}
            .sla-grey {{ background-color: #E7E6E6; color: black; font-weight: bold; border-left: 1px solid black !important; border-right: 1px solid black !important; }}
            
        </style>
    </head>
    <body>
        <div id="print-sla">
            <div class="header-top">
                <div class="title">VENCIMENTOS IMILE</div>
                <div class="subtitle">RESULTADO</div>
            </div>
            <table>
                <thead>
                    <tr>
                        <th class="left" style="width: 35%;">
                           <span class="filter-icon">▼</span>
                           <span class="filter-icon" style="margin-right: 25px;">▼</span>
                        </th>
                        <th style="width: 10%;">NA BASE</th>
                        <th style="width: 10%;">IVENTARIO</th>
                        <th style="width: 10%;">EM ROTA</th>
                        <th style="width: 10%;">ENTREGUE</th>
                        <th style="width: 10%;">Total Geral</th>
                        <th class="sla-header" style="width: 15%;">SLA</th>
                    </tr>
                </thead>
                <tbody>
                    <tr class="ds-row">
                        <td class="left"><span class="collapse-icon">-</span> {sigla}</td>
                        <td>{fmt_num(t_na_base)}</td>
                        <td>{fmt_num(t_inventario)}</td>
                        <td>{fmt_num(t_em_rota)}</td>
                        <td>{fmt_num(t_entregue)}</td>
                        <td>{fmt_num(t_geral)}</td>
                        <td class="{sla_base_cls}">{sla_base_str}</td>
                    </tr>
                    {linhas_html}
                    <tr class="footer-row">
                        <td class="left">Total Geral</td>
                        <td>{fmt_num(t_na_base)}</td>
                        <td>{fmt_num(t_inventario)}</td>
                        <td>{fmt_num(t_em_rota)}</td>
                        <td>{fmt_num(t_entregue)}</td>
                        <td>{fmt_num(t_geral)}</td>
                        <td class="{sla_base_cls}">{sla_base_str}</td>
                    </tr>
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """
    
    path_img = f"Print_Arrival_SLA_{sigla}.png"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_content(html_unico)
            page.locator("#print-sla").wait_for(state="visible", timeout=10000)
            page.locator("#print-sla").screenshot(path=path_img)
            browser.close()
    except Exception as e:
        log(f"Erro ao gerar imagem: {e}")
        path_img = None
        
    return path_img, msg

# Wrapper para uso manual ou pelo bot
def executar_rotina_sla_arrival(sigla, usuario, senha):
    arquivo = baixar_arrival_scan(sigla, usuario, senha)
    df_arrival = filtrar_awbs_por_data(arquivo)
    
    if df_arrival is None or df_arrival.empty:
        return f"⚠️ Nenhum pacote recém-chegado (D-0 a D-2) encontrado em {sigla}."
        
    awbs = df_arrival['AWB_CHAVE'].dropna().unique().tolist()
    
    arquivo_oc = consultar_oc_lote(usuario, senha, awbs, sigla)
    if not arquivo_oc or not os.path.exists(arquivo_oc):
        return f"❌ Erro ao baixar dados do OC para {sigla}."
        
    df_oc = pd.read_excel(arquivo_oc)
    tabela_dinamica = processar_logica_excel(df_oc, sigla)
    
    img_path, msg = gerar_resumo_telegram_e_imagem(tabela_dinamica, sigla)
    
    if img_path:
        print(f"\n[IMAGEM GERADA]: {img_path}")
    print(f"\n{msg}\n")
    return img_path, msg

if __name__ == "__main__":
    print("Iniciando testes do SLA Arrival buscando credenciais do .env...")
    for sigla, usuario, senha in BASES_SLA:
        if sigla in ["ITR", "JML", "SNB"]:
            print(f"\n{'='*40}")
            print(f"🔥 INICIANDO PROCESSO PARA BASE: {sigla}")
            print(f"{'='*40}")
            try:
                executar_rotina_sla_arrival(sigla, usuario, senha)
            except Exception as e:
                print(f"Erro fatal na base {sigla}: {e}")
            
    print("\n✅ Processo de todas as bases finalizado.")
