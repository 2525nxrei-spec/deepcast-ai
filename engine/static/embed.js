/**
 * Deepcast Engine — Embed Widget
 * Lightweight, self-contained IIFE for embedding Deepcast content on external sites.
 * No dependencies.
 *
 * Usage:
 *   <script src="http://localhost:8000/api/embed/latest.js"
 *           data-api-url="http://localhost:8000"
 *           data-language="ja"
 *           data-count="3"
 *           data-theme="light"
 *           data-container="deepcast-widget"></script>
 */
(function () {
  "use strict";

  /* ------------------------------------------------------------------ */
  /*  Configuration                                                      */
  /* ------------------------------------------------------------------ */

  var scriptTag =
    document.currentScript ||
    (function () {
      var scripts = document.getElementsByTagName("script");
      return scripts[scripts.length - 1];
    })();

  var CFG = {
    apiUrl: (scriptTag.getAttribute("data-api-url") || "").replace(/\/+$/, "") || "",
    language: scriptTag.getAttribute("data-language") || "ja",
    count: parseInt(scriptTag.getAttribute("data-count"), 10) || 3,
    theme: scriptTag.getAttribute("data-theme") || "light",
    containerId: scriptTag.getAttribute("data-container") || "deepcast-widget",
  };

  /* ------------------------------------------------------------------ */
  /*  Scoped CSS                                                         */
  /* ------------------------------------------------------------------ */

  var ACCENT = "#3a8a44";
  var CSS = (function () {
    /*  We scope everything under .deepcast-widget to avoid leaking.      */
    return (
      "\n" +
      ".deepcast-widget {\n" +
      "  --dc-accent: " + ACCENT + ";\n" +
      "  --dc-bg: #ffffff;\n" +
      "  --dc-card-bg: #ffffff;\n" +
      "  --dc-text: #1a1a1a;\n" +
      "  --dc-text-secondary: #555555;\n" +
      "  --dc-border: #e0e0e0;\n" +
      "  --dc-skeleton: #e8e8e8;\n" +
      "  --dc-skeleton-shine: #f5f5f5;\n" +
      "  font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;\n" +
      "  line-height: 1.5;\n" +
      "  color: var(--dc-text);\n" +
      "  box-sizing: border-box;\n" +
      "}\n" +
      ".deepcast-widget *, .deepcast-widget *::before, .deepcast-widget *::after {\n" +
      "  box-sizing: inherit;\n" +
      "}\n" +
      /* Dark theme overrides */
      ".deepcast-widget.dc-dark {\n" +
      "  --dc-bg: #1a1a2e;\n" +
      "  --dc-card-bg: #22223a;\n" +
      "  --dc-text: #e8e8e8;\n" +
      "  --dc-text-secondary: #a0a0b0;\n" +
      "  --dc-border: #33334a;\n" +
      "  --dc-skeleton: #2a2a42;\n" +
      "  --dc-skeleton-shine: #33334a;\n" +
      "}\n" +
      /* Header */
      ".deepcast-widget .dc-header {\n" +
      "  display: flex;\n" +
      "  align-items: center;\n" +
      "  justify-content: space-between;\n" +
      "  margin-bottom: 16px;\n" +
      "}\n" +
      ".deepcast-widget .dc-title {\n" +
      "  font-size: 18px;\n" +
      "  font-weight: 700;\n" +
      "  color: var(--dc-accent);\n" +
      "  margin: 0;\n" +
      "}\n" +
      /* Language toggle */
      ".deepcast-widget .dc-lang-toggle {\n" +
      "  display: none;\n" +
      "  gap: 4px;\n" +
      "}\n" +
      ".deepcast-widget .dc-lang-toggle.dc-visible {\n" +
      "  display: flex;\n" +
      "}\n" +
      ".deepcast-widget .dc-lang-btn {\n" +
      "  padding: 4px 10px;\n" +
      "  font-size: 12px;\n" +
      "  font-weight: 600;\n" +
      "  border: 1px solid var(--dc-border);\n" +
      "  border-radius: 4px;\n" +
      "  background: transparent;\n" +
      "  color: var(--dc-text-secondary);\n" +
      "  cursor: pointer;\n" +
      "  transition: all 0.2s;\n" +
      "}\n" +
      ".deepcast-widget .dc-lang-btn.dc-active {\n" +
      "  background: var(--dc-accent);\n" +
      "  color: #fff;\n" +
      "  border-color: var(--dc-accent);\n" +
      "}\n" +
      /* Card list */
      ".deepcast-widget .dc-cards {\n" +
      "  display: grid;\n" +
      "  grid-template-columns: 1fr;\n" +
      "  gap: 14px;\n" +
      "}\n" +
      "@media (min-width: 640px) {\n" +
      "  .deepcast-widget .dc-cards {\n" +
      "    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));\n" +
      "  }\n" +
      "}\n" +
      /* Card */
      ".deepcast-widget .dc-card {\n" +
      "  background: var(--dc-card-bg);\n" +
      "  border: 1px solid var(--dc-border);\n" +
      "  border-radius: 8px;\n" +
      "  padding: 16px;\n" +
      "  transition: box-shadow 0.2s, transform 0.2s;\n" +
      "}\n" +
      ".deepcast-widget .dc-card:hover {\n" +
      "  box-shadow: 0 4px 12px rgba(0,0,0,0.08);\n" +
      "  transform: translateY(-2px);\n" +
      "}\n" +
      ".deepcast-widget .dc-card-meta {\n" +
      "  display: flex;\n" +
      "  align-items: center;\n" +
      "  gap: 8px;\n" +
      "  margin-bottom: 8px;\n" +
      "}\n" +
      ".deepcast-widget .dc-badge {\n" +
      "  display: inline-block;\n" +
      "  padding: 2px 8px;\n" +
      "  font-size: 11px;\n" +
      "  font-weight: 600;\n" +
      "  border-radius: 4px;\n" +
      "  background: var(--dc-accent);\n" +
      "  color: #fff;\n" +
      "  text-transform: uppercase;\n" +
      "  letter-spacing: 0.03em;\n" +
      "}\n" +
      ".deepcast-widget .dc-date {\n" +
      "  font-size: 12px;\n" +
      "  color: var(--dc-text-secondary);\n" +
      "}\n" +
      ".deepcast-widget .dc-card-title {\n" +
      "  font-size: 15px;\n" +
      "  font-weight: 600;\n" +
      "  margin: 0 0 6px;\n" +
      "  color: var(--dc-text);\n" +
      "}\n" +
      ".deepcast-widget .dc-card-summary {\n" +
      "  font-size: 13px;\n" +
      "  color: var(--dc-text-secondary);\n" +
      "  margin: 0 0 12px;\n" +
      "}\n" +
      ".deepcast-widget .dc-read-more {\n" +
      "  display: inline-block;\n" +
      "  font-size: 13px;\n" +
      "  font-weight: 600;\n" +
      "  color: var(--dc-accent);\n" +
      "  text-decoration: none;\n" +
      "  transition: opacity 0.2s;\n" +
      "}\n" +
      ".deepcast-widget .dc-read-more:hover {\n" +
      "  opacity: 0.75;\n" +
      "}\n" +
      /* Skeleton */
      "@keyframes dc-shimmer {\n" +
      "  0% { background-position: -400px 0; }\n" +
      "  100% { background-position: 400px 0; }\n" +
      "}\n" +
      ".deepcast-widget .dc-skeleton {\n" +
      "  border-radius: 4px;\n" +
      "  background: linear-gradient(90deg, var(--dc-skeleton) 25%, var(--dc-skeleton-shine) 50%, var(--dc-skeleton) 75%);\n" +
      "  background-size: 800px 100%;\n" +
      "  animation: dc-shimmer 1.5s infinite;\n" +
      "}\n" +
      ".deepcast-widget .dc-skel-badge { width: 60px; height: 18px; margin-bottom: 10px; }\n" +
      ".deepcast-widget .dc-skel-title { width: 80%; height: 18px; margin-bottom: 8px; }\n" +
      ".deepcast-widget .dc-skel-line  { width: 100%; height: 12px; margin-bottom: 6px; }\n" +
      ".deepcast-widget .dc-skel-link  { width: 90px; height: 14px; margin-top: 8px; }\n" +
      /* Error */
      ".deepcast-widget .dc-error {\n" +
      "  text-align: center;\n" +
      "  padding: 24px 16px;\n" +
      "  color: var(--dc-text-secondary);\n" +
      "  font-size: 14px;\n" +
      "}\n" +
      /* Footer */
      ".deepcast-widget .dc-footer {\n" +
      "  margin-top: 12px;\n" +
      "  text-align: right;\n" +
      "  font-size: 11px;\n" +
      "  color: var(--dc-text-secondary);\n" +
      "}\n" +
      ".deepcast-widget .dc-footer a {\n" +
      "  color: var(--dc-accent);\n" +
      "  text-decoration: none;\n" +
      "}\n"
    );
  })();

  /* ------------------------------------------------------------------ */
  /*  Helpers                                                            */
  /* ------------------------------------------------------------------ */

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    if (attrs) {
      for (var k in attrs) {
        if (k === "className") node.className = attrs[k];
        else if (k === "textContent") node.textContent = attrs[k];
        else if (k === "innerHTML") node.innerHTML = attrs[k];
        else node.setAttribute(k, attrs[k]);
      }
    }
    if (children) {
      for (var i = 0; i < children.length; i++) {
        if (typeof children[i] === "string") {
          node.appendChild(document.createTextNode(children[i]));
        } else if (children[i]) {
          node.appendChild(children[i]);
        }
      }
    }
    return node;
  }

  function truncate(str, max) {
    if (!str) return "";
    return str.length > max ? str.slice(0, max) + "..." : str;
  }

  function formatDate(raw) {
    if (!raw) return "";
    try {
      var d = new Date(raw);
      return d.getFullYear() + "-" +
        String(d.getMonth() + 1).padStart(2, "0") + "-" +
        String(d.getDate()).padStart(2, "0");
    } catch (_) {
      return String(raw);
    }
  }

  function escapeHtml(str) {
    var div = document.createElement("div");
    div.appendChild(document.createTextNode(str || ""));
    return div.innerHTML;
  }

  /* ------------------------------------------------------------------ */
  /*  Rendering                                                          */
  /* ------------------------------------------------------------------ */

  function renderSkeleton(container, count) {
    var cards = el("div", { className: "dc-cards" });
    for (var i = 0; i < count; i++) {
      var card = el("div", { className: "dc-card" }, [
        el("div", { className: "dc-skeleton dc-skel-badge" }),
        el("div", { className: "dc-skeleton dc-skel-title" }),
        el("div", { className: "dc-skeleton dc-skel-line" }),
        el("div", { className: "dc-skeleton dc-skel-line" }),
        el("div", { className: "dc-skeleton dc-skel-link" }),
      ]);
      cards.appendChild(card);
    }
    container.appendChild(cards);
  }

  function renderError(container, lang) {
    var msg =
      lang === "ja"
        ? "\u30B3\u30F3\u30C6\u30F3\u30C4\u3092\u8AAD\u307F\u8FBC\u3081\u307E\u305B\u3093\u3067\u3057\u305F"
        : "Failed to load content";
    container.innerHTML = "";
    container.appendChild(el("div", { className: "dc-error", textContent: msg }));
  }

  function buildCard(item, lang) {
    var title = item.title || item.title_ja || item.title_en || "";
    var summary = item.summary || item.description || item.summary_ja || item.summary_en || "";
    var category = item.category || "";
    var date = item.published_at || item.created_at || "";
    var url = item.url || item.link || "#";
    var readMore = lang === "ja" ? "\u7D9A\u304D\u3092\u8AAD\u3080 \u2192" : "Read more \u2192";

    return el("div", { className: "dc-card" }, [
      el("div", { className: "dc-card-meta" }, [
        category ? el("span", { className: "dc-badge", textContent: category }) : null,
        el("span", { className: "dc-date", textContent: formatDate(date) }),
      ]),
      el("h3", { className: "dc-card-title", textContent: title }),
      el("p", { className: "dc-card-summary", textContent: truncate(summary, 150) }),
      el("a", { className: "dc-read-more", href: url, target: "_blank", rel: "noopener", textContent: readMore }),
    ]);
  }

  function renderCards(container, items, lang) {
    container.innerHTML = "";

    /* Header with optional language toggle */
    var headerTitle = el("span", { className: "dc-title", textContent: "Deepcast" });

    var btnJa = el("button", { className: "dc-lang-btn" + (lang === "ja" ? " dc-active" : ""), textContent: "JP" });
    var btnEn = el("button", { className: "dc-lang-btn" + (lang !== "ja" ? " dc-active" : ""), textContent: "EN" });
    var langToggle = el("div", { className: "dc-lang-toggle" }, [btnJa, btnEn]);

    /* Show toggle only if items contain both languages */
    var hasJa = false;
    var hasEn = false;
    for (var i = 0; i < items.length; i++) {
      var itemLang = (items[i].language || "").toLowerCase();
      if (itemLang === "ja") hasJa = true;
      if (itemLang === "en") hasEn = true;
    }
    if (hasJa && hasEn) {
      langToggle.className += " dc-visible";
    }

    var header = el("div", { className: "dc-header" }, [headerTitle, langToggle]);
    container.appendChild(header);

    /* Filter by language if toggle is visible */
    var filtered = items;
    if (hasJa && hasEn) {
      filtered = [];
      for (var j = 0; j < items.length; j++) {
        if ((items[j].language || "").toLowerCase() === lang) {
          filtered.push(items[j]);
        }
      }
      if (filtered.length === 0) filtered = items; // fallback: show all
    }

    /* Limit */
    filtered = filtered.slice(0, CFG.count);

    /* Cards grid */
    var cardsGrid = el("div", { className: "dc-cards" });
    for (var k = 0; k < filtered.length; k++) {
      cardsGrid.appendChild(buildCard(filtered[k], lang));
    }
    container.appendChild(cardsGrid);

    /* Footer */
    container.appendChild(
      el("div", { className: "dc-footer", innerHTML: 'Powered by <a href="' + escapeHtml(CFG.apiUrl || "#") + '" target="_blank" rel="noopener">Deepcast Engine</a>' })
    );

    /* Toggle handlers */
    btnJa.addEventListener("click", function () {
      renderCards(container, items, "ja");
    });
    btnEn.addEventListener("click", function () {
      renderCards(container, items, "en");
    });
  }

  /* ------------------------------------------------------------------ */
  /*  Init                                                               */
  /* ------------------------------------------------------------------ */

  function init() {
    /* Find or create container */
    var container = document.getElementById(CFG.containerId);
    if (!container) {
      container = el("div", { id: CFG.containerId });
      scriptTag.parentNode.insertBefore(container, scriptTag.nextSibling);
    }
    container.className = "deepcast-widget" + (CFG.theme === "dark" ? " dc-dark" : "");

    /* Inject scoped CSS once */
    if (!document.getElementById("deepcast-widget-styles")) {
      var style = document.createElement("style");
      style.id = "deepcast-widget-styles";
      style.textContent = CSS;
      document.head.appendChild(style);
    }

    /* Skeleton loader */
    renderSkeleton(container, CFG.count);

    /* Fetch */
    var endpoint = CFG.apiUrl + "/api/contents/latest?count=" + CFG.count + "&language=" + encodeURIComponent(CFG.language);

    fetch(endpoint)
      .then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      })
      .then(function (data) {
        var items = Array.isArray(data) ? data : (data.items || data.contents || data.data || []);
        if (items.length === 0) {
          renderError(container, CFG.language);
          return;
        }
        renderCards(container, items, CFG.language);
      })
      .catch(function () {
        renderError(container, CFG.language);
      });
  }

  /* Run when DOM is ready */
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
