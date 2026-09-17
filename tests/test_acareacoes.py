import unittest

from acareacoes import (
    extrair_awbs_da_planilha,
    filtrar_itens_novos,
    remover_awbs_ausentes_da_planilha,
    sincronizar_linhas_da_planilha,
)


class TestAcareacoes(unittest.TestCase):
    def test_filtra_itens_que_ja_estao_na_planilha(self):
        itens = [
            {"codigo": "1111111111111"},
            {"codigo": "2222222222222"},
            {"codigo": "3333333333333"},
        ]
        awbs_existentes = {"1111111111111", "3333333333333"}

        novos = filtrar_itens_novos(itens, awbs_existentes)

        self.assertEqual([item["codigo"] for item in novos], ["2222222222222"])

    def test_extrai_awbs_da_planilha_ignorando_cabecalho(self):
        valores = [
            ["AWB", "Motorista", "Status"],
            ["1111111111111", "João", "OK"],
            ["2222222222222", "Maria", "OK"],
        ]

        awbs = extrair_awbs_da_planilha(valores)

        self.assertEqual(awbs, {"1111111111111", "2222222222222"})

    def test_remove_awbs_que_nao_estao_mais_na_imile(self):
        valores = [
            ["AWB", "Motorista", "Status"],
            ["1111111111111", "João", "OK"],
            ["2222222222222", "Maria", "OK"],
            ["3333333333333", "Ana", "OK"],
        ]

        valores_atualizados = remover_awbs_ausentes_da_planilha(valores, {"1111111111111", "3333333333333"})

        self.assertEqual(valores_atualizados, [
            ["AWB", "Motorista", "Status"],
            ["1111111111111", "João", "OK"],
            ["3333333333333", "Ana", "OK"],
        ])

    def test_sincroniza_planilha_mantendo_apenas_awbs_ativos(self):
        linhas_existentes = [
            ["AWB", "Motorista", "Status"],
            ["1111111111111", "João", "OK"],
            ["2222222222222", "Maria", "OK"],
            ["3333333333333", "Ana", "OK"],
        ]
        novas_linhas = [
            ["AWB", "Motorista", "Status"],
            ["1111111111111", "João", "OK"],
            ["3333333333333", "Ana", "OK"],
        ]

        linhas_finais = sincronizar_linhas_da_planilha(linhas_existentes, novas_linhas, {"1111111111111", "3333333333333"})

        self.assertEqual(linhas_finais, [
            ["AWB", "Motorista", "Status"],
            ["1111111111111", "João", "OK"],
            ["3333333333333", "Ana", "OK"],
        ])


if __name__ == "__main__":
    unittest.main()
