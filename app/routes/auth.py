from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.forms.auth import LoginForm, RegistrationForm
from app.models import User
from app.utils.security import is_safe_redirect_url

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("user.dashboard"))

    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            full_name=form.full_name.data,
            email=form.email.data.lower(),
            phone=form.phone.data or None,
        )
        user.set_password(form.password.data)
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            # Two people registering the same email at the same moment.
            db.session.rollback()
            flash("An account with this email already exists.", "danger")
            return render_template("auth/register.html", form=form)

        flash("Account created. Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("user.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        # One generic message for "no such user" and "wrong password", so the
        # form does not reveal which emails are registered.
        if user and user.is_active and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get("next")
            if not is_safe_redirect_url(next_page):
                next_page = None
            default_page = "admin.dashboard" if user.is_admin else "user.dashboard"
            return redirect(next_page or url_for(default_page))
        flash("Invalid email or password.", "danger")

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    # POST only, so another website cannot log you out with a plain link.
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.index"))