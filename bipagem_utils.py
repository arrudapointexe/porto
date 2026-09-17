import re


def normalizar_rota(valor):
    if valor is None:
        return ""
    texto = str(valor).strip().lower()
    texto = re.sub(r"[^a-z0-9]+", "", texto)
    return texto


def obter_indice_rota(rotas, rota_atual):
    if not rotas:
        return 0

    rota_alvo = normalizar_rota(rota_atual)
    if not rota_alvo:
        return 0

    for indice, rota in enumerate(rotas):
        if normalizar_rota(rota) == rota_alvo:
            return indice

    return 0
