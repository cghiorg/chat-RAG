# ChatRAG (sin Docker) · Ollama + Chroma + Flask

Interfaz tipo chat para consultar tu wiki en PDFs usando RAG local.

## Requisitos
1) **Ollama** instalado y ejecutándose (Windows/macOS/Linux).
2) Python 3.11+
3) Modelos descargados en Ollama (una sola vez):
```
ollama pull llama3.1:8b
ollama pull nomic-embed-text
```

## Paso a paso (Windows/macOS/Linux)

1) Descomprimir este ZIP en una carpeta, por ej. `chatrag_nodocker/`.
2) Abrir una terminal en esa carpeta y crear/activar entorno:
   - Windows (PowerShell):
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate
     ```
   - macOS/Linux (bash/zsh):
     ```bash
     python -m venv .venv
     source .venv/bin/activate
     ```
3) Instalar dependencias:
   ```bash
   pip install -r requirements.txt
   ```
4) Crear archivo `.env` (puede copiarse del ejemplo):
   ```bash
   # Windows
   copy .env.example .env
   # macOS/Linux
   cp .env.example .env
   ```
   Ajustar si querés usuario/clave o los modelos.
5) Verificar que **Ollama** está funcionando:
   ```bash
   curl http://localhost:11434/api/tags
   ```
   Si devuelve JSON, está OK.
6) Ejecutar la app:
   ```bash
   python app.py
   ```
7) Abrir http://localhost:5000 e ingresar con `politecnico` / `malvinas` (por defecto).

## Uso
- Colocar PDFs en `data/pdfs/` o subir desde la UI.
- Click en **Indexar todo**.
- Realizar preguntas desde el chat.
- **Exportar índice**: descarga un `.zip` con `db/`.
- **Importar índice**: sube ese `.zip` y restaura el índice.

## Notas
- Todo corre local: privacidad y $0 por token.
- El índice (Chroma) queda en `db/` (persistente); reindexá sólo cuando sumes/edites PDFs.
