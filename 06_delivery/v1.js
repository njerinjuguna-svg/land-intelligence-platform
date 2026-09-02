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

  var VERSION = "1.0.0";

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
    el.setAttribute("data-geocode-state", "ready");
    el.setAttribute("data-geocode-version", VERSION);
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
        var back = ev.target && ev.target.closest
                 ? ev.target.closest("[data-giq-back]") : null;
        if (back && el.contains(back) && indexHtml !== null) {
          put(el, indexHtml);                 /* instant: no second request */
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

      load(indexPath, "this scheme")
        .then(function (html) { indexHtml = html; put(el, html); })
        .catch(function (err) { fail(el, err); });
      return;
    }

    load("/v1/plots/" + encodeURIComponent(ref) + "/embed", "plot '" + ref + "'")
      .then(function (html) { put(el, html); })
      .catch(function (err) { fail(el, err); });
  });
})();
