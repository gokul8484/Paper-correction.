"""Tiny SQLite helper. One connection per request."""
import os
import sqlite3
from flask import current_app, g


def get_db():
    if "db" not in g:
        path = current_app.config["DATABASE_PATH"]
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        g.db = sqlite3.connect(path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    schema = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema, encoding="utf-8") as f:
        db.executescript(f.read())
    db.commit()
