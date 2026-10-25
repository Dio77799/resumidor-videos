import json
import tempfile
import unittest
from pathlib import Path

from resumidor import energia


class TestEnergia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "trazas.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_wh(self):
        self.assertAlmostEqual(energia.wh(3600), energia.WATTS)

    def test_sin_historial_usa_valores_por_defecto(self):
        e = energia.estimar("ollama", "llama3.2:3b", "small", 600, None, True, self.log)
        # 10 min de habla ≈ 9000 caracteres ≈ 2 partes + resumen final
        self.assertEqual(e["llamadas"], 3)
        self.assertEqual(e["segundos"], round(600 * energia.WHISPER_FACTOR["small"] + 5 + 3 * 68))  # 68 s/llamada, medido
        self.assertFalse(e["medido"])

    def test_se_calibra_con_el_historial(self):
        fila = {"proveedor": "ollama", "modelo": "llama3.2:3b", "whisper": "small", "duracion_media": 100,
                "seg_transcripcion": 50, "bloques": 1, "llamadas": 1, "seg_resumen": 20}
        self.log.write_text(json.dumps(fila) + "\n" + '{"error": "x"}\n', encoding="utf-8")
        e = energia.estimar("ollama", "llama3.2:3b", "small", 100, None, True, self.log)
        self.assertTrue(e["medido"])
        self.assertEqual(e["segundos"], round(100 * 0.5 + 5 + 20))  # video corto: una sola llamada, como la medida

    def test_nube_solo_gasta_la_transcripcion(self):
        local = energia.estimar("anthropic", "claude-opus-5-5", "small", 600, None, True, self.log)
        self.assertAlmostEqual(local["wh"], round(energia.wh(600 * energia.WHISPER_FACTOR["small"] + 5), 1))

    def test_transcripcion_de_texto_no_gasta_whisper(self):
        e = energia.estimar("anthropic", "claude-opus-5-5", "small", None, 5000, False, self.log)
        self.assertEqual(e["wh"], 0)


if __name__ == "__main__":
    unittest.main()
