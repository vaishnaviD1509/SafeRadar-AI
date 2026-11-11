"""Registers all route blueprints. New blueprints are added here in later phases."""


def register_blueprints(app):
    from app.routes.main import main_bp

    app.register_blueprint(main_bp)