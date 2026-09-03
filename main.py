"""
main.py
───────
Entry point for the Student Productivity Agent backend.

Starts the FastAPI server via uvicorn.

Usage:
    python main.py

The server will be available at:
    http://127.0.0.1:8000          ← API root
    http://127.0.0.1:8000/health   ← health check
    http://127.0.0.1:8000/docs     ← interactive API docs (Swagger UI)
    http://127.0.0.1:8000/redoc    ← alternative API docs (ReDoc)

To run the Streamlit frontend (in a separate terminal):
    streamlit run frontend/app.py
"""

import uvicorn
from app.config.settings import API_HOST, API_PORT, DEBUG

if __name__ == "__main__":
    print("─" * 55)
    print("  Student Productivity Agent — Backend")
    print(f"  Starting server at http://{API_HOST}:{API_PORT}")
    print(f"  API docs → http://{API_HOST}:{API_PORT}/docs")
    print("─" * 55)

    uvicorn.run(
        "app.api.app:app",   # module path to the FastAPI instance
        host=API_HOST,
        port=API_PORT,
        reload=DEBUG,        # auto-reload on file changes in DEBUG mode
    )
