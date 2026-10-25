import io
import json
import unittest
from unittest import mock

from resumidor import proveedores


def respuesta(contenido):
    return io.BytesIO(json.dumps({"message": {"content": contenido}}).encode("utf-8"))


class TestOllama(unittest.TestCase):
    def llamar(self, modelo, contenido):
        with mock.patch("urllib.request.urlopen", return_value=respuesta(contenido)) as abrir:
            texto = proveedores.completar("ollama", "sistema", "usuario", modelo)
        return texto, json.loads(abrir.call_args.args[0].data)

    def test_quita_el_razonamiento(self):
        texto, peticion = self.llamar("qwen3:8b", "<think>pensando…</think>\n### Apuntes")
        self.assertEqual(texto, "### Apuntes")
        self.assertIs(peticion["think"], False)

    def test_gpt_oss_piensa_poco(self):
        _, peticion = self.llamar("gpt-oss:20b", "ok")
        self.assertEqual(peticion["think"], "low")

    def test_modelos_normales_no_llevan_think(self):
        _, peticion = self.llamar("gemma3:4b", "ok")
        self.assertNotIn("think", peticion)

    def test_elige_el_mejor_modelo_instalado(self):
        with mock.patch.dict("os.environ", {"OLLAMA_MODELO": ""}):
            self.assertEqual(proveedores.modelo_por_defecto("ollama", ["llama3.2:3b", "qwen3:8b"]), "qwen3:8b")
            self.assertEqual(proveedores.modelo_por_defecto("ollama", ["llama3.2:3b"]), "llama3.2:3b")
            self.assertEqual(proveedores.modelo_por_defecto("ollama", []), "llama3.2:3b")
        with mock.patch.dict("os.environ", {"OLLAMA_MODELO": "mistral:7b"}), \
             mock.patch.dict(proveedores.MODELOS_POR_DEFECTO, {"ollama": "mistral:7b"}):
            self.assertEqual(proveedores.modelo_por_defecto("ollama", ["qwen3:8b"]), "mistral:7b")

    def test_catalogo_bien_formado(self):
        for m in proveedores.CATALOGO_OLLAMA:
            self.assertRegex(m["modelo"], r"^[a-z0-9.\-]+:[a-z0-9.\-]+$")
            self.assertGreater(m["gb"], 0)


if __name__ == "__main__":
    unittest.main()
