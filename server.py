from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import shutil
import subprocess
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
EDITOR_ROOT = ROOT / "deps" / "15_EditorChordPro"
TRANSCRIBER_SUBMODULE_ROOT = ROOT / "deps" / "14_LetrasAcordesv4"
RUNTIME_ROOT = ROOT / "runtime"
UPLOADS_ROOT = RUNTIME_ROOT / "uploads"
EXPORTS_ROOT = RUNTIME_ROOT / "exports"
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8080"))
CHORDPRO_EXTENSIONS = {".cho", ".chopro", ".chordpro"}


def read_gitmodules_url(path: str) -> Path | None:
    current_name = None
    for raw in (ROOT / ".gitmodules").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("[submodule "):
            current_name = line.split('"', 2)[1]
            continue
        if current_name == path and line.startswith("url = "):
            value = line.split("=", 1)[1].strip()
            return Path(value).expanduser()
    return None


def transcriber_runtime_root() -> Path:
    explicit = os.environ.get("TRANSCRIBER_ROOT")
    if explicit:
        return Path(explicit).expanduser().resolve()

    local_source = read_gitmodules_url("deps/14_LetrasAcordesv4")
    if local_source and (local_source / ".venv" / "bin" / "python").exists():
        return local_source.resolve()

    return TRANSCRIBER_SUBMODULE_ROOT


def transcriber_python(root: Path) -> Path | str:
    venv_python = root / ".venv" / "bin" / "python"
    if venv_python.exists():
        return venv_python
    return os.environ.get("PYTHON", "python3.10")


def safe_name(value: str, fallback: str) -> str:
    name = Path(str(value or fallback)).name
    name = re.sub(r"[\x00-\x1f<>:\"/\\|?*]+", "_", name).strip(" .")
    return name or fallback


def safe_audio_name(value: str) -> str:
    return safe_name(value, "audio")


def safe_chordpro_name(value: str) -> str:
    name = safe_name(value, "cancion.chopro")
    if not name.lower().endswith((".cho", ".chopro", ".chordpro", ".txt")):
        name += ".chopro"
    return name


def safe_pdf_name(value: str) -> str:
    name = safe_name(value, "cancion.pdf")
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name


def json_response(handler: SimpleHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_json_payload(handler: SimpleHTTPRequestHandler, limit: int) -> dict:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0 or length > limit:
        raise ValueError("tamano de request invalido")
    return json.loads(handler.rfile.read(length).decode("utf-8"))


def write_base64_file(target: Path, value: str) -> int:
    data = base64.b64decode(value or "", validate=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return len(data)


def applescript_string(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def choose_save_path(default_name: str, prompt: str) -> Path | None:
    script = (
        f"set outputFile to choose file name with prompt {applescript_string(prompt)} "
        f"default name {applescript_string(default_name)}\n"
        "return POSIX path of outputFile"
    )
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).expanduser()
    if "User canceled" in result.stderr or result.returncode == -128:
        return None
    raise RuntimeError((result.stderr or result.stdout or "no pude abrir el selector de archivo").strip())


def validate_pdf_data(data: bytes) -> None:
    if not data.startswith(b"%PDF-") or not data.rstrip().endswith(b"%%EOF"):
        raise ValueError("pdf invalido")


def serve_file(handler: SimpleHTTPRequestHandler, root: Path, request_path: str) -> None:
    relative = unquote(request_path).lstrip("/")
    target = (root / relative).resolve()
    root = root.resolve()

    if not target.is_file() or root not in [target, *target.parents]:
        handler.send_error(404)
        return

    mime = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    handler.send_response(200)
    handler.send_header("Content-Type", mime)
    handler.send_header("Content-Length", str(target.stat().st_size))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    if handler.command != "HEAD":
        shutil.copyfileobj(target.open("rb"), handler.wfile)


def parse_pipeline_artifacts(output: str, runtime_root: Path) -> dict:
    chordpro_path = None
    pdf_path = None
    song_dir = None
    song_id = None

    for line in output.splitlines():
        if line.startswith("Cancion:"):
            song_id = line.split(":", 1)[1].strip()
        if line.startswith("Carpeta:"):
            song_dir = Path(line.split(":", 1)[1].strip())
        if line.startswith("ChordPro:"):
            chordpro_path = Path(line.split(":", 1)[1].strip())
        if line.startswith("PDF:"):
            pdf_path = Path(line.split(":", 1)[1].strip())

    if song_id and not song_dir:
        song_dir = runtime_root / "songs" / song_id
    if song_dir:
        chordpro_path = chordpro_path or song_dir / "10_chordpro" / "song.cho"
        pdf_path = pdf_path or song_dir / "11_pdf" / "song.pdf"

    return {
        "song_id": song_id,
        "song_dir": str(song_dir) if song_dir else None,
        "chordpro_path": str(chordpro_path) if chordpro_path else None,
        "pdf_path": str(pdf_path) if pdf_path else None,
    }


def chordpro_priority(path: Path) -> tuple[int, float]:
    name = path.name.lower()
    score = 0
    if "final" in name:
        score -= 3
    if "song" in name:
        score -= 2
    if path.suffix.lower() in {".cho", ".chopro"}:
        score -= 1
    return (score, -path.stat().st_mtime)


def readable_chordpro(path: Path) -> bool:
    if not path.is_file() or path.suffix.lower() not in CHORDPRO_EXTENSIONS:
        return False
    try:
        return bool(path.read_text(encoding="utf-8").strip())
    except UnicodeDecodeError:
        return False


def find_chordpro_file(artifacts: dict, runtime_root: Path, output: str) -> Path | None:
    file_candidates: list[Path] = []
    dir_candidates: list[Path] = []

    if artifacts.get("chordpro_path"):
        file_candidates.append(Path(artifacts["chordpro_path"]))

    if artifacts.get("song_dir"):
        song_dir = Path(artifacts["song_dir"])
        dir_candidates.extend([
            song_dir / "10_chordpro",
            song_dir / "chordpro",
            song_dir / "ChordPro",
            song_dir,
        ])

    if artifacts.get("song_id"):
        song_dir = runtime_root / "songs" / artifacts["song_id"]
        dir_candidates.extend([
            song_dir / "10_chordpro",
            song_dir / "chordpro",
            song_dir / "ChordPro",
            song_dir,
        ])

    for match in re.findall(r"(/[^\n\r]+?\.(?:cho|chopro|chordpro))\b", output, flags=re.IGNORECASE):
        file_candidates.append(Path(match.strip()))

    for candidate in file_candidates:
        if readable_chordpro(candidate):
            return candidate

    seen_dirs: set[Path] = set()
    for directory in dir_candidates:
        directory = directory.resolve()
        if directory in seen_dirs or not directory.is_dir():
            continue
        seen_dirs.add(directory)
        files = [path for path in directory.rglob("*") if readable_chordpro(path)]
        if files:
            return sorted(files, key=chordpro_priority)[0]

    return None


def run_command(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def run_transcription(payload: dict) -> dict:
    filename = safe_audio_name(payload.get("filename") or "audio")
    job_id = f"{int(time.time())}-{re.sub(r'[^a-z0-9]+', '-', Path(filename).stem.lower()).strip('-') or 'audio'}"
    job_dir = UPLOADS_ROOT / job_id
    audio_path = job_dir / filename
    write_base64_file(audio_path, payload.get("base64") or "")

    runtime_root = transcriber_runtime_root()
    python = transcriber_python(runtime_root)
    pipeline_command = [
        str(python),
        "scripts/run_full_pipeline.py",
        "--input",
        str(audio_path),
    ]
    if payload.get("force"):
        pipeline_command.append("--force")

    started = time.time()
    result = run_command(pipeline_command, runtime_root)
    output = "\n".join(part for part in [result.stdout, result.stderr] if part).strip()
    artifacts = parse_pipeline_artifacts(output, runtime_root)
    chordpro_text = ""

    chordpro_path = find_chordpro_file(artifacts, runtime_root, output)
    if chordpro_path:
        artifacts["chordpro_path"] = str(chordpro_path)
        chordpro_text = chordpro_path.read_text(encoding="utf-8")

    ok = result.returncode == 0 and bool(chordpro_text.strip())

    return {
        "ok": ok,
        "returncode": result.returncode,
        "job_id": job_id,
        "elapsed_sec": round(time.time() - started, 2),
        "runtime_root": str(runtime_root),
        "command": " ".join(pipeline_command),
        "output": output[-20000:],
        "artifacts": artifacts,
        "chordpro": chordpro_text,
        "error": None if ok else "El procesamiento termino, pero no encontre un ChordPro final para abrir en el editor.",
    }


def save_export(payload: dict, kind: str) -> dict:
    EXPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    if kind == "pdf":
        filename = safe_pdf_name(payload.get("filename") or "cancion.pdf")
    else:
        filename = safe_chordpro_name(payload.get("filename") or "cancion.chopro")

    stamped = f"{time.strftime('%Y%m%d-%H%M%S')}-{filename}"
    output = EXPORTS_ROOT / stamped
    size = write_base64_file(output, payload.get("base64") or "")

    if kind == "pdf":
        data = output.read_bytes()
        if not data.startswith(b"%PDF-") or not data.endswith(b"%%EOF"):
            output.unlink(missing_ok=True)
            raise ValueError("pdf invalido")
    else:
        text = output.read_text(encoding="utf-8")
        if not text.strip():
            output.unlink(missing_ok=True)
            raise ValueError("chordpro vacio")

    return {
        "ok": True,
        "filename": stamped,
        "size": size,
        "path": str(output),
        "url": f"/exports/{stamped}",
    }


def save_pdf_as(payload: dict) -> dict:
    filename = safe_pdf_name(payload.get("filename") or "cancion.pdf")
    data = base64.b64decode(payload.get("base64") or "", validate=True)
    validate_pdf_data(data)

    if os.environ.get("PDF_SAVE_MODE") == "runtime" or not shutil.which("osascript"):
        return save_export(payload, "pdf")

    target = choose_save_path(filename, "Guardar PDF")
    if target is None:
        return {"ok": True, "cancelled": True}
    if target.suffix.lower() != ".pdf":
        target = target.with_suffix(".pdf")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {
        "ok": True,
        "filename": target.name,
        "size": len(data),
        "path": str(target),
    }


def status_payload() -> dict:
    runtime_root = transcriber_runtime_root()
    python = transcriber_python(runtime_root)
    return {
        "ok": True,
        "editor_root": str(EDITOR_ROOT),
        "transcriber_root": str(runtime_root),
        "transcriber_python": str(python),
        "transcriber_python_exists": Path(python).exists() if isinstance(python, Path) else shutil.which(str(python)) is not None,
        "submodules": {
            "transcriber": "deps/14_LetrasAcordesv4",
            "editor": "deps/15_EditorChordPro",
        },
    }


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/status":
            json_response(self, 200, status_payload())
            return
        if path.startswith("/editor15/"):
            serve_file(self, EDITOR_ROOT, path.removeprefix("/editor15/") or "index.html")
            return
        if path.startswith("/exports/"):
            serve_file(self, EXPORTS_ROOT, path.removeprefix("/exports/"))
            return
        if path == "/":
            serve_file(self, WEB_ROOT, "index.html")
            return
        serve_file(self, WEB_ROOT, path)

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/transcribe":
                payload = read_json_payload(self, 300_000_000)
                result = run_transcription(payload)
                json_response(self, 200 if result["ok"] else 500, result)
                return
            if path == "/save-pdf":
                payload = read_json_payload(self, 40_000_000)
                json_response(self, 200, save_pdf_as(payload))
                return
            if path == "/export-pdf":
                payload = read_json_payload(self, 40_000_000)
                json_response(self, 200, save_export(payload, "pdf"))
                return
            if path in {"/save-chordpro", "/export-chordpro"}:
                payload = read_json_payload(self, 10_000_000)
                json_response(self, 200, save_export(payload, "chordpro"))
                return
            json_response(self, 404, {"ok": False, "error": "ruta inexistente"})
        except Exception as error:
            json_response(self, 400, {"ok": False, "error": str(error)})


def main() -> None:
    UPLOADS_ROOT.mkdir(parents=True, exist_ok=True)
    EXPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Flujo Letras+Acordes en http://{HOST}:{PORT}")
    print(f"Editor 15 servido desde {EDITOR_ROOT}")
    print(f"Transcriptor 14 runtime {transcriber_runtime_root()}")
    server.serve_forever()


if __name__ == "__main__":
    main()
