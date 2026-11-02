"""All settings are read from environment variables (see .env.example)."""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    DATABASE_PATH = os.environ.get("DATABASE_PATH", "instance/smarteval.db")
    OCR_ENGINE = os.environ.get("OCR_ENGINE", "demo")
    EVAL_ENGINE = os.environ.get("EVAL_ENGINE", "light")
    DEMO_MODE = os.environ.get("DEMO_MODE", "1") == "1"
    DEMO_TEACHER_USER = os.environ.get("DEMO_TEACHER_USER", "teacher")
    DEMO_TEACHER_PASSWORD = os.environ.get("DEMO_TEACHER_PASSWORD", "teacher123")
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "10")) * 1024 * 1024
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf", "txt"}
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
