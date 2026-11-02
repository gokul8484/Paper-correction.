"""SmartEval application factory."""
import os
from flask import Flask
from .config import Config
from . import db as database


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    if app.config["SECRET_KEY"] == "dev-only-change-me" and not app.debug \
            and os.environ.get("RENDER"):
        raise RuntimeError("Set SECRET_KEY in the environment for production.")

    app.teardown_appcontext(database.close_db)

    from .routes import bp
    app.register_blueprint(bp)

    with app.app_context():
        database.init_db()
        if app.config["DEMO_MODE"]:
            from .seed import seed_demo
            seed_demo(database.get_db(), app.config["DEMO_TEACHER_USER"],
                      app.config["DEMO_TEACHER_PASSWORD"])
    return app
