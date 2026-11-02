"""Entry point used by gunicorn (Render) and `python wsgi.py` locally."""
from smarteval import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
