"""Cria o banco SQLite (data/cftv.db). Regras ficam em data/rules.json."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db import init_db

if __name__ == "__main__":
    init_db()
