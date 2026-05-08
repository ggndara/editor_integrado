# Editor Integrado

Flujo integrado para subir audio, generar ChordPro con el pipeline de `14_LetrasAcordesv4`, corregirlo en el editor de `15_EditorChordPro` y exportar PDF.

## Docker

Clonar con submodules:

```bash
git clone --recurse-submodules https://github.com/ggndara/editor_integrado.git
cd editor_integrado
```

Crear un `.env` local a partir del ejemplo:

```bash
cp .env.example .env
```

Editar `.env` y definir:

```bash
OPENAI_API_KEY=...
```

Levantar el producto completo:

```bash
docker compose up --build
```

Abrir:

```text
http://127.0.0.1:8080
```

El contenedor incluye:

- servidor del proyecto 16;
- frontend del editor integrado;
- submodule `deps/14_LetrasAcordesv4` con Python, OpenAI, Madmom, ReportLab y ffmpeg;
- submodule `deps/15_EditorChordPro` como editor servido por el servidor del 16.

## Archivos generados

En Docker, el PDF no abre un selector de archivos de macOS. Se guarda en:

```text
runtime/exports/
```

Las canciones procesadas por el pipeline quedan montadas en:

```text
docker-data/songs/
```

Ambas carpetas estan ignoradas por Git.
