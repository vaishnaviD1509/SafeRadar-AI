// Route planner: pick a start and an end on the map, then compare routes by travel time and by
// the risk model's estimates. All text is built with textContent, so data can never inject HTML.
document.addEventListener("DOMContentLoaded", function () {
  var element = document.getElementById("route-map");
  if (!element) { return; }

  if (typeof L === "undefined") {
    element.textContent = "The map could not be loaded. Check your internet connection.";
    return;
  }

  var center = JSON.parse(element.dataset.center);
  var zoom = parseInt(element.dataset.zoom, 10);
  var routeUrl = element.dataset.routeUrl;
  var gridUrl = element.dataset.gridUrl;

  var pickStartButton = document.getElementById("pick-start");
  var pickEndButton = document.getElementById("pick-end");
  var locationButton = document.getElementById("use-location");
  var clearButton = document.getElementById("clear-points");
  var findButton = document.getElementById("find-routes");
  var departInput = document.getElementById("depart");
  var showRisk = document.getElementById("show-risk");
  var statusEl = document.getElementById("route-status");
  var adviceEl = document.getElementById("route-advice");
  var resultsEl = document.getElementById("route-results");
  var disclaimerEl = document.getElementById("route-disclaimer");
  var travelNote = document.getElementById("travel-note");

  var ROUTE_COLORS = ["#6d28d9", "#0f1b3d", "#db2777"];
  var LEVEL_COLORS = { Low: "#2e9e5b", Moderate: "#e0a800", High: "#c62828" };

  var map = L.map(element).setView(center, zoom);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(map);

  var riskLayer = L.featureGroup().addTo(map);
  var routeLayer = L.featureGroup().addTo(map);
  var pointLayer = L.featureGroup().addTo(map);

  var start = null;
  var end = null;
  var picking = "start";
  var polylines = [];
  var cards = [];
  var requestId = 0;

  // ---------- start and end points ----------
  function drawPoints() {
    pointLayer.clearLayers();
    [["Start", start, "#0f1b3d"], ["End", end, "#db2777"]].forEach(function (item) {
      if (!item[1]) { return; }
      L.circleMarker([item[1].lat, item[1].lng], {
        radius: 9, color: "#ffffff", weight: 2, fillColor: item[2], fillOpacity: 1
      }).bindTooltip(item[0], { permanent: true, direction: "top", offset: [0, -8] }).addTo(pointLayer);
    });
  }

  function updateControls() {
    pickStartButton.classList.toggle("active", picking === "start");
    pickEndButton.classList.toggle("active", picking === "end");
    findButton.disabled = !(start && end);
    if (!start) {
      statusEl.textContent = "Click the map to choose your start.";
    } else if (!end) {
      statusEl.textContent = "Now click the map to choose your end.";
    } else {
      statusEl.textContent = "Ready. Press Find routes.";
    }
  }

  function clearResults() {
    requestId += 1;                       // ignore any answer that is still on its way
    routeLayer.clearLayers();
    polylines = [];
    cards = [];
    resultsEl.textContent = "";
    adviceEl.hidden = true;
    disclaimerEl.hidden = true;
    travelNote.hidden = true;
    findButton.textContent = "Find routes";
  }

  function setPoint(kind, latlng, moveMap) {
    var point = { lat: latlng.lat, lng: latlng.lng };
    if (kind === "start") {
      start = point;
      picking = "end";
    } else {
      end = point;
      picking = "start";
    }
    clearResults();
    drawPoints();
    updateControls();
    if (moveMap) { map.setView([point.lat, point.lng], Math.max(map.getZoom(), 15)); }
  }

  map.on("click", function (event) { setPoint(picking, event.latlng, false); });
  pickStartButton.addEventListener("click", function () { picking = "start"; updateControls(); });
  pickEndButton.addEventListener("click", function () { picking = "end"; updateControls(); });

  clearButton.addEventListener("click", function () {
    start = null;
    end = null;
    picking = "start";
    clearResults();
    riskLayer.clearLayers();
    drawPoints();
    updateControls();
  });

  // The browser asks for permission; nothing is read without it.
  locationButton.addEventListener("click", function () {
    if (!navigator.geolocation) {
      statusEl.textContent = "Your browser cannot share your location. Please click the map instead.";
      return;
    }
    statusEl.textContent = "Waiting for your location...";
    navigator.geolocation.getCurrentPosition(
      function (position) {
        setPoint("start", { lat: position.coords.latitude, lng: position.coords.longitude }, true);
      },
      function (error) {
        var messages = {
          1: "Location permission was denied. Please click the map instead.",
          2: "Your location is not available right now. Please click the map instead.",
          3: "Finding your location took too long. Please click the map instead."
        };
        statusEl.textContent = messages[error.code] || "Could not get your location. Please click the map instead.";
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  });

  // ---------- results ----------
  function riskText(risk) {
    if (!risk) { return "Risk not estimated (no risk model yet)."; }
    if (risk.risk_index === null) {
      return "Not enough data to estimate risk (" + risk.coverage_pct + "% of the route covered). Unknown does not mean safe.";
    }
    return "Relative risk index " + risk.risk_index + " / 100, based on " + risk.coverage_pct + "% of the route.";
  }

  function mixText(risk) {
    return "High " + risk.high_pct + "% \u00B7 Moderate " + risk.moderate_pct + "% \u00B7 Low " +
      risk.low_pct + "% \u00B7 Unknown " + risk.unknown_pct + "%";
  }

  function select(index) {
    polylines.forEach(function (line, i) {
      line.setStyle({ weight: i === index ? 7 : 4, opacity: i === index ? 0.95 : 0.55 });
      if (i === index) { line.bringToFront(); }
    });
    cards.forEach(function (card, i) {
      card.classList.toggle("selected", i === index);
      card.setAttribute("aria-pressed", i === index ? "true" : "false");
    });
  }

  function addBadge(parent, text, className) {
    var badge = document.createElement("span");
    badge.className = "badge ms-1 " + className;
    badge.textContent = text;
    parent.appendChild(badge);
  }

  function buildCard(route, index, color, modeName, suggested) {
    var card = document.createElement("div");
    card.className = "sr-route-card";
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.setAttribute("aria-pressed", "false");

    var head = document.createElement("div");
    var dot = document.createElement("span");
    dot.className = "sr-route-dot";
    dot.style.background = color;
    var title = document.createElement("strong");
    title.textContent = "Route " + route.id;
    head.appendChild(dot);
    head.appendChild(title);
    if (suggested) { addBadge(head, "Suggested", "text-bg-success"); }
    route.labels.forEach(function (label) { addBadge(head, label, "sr-badge"); });
    card.appendChild(head);

    var trip = document.createElement("div");
    trip.className = "small";
    trip.textContent = route.distance_km + " km \u00B7 about " + route.duration_min + " min (" + modeName + ")";
    card.appendChild(trip);

    var risk = document.createElement("div");
    risk.className = "small";
    risk.textContent = riskText(route.risk);
    card.appendChild(risk);

    if (route.risk) {
      var mix = document.createElement("div");
      mix.className = "small text-muted";
      mix.textContent = mixText(route.risk);
      card.appendChild(mix);
    }

    card.addEventListener("click", function () { select(index); });
    card.addEventListener("keydown", function (event) {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        select(index);
      }
    });
    return card;
  }

  function indexOfRoute(routes, id) {
    for (var i = 0; i < routes.length; i++) {
      if (routes[i].id === id) { return i; }
    }
    return -1;
  }

  function loadGrid(slotIndex, isWeekend) {
    fetch(gridUrl + "?slot=" + encodeURIComponent(slotIndex) + "&weekend=" + (isWeekend ? 1 : 0), {
      credentials: "same-origin", headers: { "Accept": "application/json" }
    })
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (body) {
        riskLayer.clearLayers();
        if (!body) { return; }
        body.cells.forEach(function (cell) {
          var color = LEVEL_COLORS[cell.level] || "#9ca3af";
          L.rectangle([[cell.south, cell.west], [cell.north, cell.east]], {
            color: color, weight: 1, fillColor: color, fillOpacity: 0.22, interactive: false
          }).addTo(riskLayer);
        });
        routeLayer.bringToFront();
        pointLayer.bringToFront();
      })
      .catch(function () { riskLayer.clearLayers(); });
  }

  function showRoutes(body) {
    var modeName = body.travel_mode === "foot" ? "walking" : body.travel_mode;
    var recommendation = body.recommendation;

    body.routes.forEach(function (route, index) {
      var color = ROUTE_COLORS[index % ROUTE_COLORS.length];
      polylines.push(L.polyline(route.geometry, { color: color, weight: 4, opacity: 0.6 }).addTo(routeLayer));
      var card = buildCard(route, index, color, modeName, route.id === recommendation.lowest_risk_id);
      cards.push(card);
      resultsEl.appendChild(card);
    });

    var chosen = indexOfRoute(body.routes, recommendation.lowest_risk_id);
    if (chosen < 0) { chosen = indexOfRoute(body.routes, recommendation.fastest_id); }
    select(Math.max(chosen, 0));

    // Green for a clear difference, yellow for a small one, blue when nothing can be suggested.
    var tone = recommendation.confidence === "clear" ? "alert-success"
      : (recommendation.confidence === "slight" ? "alert-warning" : "alert-info");
    adviceEl.className = "alert small " + tone;
    adviceEl.textContent = recommendation.message;
    adviceEl.hidden = false;
    disclaimerEl.textContent = body.risk_model ? body.disclaimer : "";
    disclaimerEl.hidden = !body.risk_model;

    if (body.travel_mode !== "foot") {
      travelNote.textContent = "Times are for " + modeName + ": the routing server in use offers car routes. " +
        "Use the comparison for the road choice and your own judgement on foot.";
      travelNote.hidden = false;
    }

    map.fitBounds(routeLayer.getBounds(), { padding: [30, 30] });
    statusEl.textContent = body.routes.length + " route" + (body.routes.length === 1 ? "" : "s") +
      " found for " + body.slot.toLowerCase() + " (" + body.slot_hours + "), " +
      (body.is_weekend ? "weekend" : "weekday") + ".";
    findButton.textContent = "Find routes again";

    if (body.risk_model) { loadGrid(body.slot_index, body.is_weekend); }
  }

  function findRoutes() {
    if (!start || !end) { return; }
    clearResults();
    var mine = requestId;
    var url = routeUrl + "?from_lat=" + start.lat.toFixed(6) + "&from_lon=" + start.lng.toFixed(6) +
      "&to_lat=" + end.lat.toFixed(6) + "&to_lon=" + end.lng.toFixed(6);
    if (departInput.value) { url += "&when=" + encodeURIComponent(departInput.value); }

    findButton.disabled = true;
    statusEl.textContent = "Finding routes...";

    fetch(url, { credentials: "same-origin", headers: { "Accept": "application/json" } })
      .then(function (response) {
        return response.json().then(function (body) {
          return { ok: response.ok, code: response.status, body: body };
        });
      })
      .then(function (result) {
        if (mine !== requestId) { return; }
        findButton.disabled = false;
        if (!result.ok) {
          statusEl.textContent = result.code === 401
            ? "Please log in again to plan a route."
            : (result.body.message || result.body.error || "Could not find routes.");
          return;
        }
        showRoutes(result.body);
      })
      .catch(function () {
        if (mine !== requestId) { return; }
        findButton.disabled = false;
        statusEl.textContent = "Could not find routes. Check your connection and try again.";
      });
  }

  findButton.addEventListener("click", findRoutes);
  showRisk.addEventListener("change", function () {
    if (showRisk.checked) { map.addLayer(riskLayer); } else { map.removeLayer(riskLayer); }
  });

  updateControls();
});