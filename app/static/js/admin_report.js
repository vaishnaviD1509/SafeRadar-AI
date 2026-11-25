// Small map on the report review page: shows where the report says it happened.
document.addEventListener("DOMContentLoaded", function () {
  var element = document.getElementById("review-map");
  if (!element) { return; }

  if (typeof L === "undefined") {
    element.textContent = "The map could not be loaded. Check your internet connection.";
    return;
  }

  var lat = parseFloat(element.dataset.lat);
  var lng = parseFloat(element.dataset.lng);
  if (isNaN(lat) || isNaN(lng)) { return; }

  var map = L.map(element).setView([lat, lng], 16);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(map);

  L.circleMarker([lat, lng], {
    radius: 10, color: "#6d28d9", weight: 3, fillColor: "#f9a8d4", fillOpacity: 0.9
  }).addTo(map);
});