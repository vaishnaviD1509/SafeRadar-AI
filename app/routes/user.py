from flask import Blueprint, current_app, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.forms.user import ContactForm, ProfileForm
from app.models import TrustedContact
from app.services.stats import (
    get_current_risk, get_dashboard_stats, get_map_markers, get_recent_incidents,
)

user_bp = Blueprint("user", __name__)


@user_bp.route("/dashboard")
@login_required
def dashboard():
    return render_template(
        "user/dashboard.html",
        stats=get_dashboard_stats(current_user),
        recent=get_recent_incidents(),
        markers=get_map_markers(),
        risk=get_current_risk(),
        map_center=current_app.config["DEFAULT_MAP_CENTER"],
        map_zoom=current_app.config["DEFAULT_MAP_ZOOM"],
        max_contacts=current_app.config["MAX_TRUSTED_CONTACTS"],
    )


@user_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    form = ProfileForm(obj=current_user)
    if form.validate_on_submit():
        current_user.full_name = form.full_name.data
        current_user.phone = form.phone.data or None
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("user.profile"))

    return render_template(
        "user/profile.html",
        form=form,
        contact_form=ContactForm(),
        contacts=current_user.contacts,
        max_contacts=current_app.config["MAX_TRUSTED_CONTACTS"],
    )


@user_bp.route("/contacts/add", methods=["POST"])
@login_required
def add_contact():
    form = ContactForm()
    max_contacts = current_app.config["MAX_TRUSTED_CONTACTS"]

    if len(current_user.contacts) >= max_contacts:
        flash(f"You can save up to {max_contacts} trusted contacts.", "warning")
    elif form.validate_on_submit():
        phone = form.contact_phone.data
        if any(contact.phone == phone for contact in current_user.contacts):
            flash("That number is already in your trusted contacts.", "warning")
        else:
            db.session.add(TrustedContact(
                user_id=current_user.id,
                name=form.contact_name.data,
                phone=phone,
                relationship_label=form.contact_relation.data or None,
            ))
            db.session.commit()
            flash("Trusted contact added.", "success")
    else:
        for errors in form.errors.values():
            for error in errors:
                flash(error, "danger")

    return redirect(url_for("user.profile"))


@user_bp.route("/contacts/<int:contact_id>/delete", methods=["POST"])
@login_required
def delete_contact(contact_id):
    # Filtering by user_id means you can only delete your own contacts.
    contact = TrustedContact.query.filter_by(
        id=contact_id, user_id=current_user.id
    ).first_or_404()
    db.session.delete(contact)
    db.session.commit()
    flash("Contact removed.", "info")
    return redirect(url_for("user.profile"))