"""Initialize the database — creates all tables and enables pgvector.

Usage:
    python -m scripts.init_db
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import init_db
from app.models import *  # noqa: F401,F403 — ensures all models are registered

if __name__ == "__main__":
    print("Initialising database ...")
    init_db()
    print("✓ Done. All tables created.")
