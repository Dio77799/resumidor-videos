"""
Interfaz web local: arrastras el archivo, eliges proveedor, ves el progreso y descargas los apuntes.
Solo librería estándar. Escucha únicamente en 127.0.0.1.

Uso:  python app.py   ->  abre http://127.0.0.1:8770
"""
import json
import threading
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

import proveedores
import resumir
from transcribir import EXT_MEDIA, EXT_TEXTO, MODELOS_WHISPER

PUERTO = 8770
HTML = resumir.BASE / "web" / "index.html"
ENTRADA = resumir.BASE / "entrada"
MAX_BYTES = 8 * 1024**3  # 8 GB
ORIGENES = {f"http://127.0.0.1:{PUERTO}", f"http://localhost:{PUERTO}"}

trabajos: dict[str, dict] = {}
descargas: dict[str, dict] = {}  # modelo de Ollama -> estado de su descarga
candado_llm = threading.Lock()  # un resumen a la vez: Ollama y Whisper en local no ganan nada en paralelo


def procesar(id_: str, ruta: Path, opciones: dict) -> None:
    t = trabajos[id_]

    def progreso(fraccion, mensaje):
        t["progreso"], t["mensaje"] = round(fraccion, 3), mensaje

    try:
        if candado_llm.locked():
            progreso(0, "En cola: esperando a que termine el resumen anterior…")
        with candado_llm:
            t["estado"] = "procesando"
            salida = resumir.resumir(
                ruta,
                proveedor=opciones["proveedor"],
                modelo=opciones.get("modelo") or None,
                api_key=opciones.get("api_key") or None,
                idioma=opciones.get("idioma") or "es",
                modelo_whisper=opciones.get("whisper") or "small",
                titulo=opciones.get("titulo") or Path(t["archivo"]).stem,
                progreso=progreso,
            )
        t.update(estado="listo", salida=salida.name, markdown=salida.read_text(encoding="utf-8"),
                 srt=salida.with_suffix(".srt").name if salida.with_suffix(".srt").exists() else None)
    except Exception as e:  # se muestra en la interfaz; la key nunca forma parte del mensaje
        t.update(estado="error", mensaje=str(e))
        resumir.traza({"error": type(e).__name__, "mensaje": str(e)[:300], "proveedor": opciones.get("proveedor"),
                       "modelo": opciones.get("modelo"), "archivo": Path(t["archivo"]).suffix.lower()})
    finally:
        opciones.pop("api_key", None)


def descargar(modelo: str) -> None:
    d = descargas[modelo]

    def progreso(fraccion, mensaje):
        if fraccion is not None:
            d["progreso"] = round(fraccion, 3)
        d["mensaje"] = mensaje

    try:
        proveedores.descargar_ollama(modelo, progreso)
        d.update(estado="listo", progreso=1, mensaje="Descargado")
    except Exception as e:
        d.update(estado="error", mensaje=str(e))


class Manejador(BaseHTTPRequestHandler):
    def log_message(self, *args):  # sin logs de peticiones en consola (podrían incluir nombres de archivo)
        pass

    def _enviar(self, cuerpo: bytes, tipo: str, codigo=200, extra: dict | None = None):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(cuerpo)

    def _json(self, datos, codigo=200):
        self._enviar(json.dumps(datos, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", codigo)

    def _origen_valido(self) -> bool:
        # Evita que otra web abierta en el navegador mande peticiones a este servidor local.
        origen = self.headers.get("Origin")
        return origen is None or origen in ORIGENES

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            self._enviar(HTML.read_bytes(), "text/html; charset=utf-8")
        elif url.path == "/api/info":
            instalados = proveedores.modelos_ollama()
            self._json({
                "disponibles": proveedores.disponibles(),
                "modelos_ollama": instalados,
                "catalogo_ollama": [{**m, "instalado": m["modelo"] in instalados} for m in proveedores.CATALOGO_OLLAMA],
                "modelos_por_defecto": proveedores.MODELOS_POR_DEFECTO,
                "modelos_whisper": MODELOS_WHISPER,
                "extensiones": sorted(EXT_TEXTO | EXT_MEDIA),
            })
        elif url.path.startswith("/api/trabajo/"):
            t = trabajos.get(url.path.rsplit("/", 1)[-1])
            if t:
                self._json({k: v for k, v in t.items() if k != "ruta"})
            else:
                self._json({"estado": "desconocido"}, 404)
        elif url.path == "/api/ollama/descargas":
            self._json(descargas)
        elif url.path.startswith("/descargar/"):
            nombre = Path(unquote(url.path.rsplit("/", 1)[-1])).name
            ruta = resumir.SALIDA / nombre
            if ruta.suffix in {".md", ".srt"} and ruta.is_file():
                tipo = "text/markdown; charset=utf-8" if ruta.suffix == ".md" else "text/plain; charset=utf-8"
                self._enviar(ruta.read_bytes(), tipo, extra={"Content-Disposition": f'attachment; filename="{nombre}"'})
            else:
                self._json({"error": "No existe"}, 404)
        else:
            self._json({"error": "No encontrado"}, 404)

    def do_POST(self):
        if not self._origen_valido():
            return self._json({"error": "Origen no permitido"}, 403)
        url = urlparse(self.path)
        largo = int(self.headers.get("Content-Length") or 0)

        if url.path == "/api/subir":
            # El navegador manda el archivo tal cual en el cuerpo y el nombre en una cabecera.
            nombre = Path(unquote(self.headers.get("X-Nombre", "archivo"))).name
            ext = Path(nombre).suffix.lower()
            if ext not in EXT_TEXTO | EXT_MEDIA:
                return self._json({"error": f"Formato no soportado: {ext or 'sin extensión'}"}, 400)
            if not 0 < largo <= MAX_BYTES:
                return self._json({"error": "Archivo vacío o demasiado grande"}, 400)
            ENTRADA.mkdir(exist_ok=True)
            id_ = uuid.uuid4().hex[:12]
            ruta = ENTRADA / f"{id_}{ext}"
            with ruta.open("wb") as f:
                restante = largo
                while restante:
                    trozo = self.rfile.read(min(restante, 1024 * 1024))
                    if not trozo:
                        break
                    f.write(trozo)
                    restante -= len(trozo)
            trabajos[id_] = {"estado": "subido", "archivo": nombre, "ruta": str(ruta),
                             "progreso": 0, "mensaje": "Archivo recibido"}
            return self._json({"id": id_, "titulo": Path(nombre).stem})

        if url.path == "/api/resumir":
            try:
                opciones = json.loads((self.rfile.read(largo) or b"{}").decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return self._json({"error": "Petición mal formada (se espera JSON en UTF-8)"}, 400)
            t = trabajos.get(opciones.get("id", ""))
            if not t or t["estado"] not in {"subido", "listo", "error"}:
                return self._json({"error": "Sube un archivo primero"}, 400)
            if opciones.get("proveedor") not in proveedores.MODELOS_POR_DEFECTO:
                return self._json({"error": "Proveedor no válido"}, 400)
            t.update(estado="en_cola", progreso=0, mensaje="Empezando…", markdown=None, salida=None)
            threading.Thread(target=procesar, args=(opciones["id"], Path(t["ruta"]), opciones), daemon=True).start()
            return self._json({"ok": True})

        if url.path == "/api/ollama/descargar":
            try:
                modelo = json.loads((self.rfile.read(largo) or b"{}").decode("utf-8")).get("modelo", "")
            except (UnicodeDecodeError, json.JSONDecodeError):
                return self._json({"error": "Petición mal formada"}, 400)
            # Solo modelos del catálogo: la interfaz no debe poder descargar cualquier cosa.
            if modelo not in {m["modelo"] for m in proveedores.CATALOGO_OLLAMA}:
                return self._json({"error": "Modelo fuera del catálogo"}, 400)
            if descargas.get(modelo, {}).get("estado") != "descargando":
                descargas[modelo] = {"estado": "descargando", "progreso": 0, "mensaje": "Empezando…"}
                threading.Thread(target=descargar, args=(modelo,), daemon=True).start()
            return self._json({"ok": True})

        self._json({"error": "No encontrado"}, 404)


def main():
    servidor = ThreadingHTTPServer(("127.0.0.1", PUERTO), Manejador)
    url = f"http://127.0.0.1:{PUERTO}"
    print(f"Resumidor de videos en {url}  (Ctrl+C para salir)")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrado.")


if __name__ == "__main__":
    main()
