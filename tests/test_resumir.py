import tempfile
import unittest
from pathlib import Path
from unittest import mock

from resumidor import proveedores
from resumidor import resumir
from resumidor.transcribir import Segmento

EJEMPLO = Path(__file__).resolve().parent.parent / "ejemplos" / "clase_fotosintesis.srt"


FINAL = "### Resumen general\nTexto.\n\n### Apuntes clave\n- Uno\n\n### Preguntas de repaso\n1. ¿Qué?"
SECCION = "### Tema de prueba\nResumen.\n\n- Idea"


def llm_falso(proveedor, sistema, usuario, modelo=None, api_key=None):
    """Simula al modelo: responde según qué plantilla recibió (con los títulos mal nivelados a propósito)."""
    if "transcripción completa" in usuario:
        return f"{FINAL}\n\n### Notas por sección\n{SECCION}"
    if "Estos son los apuntes por secciones" in usuario:
        return FINAL
    return SECCION


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

    def comprobar_md(self, r) -> str:
        texto = r.md.read_text(encoding="utf-8")
        self.assertTrue(texto.startswith("# Clase fotosintesis"))
        self.assertIn("· duración 02:12", texto)
        # Los títulos que el modelo puso con ### se normalizan a ##.
        for seccion in ("## Resumen general", "## Apuntes clave", "## Preguntas de repaso", "## Notas por sección"):
            self.assertIn(seccion, texto)
        self.assertEqual(texto.count("## Notas por sección"), 1)
        self.assertTrue(r.srt.exists())
        return texto

    def test_una_llamada_si_cabe_entero(self):
        r = resumir.resumir(EJEMPLO, proveedor="ollama", progreso=lambda f, m: None)
        texto = self.comprobar_md(r)
        self.assertEqual(proveedores.completar.call_count, 1)
        self.assertEqual(r.estadisticas["llamadas"], 1)
        self.assertNotIn("`[00:00", texto)  # sin tiempos por sección: no se inventa un tramo

    def test_por_partes_da_el_mismo_formato(self):
        r = resumir.resumir(EJEMPLO, proveedor="ollama", progreso=lambda f, m: None, una_llamada=False)
        texto = self.comprobar_md(r)
        self.assertEqual(proveedores.completar.call_count, 2)
        self.assertIn("### Tema de prueba `[00:00–02:12]`", texto)

    def test_si_el_modelo_olvida_las_notas_no_falla(self):
        proveedores.completar.side_effect = lambda *a, **k: FINAL
        texto = resumir.resumir(EJEMPLO, proveedor="ollama", progreso=lambda f, m: None).md.read_text(encoding="utf-8")
        self.assertIn("## Resumen general", texto)
        self.assertNotIn("## Notas por sección", texto)

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
