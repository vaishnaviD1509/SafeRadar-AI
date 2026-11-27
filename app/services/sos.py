"""Emergency SOS: a private, temporary link that shows a person's live location.

What this does and does not do
------------------------------
* It creates an alert with an unguessable link. People who have the link can see the latest
  location while the alert is live. Nothing else about the person is shown.
* It CANNOT send messages. The person sends the link from their own phone (text, WhatsApp
  or share sheet). So delivery_status is never changed from "not_sent": the app can not know
  whether a message arrived.
* It does not contact the police or any emergency service. The page tells people to call 112.

Privacy
-------
* Only the latest position is kept, not a trail.
* The public view shows the first name only, and no location once the alert has ended or
  expired.
* When an alert ends, its saved location is erased (set to 0, 0). Expired alerts are erased
  and old alerts are deleted by purge_old_alerts() (the "flask purge-sos" command).
* Alerts expire by themselves (SOS_DURATION_MINUTES, 4 hours by default).
"""
import math
import re
from datetime import timedelta
from ipaddress import ip_address
from urllib.parse import quote

from flask import current_app, request, url_for
from sqlalchemy import or_

from app.extensions import db
from app.models import SOSAlert
from app.models.base import utcnow
from app.utils.timeutils import to_local

ENDED_STATUSES = ("resolved", "cancelled")
STALE_AFTER_SECONDS = 300      # no update for 5 minutes: the viewer is warned


class TooManyAlerts(Exception):
    """The person started too many alerts in the last hour."""


class AlertEnded(Exception):
    """The alert is no longer live, so it can not be updated."""


# ---------- checking input ----------

def _number(value, name, low, high):
    if value is None or isinstance(value, (bool, str)):
        raise ValueError(f"{name} must be a number.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number.")
    if not math.isfinite(number) or not low <= number <= high:
        raise ValueError(f"{name} must be between {low:g} and {high:g}.")
    return number


def validate_position(latitude, longitude, accuracy=None):
    """(latitude, longitude, accuracy) as floats. Raises ValueError for anything unusable."""
    lat = _number(latitude, "latitude", -90, 90)
    lon = _number(longitude, "longitude", -180, 180)
    acc = None if accuracy is None else _number(accuracy, "accuracy", 0, 100000)
    return lat, lon, acc


# ---------- alert life cycle ----------

def is_live(alert, now=None):
    """Active and not past its expiry time."""
    now = now or utcnow()
    return alert.status == "active" and (alert.expires_at is None or now < alert.expires_at)


def get_live_alert(user):
    now = utcnow()
    return (
        SOSAlert.query
        .filter(SOSAlert.user_id == user.id, SOSAlert.status == "active",
                or_(SOSAlert.expires_at.is_(None), SOSAlert.expires_at > now))
        .order_by(SOSAlert.id.desc())
        .first()
    )


def get_owned_alert(user, alert_id):
    """An alert, but only if it belongs to this user."""
    return SOSAlert.query.filter_by(id=alert_id, user_id=user.id).first()


def get_alert_by_token(token):
    return SOSAlert.query.filter_by(share_token=str(token)[:64]).first()


def _move(alert, lat, lon, accuracy):
    alert.latitude = lat
    alert.longitude = lon
    alert.accuracy_m = accuracy
    alert.updated_at = utcnow()           # set by hand: identical coordinates still count as an update


def _scrub(alert):
    """Erase the saved location (the columns can not be empty, so 0, 0 means 'erased').

    Returns True if something was erased, False if it had been erased already.
    """
    if alert.latitude == 0.0 and alert.longitude == 0.0 and alert.accuracy_m is None:
        return False
    alert.latitude = 0.0
    alert.longitude = 0.0
    alert.accuracy_m = None
    return True


def start_alert(user, latitude, longitude, accuracy=None):
    """Start an SOS and return (alert, created).

    If the user already has a live alert it is reused (and moved to the new position), so one
    person never has two different live links. Raises ValueError for a bad position and
    TooManyAlerts after too many alerts in an hour.
    """
    lat, lon, acc = validate_position(latitude, longitude, accuracy)

    existing = get_live_alert(user)
    if existing is not None:
        _move(existing, lat, lon, acc)
        db.session.commit()
        return existing, False

    limit = current_app.config.get("SOS_MAX_PER_HOUR", 5)
    recent = SOSAlert.query.filter(
        SOSAlert.user_id == user.id, SOSAlert.created_at >= utcnow() - timedelta(hours=1)
    ).count()
    if recent >= limit:
        raise TooManyAlerts()

    minutes = current_app.config.get("SOS_DURATION_MINUTES", 240)
    alert = SOSAlert(
        user_id=user.id, latitude=lat, longitude=lon, accuracy_m=acc,
        expires_at=utcnow() + timedelta(minutes=minutes),
    )
    db.session.add(alert)
    db.session.commit()
    return alert, True


def update_location(alert, latitude, longitude, accuracy=None):
    lat, lon, acc = validate_position(latitude, longitude, accuracy)
    if not is_live(alert):
        raise AlertEnded()
    _move(alert, lat, lon, acc)
    db.session.commit()
    return alert


def end_alert(alert, status="resolved"):
    """Stop sharing and erase the saved location. An alert that has already ended is left alone."""
    if status not in ENDED_STATUSES:
        raise ValueError("status must be 'resolved' or 'cancelled'.")
    if alert.status == "active":
        alert.status = status
        alert.resolved_at = utcnow()
        _scrub(alert)
        db.session.commit()
    return alert


def purge_old_alerts(keep_days=30):
    """Erase the saved location of every alert that is no longer live, and delete old alerts.

    An alert that is not live has ended or expired. Alerts that are still live are never
    touched. Returns (erased, deleted).
    """
    if keep_days < 1:
        raise ValueError("keep_days must be at least 1.")
    now = utcnow()
    not_live = or_(SOSAlert.status != "active", SOSAlert.expires_at <= now)

    erased = 0
    for alert in SOSAlert.query.filter(not_live).all():
        if _scrub(alert):
            erased += 1

    cutoff = now - timedelta(days=keep_days)
    deleted = SOSAlert.query.filter(not_live, SOSAlert.created_at < cutoff).delete(synchronize_session=False)
    db.session.commit()
    return erased, int(deleted)


# ---------- the link and the message ----------

def share_url(alert):
    """The link people open. PUBLIC_BASE_URL (for a deployed site or a tunnel) wins if it is set."""
    base = (current_app.config.get("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if base.startswith(("http://", "https://")):
        return base + url_for("share.live", token=alert.share_token)
    return url_for("share.live", token=alert.share_token, _external=True)


def is_local_address():
    """True when the app is reached through an address that people outside can not open."""
    base = (current_app.config.get("PUBLIC_BASE_URL") or "").strip()
    if base.startswith(("http://", "https://")):
        return False
    host = request.host.split(":")[0].strip("[]").lower()
    if host == "localhost" or host.endswith(".local"):
        return True
    try:
        return ip_address(host).is_private
    except ValueError:
        return False


def share_message(user, url):
    return (f"{user.full_name} started an SOS in SafeRadar AI and may need help. "
            f"Live location: {url} If you cannot reach them, call 112.")


def whatsapp_number(phone):
    """Digits only, with a country code. A 10-digit number is taken to be Indian (+91)."""
    text = str(phone or "").strip()
    digits = re.sub(r"\D", "", text)
    if text.startswith("+"):
        return digits
    digits = digits.lstrip("0")
    return "91" + digits if len(digits) == 10 else digits


def contact_links(user, message):
    """Ready-made 'text' and 'WhatsApp' links for each trusted contact. Nothing is sent by us."""
    text = quote(message, safe="")
    return [
        {
            "name": contact.name,
            "relation": contact.relationship_label,
            "sms": f"sms:{contact.phone}?body={text}",
            "whatsapp": f"https://wa.me/{whatsapp_number(contact.phone)}?text={text}",
        }
        for contact in user.contacts
    ]


def alert_view(user, alert):
    """What the owner's SOS page needs about a live alert."""
    url = share_url(alert)
    message = share_message(user, url)
    return {
        "id": alert.id,
        "share_url": url,
        "message": message,
        "contacts": contact_links(user, message),
        "expires": to_local(alert.expires_at).strftime("%I:%M %p, %d %b") if alert.expires_at else None,
        "updated": to_local(alert.updated_at).strftime("%I:%M:%S %p"),
    }


def public_view(alert, now=None):
    """What anyone with the link may see. The location is included only while the alert is live."""
    now = now or utcnow()
    name = (alert.user.full_name.split() or ["Someone"])[0] if alert.user else "Someone"

    if not is_live(alert, now):
        state = alert.status if alert.status in ENDED_STATUSES else "expired"
        return {"name": name, "live": False, "state": state}

    seconds_ago = max(0, int((now - alert.updated_at).total_seconds()))
    return {
        "name": name,
        "live": True,
        "state": "live",
        "latitude": round(alert.latitude, 5),
        "longitude": round(alert.longitude, 5),
        "accuracy_m": alert.accuracy_m,
        "updated_text": to_local(alert.updated_at).strftime("%I:%M:%S %p"),
        "seconds_ago": seconds_ago,
        "stale": seconds_ago > STALE_AFTER_SECONDS,
    }