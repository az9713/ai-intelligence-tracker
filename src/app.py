"""Flask application factory for the AI Intelligence Tracking System."""

import logging
import os

from flask import Flask, render_template

logger = logging.getLogger(__name__)


def create_app(schedule: bool = True) -> Flask:
    """Create and configure the Flask application.

    Args:
        schedule: If True, start the APScheduler background scheduler.

    Returns:
        Configured Flask application instance.
    """
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )
    app.config["JSON_SORT_KEYS"] = False

    # Register API blueprint
    from src.routes_api import api_bp
    app.register_blueprint(api_bp, url_prefix="/api")

    # Root route
    @app.route("/")
    def index():
        return render_template("index.html")

    # Start scheduler if requested.
    # Guard against Werkzeug's reloader spawning a second process in debug mode —
    # only start in the child reloader process (WERKZEUG_RUN_MAIN=true) or when
    # not running under the Werkzeug reloader at all.
    if schedule:
        in_reloader_child = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
        under_reloader = "WERKZEUG_RUN_MAIN" in os.environ
        if in_reloader_child or not under_reloader:
            from src.scheduler import start_scheduler
            start_scheduler(app)
            logger.info("APScheduler started with application")

    return app
