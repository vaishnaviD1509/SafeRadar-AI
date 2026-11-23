// Emergency SOS page: starts an alert, keeps sending the position while the page is open, and
// shows buttons to send the private link. All text is built with textContent, so data can never
// inject HTML. Nothing here sends a message: the buttons only open the person's own messaging app.
document.addEventListener("DOMContentLoaded", function () {
  var root = document.getElementById("sos-app");
  if (!root) { return; }

  var csrf = root.dataset.csrf;
  var startUrl = root.dataset.startUrl;                 // like /sos/start
  var SEND_EVERY_MS = 15000;

  var idlePanel = document.getElementById("sos-idle");
  var activePanel = document.getElementById("sos-active");
  var startButton = document.getElementById("sos-start");
  var statusEl = document.getElementById("sos-status");
  var linkInput = document.getElementById("sos-link");
  var copyButton = document.getElementById("sos-copy");
  var contactsEl = document.getElementById("sos-contacts");
  var shareButton = document.getElementById("sos-native-share");
  var expiresEl = document.getElementById("sos-expires");
  var updatedEl = document.getElementById("sos-updated");
  var stopButton = document.getElementById("sos-stop");
  var cancelButton = document.getElementById("sos-cancel");

  var current = null;         // the live alert, as sent by the server
  var watchId = null;
  var lastSent = 0;

  function urlFor(action) {
    return startUrl.replace(/\/start$/, "/" + current.id + "/" + action);
  }

  function post(url, body) {
    return fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "Accept": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify(body || {})
    }).then(function (response) {
      return response.json().then(function (data) {
        return { ok: response.ok, code: response.status, body: data };
      });
    });
  }

  function positionBody(position) {
    return {
      latitude: position.coords.latitude,
      longitude: position.coords.longitude,
      accuracy: position.coords.accuracy
    };
  }

  function locationProblem(error) {
    var messages = {
      1: "Location permission was denied. Allow it in your browser settings, or call 112.",
      2: "Your location is not available right now. Try again, or call 112.",
      3: "Finding your location took too long. Try again, or call 112."
    };
    return messages[error.code] || "Could not get your location. Try again, or call 112.";
  }

  // ---------- panels ----------
  function showIdle(message) {
    stopWatching();
    current = null;
    activePanel.hidden = true;
    idlePanel.hidden = false;
    startButton.disabled = false;
    statusEl.textContent = message || "";
  }

  function safeHref(value, prefix) {
    return (typeof value === "string" && value.indexOf(prefix) === 0) ? value : null;
  }

  function addLink(parent, text, href) {
    if (!href) { return; }
    var link = document.createElement("a");
    link.className = "btn btn-sm sr-btn-outline-dark";
    link.textContent = text;
    link.href = href;
    link.rel = "noopener noreferrer";
    parent.appendChild(link);
  }

  function renderContacts(contacts) {
    contactsEl.textContent = "";
    if (!contacts.length) {
      var none = document.createElement("p");
      none.className = "small";
      none.textContent = "You have no trusted contacts saved. Copy the link and send it yourself.";
      contactsEl.appendChild(none);
      return;
    }
    contacts.forEach(function (contact) {
      var row = document.createElement("div");
      row.className = "sr-contact-actions";
      var name = document.createElement("strong");
      name.textContent = contact.name + (contact.relation ? " (" + contact.relation + ")" : "");
      row.appendChild(name);
      addLink(row, "Text", safeHref(contact.sms, "sms:"));
      addLink(row, "WhatsApp", safeHref(contact.whatsapp, "https://wa.me/"));
      contactsEl.appendChild(row);
    });
  }

  function showActive(view) {
    current = view;
    idlePanel.hidden = true;
    activePanel.hidden = false;
    linkInput.value = view.share_url;
    expiresEl.textContent = view.expires ? " (or until " + view.expires + ")" : "";
    updatedEl.textContent = "Your location was last sent at " + view.updated + ".";
    renderContacts(view.contacts);
    shareButton.hidden = !navigator.share;
  }

  // ---------- keeping the position fresh ----------
  function onPosition(position) {
    if (!current) { return; }
    var now = Date.now();
    if (now - lastSent < SEND_EVERY_MS) { return; }
    lastSent = now;
    var mine = current.id;
    post(urlFor("update"), positionBody(position))
      .then(function (result) {
        if (!current || current.id !== mine) { return; }
        if (result.ok) {
          updatedEl.textContent = "Your location was last sent at " + result.body.updated + ".";
        } else if (result.code === 409) {
          showIdle("This SOS has ended, so your location is no longer shared.");
        } else {
          updatedEl.textContent = "Could not send your location just now. Trying again soon.";
        }
      })
      .catch(function () {
        updatedEl.textContent = "Could not send your location just now. Check your connection. Trying again soon.";
      });
  }

  function onWatchError(error) {
    updatedEl.textContent = locationProblem(error);
  }

  function startWatching() {
    if (!navigator.geolocation || watchId !== null) { return; }
    watchId = navigator.geolocation.watchPosition(onPosition, onWatchError,
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 20000 });
  }

  function stopWatching() {
    if (watchId !== null && navigator.geolocation) { navigator.geolocation.clearWatch(watchId); }
    watchId = null;
  }

  // ---------- buttons ----------
  startButton.addEventListener("click", function () {
    if (!navigator.geolocation) {
      statusEl.textContent = "Your browser cannot share your location. Call 112.";
      return;
    }
    startButton.disabled = true;
    statusEl.textContent = "Getting your location...";
    navigator.geolocation.getCurrentPosition(
      function (position) {
        post(startUrl, positionBody(position))
          .then(function (result) {
            if (!result.ok) {
              startButton.disabled = false;
              statusEl.textContent = (result.body && result.body.error) || "Could not start SOS. Call 112.";
              return;
            }
            statusEl.textContent = "";
            lastSent = Date.now();
            showActive(result.body.alert);
            startWatching();
          })
          .catch(function () {
            startButton.disabled = false;
            statusEl.textContent = "Could not start SOS. Check your connection, or call 112.";
          });
      },
      function (error) {
        startButton.disabled = false;
        statusEl.textContent = locationProblem(error);
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
    );
  });

  function endAlert(status, message) {
    if (!current) { return; }
    var url = urlFor("end");
    stopWatching();
    post(url, { status: status })
      .then(function (result) {
        if (result.ok) {
          showIdle(message);
        } else {
          startWatching();
          updatedEl.textContent = (result.body && result.body.error) || "Could not stop sharing. Try again.";
        }
      })
      .catch(function () {
        startWatching();
        updatedEl.textContent = "Could not stop sharing. Check your connection and try again.";
      });
  }

  stopButton.addEventListener("click", function () {
    endAlert("resolved", "Sharing stopped. Your link no longer shows your location.");
  });
  cancelButton.addEventListener("click", function () {
    endAlert("cancelled", "SOS cancelled. Your link no longer shows your location.");
  });

  copyButton.addEventListener("click", function () {
    var done = function () { copyButton.textContent = "Copied"; setTimeout(function () { copyButton.textContent = "Copy"; }, 2000); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(linkInput.value).then(done, function () { linkInput.select(); });
    } else {
      linkInput.select();
      try { document.execCommand("copy"); done(); } catch (error) { /* the text stays selected */ }
    }
  });

  shareButton.addEventListener("click", function () {
    if (navigator.share && current) {
      navigator.share({ title: "SOS", text: current.message }).catch(function () { /* cancelled */ });
    }
  });

  // The page was opened while an alert was already live (for example after a reload).
  var existing = JSON.parse(root.dataset.active);
  if (existing) {
    showActive(existing);
    startWatching();
  }
});