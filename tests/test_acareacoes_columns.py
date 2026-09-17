import unittest

from acareacoes import normalizar_df_para_planilha


class AcareacoesColumnsTests(unittest.TestCase):
    def test_normalizar_df_para_planilha_inclui_bairro_numero_e_enviado(self):
        df = normalizar_df_para_planilha([
            {
                "AWB": "123",
                "Motorista": "João",
                "Nome": "Maria",
                "Telefone": "11999999999",
                "Endereco": "Rua A",
                "Produto": "Produto X",
                "Valor": "10.00",
                "Prazo do Processo": "2026-01-01",
            }
        ])

        self.assertIn("Bairro", df.columns)
        self.assertIn("Número do Cliente", df.columns)
        self.assertIn("Enviado", df.columns)
        self.assertEqual(df.loc[0, "Número do Cliente"], "11999999999")
        self.assertEqual(df.loc[0, "Bairro"], "")
        self.assertFalse(df.loc[0, "Enviado"])


if __name__ == "__main__":
    unittest.main()
