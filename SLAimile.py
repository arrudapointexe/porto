import os
import re
import pandas as pd
from datetime import datetime
from playwright.sync_api import sync_playwright
import unicodedata

from imile_utils import login_imile
from config import ITR_LOC_CITIES, ITR_INT_CITIES, JML_LOC_CITIES, JML_INT_CITIES, BACKLOG_FIM_DE_SEMANA, BACKLOG_DIA_DE_SEMANA

# Funções utilitárias
def remover_acentos(texto):
    if pd.isna(texto): return ""
    texto = str(texto).upper().strip()
    return ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')

def obter_backlogs():
    hoje = datetime.now()
    # Segunda = 0, Domingo = 6
    if hoje.weekday() == 0:  # Segunda-feira puxa regras do fim de semana
        return BACKLOG_FIM_DE_SEMANA["loc"], BACKLOG_FIM_DE_SEMANA["int"]
    else:
        return BACKLOG_DIA_DE_SEMANA["loc"], BACKLOG_DIA_DE_SEMANA["int"]

def baixar_inventario(page, sigla):
    print(f"[{sigla}] Navegando para extrair o Inventário...")
    try:
        page.get_by_text("Monitor").first.click(force=True, timeout=20000)
    except:
        page.reload(wait_until="domcontentloaded")
        page.get_by_text("Monitoramento", exact=False).first.click(force=True, timeout=20000)
    
    page.wait_for_timeout(2000)
    try:
        page.get_by_text("Operation Monitor", exact=False).first.click(force=True)
    except:
        try: page.get_by_text("Monitor de operação", exact=False).first.click(force=True)
        except: pass
    
    page.wait_for_timeout(2000)
    try:
        page.get_by_text("Inventory Monitor", exact=False).first.click(force=True)
    except:
        try: page.get_by_text("Monitor do inventário", exact=False).first.click(force=True)
        except: pass

    page.wait_for_timeout(8000)

    try:
        page.locator('.ImileActionButton-root:has-text("Export")').first.click(force=True, timeout=5000)
    except:
        page.locator('.ImileActionButton-root:has-text("extrair")').first.click(force=True, timeout=5000)

    page.wait_for_timeout(1000)
    try:
        page.locator('li.ImileMenuItem-root:has-text("Export All")').first.click(force=True, timeout=3000)
    except:
        page.locator('li.ImileMenuItem-root:has-text("Exportar tudo")').first.click(force=True, timeout=3000)
        
    page.wait_for_timeout(1000)
    page.locator('.export-button').first.click(force=True)

    print(f"[{sigla}] Aguardando arquivo ser gerado...")
    page.wait_for_timeout(12000)

    # Abre central de downloads
    page.locator('span.Imile-ButtonIcon-root svg path[d*="M8 0C3.57"]').locator('..').first.click(force=True)
    
    try:
        btn_baixar = page.locator('button:has-text("download")').last
        btn_baixar.wait_for(state="visible", timeout=15000)
    except:
        btn_baixar = page.locator('button:has-text("Baixar")').last
        btn_baixar.wait_for(state="visible", timeout=15000)

    with page.expect_download(timeout=120000) as download_info:
        btn_baixar.click(force=True)

    arquivo = f"temp_inv_{sigla}.xlsx"
    download_info.value.save_as(arquivo)
    print(f"[{sigla}] Inventário extraído e salvo como {arquivo}.")
    return arquivo

# 1. Rotina Matinal (Criar o BD)
def atualizar_bd_manha(usuario, senha, sigla):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--start-maximized"])
        context = browser.new_context(no_viewport=True, accept_downloads=True)
        page = context.new_page()
        try:
            print(f"[{sigla}] Atualizando BD matinal...")
            login_imile(page, usuario, senha)
            arquivo_bruto = baixar_inventario(page, sigla)
            if arquivo_bruto and os.path.exists(arquivo_bruto):
                # Salva o BD definitivo do dia
                df = pd.read_excel(arquivo_bruto)
                caminho_bd = f"BD_Inventario_Hoje_{sigla}.xlsx"
                df.to_excel(caminho_bd, index=False)
                print(f"[{sigla}] BD Matinal atualizado: {caminho_bd} com {len(df)} pacotes.")
                os.remove(arquivo_bruto)
                return True
        except Exception as e:
            print(f"[{sigla}] Erro ao atualizar BD matinal: {e}")
            return False
        finally:
            browser.close()

# 2. Rotina de SLA ao longo do dia (Compara BD com Inventário Atual)
def extrair_e_comparar_sla(usuario, senha, sigla, cidades_loc, cidades_int):
    caminho_bd = f"BD_Inventario_Hoje_{sigla}.xlsx"
    if not os.path.exists(caminho_bd):
        return None, f"⚠️ Erro: Banco de dados matinal de {sigla} não encontrado. Por favor, atualize o BD primeiro (/bd_manha)."
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--start-maximized"])
        context = browser.new_context(no_viewport=True, accept_downloads=True)
        page = context.new_page()
        try:
            login_imile(page, usuario, senha)
            arquivo_atual = baixar_inventario(page, sigla)
            
            if not arquivo_atual or not os.path.exists(arquivo_atual):
                return None, f"⚠️ Erro: Falha ao baixar inventário atual de {sigla}."

            df_bd = pd.read_excel(caminho_bd)
            df_atual = pd.read_excel(arquivo_atual)
            
            col_awb_bd = next((c for c in df_bd.columns if 'waybill' in c.lower()), 'Waybill No')
            col_awb_at = next((c for c in df_atual.columns if 'waybill' in c.lower()), 'Waybill No')
            col_city = next((c for c in df_bd.columns if 'destination city' in c.lower()), 'Destination City')
            col_backlog = next((c for c in df_bd.columns if 'backlog' in c.lower()), 'Backlog time(Station)')

            df_bd[col_city] = df_bd[col_city].apply(remover_acentos)
            df_bd[col_backlog] = pd.to_numeric(df_bd[col_backlog], errors='coerce').fillna(0)
            
            backlog_loc, backlog_int = obter_backlogs()
            
            # Filtra os Vencimentos (Vence Hoje + Perdas) baseados no BD da Manhã
            df_vencimentos_loc = df_bd[(df_bd[col_city].isin(cidades_loc)) & (df_bd[col_backlog] >= (backlog_loc - 1))]
            df_vencimentos_int = df_bd[(df_bd[col_city].isin(cidades_int)) & (df_bd[col_backlog] >= (backlog_int - 1))]
            df_vencimentos = pd.concat([df_vencimentos_loc, df_vencimentos_int])
            
            if df_vencimentos.empty:
                return None, f"✅ Excelente! Não há pacotes 'Vence Hoje' ou 'Perdas' no BD matinal para a base {sigla}."

            awbs_atuais = set(df_atual[col_awb_at].astype(str))
            
            # Mapeamento do inventario atual para facilitar
            dict_status_atual = dict(zip(df_atual[col_awb_at].astype(str), df_atual[next((c for c in df_atual.columns if 'last scan type' in c.lower()), 'Last Scan Type')]))
            
            def classificar_status(awb):
                if awb not in awbs_atuais:
                    return "ENTREGUE"
                
                status_cru = str(dict_status_atual.get(awb, "")).lower()
                
                # Regras de agrupamento da iMile
                if any(x in status_cru for x in ["out for delivery", "em rota de entrega", "delivering"]):
                    return "EM ROTA"
                elif any(x in status_cru for x in ["arrive", "receive", "offload", "unload"]):
                    return "RECEBIDO NA BASE"
                elif any(x in status_cru for x in ["assign", "atribui"]):
                    return "INVENTARIO" # ou em rota dependendo da regra, INVENTARIO é mais seguro
                else:
                    return "INVENTARIO"
            
            df_vencimentos['Status_Final'] = df_vencimentos[col_awb_bd].astype(str).apply(classificar_status)
            
            # Arruma as cidades para ficar bonito (Capitalizado)
            df_vencimentos['Cidade'] = df_vencimentos[col_city].str.title()
            
            # Monta a Tabela Dinâmica
            pivot = pd.pivot_table(df_vencimentos, values=col_awb_bd, index=['Cidade'], columns=['Status_Final'], aggfunc='count', fill_value=0)
            
            # Garante que todas as colunas desejadas existam
            colunas_desejadas = ["RECEBIDO NA BASE", "INVENTARIO", "EM ROTA", "ENTREGUE"]
            for col in colunas_desejadas:
                if col not in pivot.columns:
                    pivot[col] = 0
            
            pivot = pivot[colunas_desejadas] # Ordena
            pivot['Total Geral'] = pivot.sum(axis=1) # Cria coluna total
            
            # Ordenar por Total Geral decrescente (ou alfabético)
            pivot = pivot.sort_values(by='Total Geral', ascending=False)
            
            # Adicionar linha de Total Geral
            pivot.loc['Total Geral'] = pivot.sum(axis=0)

            path_imagem = gerar_imagem_planilha(sigla, pivot, page)
            
            # Calculando um resumo pro telegram
            totais = pivot.loc['Total Geral']
            msg = f"📊 *VENCIMENTOS IMILE - {sigla}*\n\n"
            msg += f"📦 Recebido na Base: {totais['RECEBIDO NA BASE']}\n"
            msg += f"📦 Inventário: {totais['INVENTARIO']}\n"
            msg += f"🚚 Em Rota: {totais['EM ROTA']}\n"
            msg += f"✅ Entregue (Evolução): {totais['ENTREGUE']}\n"
            msg += f"━━━━━━━━━━━━━━━━━━━━\n"
            msg += f"📈 *TOTAL GERAL:* {totais['Total Geral']} pacotes"
            
            return path_imagem, msg

        except Exception as e:
            return None, f"⚠️ Erro ao calcular SLA de {sigla}: {e}"
        finally:
            browser.close()
            if 'arquivo_atual' in locals() and os.path.exists(arquivo_atual):
                os.remove(arquivo_atual)

def gerar_imagem_planilha(sigla, pivot_df, page):
    # Gerando as linhas da tabela
    linhas_html = ""
    # Cores de linhas intercaladas
    cores = ["#D9E1F2", "#B4C6E7"]
    
    for i, (cidade, row) in enumerate(pivot_df.iterrows()):
        if cidade == 'Total Geral':
            continue
            
        cor = cores[i % 2]
        linhas_html += f"""
        <tr style="background-color: {cor};">
            <td class="left" style="padding-left: 30px;">{cidade}</td>
            <td>{row['RECEBIDO NA BASE'] if row['RECEBIDO NA BASE'] > 0 else ''}</td>
            <td>{row['INVENTARIO'] if row['INVENTARIO'] > 0 else ''}</td>
            <td>{row['EM ROTA'] if row['EM ROTA'] > 0 else ''}</td>
            <td>{row['ENTREGUE'] if row['ENTREGUE'] > 0 else ''}</td>
            <td class="total-cell">{row['Total Geral']}</td>
        </tr>
        """
    
    # Pegar total
    total = pivot_df.loc['Total Geral']

    html_unico = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ background: white; margin: 0; padding: 10px; font-family: Calibri, Arial, sans-serif; }}
            #print-sla {{ display: inline-flex; flex-direction: column; width: 850px; background: white; border: 1px solid #ccc; }}
            
            .header-img {{ background-color: #203764; color: white; padding: 15px; font-size: 28px; font-weight: bold; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; display: flex; align-items: center; justify-content: space-between;}}
            .filter-icon {{ font-size: 14px; background: white; color: black; padding: 2px 6px; border: 1px solid #aaa; margin-left: 10px; }}
            
            table {{ border-collapse: collapse; font-size: 15px; width: 100%; }}
            th {{ background: #203764; color: white; text-align: center; padding: 6px 10px; font-weight: bold; border-right: 1px solid white; }}
            th.left {{ text-align: left; padding-left: 10px; }}
            
            td {{ color: black; padding: 6px 10px; text-align: center; border-right: 1px solid white; }}
            td.left {{ text-align: left; }}
            
            .ds-row {{ background-color: #E2EBF5; font-weight: bold; border-top: 1px solid #999; border-bottom: 1px solid #999; }}
            .ds-row td {{ text-align: center; }}
            .ds-row td.left {{ display: flex; align-items: center; gap: 5px; }}
            .collapse-icon {{ font-size: 10px; border: 1px solid #666; padding: 0px 3px; display: inline-block; cursor: pointer; background: white; line-height: 10px; }}
            
            .footer-row {{ background-color: #203764; color: white; font-weight: bold; }}
            .footer-row td {{ color: white; }}
            .total-cell {{ font-weight: bold; }}
        </style>
    </head>
    <body>
        <div id="print-sla">
            <div class="header-img">
                VENCIMENTOS IMILE
            </div>
            <table>
                <thead>
                    <tr>
                        <th class="left" style="width: 35%;">
                           <span style="display:inline-block; font-size:10px; float:right; margin-top:5px;">↓</span>
                        </th>
                        <th style="width: 13%;">RECEBIDO NA BASE</th>
                        <th style="width: 13%;">INVENTARIO</th>
                        <th style="width: 13%;">EM ROTA</th>
                        <th style="width: 13%;">ENTREGUE</th>
                        <th style="width: 13%;">Total Geral</th>
                    </tr>
                </thead>
                <tbody>
                    <tr class="ds-row">
                        <td class="left"><span class="collapse-icon">-</span> DS {sigla}</td>
                        <td>{total['RECEBIDO NA BASE']}</td>
                        <td>{total['INVENTARIO']}</td>
                        <td>{total['EM ROTA']}</td>
                        <td>{total['ENTREGUE']}</td>
                        <td>{total['Total Geral']}</td>
                    </tr>
                    {linhas_html}
                    <tr class="footer-row">
                        <td class="left">Total Geral</td>
                        <td>{total['RECEBIDO NA BASE']}</td>
                        <td>{total['INVENTARIO']}</td>
                        <td>{total['EM ROTA']}</td>
                        <td>{total['ENTREGUE']}</td>
                        <td>{total['Total Geral']}</td>
                    </tr>
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """
    path_img = f"Print_Evolucao_SLA_{sigla}.png"
    try:
        page.set_content(html_unico)
        page.locator("#print-sla").wait_for(state="visible", timeout=10000)
        page.locator("#print-sla").screenshot(path=path_img)
        return path_img
    except Exception as e:
        print(f"Erro ao gerar imagem: {e}")
        return None
