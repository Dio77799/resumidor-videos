import unittest
from pathlib import Path

from transcribir import a_srt, formato_tiempo, leer_subtitulos, leer_txt, obtener_segmentos

EJEMPLO = Path(__file__).resolve().parent.parent / "ejemplos" / "clase_fotosintesis.srt"


class TestSubtitulos(unittest.TestCase):
    def test_srt_de_ejemplo(self):
        segmentos = obtener_segmentos(EJEMPLO)
        self.assertEqual(len(segmentos), 9)
        self.assertEqual(segmentos[0].inicio, 0.0)
        self.assertEqual(segmentos[-1].fin, 132.0)
        self.assertIn("fotosíntesis", segmentos[0].texto)

    def test_vtt_quita_etiquetas_y_duplicados(self):
        vtt = ("WEBVTT\n\n00:00:01.000 --> 00:00:03.500 align:start\n<c>Hola</c> mundo\n\n"
               "00:00:03.500 --> 00:00:05.000\nHola mundo\n\n01:02.000 --> 01:04.000\nSiguiente")
        segmentos = leer_subtitulos(vtt)
        self.assertEqual([s.texto for s in segmentos], ["Hola mundo", "Siguiente"])
        self.assertEqual(segmentos[1].inicio, 62.0)

    def test_txt_por_parrafos(self):
        segmentos = leer_txt("Primer párrafo.\n\nSegundo\npárrafo.\n\n\n")
        self.assertEqual(len(segmentos), 2)
        self.assertIsNone(segmentos[0].inicio)

    def test_ida_y_vuelta_srt(self):
        original = obtener_segmentos(EJEMPLO)
        self.assertEqual(leer_subtitulos(a_srt(original)), original)

    def test_formato_tiempo(self):
        self.assertEqual(formato_tiempo(75), "01:15")
        self.assertEqual(formato_tiempo(3725), "1:02:05")
        self.assertEqual(formato_tiempo(None), "")

    def test_formato_no_soportado(self):
        with self.assertRaises(ValueError):
            obtener_segmentos(Path("documento.pdf"))


if __name__ == "__main__":
    unittest.main()
