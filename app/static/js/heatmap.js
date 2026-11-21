// Draws the safety heatmap: model risk squares plus approved report markers.
// All text shown on the map is built with textContent, so data can never inject HTML.
document.addEventListener("DOMContentLoaded", function () {
  var element = document.getElementById("heatmap");
  if (!element) { return; }

  if (typeof L === "undefined") {
    element.textContent = "The map could not be loaded. Check your internet connection.";
    return;
  }

  var center = JSON.parse(element.dataset.center);
  var zoom = parseInt(element.dataset.zoom, 10);
  var markers = JSON.parse(element.dataset.markers);
  var gridUrl = element.dataset.gridUrl;
  var modelReady = element.dataset.modelReady === "1";

  var slotSelect = document.getElementById("slot-select");
  var daySelect = document.getElementById("day-select");
  var showRisk = document.getElementById("show-risk");
  var showMarkers = document.getElementById("show-markers");
  var status = document.getElementById("heatmap-status");
  var syntheticNote = document.getElementById("synthetic-note");

  var LEVEL_COLORS = { Low: "#2e9e5b", Moderate: "#e0a800", High: "#c62828" };

  var map = L.map(element).setView(center, zoom);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(map);

  var riskLayer = L.featureGroup().addTo(map);
  var markerLayer = L.layerGroup().addTo(map);

  // ---------- report markers ----------
  function severityColor(severity) {
    if (severity <= 2) { return LEVEL_COLORS.Low; }
    if (severity === 3) { return LEVEL_COLORS.Moderate; }
    return LEVEL_COLORS.High;
  }

  markers.forEach(function (item) {
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
      radius: 6, color: "#0f1b3d", weight: 1.5,
      fillColor: severityColor(item.severity), fillOpacity: 0.9
    }).bindPopup(popup).addTo(markerLayer);
  });

  // ---------- risk squares ----------
  function tooltipFor(cell) {
    var tip = document.createElement("div");
    var head = document.createElement("strong");
    head.textContent = cell.level + " relative risk";
    var detail = document.createElement("div");
    detail.textContent = ["High", "Moderate", "Low"].map(function (name) {
      return name + " " + Math.round((cell.probabilities[name] || 0) * 100) + "%";
    }).join(" \u00B7 ");
    var caution = document.createElement("em");
    caution.textContent = "A model estimate. Low does not mean safe.";
    tip.appendChild(head);
    tip.appendChild(detail);
    tip.appendChild(caution);
    return tip;
  }

  var requestId = 0;
  var fitted = false;

  function loadGrid() {
    var mine = ++requestId;
    status.textContent = "Loading risk estimates...";
    var url = gridUrl + "?slot=" + encodeURIComponent(slotSelect.value) +
              "&weekend=" + encodeURIComponent(daySelect.value);

    fetch(url, { credentials: "same-origin", headers: { "Accept": "application/json" } })
      .then(function (response) {
        return response.json().then(function (body) {
          return { ok: response.ok, code: response.status, body: body };
        });
      })
      .then(function (result) {
        if (mine !== requestId) { return; }   // a newer choice replaced this one
        riskLayer.clearLayers();

        if (!result.ok) {
          status.textContent = result.code === 401
            ? "Please log in again to see risk estimates."
            : (result.body.message || result.body.error || "Could not load risk estimates.");
          return;
        }

        var body = result.body;
        body.cells.forEach(function (cell) {
          var color = LEVEL_COLORS[cell.level] || "#9ca3af";
          L.rectangle([[cell.south, cell.west], [cell.north, cell.east]], {
            color: color, weight: 1, fillColor: color, fillOpacity: 0.35
          }).bindTooltip(tooltipFor(cell), { sticky: true }).addTo(riskLayer);
        });

        syntheticNote.hidden = !body.synthetic;
        if (!body.cells.length) {
          status.textContent = "No area has enough reports for an estimate. Unknown does not mean safe.";
          return;
        }
        status.textContent = body.slot + " (" + body.slot_hours + "), " +
          (body.is_weekend ? "weekends" : "weekdays") + ": " + body.cells.length +
          " areas coloured (" + body.counts.High + " high, " + body.counts.Moderate +
          " moderate, " + body.counts.Low + " low). Uncoloured areas are unknown.";

        if (!fitted) {
          map.fitBounds(riskLayer.getBounds(), { maxZoom: 15, padding: [20, 20] });
          fitted = true;
        }
      })
      .catch(function () {
        if (mine !== requestId) { return; }
        riskLayer.clearLayers();
        status.textContent = "Could not load risk estimates. Check your connection and try again.";
      });
  }

  // ---------- controls ----------
  showRisk.addEventListener("change", function () {
    if (showRisk.checked) { map.addLayer(riskLayer); } else { map.removeLayer(riskLayer); }
  });
  showMarkers.addEventListener("change", function () {
    if (showMarkers.checked) { map.addLayer(markerLayer); } else { map.removeLayer(markerLayer); }
  });
  slotSelect.addEventListener("change", loadGrid);
  daySelect.addEventListener("change", loadGrid);

  if (modelReady) { loadGrid(); }
});