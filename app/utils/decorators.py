from functools import wraps

from flask import abort
from flask_login import current_user, login_required


def admin_required(view):
    """Only logged-in admins may open the view.
    Logged-out visitors go to the login page; regular users get 403."""

    @wraps(view)
    @login_required
    def wrapped_view(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)

    return wrapped_view