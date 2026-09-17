import os
import re
import unicodedata
import pandas as pd
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from database import listar_bipagens
from config import MOTORISTAS_ABRANGENCIA
from atualizar_latencia_imile import (
    baixar_inventario_imile,
    preparar_dataframe_base,
    buscar_coluna_por_tokens,
    normalizar_cidade,
    login_imile,
)

load_dotenv()


def normalizar_texto(texto):
    if pd.isna(texto):
        return ""
    texto = unicodedata.normalize('NFKD', str(texto))
    texto = ''.join(char for char in texto if not unicodedata.combining(char))
    texto = texto.encode('ascii', 'ignore').decode('ascii')
    texto = texto.strip().lower()
    texto = re.sub(r'[^a-z0-9\s]', ' ', texto)
    texto = re.sub(r'\s+', ' ', texto).strip()
    return texto


def buscar_config_para_rota(rota):
    chave = normalizar_texto(rota)
    if not chave:
        return None

    for nome, config in MOTORISTAS_ABRANGENCIA.items():
        if normalizar_texto(nome) == chave:
            return config

    return None


def pertence_a_area(cidade, bairro, config):
    if not config:
        return None

    cidades = {normalizar_texto(item) for item in config.get('cidades', []) if item}
    bairros = {normalizar_texto(item) for item in config.get('bairros', []) if item}

    cidade_norm = normalizar_texto(cidade)
    bairro_norm = normalizar_texto(bairro)

    if cidade_norm and cidade_norm in cidades:
        return True

    if bairro_norm and bairro_norm in bairros:
        return True

    for cidade_config in cidades:
        if cidade_norm and (cidade_norm.startswith(cidade_config) or cidade_config.startswith(cidade_norm)):
            return True

    for bairro_config in bairros:
        if bairro_norm and (bairro_norm.startswith(bairro_config) or bairro_config.startswith(bairro_norm)):
            return True

    return False


def encontrar_linha_por_awb(df, awb):
    if df is None or df.empty:
        return None

    col_awb = buscar_coluna_por_tokens(df.columns, ['waybill', 'tracking', 'awb', 'bill'])
    if not col_awb:
        return None

    awb_norm = normalizar_texto(awb)
    if not awb_norm:
        return None

    mascara = df[col_awb].astype(str).apply(normalizar_texto) == awb_norm
    if mascara.any():
        return df.loc[mascara].iloc[0]

    return None


def extrair_destino_da_linha(linha, df_columns):
    col_city = buscar_coluna_por_tokens(df_columns, ['consignee city', 'city'])
    col_area = buscar_coluna_por_tokens(df_columns, ['consignee area', 'district', 'subdistrict', 'county', 'area'])
    col_address = buscar_coluna_por_tokens(df_columns, ['consignee address', 'address'])

    cidade = linha.get(col_city, '') if col_city else ''
    bairro = linha.get(col_area, '') if col_area else ''
    endereco = linha.get(col_address, '') if col_address else ''

    return cidade, bairro, endereco


def avaliar_bipagens_fora_rota(sigla='ITR', usuario=None, senha=None, output_path='bipagens_fora_rota.xlsx'):
    usuario = usuario or os.getenv('IMILE_ITR_USER') or os.getenv('IMILE_JML_USER')
    senha = senha or os.getenv('IMILE_PASS')

    if not usuario or not senha:
        raise RuntimeError('Credenciais da iMile não encontradas. Defina IMILE_ITR_USER/IMILE_JML_USER e IMILE_PASS no .env.')

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--start-maximized'])
        context = browser.new_context(no_viewport=True, accept_downloads=True)
        page = context.new_page()

        try:
            login_imile(page, usuario, senha)
            caminho_temporario = baixar_inventario_imile(page, sigla)
            if not caminho_temporario or not os.path.exists(caminho_temporario):
                raise RuntimeError(f'Falha ao baixar o inventário para {sigla}.')

            df_inventario = preparar_dataframe_base(caminho_temporario, sigla)
            if df_inventario is None:
                raise RuntimeError('Não foi possível preparar o DataFrame do inventário.')
        finally:
            try:
                context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass
            if caminho_temporario and os.path.exists(caminho_temporario):
                try:
                    os.remove(caminho_temporario)
                except Exception:
                    pass

    bipagens = listar_bipagens(limit=1000)
    resultados = []

    for item in bipagens:
        codigo = str(item.get('codigo', '')).strip()
        rota = str(item.get('rota', '')).strip()
        config = buscar_config_para_rota(rota)

        if not config:
            continue

        linha = encontrar_linha_por_awb(df_inventario, codigo)
        if linha is None:
            continue

        cidade, bairro, endereco = extrair_destino_da_linha(linha, df_inventario.columns)
        dentro_da_area = pertence_a_area(cidade, bairro, config)

        if not dentro_da_area:
            resultados.append({
                'codigo': codigo,
                'rota': rota,
                'cidade': cidade,
                'bairro': bairro,
                'endereco': endereco,
                'status': 'FORA DE ROTA',
            })

    if resultados:
        df_resultados = pd.DataFrame(resultados)
        df_resultados.to_excel(output_path, index=False)
        print(f'🚨 {len(df_resultados)} bipagens fora de rota encontradas. Arquivo salvo em {output_path}.')
        return df_resultados

    print('✅ Nenhuma bipagem fora de rota foi identificada.')
    return pd.DataFrame(columns=['codigo', 'rota', 'cidade', 'bairro', 'endereco', 'status'])


if __name__ == '__main__':
    sigla = os.getenv('IMILE_BASE_PADRAO', 'ITR')
    avaliar_bipagens_fora_rota(sigla=sigla)
