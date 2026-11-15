// Location picker and character counter for the report form.
// The chosen point is written into two hidden inputs, which Flask validates.
document.addEventListener("DOMContentLoaded", function () {
  var description = document.getElementById("description");
  var counter = document.getElementById("char-count");
  if (description && counter) {
    var updateCount = function () { counter.textContent = description.value.length; };
    description.addEventListener("input", updateCount);
    updateCount();
  }

  var mapElement = document.getElementById("pick-map");
  if (!mapElement) { return; }

  if (typeof L === "undefined") {
    mapElement.textContent = "The map could not be loaded. Check your internet connection.";
    return;
  }

  var latInput = document.getElementById("latitude");
  var lngInput = document.getElementById("longitude");
  var status = document.getElementById("pick-status");
  var locateButton = document.getElementById("use-location");
  var pickErrors = document.getElementById("pick-errors");

  var center = JSON.parse(mapElement.dataset.center);
  var zoom = parseInt(mapElement.dataset.zoom, 10);
  var map = L.map(mapElement).setView(center, zoom);

  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(map);

  var pin = null;

  function setPoint(lat, lng, moveMap) {
    latInput.value = lat.toFixed(6);
    lngInput.value = lng.toFixed(6);
    if (pin) {
      pin.setLatLng([lat, lng]);
    } else {
      pin = L.circleMarker([lat, lng], {
        radius: 10, color: "#6d28d9", weight: 3, fillColor: "#f9a8d4", fillOpacity: 0.9
      }).addTo(map);
    }
    status.textContent = "Chosen: " + lat.toFixed(5) + ", " + lng.toFixed(5);
    if (pickErrors) { pickErrors.style.display = "none"; }  // the problem is fixed
    if (moveMap) { map.setView([lat, lng], Math.max(map.getZoom(), 16)); }
  }

  map.on("click", function (event) {
    setPoint(event.latlng.lat, event.latlng.lng, false);
  });

  // Keep the pin if the page is shown again after a validation error.
  var savedLat = parseFloat(mapElement.dataset.lat);
  var savedLng = parseFloat(mapElement.dataset.lng);
  if (!isNaN(savedLat) && !isNaN(savedLng)) {
    setPoint(savedLat, savedLng, true);
  }

  // The browser asks the user for permission; nothing is read without it.
  locateButton.addEventListener("click", function () {
    if (!navigator.geolocation) {
      status.textContent = "Your browser cannot share your location. Please click the map instead.";
      return;
    }
    status.textContent = "Waiting for your location...";
    navigator.geolocation.getCurrentPosition(
      function (position) {
        setPoint(position.coords.latitude, position.coords.longitude, true);
      },
      function (error) {
        var messages = {
          1: "Location permission was denied. Please click the map instead.",
          2: "Your location is not available right now. Please click the map instead.",
          3: "Finding your location took too long. Please click the map instead."
        };
        status.textContent = messages[error.code] || "Could not get your location. Please click the map instead.";
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  });
});