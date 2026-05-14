const els = {
  audioInput: document.querySelector("#audioInput"),
  audioName: document.querySelector("#audioName"),
  dropZone: document.querySelector("#dropZone"),
  exportPdfButton: document.querySelector("#exportPdfButton"),
  editorCard: document.querySelector("#editorCard"),
  editorFrame: document.querySelector("#editorFrame"),
  statusText: document.querySelector("#statusText"),
};

let selectedAudio = null;
let currentChordProName = "cancion.chopro";
let appBusy = false;
let currentDocumentReady = false;

if ("scrollRestoration" in window.history) {
  window.history.scrollRestoration = "manual";
}
window.scrollTo(0, 0);

function setStatus(message) {
  els.statusText.textContent = message;
}

function setBusy(busy) {
  appBusy = busy;
  els.dropZone.classList.toggle("busy", busy);
  els.audioInput.disabled = busy;
  els.exportPdfButton.disabled = busy || !currentDocumentReady || !editorHasDocument();
}

function editorHasDocument() {
  try {
    const frame = els.editorFrame.contentWindow;
    return Boolean(frame?.hasContent?.());
  } catch {
    return false;
  }
}

function textToBase64Url(text) {
  return btoa(
    Array.from(new TextEncoder().encode(text), (byte) => String.fromCharCode(byte)).join(""),
  )
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function bytesToBase64(bytes) {
  let binary = "";
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return btoa(binary);
}

function setAudio(file) {
  selectedAudio = file || null;
  els.audioName.textContent = "Subir audio";
  els.dropZone.title = file ? file.name : "Subir audio";
  setBusy(false);
  if (selectedAudio) transcribeAudio();
}

async function transcribeAudio() {
  if (!selectedAudio) return;

  setBusy(true);
  setStatus("");
  openPlainTextInEditor("Procesando el archivo de audio, esto puede tardar unos minutos.", "procesando.txt");

  try {
    const response = await fetch("/api/transcribe", {
      method: "POST",
      headers: {
        "Content-Type": selectedAudio.type || "application/octet-stream",
        "X-Audio-Filename": encodeURIComponent(selectedAudio.name || "audio"),
      },
      body: selectedAudio,
    });
    const result = await response.json();
    if (!response.ok || !result.ok) {
      throw new Error(result.error || "No se pudo procesar el audio.");
    }

    currentChordProName = `${result.artifacts.song_id || "cancion"}.chopro`;
    openChordProInEditor(result.chordpro, currentChordProName);
    setStatus("");
  } catch (error) {
    openPlainTextInEditor(`No pude procesar el audio.\n\n${error.message}`, "error.txt");
    setStatus(error.message);
  } finally {
    els.audioInput.value = "";
    setBusy(false);
  }
}

function openPlainTextInEditor(source, name) {
  openEditorSource(source, name, false);
}

function openChordProInEditor(source, name) {
  openEditorSource(source, name, true);
}

function openEditorSource(source, name, exportable) {
  currentDocumentReady = exportable;
  const params = new URLSearchParams();
  params.set("source", textToBase64Url(source));
  params.set("name", name || currentChordProName);
  els.editorFrame.dataset.revealOnLoad = "true";
  els.editorFrame.src = `/editor.html?v=${Date.now()}#${params.toString()}`;
  els.exportPdfButton.disabled = !exportable;
}

async function exportPdf() {
  const frame = els.editorFrame.contentWindow;
  if (!frame) return;

  setBusy(true);
  setStatus("");

  try {
    if (!frame.hasContent?.()) {
      throw new Error("No hay contenido para exportar.");
    }

    frame.syncEditorToDoc?.();
    const rows = frame.exportPdfRows?.() || [];
    const bytes = frame.makePdfBytes?.(rows.length ? rows : [{ text: "", kind: "blank" }]);
    if (!bytes?.byteLength) {
      throw new Error("El PDF generado quedo vacio.");
    }

    const response = await fetch("/save-pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename: `${frame.sourceBaseName?.() || "cancion"}.pdf`,
        base64: bytesToBase64(bytes),
      }),
    });
    const result = await response.json();
    if (!response.ok || !result.ok) {
      throw new Error(result.error || "No se pudo exportar el PDF.");
    }
    if (result.url) {
      window.open(`${result.url}?v=${Date.now()}`, "_blank", "noopener");
    }
    if (result.cancelled) return;
  } catch (error) {
    setStatus(error.message);
    window.alert(`No pude exportar el PDF.\n\n${error.message}`);
  } finally {
    setBusy(false);
  }
}

async function loadStatus() {
  try {
    const response = await fetch("/api/status");
    const status = await response.json();
    if (!status.transcriber_python_exists) {
      setStatus(`No encontre Python del transcriptor: ${status.transcriber_python}`);
      return;
    }
    setStatus("");
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

els.exportPdfButton.addEventListener("click", exportPdf);
els.editorFrame.addEventListener("load", () => {
  if (els.editorFrame.dataset.revealOnLoad === "true") {
    delete els.editorFrame.dataset.revealOnLoad;
    window.setTimeout(() => {
      if (window.matchMedia("(max-width: 760px)").matches) {
        els.editorCard.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }, 120);
  }
  if (!appBusy) setBusy(false);
});

loadStatus();
