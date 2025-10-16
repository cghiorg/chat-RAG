import os, uuid, re, shutil, zipfile, io
from pathlib import Path
from typing import List, Dict, Any
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_file, flash
from dotenv import load_dotenv
import fitz  # PyMuPDF
os.environ["CHROMA_TELEMETRY_IMPLEMENTATION"] = "none"
os.environ["CHROMA_TELEMETRY_DISABLED"] = "true"   # por si tu versión lo respeta
os.environ["ANONYMIZED_TELEMETRY"] = "False"       # compat con variantes viejas
import chromadb
from chromadb.config import Settings
import ollama

load_dotenv(override=False)
GEN_MODEL = os.getenv("RAG_GENERATION_MODEL", "llama3.2:3b-instruct-q4_K_M")
# GEN_MODEL = os.getenv("RAG_GENERATION_MODEL", "qwen2.5:1.5b-instruct-q4_K_M")
EMB_MODEL = os.getenv("RAG_EMBEDDING_MODEL", "nomic-embed-text")
CHROMA_DIR = os.getenv("CHROMA_DB_DIR", "./db")
COLLECTION = os.getenv("CHROMA_COLLECTION", "wiki_pdf")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "150"))
PDF_DIR = Path(os.getenv("PDF_DIR", "./data/pdfs")).resolve()
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads")).resolve()
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
os.environ["OLLAMA_HOST"] = OLLAMA_HOST

LOGIN_USER = os.getenv("LOGIN_USER", "politecnico")
LOGIN_PASS = os.getenv("LOGIN_PASS", "malvinas")

PDF_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
Path(CHROMA_DIR).mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret")

# ---------- Auth ----------
def is_public_path(path: str) -> bool:
    if path == "/login" or path.startswith("/static") or path == "/healthz":
        return True
    return False

@app.before_request
def require_login():
    if is_public_path(request.path):
        return
    if not session.get("user"):
        return redirect(url_for("login"))

@app.get("/login")
def login():
    return render_template("login.html")

@app.post("/login")
def do_login():
    u = request.form.get("username","").strip()
    p = request.form.get("password","").strip()
    if u == LOGIN_USER and p == LOGIN_PASS:
        session["user"] = u
        return redirect(url_for("chat_ui"))
    flash("Usuario o contraseña incorrectos.")
    return redirect(url_for("login"))

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------- Utils ----------
def clean_text(s: str) -> str:
    s = s.replace("\r", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def pdf_to_page_texts(path: Path):
    doc = fitz.open(str(path))
    out = []
    for i, page in enumerate(doc):
        text = clean_text(page.get_text("text"))
        if text:
            out.append({"page": i + 1, "text": text})
    return out

def chunk_text(text: str, chunk_size: int, overlap: int):
    chunks = []
    i = 0
    n = len(text)
    while i < n:
        chunk = text[i:i+chunk_size]
        chunks.append(chunk)
        i += max(1, chunk_size - overlap)
    return chunks

def format_source(meta: dict) -> str:
    src = meta.get("source", "desconocido")
    page = meta.get("page")
    return f"{src} (p. {page})" if page else src

# ---------- Chroma singleton ----------
_chroma_client = None
_chroma_col = None
def get_chroma():
    global _chroma_client, _chroma_col
    if _chroma_client is None:
        _chroma_client = chromadb.Client(Settings(
            persist_directory=CHROMA_DIR, is_persistent=True
        ))
    if _chroma_col is None:
        try:
            _chroma_col = _chroma_client.get_collection(COLLECTION)
        except Exception:
            _chroma_col = _chroma_client.create_collection(COLLECTION)
    return _chroma_client, _chroma_col

def embed_batch(texts: List[str]):
    vecs = []
    for t in texts:
        out = ollama.embeddings(model=EMB_MODEL, prompt=t)
        vecs.append(out["embedding"])
    return vecs

def add_docs_to_chroma(docs: List[str], metas: List[dict]):
    _, col = get_chroma()
    embs = embed_batch(docs)
    ids = [str(uuid.uuid4()) for _ in docs]
    col.add(ids=ids, documents=docs, metadatas=metas, embeddings=embs)

def rag_answer(question: str, k: int = 5) -> dict:
    _, col = get_chroma()
    q_emb = ollama.embeddings(model=EMB_MODEL, prompt=question)["embedding"]
    res = col.query(query_embeddings=[q_emb], n_results=k)

    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]

    if not docs:
        return {"answer": "No hay resultados en el índice. Indexá PDFs primero.", "sources": []}

    header = """Sos un asistente que responde EXCLUSIVAMENTE con la información del contexto.
Si algo no está en el contexto, respondé: "No tengo esa información en la wiki".

=== CONTEXTO ===
"""
    context = "\n\n---\n\n".join(docs)
    prompt = f"""{header}{context}

=== PREGUNTA ===
{question}

Respondé en español, claro y conciso."""
    out = ollama.chat(
        model=GEN_MODEL,
        messages=[{"role": "user", "content": prompt}],
        options={
            "temperature": 0.2,
            "num_ctx": 1024,                 # 2048 -> 1024 (menos tokens que procesar)
            "num_predict": 128,              # 256 -> 128 (respuestas más cortas = más rápido)
            "num_thread": os.cpu_count(),    # usar todos los hilos del i7-3770
            "low_vram": True,
            "keep_alive": "2h"               # mantiene el modelo cargado y evita el “arranque en frío”
        }
    )
    answer = out["message"]["content"].strip()
    sources = [format_source(m) for m in metas]
    return {"answer": answer, "sources": sources}

# ---------- UI ----------
@app.get("/")
def chat_ui():
    local_pdfs = sorted([p.name for p in PDF_DIR.glob("*.pdf")])
    uploaded_pdfs = sorted([p.name for p in UPLOAD_DIR.glob("*.pdf")])
    return render_template("chat.html", local_pdfs=local_pdfs, uploaded_pdfs=uploaded_pdfs)

# ---------- APIs ----------
@app.post("/api/upload")
def api_upload():
    f = request.files.get("pdf")
    if not f or f.filename == "":
        return jsonify({"ok": False, "error": "No se envió archivo."}), 400
    if not f.filename.lower().endswith(".pdf"):
        return jsonify({"ok": False, "error": "Solo PDF."}), 400
    dest = UPLOAD_DIR / f.filename
    f.save(dest)
    return jsonify({"ok": True, "filename": f.filename})

@app.post("/api/index")
def api_index():
    sources = list(PDF_DIR.glob("*.pdf")) + list(UPLOAD_DIR.glob("*.pdf"))
    if not sources:
        return jsonify({"ok": False, "error": "No hay PDFs en data/pdfs ni en uploads."}), 400

    pages_count = 0
    chunks_count = 0
    for pdf in sources:
        try:
            pages = pdf_to_page_texts(pdf)
            pages_count += len(pages)
            for page in pages:
                chunks = chunk_text(page["text"], CHUNK_SIZE, CHUNK_OVERLAP)
                if not chunks:
                    continue
                metas = [{"source": pdf.name, "page": page["page"]} for _ in chunks]
                add_docs_to_chroma(chunks, metas)
                chunks_count += len(chunks)
        except Exception as e:
            print(f"[WARN] {pdf.name}: {e}")
    return jsonify({"ok": True, "pages": pages_count, "chunks": chunks_count})

@app.post("/api/ask")
def api_ask():
    data = request.get_json(force=True, silent=True) or {}
    q = (data.get("q") or "").strip()
    k = int(data.get("k") or 5)
    if not q:
        return jsonify({"ok": False, "error": "Falta 'q'."}), 400
    result = rag_answer(q, k=k)
    return jsonify({"ok": True, "answer": result["answer"], "sources": result["sources"]})

@app.post("/api/wipe")
def api_wipe():
    client, _ = get_chroma()
    try:
        client.delete_collection(COLLECTION)
        global _chroma_col
        _chroma_col = None
        if os.path.isdir(CHROMA_DIR):
            shutil.rmtree(CHROMA_DIR, ignore_errors=True)
            os.makedirs(CHROMA_DIR, exist_ok=True)
        return jsonify({"ok": True, "msg": f"Colección '{COLLECTION}' eliminada."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.post("/api/export")
def api_export():
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zf:
        base_dir = Path(CHROMA_DIR)
        if base_dir.exists():
            for root, dirs, files in os.walk(base_dir):
                for f in files:
                    full = Path(root) / f
                    arc = str(full.relative_to(base_dir.parent))
                    zf.write(full, arcname=arc)
    mem.seek(0)
    return send_file(mem, mimetype="application/zip", as_attachment=True, download_name="chroma_index.zip")

@app.post("/api/import")
def api_import():
    file = request.files.get("zip")
    if not file or file.filename == "":
        return jsonify({"ok": False, "error": "Falta archivo .zip"}), 400
    if not file.filename.lower().endswith(".zip"):
        return jsonify({"ok": False, "error": "Debe ser .zip"}), 400

    client, _ = get_chroma()
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    global _chroma_col
    _chroma_col = None

    if os.path.isdir(CHROMA_DIR):
        shutil.rmtree(CHROMA_DIR, ignore_errors=True)
    os.makedirs(CHROMA_DIR, exist_ok=True)

    with zipfile.ZipFile(file, "r") as z:
        z.extractall(Path(CHROMA_DIR).parent)

    return jsonify({"ok": True, "msg": "Índice importado correctamente. Volvé a preguntar."})

@app.get("/healthz")
def healthz():
    return {"ok": True}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
