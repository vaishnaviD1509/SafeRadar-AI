from urllib.parse import urljoin, urlparse

from flask import request


def is_safe_redirect_url(target):
    """True only if `target` points back to this same site.
    Stops attackers using /login?next=https://evil.com (open redirect)."""
    if not target:
        return False
    host_url = urlparse(request.host_url)
    redirect_url = urlparse(urljoin(request.host_url, target))
    return redirect_url.scheme in ("http", "https") and host_url.netloc == redirect_url.netloc