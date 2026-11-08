/* Find a therapist (FR 3.1, FR 3.2).
 * - Location from the W3C Geolocation API, or a typed place name (geocoded by our server).
 * - Every network call times out after 5 s (SRS 3.4).
 * - The map (Leaflet) loads only when needed. If it doesn't load within 5 s,
 *   results are shown as a list only (sequence diagram, steps 31-33).
 */
(function () {
  "use strict";
  var cfg = window.AUTISMCARE;
  var TIMEOUT_MS = 5000;
  var LEAFLET_JS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js";
  var LEAFLET_CSS = "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css";

  var $ = function (id) { return document.getElementById(id); };
  var state = { lat: null, lng: null, source: null, place: "" };
  var map = null, markerLayer = null, mapFailed = false;

  // ---------- helpers ----------
  function fetchJSON(url) {
    var ctrl = new AbortController();
    var timer = setTimeout(function () { ctrl.abort(); }, TIMEOUT_MS);
    return fetch(url, { signal: ctrl.signal, headers: { Accept: "application/json" } })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (body) {
          if (!r.ok) throw new Error(body.detail || "Something went wrong. Please try again.");
          return body;
        });
      })
      .catch(function (e) {
        if (e.name === "AbortError") throw new Error("The connection is slow. Please try again.");
        throw e;
      })
      .finally(function () { clearTimeout(timer); });
  }

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "text") node.textContent = attrs[k];
      else if (k === "className") node.className = attrs[k];
      else node.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) { if (c) node.appendChild(c); });
    return node;
  }

  function showError(msg) {
    var box = $("search-error");
    box.textContent = msg;
    box.hidden = !msg;
  }

  function setStatus(msg) { $("location-status").textContent = msg; }

  // ---------- filter options ----------
  function fillSelect(select, items) {
    items.forEach(function (it) {
      var value = typeof it === "string" ? it : it.value;
      var label = typeof it === "string" ? it : it.label;
      select.appendChild(el("option", { value: value, text: label }));
    });
  }

  fetchJSON(cfg.filterUrl).then(function (opts) {
    fillSelect($("specialization"), opts.specializations);
    fillSelect($("insurance"), opts.insurance_providers);
    fillSelect($("mode"), opts.modes);
  }).catch(function () { /* filters stay at "Any" */ });

  // ---------- location ----------
  $("radius").addEventListener("input", function () { $("radius-value").textContent = this.value; });

  $("use-location").addEventListener("click", function () {
    if (!navigator.geolocation) {
      setStatus("Your browser can't share its location. Type a town instead.");
      return;
    }
    setStatus("Finding your location…");
    navigator.geolocation.getCurrentPosition(
      function (pos) {
        state.lat = pos.coords.latitude;
        state.lng = pos.coords.longitude;
        state.source = "gps";
        $("place").value = "";
        setStatus("Using your current location.");
      },
      function () {
        setStatus("We couldn't get your location. Check your location permission, or type a town instead.");
      },
      { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 }
    );
  });

  function resolveLocation() {
    var place = $("place").value.trim();
    if (place && (state.source !== "place" || place !== state.place)) {
      setStatus("Looking up “" + place + "”…");
      return fetchJSON(cfg.geocodeUrl + "?q=" + encodeURIComponent(place)).then(function (c) {
        state.lat = c.lat; state.lng = c.lng; state.source = "place"; state.place = place;
        setStatus("Searching around " + place + ".");
      });
    }
    if (state.lat === null) {
      return Promise.reject(new Error("Share your location or type a town or area first."));
    }
    return Promise.resolve();
  }

  // ---------- search ----------
  $("search-form").addEventListener("submit", function (e) {
    e.preventDefault();
    showError("");
    var btn = this.querySelector("button[type=submit]");
    btn.disabled = true;
    resolveLocation()
      .then(function () {
        var q = new URLSearchParams({ lat: state.lat, lng: state.lng, radius: $("radius").value });
        ["specialization", "insurance", "mode"].forEach(function (k) { if ($(k).value) q.set(k, $(k).value); });
        return fetchJSON(cfg.searchUrl + "?" + q.toString());
      })
      .then(render)
      .catch(function (err) { showError(err.message); })
      .finally(function () { btn.disabled = false; });
  });

  function render(data) {
    var list = $("results");
    list.textContent = "";
    $("result-summary").textContent = data.count
      ? data.count + " verified therapist" + (data.count === 1 ? "" : "s") + " within " + data.radius_km + " km"
      : "No verified therapists found within " + data.radius_km + " km. Try a larger radius or fewer filters.";

    data.results.forEach(function (t) {
      var nearest = t.clinics[0];
      var tags = el("p", { className: "tags" }, t.specializations.map(function (s) {
        return el("span", { className: "tag", text: s });
      }));
      list.appendChild(el("li", { className: "list-item result" }, [
        el("div", {}, [
          el("h2", { className: "result-name" }, [
            el("a", { href: cfg.profileUrl.replace("{id}", t.id), text: t.full_name }),
          ]),
          el("p", { className: "help", text: t.distance_km + " km away · " + t.consultation_modes.join(", ") }),
          nearest ? el("p", { className: "help", text: nearest.name + " · " + nearest.operating_hours }) : null,
          nearest && nearest.insurance_providers.length
            ? el("p", { className: "help", text: "Insurance: " + nearest.insurance_providers.join(", ") }) : null,
          tags,
        ]),
        el("a", { className: "btn btn-secondary", href: "tel:" + t.phone, text: "Call" }),
      ]));
    });
    drawMap(data);
  }

  // ---------- map (optional, with 5 s fallback) ----------
  function loadLeaflet() {
    if (window.L) return Promise.resolve(window.L);
    return new Promise(function (resolve, reject) {
      var css = el("link", { rel: "stylesheet", href: LEAFLET_CSS });
      document.head.appendChild(css);
      var s = el("script", { src: LEAFLET_JS });
      var timer = setTimeout(function () { reject(new Error("timeout")); }, TIMEOUT_MS);
      s.onload = function () { clearTimeout(timer); resolve(window.L); };
      s.onerror = function () { clearTimeout(timer); reject(new Error("load failed")); };
      document.head.appendChild(s);
    });
  }

  function mapUnavailable() {
    mapFailed = true;
    $("map").hidden = true;
    $("map-notice").hidden = false;
  }

  function drawMap(data) {
    if (mapFailed) return;
    if (!data.results.length) { $("map").hidden = true; return; }
    loadLeaflet().then(function (L) {
      $("map").hidden = false;
      if (!map) {
        map = L.map("map", { scrollWheelZoom: false });
        var tiles = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 18,
          attribution: "&copy; OpenStreetMap contributors",
        }).addTo(map);
        var loaded = false;
        tiles.on("tileload", function () { loaded = true; });
        setTimeout(function () { if (!loaded) mapUnavailable(); }, TIMEOUT_MS);
        markerLayer = L.layerGroup().addTo(map);
      }
      markerLayer.clearLayers();
      var circle = L.circle([state.lat, state.lng], {
        radius: data.radius_km * 1000, color: "#3d6b6a", weight: 1, fillOpacity: 0.05,
      }).addTo(markerLayer);
      L.circleMarker([state.lat, state.lng], { radius: 6, color: "#26323a", fillOpacity: 1 })
        .bindTooltip("You are here").addTo(markerLayer);

      data.results.forEach(function (t) {
        t.clinics.forEach(function (c) {
          var popup = el("div", {}, [
            el("strong", { text: t.full_name }), el("br"),
            document.createTextNode(c.name + " · " + c.distance_km + " km"), el("br"),
            el("a", { href: cfg.profileUrl.replace("{id}", t.id), text: "View profile" }),
          ]);
          L.marker([c.latitude, c.longitude]).bindPopup(popup).addTo(markerLayer);
        });
      });
      map.fitBounds(circle.getBounds());
      map.invalidateSize();
    }).catch(mapUnavailable);
  }
})();
