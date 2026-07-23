"""Lokaler Dev-Server-Start: macht 'src/' importierbar und laedt .env aus dem
Projektverzeichnis, unabhaengig davon, aus welchem Arbeitsverzeichnis das
Skript aufgerufen wird. Fuer Production siehe README (Render-Deployment).
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / "src"))

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("lol_coach.web.app:app", host="127.0.0.1", port=8420, reload=True)
