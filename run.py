"""JobMatch AI — Flask App Entry Point.

Run with:
    python run.py

Then open http://localhost:5000
"""

from webapp.app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000, exclude_patterns=["venv/*"])
