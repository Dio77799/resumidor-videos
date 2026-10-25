import tempfile
import unittest
from pathlib import Path
from unittest import mock

import proveedores
import resumir
from transcribir import Segmento

EJEMPLO = Path(__file__).resolve().parent.parent / "ejemplos" / "clase_fotosintesis.srt"


def llm_falso(proveedor, sistema, usuario, modelo=None, api_key=None):
    """Simula al modelo: responde según qué plantilla recibió."""
    if "Estos son los apuntes por secciones" in usuario:
        return "### Resumen general\nTexto.\n\n### Apuntes clave\n- Uno\n\n### Preguntas de repaso\n1. ¿Qué?"
    return "### Tema de prueba\nResumen.\n\n- Idea"


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.parches = [mock.patch.object(resumir, "SALIDA", tmp / "salida"),
                        mock.patch.object(resumir, "LOG", tmp / "logs" / "trazas.jsonl"),
                        mock.patch.object(proveedores, "completar", side_effect=llm_falso)]
        for p in self.parches:
            p.start()

    def tearDown(self):
        for p in self.parches:
            p.stop()
        self.tmp.cleanup()

    def test_genera_md_y_srt(self):
        md = resumir.resumir(EJEMPLO, proveedor="ollama", progreso=lambda f, m: None)
        texto = md.read_text(encoding="utf-8")
        self.assertTrue(texto.startswith("# Clase fotosintesis"))
        # Los títulos que el modelo puso con ### se normalizan a ##.
        for seccion in ("## Resumen general", "## Apuntes clave", "## Preguntas de repaso", "## Notas por sección"):
            self.assertIn(seccion, texto)
        self.assertIn("### Tema de prueba `[00:00–02:12]`", texto)
        self.assertTrue(md.with_suffix(".srt").exists())

    def test_la_key_no_se_escribe_en_la_traza(self):
        resumir.resumir(EJEMPLO, proveedor="anthropic", api_key="sk-secreta-123", progreso=lambda f, m: None)
        self.assertNotIn("sk-secreta-123", resumir.LOG.read_text(encoding="utf-8"))

    def test_agrupar_respeta_el_tamano(self):
        segmentos = [Segmento(i, i + 1, "x" * 100) for i in range(10)]
        bloques = resumir.agrupar(segmentos, 350)
        self.assertEqual([len(b) for b in bloques], [3, 3, 3, 1])

    def test_plantilla_reemplaza_variables(self):
        texto = resumir.plantilla("sistema", idioma="inglés")
        self.assertIn("inglés", texto)
        self.assertNotIn("{idioma}", texto)


if __name__ == "__main__":
    unittest.main()
