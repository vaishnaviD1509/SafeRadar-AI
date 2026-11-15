// Draws the small map on the dashboard. Data comes from data-* attributes
// that Flask fills in, so no personal details are hard-coded in this file.
document.addEventListener("DOMContentLoaded", function () {
  var element = document.getElementById("map-preview");
  if (!element) { return; }

  if (typeof L === "undefined") {
    element.textContent = "The map could not be loaded. Check your internet connection.";
    return;
  }

  var center = JSON.parse(element.dataset.center);
  var zoom = parseInt(element.dataset.zoom, 10);
  var markers = JSON.parse(element.dataset.markers);

  var map = L.map(element, { scrollWheelZoom: false }).setView(center, zoom);

  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(map);

  markers.forEach(function (item) {
    // Popup text is built with textContent, so report data can never inject HTML.
    var popup = document.createElement("div");
    var title = document.createElement("strong");
    title.textContent = item.category;
    var detail = document.createElement("div");
    detail.textContent = "Severity " + item.severity + "/5 \u00B7 " + item.date;
    popup.appendChild(title);
    popup.appendChild(detail);
    if (item.synthetic) {
      var note = document.createElement("em");
      note.textContent = "Synthetic demo data";
      popup.appendChild(note);
    }

    L.circleMarker([item.lat, item.lng], {
      radius: 8, color: "#6d28d9", weight: 2, fillColor: "#f9a8d4", fillOpacity: 0.8
    }).bindPopup(popup).addTo(map);
  });
});