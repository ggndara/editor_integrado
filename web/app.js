const els = {
  audioInput: document.querySelector("#audioInput"),
  audioName: document.querySelector("#audioName"),
  dropZone: document.querySelector("#dropZone"),
  transcribeButton: document.querySelector("#transcribeButton"),
  exportBothButton: document.querySelector("#exportBothButton"),
  clearEditorButton: document.querySelector("#clearEditorButton"),
  copyChordProButton: document.querySelector("#copyChordProButton"),
  editorCard: document.querySelector("#editorCard"),
  editorFrame: document.querySelector("#editorFrame"),
  statusText: document.querySelector("#statusText"),
};

let selectedAudio = null;
let currentChordProName = "cancion.chopro";

if ("scrollRestoration" in window.history) {
  window.history.scrollRestoration = "manual";
}
window.scrollTo(0, 0);

function setStatus(message) {
  els.statusText.textContent = message;
}

function setBusy(busy) {
  els.transcribeButton.disabled = busy || !selectedAudio;
  els.exportBothButton.disabled = busy || !editorHasDocument();
}

function editorHasDocument() {
  try {
    const frame = els.editorFrame.contentWindow;
    return Boolean(frame?.hasContent?.());
  } catch {
    return false;
  }
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const value = String(reader.result || "");
      resolve(value.includes(",") ? value.split(",", 2)[1] : value);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

function textToBase64Url(text) {
  return btoa(
    Array.from(new TextEncoder().encode(text), (byte) => String.fromCharCode(byte)).join(""),
  )
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function setAudio(file) {
  selectedAudio = file || null;
  els.audioName.textContent = file ? file.name : "Elegir archivo";
  setBusy(false);
}

async function transcribeAudio() {
  if (!selectedAudio) return;

  setBusy(true);
  setStatus("Subiendo audio y ejecutando el pipeline 14 en español...");

  try {
    const base64 = await fileToBase64(selectedAudio);
    const response = await fetch("/api/transcribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename: selectedAudio.name,
        base64,
        lyrics_language: "es",
      }),
    });
    const result = await response.json();
    if (!response.ok || !result.ok) {
      throw new Error(result.output || result.error || "No se pudo generar ChordPro.");
    }

    currentChordProName = `${result.artifacts.song_id || "cancion"}.chopro`;
    openChordProInEditor(result.chordpro, currentChordProName);
    setStatus(`ChordPro generado en ${result.elapsed_sec}s.\nAhora corregi el texto en el editor.`);
  } catch (error) {
    setStatus(`Error:\n${error.message}`);
  } finally {
    setBusy(false);
  }
}

function openChordProInEditor(source, name) {
  const params = new URLSearchParams();
  params.set("source", textToBase64Url(source));
  params.set("name", name || currentChordProName);
  els.editorFrame.dataset.revealOnLoad = "true";
  els.editorFrame.src = `/editor.html?v=${Date.now()}#${params.toString()}`;
  els.exportBothButton.disabled = false;
}

async function exportPdfAndChordPro() {
  const frame = els.editorFrame.contentWindow;
  if (!frame) return;

  setBusy(true);
  setStatus("Exportando ChordPro y PDF desde el editor 15...");

  try {
    if (typeof frame.saveChordPro === "function") {
      await frame.saveChordPro();
    } else {
      frame.document.querySelector("#chordProButton")?.click();
    }

    if (typeof frame.savePdf === "function") {
      await frame.savePdf();
    } else {
      frame.document.querySelector("#pdfButton")?.click();
    }

    setStatus("Exportacion lista. Los archivos quedaron en runtime/exports.");
  } catch (error) {
    setStatus(`Error al exportar:\n${error.message}`);
  } finally {
    setBusy(false);
  }
}

async function loadStatus() {
  try {
    const response = await fetch("/api/status");
    const status = await response.json();
    if (!status.transcriber_python_exists) {
      setStatus(`Atencion: no encontre Python del transcriptor.\n${status.transcriber_python}`);
      return;
    }
    setStatus("Listo. Subi un audio para empezar.");
  } catch {
    setStatus("No pude leer el estado del servidor.");
  }
}

els.audioInput.addEventListener("change", (event) => {
  setAudio(event.currentTarget.files?.[0]);
});

els.dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  els.dropZone.classList.add("dragging");
});

els.dropZone.addEventListener("dragleave", () => {
  els.dropZone.classList.remove("dragging");
});

els.dropZone.addEventListener("drop", (event) => {
  event.preventDefault();
  els.dropZone.classList.remove("dragging");
  setAudio(event.dataTransfer.files?.[0]);
});

els.transcribeButton.addEventListener("click", transcribeAudio);
els.exportBothButton.addEventListener("click", exportPdfAndChordPro);
els.clearEditorButton.addEventListener("click", () => {
  els.editorFrame.src = "/editor.html";
  els.exportBothButton.disabled = true;
  setStatus("Editor limpio.");
});
els.copyChordProButton.addEventListener("click", async () => {
  const frame = els.editorFrame.contentWindow;
  if (!frame?.exportChordPro) return;
  await navigator.clipboard.writeText(frame.exportChordPro());
  setStatus("ChordPro copiado.");
});
els.editorFrame.addEventListener("load", () => {
  if (els.editorFrame.dataset.revealOnLoad === "true") {
    delete els.editorFrame.dataset.revealOnLoad;
    window.setTimeout(() => {
      if (window.matchMedia("(max-width: 760px)").matches) {
        els.editorCard.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }, 120);
  }
  setBusy(false);
});

loadStatus();
