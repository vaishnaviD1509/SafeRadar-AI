// Public page that people open from the SOS link: shows the latest location while it is shared
// and checks for a newer one every 10 seconds. All text uses textContent.
document.addEventListener("DOMContentLoaded", function () {
  var root = document.getElementById("share-app");
  if (!root) { return; }

  var state = JSON.parse(root.dataset.state);
  var stateUrl = root.dataset.stateUrl;
  var REFRESH_MS = 10000;

  var banner = document.getElementById("share-banner");
  var title = document.getElementById("share-title");
  var message = document.getElementById("share-message");
  var liveBox = document.getElementById("share-live");
  var mapEl = document.getElementById("share-map");
  var coords = document.getElementById("share-coords");
  var updated = document.getElementById("share-updated");
  var stale = document.getElementById("share-stale");
  var geoLink = document.getElementById("share-geo");
  var osmLink = document.getElementById("share-osm");
  var refreshNote = document.getElementById("share-refresh");

  var map = null;
  var marker = null;
  var circle = null;
  var timer = null;

  function endedText(s) {
    if (s.state === "expired") { return "This SOS link has expired. This link no longer shows any location."; }
    if (s.state === "cancelled") {
      return s.name + " cancelled this SOS; it may have been started by mistake. This link no longer shows any location.";
    }
    return s.name + " stopped sharing their location. This link no longer shows any location.";
  }

  function drawMap(s) {
    if (typeof L === "undefined") {
      mapEl.textContent = "The map could not be loaded. Use the coordinates or the links below.";
      return;
    }
    var point = [s.latitude, s.longitude];
    if (!map) {
      map = L.map(mapEl).setView(point, 16);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
      }).addTo(map);
      marker = L.circleMarker(point, {
        radius: 10, color: "#ffffff", weight: 3, fillColor: "#dc2626", fillOpacity: 1
      }).addTo(map);
    } else {
      marker.setLatLng(point);
      map.setView(point, map.getZoom());
    }
    if (circle) { map.removeLayer(circle); circle = null; }
    if (s.accuracy_m !== null && s.accuracy_m !== undefined && s.accuracy_m > 0) {
      circle = L.circle(point, {
        radius: Math.min(s.accuracy_m, 500), color: "#dc2626", weight: 1, fillOpacity: 0.12
      }).addTo(map);
    }
  }

  function apply(next) {
    state = next;
    if (state.live) {
      banner.classList.remove("ended");
      title.textContent = state.name + " started an SOS";
      message.textContent = "Their live location is shown below. If you think they may be in danger, " +
        "try to call them, and call 112 if needed.";
      liveBox.hidden = false;
      coords.textContent = state.latitude.toFixed(5) + ", " + state.longitude.toFixed(5) +
        ((state.accuracy_m !== null && state.accuracy_m !== undefined)
          ? " (accuracy about " + Math.round(state.accuracy_m) + " m)" : "");
      updated.textContent = state.updated_text;
      stale.hidden = !state.stale;
      geoLink.href = "geo:" + state.latitude + "," + state.longitude;
      osmLink.href = "https://www.openstreetmap.org/?mlat=" + state.latitude + "&mlon=" + state.longitude +
        "#map=17/" + state.latitude + "/" + state.longitude;
      drawMap(state);
    } else {
      banner.classList.add("ended");
      title.textContent = "This SOS has ended";
      message.textContent = endedText(state);
      liveBox.hidden = true;
      stale.hidden = true;
      refreshNote.textContent = "";
      if (timer) { clearInterval(timer); timer = null; }
    }
  }

  function refresh() {
    fetch(stateUrl, { cache: "no-store", headers: { "Accept": "application/json" } })
      .then(function (response) {
        if (response.status === 404) { return { name: state.name, live: false, state: "resolved" }; }
        if (!response.ok) { throw new Error("bad answer"); }
        return response.json();
      })
      .then(function (next) {
        refreshNote.textContent = "";
        apply(next);
      })
      .catch(function () {
        refreshNote.textContent = "Could not refresh just now. Trying again...";
      });
  }

  apply(state);
  if (state.live) { timer = setInterval(refresh, REFRESH_MS); }
});