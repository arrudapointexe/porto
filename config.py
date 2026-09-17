import os
from dotenv import load_dotenv
load_dotenv()

CHAT_ID_ALVO = "7078348831"

BASES_ACAREACOES = [
    ("JML", os.getenv("IMILE_JML_USER"), os.getenv("JML_IMILE_PASS")),
    ("ITR", os.getenv("IMILE_ITR_USER"), os.getenv("ITR_IMILE_PASS")),
    ("GNH", os.getenv("IMILE_GNH_USER"), os.getenv("IMILE_PASS")),
    ("MNT", os.getenv("IMILE_MNT_USER"), os.getenv("IMILE_PASS")),
    ("GVR", os.getenv("IMILE_GVR_USER"), os.getenv("IMILE_PASS")),
    ("TFO", os.getenv("IMILE_TFO_USER"), os.getenv("IMILE_PASS")),
    ("RBN", os.getenv("IMILE_RBN_USER"), os.getenv("IMILE_PASS")),
    ("CPH", os.getenv("IMILE_CPH_USER"), os.getenv("IMILE_PASS")),
    ("QHG", os.getenv("IMILE_QHG_USER"), os.getenv("IMILE_PASS")),
    ("CTP", os.getenv("IMILE_CTP_USER"), os.getenv("IMILE_PASS"))
]

BASES_SLA = [
    ("JML", os.getenv("IMILE_JML_USER"), os.getenv("JML_IMILE_PASS")),
    ("ITR", os.getenv("IMILE_ITR_USER"), os.getenv("ITR_IMILE_PASS")),
    ("SNB", os.getenv("IMILE_SNB_USER"), os.getenv("IMILE_PASS"))
]

ITR_LOC_CITIES = ['ITABIRA']
ITR_INT_CITIES = ['ITAMBE DO MATO DENTRO', 'FERROS', 'MORRO DO PILAR', 'SANTO ANTONIO DO RIO ABAIXO', 'SANTA MARIA DE ITABIRA', 'PASSABEM', 'CARMESIA', 'SAO SEBASTIAO DO RIO PRETO']

JML_LOC_CITIES = ['JOAO MONLEVADE']
JML_INT_CITIES = ['NOVA ERA', 'RIO PIRACICABA', 'SAO DOMINGOS DO PRATA', 'SAO GONCALO DO RIO ABAIXO', 'SAO JOSE DO GOIABAL', 'BELA VISTA DE MINAS', 'DIONISIO', 'DOM SILVERIO', 'ALVINOPOLIS', 'BOM JESUS DO AMPARO', 'NOVA UNIAO', 'SEM-PEIXE', 'SEM PEIXE']

SNB_LOC_CITIES = ['SANTA BARBARA']
SNB_INT_CITIES = ['CATAS ALTAS', 'BARAO DE COCAIS']

BACKLOG_CRITICO = 3

BACKLOG_FIM_DE_SEMANA = {"int": 4, "loc": 3}
BACKLOG_DIA_DE_SEMANA = {"int": 3, "loc": 2}

# Estrutura para o script de checagem de bipagens fora de rota
# Exemplo: {'motorista': {'cidades': [...], 'bairros': [...]}}
MOTORISTAS_ABRANGENCIA = {
    "roca": {
        "cidades": ["ITABIRA", "SANTA BARBARA", "BARAO DE COCAIS", "SANTA MARIA DE ITABIRA"],
        "bairros": []
    },
    "santa barbara": {
        "cidades": ["SANTA BARBARA", "ITABIRA", "BARAO DE COCAIS"],
        "bairros": []
    },
    "itabira": {
        "cidades": ["ITABIRA"],
        "bairros": []
    },
    "francismar": {
        "cidades": ["ITABIRA"],
        "bairros": []
    }
}
