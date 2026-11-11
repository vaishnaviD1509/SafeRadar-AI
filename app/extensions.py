"""Extension objects are created here, without an app, and attached to the
app later inside create_app(). This avoids circular imports."""
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
csrf = CSRFProtect()