/* ==========================================================================
 * GEOCODE LANDIQ EMBED LOADER v1
 * Land Intelligence Platform - Geocode Spatial Solutions Ltd
 *
 * THIS IS THE PRODUCT. Everything else in this repository exists so that
 * these two lines work on somebody else's website:
 *
 *     <div id="geocode-plot" data-plot-ref="PLOT-457"></div>
 *     <script src="https://embed.geocode.co.ke/v1.js" data-key="pk_live_..."></script>
 *
 * That is the whole integration. If we are writing bespoke code per customer
 * we are a consultancy, not a product.
 *
 * --------------------------------------------------------------------------
 * WHAT THIS FILE IS NOT ALLOWED TO DO
 * --------------------------------------------------------------------------
 * It does not fetch geometry, hold geometry, or know what geometry is. It
 * asks our server for rendered HTML and puts it on the page. That is the
 * whole reason the embed model was chosen over an API of values or an API of
 * geometry: the client receives NOTHING that could be a database, so ODbL
 * share-alike is never engaged on distribution (checklist A4).
 *
 * It also does not load a framework, a CSS file, or a font. A widget that
 * drags 200 KB onto a client's page will be removed by their developer
 * within a week, and rightly.
 *
 * --------------------------------------------------------------------------
 * WHY IT FAILS SILENTLY, AND WHERE IT DOES NOT
 * --------------------------------------------------------------------------
 * This runs inside someone else's page, on their traffic, in front of their
 * buyers. A widget that throws an exception or draws a red error box on a
 * client's live listing is worse than one that shows nothing: it makes their
 * site look broken and it is our name in the console.
 *
 * So every failure path removes the widget and logs to console. The one
 * exception is a MISSING PLOT REFERENCE, which is a wiring mistake during
 * integration and must be loud enough that their developer sees it before
 * go-live rather than after.
 * ======================================================================== */
(function () {
  "use strict";

  var VERSION = "1.3.0";

  /* document.currentScript is the tag being executed RIGHT NOW, which is how
   * the key is read without the client having to name anything globally.
   * It is null inside async/deferred execution and in older browsers, so the
   * fallback finds the last script whose src looks like ours. */
  var self = document.currentScript || (function () {
    var all = document.getElementsByTagName("script");
    for (var i = all.length - 1; i >= 0; i--) {
      if (/\/v1(\.min)?\.js(\?|$)/.test(all[i].src || "")) return all[i];
    }
    return null;
  })();

  function warn(msg) {
    if (window.console && console.warn) console.warn("[Geocode LandIQ] " + msg);
  }

  if (!self) { warn("could not locate own script tag; not rendering."); return; }

  var key = self.getAttribute("data-key");
  /* The origin is derived from where this file was served, NOT hardcoded.
   * Staging, production and a client's own reverse proxy then all work with
   * no change to the snippet they pasted. */
  var origin = (function () {
    try { return new URL(self.src, window.location.href).origin; }
    catch (e) { return ""; }
  })();

  if (!key) { warn("no data-key on the script tag; not rendering."); return; }

  /* One widget per element, so a page can carry several plots - a scheme
   * listing showing four plots is a real case and must not need four
   * script tags. */
  var targets = document.querySelectorAll(
    "#geocode-plot, [data-geocode-plot], .geocode-plot, " +
    "#geocode-scheme, [data-geocode-scheme]");

  if (!targets.length) { warn("no container found on the page."); return; }

  /* ------------------------------------------------------------------
   * Fetching. One function, because the two modes differ only in URL and
   * every failure path below is identical for both.
   * ------------------------------------------------------------------ */
  function load(path, what) {
    return fetch(origin + path, {
      method: "GET",
      headers: { "X-API-Key": key },
      credentials: "omit",
      /* No cookies, ever. This runs on a client's domain and a credentialed
       * cross-origin request would drag their session into our logs. */
      cache: "no-store"
    }).then(function (res) {
      if (res.status === 404) {
        /* An unknown reference is a 404 and NEVER a nearest match - that
         * rule lives in the API and this is the client-side half of it.
         * Serving the wrong plot's analysis to a buyer is the worst
         * failure this product has, so an unrecognised plot renders
         * nothing at all. */
        throw { quiet: true, msg: what + " is not in this account. Check the "
              + "parcel_ref mapping agreed at onboarding." };
      }
      if (res.status === 401 || res.status === 403) {
        throw { quiet: true, msg: "API key rejected. If the key is correct, "
              + "the account may be inactive - contact Geocode." };
      }
      if (res.status === 429) {
        throw { quiet: true, msg: "rate limit reached for this account." };
      }
      if (!res.ok) throw { quiet: true, msg: "server returned " + res.status };
      return res.text();
    });
  }

  /* The server sends a self-contained fragment with its own scoped styles.
   * It is inserted as HTML because that is the entire point of the embed
   * model - we render, they display.
   *
   * NOTE FOR WHOEVER TOUCHES THIS NEXT: this is safe only because the
   * response comes from our own origin over TLS and is built by
   * report_content.py from database values. It is NOT safe to widen this to
   * any other source, and nothing here should ever interpolate anything the
   * host page supplies. */
  function put(el, html) {
    el.innerHTML = html;
    absolutise(el);
    el.setAttribute("data-geocode-state", "ready");
    el.setAttribute("data-geocode-version", VERSION);
  }

  /* THE SERVER WRITES ROOT-RELATIVE IMAGE PATHS, AND IT HAS TO.
   *
   * It emits src="/v1/scheme/map?..." because it cannot know what hostname
   * it is reachable at: localhost today, a tunnel this week, a real domain
   * later, possibly behind the client's own reverse proxy. Baking one in
   * would be wrong within a day.
   *
   * But a root-relative path on the CLIENT'S page resolves against the
   * CLIENT'S domain, where nothing of ours exists. It only appeared to work
   * because the demo page is served by the same API. On a real seller's site
   * every picture would have 404ed.
   *
   * This file is the only place that knows the answer - `origin` is derived
   * from where this script itself was loaded - so this is where it gets
   * fixed, once, on every fragment. */
  function absolutise(root) {
    var imgs = root.querySelectorAll('img[src^="/v1/"]');
    for (var i = 0; i < imgs.length; i++) {
      imgs[i].setAttribute("src", origin + imgs[i].getAttribute("src"));
      hideIfBroken(imgs[i]);
    }
    var det = root.querySelectorAll('[data-giq-detail^="/v1/"]');
    for (var j = 0; j < det.length; j++) {
      det[j].setAttribute("data-giq-detail",
                          origin + det[j].getAttribute("data-giq-detail"));
    }
  }

  /* A PICTURE THAT DOES NOT ARRIVE MUST LEAVE NO HOLE.
   *
   * When Google refuses - billing lapsed, quota spent, key wrong - our image
   * endpoint 404s and the browser draws its broken-image icon with the alt
   * text beside it, on the seller's live listing, under our name. That is
   * precisely the "red error box" this file's header promises never to
   * draw, and it went unnoticed because in testing Google always answered.
   *
   * The panel is built so that every picture is optional: the analysis, the
   * distances and the plot list are all still right without them. So a
   * failed image takes its own frame away and the panel closes over the gap.
   * The reason still reaches the console, where somebody can act on it. */
  function hideIfBroken(img) {
    img.addEventListener("error", function () {
      var frame = img.closest ? (img.closest(".tile") || img.closest(".smap"))
                              : null;
      (frame || img).style.display = "none";
      warn("an image did not load (" + img.getAttribute("src") + "). The "
         + "panel is showing everything else. If ALL images are missing, "
         + "run check_maps_key.py - it prints Google's own reason.");
    });
  }

  /* ------------------------------------------------------------------
   * PANNING AND ZOOMING THE SCHEME MAP
   *
   * The map is one flat picture, and it stays one flat picture: this moves
   * and scales the <img> with a CSS transform and nothing else. No tiles, no
   * map library, and above all no plot outlines - the browser still has no
   * idea where any boundary is, which is the whole reason the map is a
   * picture rather than a map widget (B4).
   *
   * Zooming past 1 swaps in a second picture of the SAME ground at twice the
   * resolution, so magnifying reveals detail rather than blur. Both frame
   * identical ground, so the tap arithmetic below does not change when the
   * swap happens.
   * ------------------------------------------------------------------ */
  var MAX_ZOOM = 6, ZOOM_STEP = 1.6;

  function mapState(m) {
    if (!m.__giq) m.__giq = { s: 1, tx: 0, ty: 0, detail: false, pts: {} };
    return m.__giq;
  }

  function applyTransform(m) {
    var st = mapState(m);
    m.style.transform = "translate(" + st.tx + "px," + st.ty + "px) scale("
                      + st.s + ")";
  }

  /* The picture may never be dragged away from the window it sits in. */
  function clampPan(m) {
    var st = mapState(m), c = m.parentNode;
    var cw = c.clientWidth, ch = c.clientHeight;
    var w = m.offsetWidth * st.s, h = m.offsetHeight * st.s;
    st.tx = (w <= cw) ? (cw - w) / 2 : Math.min(0, Math.max(cw - w, st.tx));
    st.ty = (h <= ch) ? (ch - h) / 2 : Math.min(0, Math.max(ch - h, st.ty));
  }

  function loadDetail(m) {
    var st = mapState(m);
    if (st.detail) return;
    var url = m.getAttribute("data-giq-detail");
    if (!url) return;
    st.detail = true;              /* set first: never request it twice */
    var pre = new Image();
    /* Swapped only once it has actually arrived, so the buyer never watches
     * the map blank out and redraw while they are looking at it. */
    pre.onload = function () { m.src = url; };
    pre.onerror = function () { st.detail = true; };
    pre.src = url;
  }

  /* ax, ay are in container coordinates and stay put while the scale
   * changes, which is what makes zooming feel like it happened where you
   * pointed rather than somewhere else. */
  function setZoom(m, next, ax, ay) {
    var st = mapState(m);
    next = Math.max(1, Math.min(MAX_ZOOM, next));
    var u = (ax - st.tx) / st.s, v = (ay - st.ty) / st.s;
    st.tx = ax - u * next;
    st.ty = ay - v * next;
    st.s = next;
    clampPan(m);
    applyTransform(m);
    if (next > 1.05) loadDetail(m);
  }

  function zoomBy(m, dir) {
    var st = mapState(m), c = m.parentNode;
    if (dir === "reset") {
      st.s = 1; st.tx = 0; st.ty = 0;
      clampPan(m); applyTransform(m);
      return;
    }
    setZoom(m, dir === "in" ? st.s * ZOOM_STEP : st.s / ZOOM_STEP,
            c.clientWidth / 2, c.clientHeight / 2);
  }

  function pointToFraction(m, clientX, clientY) {
    var st = mapState(m), r = m.parentNode.getBoundingClientRect();
    var u = ((clientX - r.left) - st.tx) / st.s;
    var v = ((clientY - r.top) - st.ty) / st.s;
    var fx = u / m.offsetWidth, fy = v / m.offsetHeight;
    if (!(fx >= 0 && fx <= 1 && fy >= 0 && fy <= 1)) return null;
    return [fx, fy];
  }

  /* Satellite / Map / Street on the plot page.
   *
   * BOUND FOR BOTH MODES, which the first version was not. The switch lived
   * inside the scheme container's click handler, so it worked when a buyer
   * arrived at a plot through the scheme list and was completely dead on a
   * page that embeds one plot directly - the same markup, the same buttons,
   * nothing happening. A control's behaviour cannot live in one of the two
   * paths that render it.
   *
   * Every pane is already in the document. This shows one and hides the
   * rest, and deliberately does NOT touch any iframe's src: a map the buyer
   * has panned somewhere stays where they left it when they flick to the
   * photograph and back, which is the whole reason to have a switch rather
   * than two panels stacked up. */
  function bindViewSwitch(el) {
    el.addEventListener("click", function (ev) {
      var vb = ev.target && ev.target.closest
             ? ev.target.closest("[data-giq-view]") : null;
      if (!vb || !el.contains(vb)) return;
      var live = vb.closest(".live");
      if (!live) return;
      var want = vb.getAttribute("data-giq-view");
      var panes = live.querySelectorAll("[data-giq-pane]");
      for (var p = 0; p < panes.length; p++) {
        panes[p].hidden = (panes[p].getAttribute("data-giq-pane") !== want);
      }
      var all = live.querySelectorAll("[data-giq-view]");
      for (var i = 0; i < all.length; i++) {
        all[i].className = (all[i] === vb) ? "on" : "";
      }
    });
  }

  /* ------------------------------------------------------------------
   * THE LIVE SCHEME MAP
   *
   * Google's own satellite, with the seller's plots drawn on it as clickable
   * shapes. This is the one place in this file that handles geometry, and it
   * is a deliberate, narrow exception rather than a drift: see the block
   * above /v1/scheme/plots in api_01_embed.py for what may come through it
   * and what may never.
   *
   * IT IS ALSO THE ONE PLACE THAT LOADS SOMETHING. The header of this file
   * says it does not drag a framework onto a client's page, and Google Maps
   * is exactly that. The reasoning has not changed, so the loading is
   * bounded: nothing is fetched unless a scheme container is actually on the
   * page, the script is requested once however many widgets there are, and
   * anything that goes wrong puts the old drawn picture back rather than
   * leaving a hole.
   * ------------------------------------------------------------------ */
  var gmapsPromise = null;

  function loadGoogleMaps(apiKey) {
    if (gmapsPromise) return gmapsPromise;
    gmapsPromise = new Promise(function (resolve, reject) {
      if (window.google && window.google.maps) return resolve(window.google);
      var cb = "__giqMapsReady";
      window[cb] = function () { resolve(window.google); };
      var s = document.createElement("script");
      s.src = "https://maps.googleapis.com/maps/api/js?key="
            + encodeURIComponent(apiKey) + "&callback=" + cb + "&loading=async";
      s.async = true;
      s.onerror = function () { reject(new Error("Google Maps did not load")); };
      document.head.appendChild(s);
    });
    return gmapsPromise;
  }

  var PLOT_FILL = { available: "#1f7a44", default: "#8a9a90" };

  function liveScheme(el, box, onPlot) {
    var proj = box.getAttribute("data-giq-project") || "";
    var path = "/v1/scheme/plots"
             + (proj ? "?project=" + encodeURIComponent(proj) : "");

    function fallback(why) {
      /* The drawn picture, back in the same box, with the gestures it always
       * had. A buyer must never be shown an empty rectangle where the map
       * was, and a seller must never have to know which of the two they
       * are looking at. */
      warn("live map unavailable (" + why + "); using the drawn map instead.");
      var url = box.getAttribute("data-giq-fallback");
      if (!url) { box.style.display = "none"; return; }
      box.classList.remove("smaplive");
      box.style.height = "";
      box.innerHTML = '<img data-giq-map alt="Map of the plots in this scheme"'
        + ' data-giq-project="' + proj.replace(/"/g, "&quot;") + '"'
        + ' src="' + origin + url + '">'
        + '<div class="smapz">'
        + '<button type="button" data-giq-zoom="in">+</button>'
        + '<button type="button" data-giq-zoom="out">−</button>'
        + '<button type="button" data-giq-zoom="reset">□</button></div>'
        + '<div class="smapc">Drag to move, + and - to zoom, tap a plot</div>';
      hideIfBroken(box.querySelector("img"));
    }

    fetch(origin + path, {
      method: "GET", headers: { "X-API-Key": key },
      credentials: "omit", cache: "no-store"
    }).then(function (r) {
      if (!r.ok) throw new Error("plots " + r.status);
      return r.json();
    }).then(function (data) {
      if (!data || !data.plots || !data.plots.length) throw new Error("empty");
      return loadGoogleMaps(data.key).then(function (google) {
        drawLive(google, box, data, onPlot);
      });
    }).catch(function (e) { fallback(e && e.message ? e.message : "error"); });
  }

  function drawLive(google, box, data, onPlot) {
    box.innerHTML = "";
    var map = new google.maps.Map(box, {
      mapTypeId: "hybrid",
      streetViewControl: false,
      fullscreenControl: true,
      mapTypeControl: true,
      /* gestureHandling "greedy" would swallow the client's page scroll. On
       * a phone "cooperative" asks for two fingers, which is what every
       * embedded map on the web does and what a reader expects. */
      gestureHandling: "cooperative"
    });
    var b = data.bounds;
    map.fitBounds(new google.maps.LatLngBounds(
      { lat: b.south, lng: b.west }, { lat: b.north, lng: b.east }));

    var labels = [];
    for (var i = 0; i < data.plots.length; i++) {
      var p = data.plots[i];
      var paths = [];
      for (var r = 0; r < p.rings.length; r++) {
        var ring = [];
        for (var c = 0; c < p.rings[r].length; c++) {
          ring.push({ lat: p.rings[r][c][1], lng: p.rings[r][c][0] });
        }
        paths.push(ring);
      }
      var sold = p.state !== "available";
      var poly = new google.maps.Polygon({
        paths: paths, map: map,
        strokeColor: "#ffffff", strokeOpacity: 0.95, strokeWeight: 1.4,
        fillColor: sold ? PLOT_FILL.default : PLOT_FILL.available,
        fillOpacity: sold ? 0.18 : 0.30,
        clickable: true, zIndex: 1
      });
      (function (ref) {
        poly.addListener("click", function () { onPlot(ref); });
      })(p.ref);

      var c0 = paths[0][0];
      labels.push({ n: p.n, lat: c0.lat, lng: c0.lng, poly: poly });
    }

    /* NUMBERS ONLY WHERE THEY CAN BE READ, AND ONLY WHERE YOU ARE LOOKING.
     *
     * 688 markers at once is a slow map on a mid-range phone, and at the
     * zoom that shows a whole scheme the numbers would be unreadable anyway.
     * They appear once you are close enough for them to mean something, and
     * only for the plots actually on screen. */
    var markers = [];
    function refreshLabels() {
      for (var m = 0; m < markers.length; m++) markers[m].setMap(null);
      markers = [];
      if (map.getZoom() < 17) return;
      var view = map.getBounds();
      if (!view) return;
      for (var i = 0; i < labels.length && markers.length < 300; i++) {
        var L = labels[i];
        var at = new google.maps.LatLng(L.lat, L.lng);
        if (!view.contains(at)) continue;
        var c = L.poly.getPath().getArray();
        var sx = 0, sy = 0;
        for (var k2 = 0; k2 < c.length; k2++) { sx += c[k2].lat(); sy += c[k2].lng(); }
        markers.push(new google.maps.Marker({
          position: { lat: sx / c.length, lng: sy / c.length },
          map: map, clickable: false,
          icon: { path: google.maps.SymbolPath.CIRCLE, scale: 0 },
          label: { text: String(L.n), color: "#ffffff",
                   fontSize: "11px", fontWeight: "600" }
        }));
      }
    }
    map.addListener("idle", refreshLabels);
  }

  function bindMapGestures(el) {
    function live(ev) {
      var m = ev.target && ev.target.closest
            ? ev.target.closest("[data-giq-map]") : null;
      return (m && el.contains(m)) ? m : null;
    }

    el.addEventListener("pointerdown", function (ev) {
      var m = live(ev);
      if (!m) return;
      var st = mapState(m);
      st.pts[ev.pointerId] = { x: ev.clientX, y: ev.clientY };
      m.__giqMoved = false;
      st.start = { tx: st.tx, ty: st.ty, s: st.s, d: 0 };
      var ids = Object.keys(st.pts);
      if (ids.length === 2) {
        var a = st.pts[ids[0]], b = st.pts[ids[1]];
        st.start.d = Math.hypot(b.x - a.x, b.y - a.y);
      }
      m.classList.add("giq-drag");
      if (m.setPointerCapture) { try { m.setPointerCapture(ev.pointerId); }
                                 catch (e) {} }
    });

    el.addEventListener("pointermove", function (ev) {
      var m = live(ev);
      if (!m) return;
      var st = mapState(m);
      var prev = st.pts[ev.pointerId];
      if (!prev) return;
      var ids = Object.keys(st.pts);

      if (ids.length >= 2 && st.start && st.start.d > 0) {
        st.pts[ev.pointerId] = { x: ev.clientX, y: ev.clientY };
        var a = st.pts[ids[0]], b = st.pts[ids[1]];
        var d = Math.hypot(b.x - a.x, b.y - a.y);
        if (d > 0) {
          var r = m.parentNode.getBoundingClientRect();
          setZoom(m, st.start.s * (d / st.start.d),
                  (a.x + b.x) / 2 - r.left, (a.y + b.y) / 2 - r.top);
          m.__giqMoved = true;
        }
        ev.preventDefault();
        return;
      }

      if (st.s <= 1) return;              /* nothing to pan while it fits */
      var dx = ev.clientX - prev.x, dy = ev.clientY - prev.y;
      st.pts[ev.pointerId] = { x: ev.clientX, y: ev.clientY };
      st.tx += dx; st.ty += dy;
      /* Four pixels of slop, so that the small movement every real finger
       * makes while tapping is still a tap and not a drag that swallows it. */
      if (Math.abs(dx) > 1 || Math.abs(dy) > 1) m.__giqMoved = true;
      clampPan(m);
      applyTransform(m);
      ev.preventDefault();
    });

    function release(ev) {
      var m = live(ev);
      if (!m) return;
      delete mapState(m).pts[ev.pointerId];
      if (!Object.keys(mapState(m).pts).length) m.classList.remove("giq-drag");
    }
    el.addEventListener("pointerup", release);
    el.addEventListener("pointercancel", release);

    el.addEventListener("dblclick", function (ev) {
      var m = live(ev);
      if (!m) return;
      var r = m.parentNode.getBoundingClientRect();
      setZoom(m, mapState(m).s * ZOOM_STEP * ZOOM_STEP,
              ev.clientX - r.left, ev.clientY - r.top);
      ev.preventDefault();
    });

    /* Wheel zooms only with ctrl or meta held. A bare wheel over an embed
     * belongs to the client's page: stealing it strands a reader who was
     * scrolling past the widget, which is exactly the kind of thing that
     * gets a widget removed. */
    el.addEventListener("wheel", function (ev) {
      var m = live(ev);
      if (!m || !(ev.ctrlKey || ev.metaKey)) return;
      var r = m.parentNode.getBoundingClientRect();
      setZoom(m, mapState(m).s * (ev.deltaY < 0 ? 1.15 : 1 / 1.15),
              ev.clientX - r.left, ev.clientY - r.top);
      ev.preventDefault();
    }, { passive: false });
  }

  function fail(el, err) {
    /* Leave the container empty and the page intact. The client's layout
     * closes over the gap and their buyer sees a listing without an
     * analysis panel, rather than a broken one. */
    el.innerHTML = "";
    el.setAttribute("data-geocode-state", "error");
    warn((err && err.msg) || (err && err.message) || "request failed");
  }

  Array.prototype.forEach.call(targets, function (el) {
    if (el.getAttribute("data-geocode-state")) return;   // already handled
    el.setAttribute("data-geocode-state", "loading");

    var ref = el.getAttribute("data-plot-ref")
           || el.getAttribute("data-geocode-plot");

    /* SCHEME MODE. The attribute may be present and empty, which means
     * "every plot this key can see" - so its presence is tested, not its
     * value. A seller with one scheme should not have to type its name. */
    var isScheme = el.hasAttribute("data-scheme")
                || el.hasAttribute("data-geocode-scheme")
                || el.id === "geocode-scheme";

    if (!ref && !isScheme) {
      /* THE ONE LOUD FAILURE. Everything else in this file fails quietly,
       * because a broken widget on a live page should disappear rather than
       * embarrass the client. This one is different: it means the plot
       * reference was never wired up, it will affect EVERY plot on the site,
       * and it is a five-minute fix during integration and a disaster after
       * go-live. Their developer needs to see it. */
      warn("container has no data-plot-ref and is not a scheme container. "
         + "Add data-plot-ref=\"<your plot reference>\" for one plot, or "
         + "data-scheme for the whole scheme.");
      el.setAttribute("data-geocode-state", "misconfigured");
      return;
    }

    if (isScheme) {
      var project = el.getAttribute("data-scheme")
                 || el.getAttribute("data-geocode-scheme") || "";
      var indexPath = "/v1/scheme/embed"
                    + (project ? "?project=" + encodeURIComponent(project) : "");
      var indexHtml = null;

      /* Clicking a card swaps the detail in. Delegated from the container,
       * once, so it survives every re-render - binding per card would leak a
       * listener each time the index comes back. */
      el.addEventListener("click", function (ev) {
        var card = ev.target && ev.target.closest
                 ? ev.target.closest("[data-giq-plot]") : null;
        if (card && el.contains(card)) {
          showPlot(card.getAttribute("data-giq-plot"));
          return;
        }

        var zb = ev.target && ev.target.closest
               ? ev.target.closest("[data-giq-zoom]") : null;
        if (zb && el.contains(zb)) {
          var zmap = el.querySelector("[data-giq-map]");
          if (zmap) zoomBy(zmap, zb.getAttribute("data-giq-zoom"));
          return;
        }


        /* TAPPING THE MAP.
         *
         * The picture is a plain <img>. This file does not know where any
         * plot is and must never be given that - it is the client's parcel
         * geometry and B4 keeps it off the browser. What it does know is
         * where the finger landed, so it sends that as a fraction of the
         * image and the server answers with one plot reference. */
        var map = ev.target && ev.target.closest
                ? ev.target.closest("[data-giq-map]") : null;
        if (map && el.contains(map)) {
          if (map.__giqMoved) { map.__giqMoved = false; return; }  /* a drag */
          var f = pointToFraction(map, ev.clientX, ev.clientY);
          if (!f) return;
          var proj = map.getAttribute("data-giq-project") || "";
          var at = "/v1/scheme/at?x=" + f[0].toFixed(5) + "&y=" + f[1].toFixed(5)
                 + (proj ? "&project=" + encodeURIComponent(proj) : "");
          fetch(origin + at, {
            method: "GET",
            headers: { "X-API-Key": key },
            credentials: "omit",
            cache: "no-store"
          }).then(function (res) {
            /* A tap on a road or the edge of the scheme is a 404 and does
             * nothing at all. It is NOT resolved to the closest plot from
             * here: showing a buyer the analysis of land they were not
             * pointing at is the worst thing this product can do, and the
             * server already forgives a near miss within one plot width. */
            if (!res.ok) return null;
            return res.json();
          }).then(function (data) {
            if (data && data.ref) showPlot(data.ref);
          }).catch(function () { /* a tap that fails is a tap that did nothing */ });
          return;
        }

        var back = ev.target && ev.target.closest
                 ? ev.target.closest("[data-giq-back]") : null;
        if (back && el.contains(back) && indexHtml !== null) {
          put(el, indexHtml);                 /* instant: no second request */
          /* The cached index carries an EMPTY live-map container, so going
           * back has to build the map again. Forgetting this is how "back"
           * quietly turns a working map into a grey box. */
          var again = el.querySelector("[data-giq-livemap]");
          if (again) liveScheme(el, again, showPlot);
          if (el.scrollIntoView) el.scrollIntoView({ block: "nearest" });
        }
      });

      function showPlot(plotRef) {
        if (!plotRef) return;
        load("/v1/plots/" + encodeURIComponent(plotRef) + "/embed",
             "plot '" + plotRef + "'")
          .then(function (html) {
            put(el, '<div class="giq"><button class="back" type="button" '
                  + 'data-giq-back>&#8592; All plots</button></div>' + html);
            if (el.scrollIntoView) el.scrollIntoView({ block: "nearest" });
          })
          .catch(function (err) { fail(el, err); });
      }

      /* Bound once on the container, not on the image: put() replaces the
       * whole fragment every time the buyer goes back to the list, and a
       * listener attached to the old <img> would go with it. */
      bindMapGestures(el);
      bindViewSwitch(el);

      load(indexPath, "this scheme")
        .then(function (html) {
          indexHtml = html;
          put(el, html);
          var box = el.querySelector("[data-giq-livemap]");
          if (box) liveScheme(el, box, showPlot);
        })
        .catch(function (err) { fail(el, err); });
      return;
    }

    bindViewSwitch(el);
    load("/v1/plots/" + encodeURIComponent(ref) + "/embed", "plot '" + ref + "'")
      .then(function (html) { put(el, html); })
      .catch(function (err) { fail(el, err); });
  });
})();
