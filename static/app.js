const chatBox = document.getElementById("chatBox");
const askForm = document.getElementById("askForm");
const qInput = document.getElementById("q");
const kInput = document.getElementById("k");
const uploadForm = document.getElementById("uploadForm");
const indexBtn = document.getElementById("indexBtn");
const wipeBtn = document.getElementById("wipeBtn");
const opsMsg = document.getElementById("opsMsg");
const exportBtn = document.getElementById("exportBtn");
const importForm = document.getElementById("importForm");

function addMsg(role, text, sources=[]) {
  const wrap = document.createElement("div");
  const mine = role === "user";
  wrap.className = `flex ${mine ? "justify-end" : "justify-start"}`;

  const bubble = document.createElement("div");
  bubble.className = `max-w-[85%] p-3 rounded-2xl border ${mine ? "bg-emerald-600/90 border-emerald-500" : "bg-slate-900/70 border-slate-700"}`;

  const p = document.createElement("div");
  p.className = "whitespace-pre-wrap text-sm";
  p.textContent = text;

  bubble.appendChild(p);

  if (!mine && sources && sources.length) {
    const ul = document.createElement("ul");
    ul.className = "mt-2 text-xs text-slate-300 list-disc list-inside";
    sources.forEach(s => {
      const li = document.createElement("li");
      li.textContent = s;
      ul.appendChild(li);
    });
    bubble.appendChild(ul);
  }

  wrap.appendChild(bubble);
  chatBox.appendChild(wrap);
  chatBox.scrollTop = chatBox.scrollHeight;
}

function addTyping() {
  const wrap = document.createElement("div");
  wrap.className = "flex justify-start";
  wrap.id = "typingWrap";

  const bubble = document.createElement("div");
  bubble.className = "max-w-[85%] p-3 rounded-2xl border bg-slate-900/70 border-slate-700";

  const p = document.createElement("div");
  p.className = "whitespace-pre-wrap text-sm text-slate-300";
  p.textContent = "Procesando…";

  const dots = document.createElement("span");
  dots.id = "typingDots";
  dots.textContent = " ";
  p.appendChild(dots);

  bubble.appendChild(p);
  wrap.appendChild(bubble);
  chatBox.appendChild(wrap);
  chatBox.scrollTop = chatBox.scrollHeight;

  // animación de puntitos
  let i = 0;
  const interval = setInterval(() => {
    if (!document.getElementById("typingDots")) { clearInterval(interval); return; }
    i = (i + 1) % 4;
    dots.textContent = ".".repeat(i) + " ".repeat(3 - i);
  }, 400);
}

function removeTyping() {
  const t = document.getElementById("typingWrap");
  if (t) t.remove();
}

askForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const q = qInput.value.trim();
  const k = parseInt(kInput.value || "5", 10);
  if (!q) return;

  addMsg("user", q);
  qInput.value = "";
  addTyping();
  askForm.querySelector("button").disabled = true;
  qInput.disabled = true;
  kInput.disabled = true;

  try {
    const res = await fetch("/api/ask", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ q, k })
    });
    const data = await res.json();
    removeTyping();
    if (data.ok) {
      addMsg("assistant", data.answer, data.sources);
    } else {
      addMsg("assistant", "Error: " + (data.error || "desconocido"));
    }
  } catch (err) {
    removeTyping();
    addMsg("assistant", "Error de red.");
  } finally {
    askForm.querySelector("button").disabled = false;
    qInput.disabled = false;
    kInput.disabled = false;
    qInput.focus();
  }
});

uploadForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const formData = new FormData(uploadForm);
  opsMsg.textContent = "Subiendo...";
  const res = await fetch("/api/upload", { method:"POST", body: formData });
  const data = await res.json();
  opsMsg.textContent = data.ok ? "PDF subido." : ("Error: " + data.error);
});

indexBtn.addEventListener("click", async () => {
  opsMsg.textContent = "Indexando...";
  const res = await fetch("/api/index", { method:"POST" });
  const data = await res.json();
  opsMsg.textContent = data.ok ? `Indexado: páginas=${data.pages}, chunks=${data.chunks}` : ("Error: " + data.error);
});

wipeBtn.addEventListener("click", async () => {
  if (!confirm("¿Borrar la colección completa?")) return;
  const res = await fetch("/api/wipe", { method:"POST" });
  const data = await res.json();
  opsMsg.textContent = data.ok ? data.msg : ("Error: " + data.error);
});

exportBtn.addEventListener("click", async () => {
  opsMsg.textContent = "Exportando índice...";
  const res = await fetch("/api/export", { method: "POST" });
  if (!res.ok) { opsMsg.textContent = "Error al exportar"; return; }
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "chroma_index.zip";
  a.click();
  window.URL.revokeObjectURL(url);
  opsMsg.textContent = "Exportado.";
});

importForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const formData = new FormData(importForm);
  opsMsg.textContent = "Importando índice...";
  const res = await fetch("/api/import", { method:"POST", body: formData });
  const data = await res.json();
  opsMsg.textContent = data.ok ? data.msg : ("Error: " + data.error);
});
