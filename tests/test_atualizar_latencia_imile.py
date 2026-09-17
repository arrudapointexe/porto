import unittest
import pandas as pd

from atualizar_latencia_imile import dividir_em_lotes, preparar_colunas_para_arquivo_excel, adicionar_coluna_abrangencia


class TestDividirEmLotes(unittest.TestCase):
    def test_divide_lista_em_lotes_de_tamanho_1000(self):
        lista = list(range(1900))

        lotes = list(dividir_em_lotes(lista, tamanho_lote=1000))

        self.assertEqual(len(lotes), 2)
        self.assertEqual(lotes[0], list(range(1000)))
        self.assertEqual(lotes[1], list(range(1000, 1900)))

    def test_prepara_colunas_para_excel_como_texto(self):
        df = pd.DataFrame({
            'Waybill': [1234567890123, 9876543210987],
            'Status': ['OK', 'OK']
        })

        df_processado = preparar_colunas_para_arquivo_excel(df)

        self.assertEqual(df_processado['Waybill'].dtype, object)
        self.assertEqual(df_processado['Waybill'].iloc[0], '1234567890123')

    def test_adiciona_coluna_abrangencia_com_base_jml(self):
        df = pd.DataFrame([
            {'Base': 'JML', 'Consignee City': 'RIO PIRACICABA'},
            {'Base': 'JML', 'Consignee City': 'BELO HORIZONTE'},
        ])

        df_processado = adicionar_coluna_abrangencia(df)

        self.assertEqual(df_processado['abrangencia'].tolist(), [1, 0])

    def test_adiciona_coluna_abrangencia_com_variacoes_de_texto(self):
        df = pd.DataFrame([
            {'Base': 'JML', 'Consignee City': 'São Gonçalo do Rio Abaixo'},
            {'Base': 'JML', 'Consignee City': 'São José do Goiabal'},
        ])

        df_processado = adicionar_coluna_abrangencia(df)

        self.assertEqual(df_processado['abrangencia'].tolist(), [1, 1])

    def test_adiciona_coluna_abrangencia_com_sufixos_e_variantes(self):
        df = pd.DataFrame([
            {'Base': 'ITR', 'Consignee City': 'Itabira - MG'},
            {'Base': 'ITR', 'Consignee City': 'Ferros / MG'},
            {'Base': 'JML', 'Consignee City': 'São Gonçalo do Rio Abaixo - MG'},
        ])

        df_processado = adicionar_coluna_abrangencia(df)

        self.assertEqual(df_processado['abrangencia'].tolist(), [1, 1, 1])


if __name__ == '__main__':
    unittest.main()
