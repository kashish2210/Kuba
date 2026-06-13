(function () {
  "use strict";
  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

  ready(function () {
    var ta = document.getElementById("receipt-html");
    var cfg = window.RECEIPT || {};

    function token(name) { return "{{ " + name + " }}"; }

    function insertAtCaret(text) {
      if (!ta) return;
      var start = ta.selectionStart || 0;
      var end = ta.selectionEnd || 0;
      ta.value = ta.value.slice(0, start) + text + ta.value.slice(end);
      var pos = start + text.length;
      ta.selectionStart = ta.selectionEnd = pos;
      ta.focus();
    }

    // Pills: click to insert, drag to drop into the editor.
    document.querySelectorAll(".pill").forEach(function (pill) {
      pill.addEventListener("click", function () { insertAtCaret(token(pill.dataset.token)); });
      pill.addEventListener("dragstart", function (e) {
        e.dataTransfer.setData("text/plain", token(pill.dataset.token));
      });
    });
    if (ta) {
      ta.addEventListener("dragover", function (e) { e.preventDefault(); });
      ta.addEventListener("drop", function (e) {
        e.preventDefault();
        insertAtCaret(e.dataTransfer.getData("text/plain"));
      });
    }

    // Toggle: custom HTML block visibility from "use default".
    var useDefault = document.getElementById("id_use_default");
    var customBlock = document.getElementById("custom-html-block");
    function syncDefault() {
      if (useDefault && customBlock) customBlock.style.display = useDefault.checked ? "none" : "";
    }
    if (useDefault) { useDefault.addEventListener("change", function () { syncDefault(); refresh(); }); syncDefault(); }

    // Toggle: SMTP fields from "use platform default".
    var smtpDefault = document.getElementById("id_smtp_use_default");
    var smtpFields = document.getElementById("smtp-fields");
    function syncSmtp() {
      if (smtpDefault && smtpFields) smtpFields.style.display = smtpDefault.checked ? "none" : "";
    }
    if (smtpDefault) { smtpDefault.addEventListener("change", syncSmtp); syncSmtp(); }

    // Live preview.
    var frame = document.getElementById("receipt-preview");
    function refresh() {
      if (!frame || !cfg.previewUrl) return;
      var body = new URLSearchParams();
      body.set("template_html", ta ? ta.value : "");
      if (useDefault && useDefault.checked) body.set("use_default", "on");
      fetch(cfg.previewUrl, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded", "X-CSRFToken": cfg.csrf },
        body: body.toString(),
      }).then(function (r) { return r.text(); }).then(function (html) {
        frame.srcdoc = html;
      });
    }

    var btn = document.getElementById("refresh-preview");
    if (btn) btn.addEventListener("click", refresh);
    if (ta) {
      var timer = null;
      ta.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(refresh, 500); });
    }
    refresh();

    // ── Theme Picker ─────────────────────────────────────────────────────────
    var overlay = document.getElementById("theme-overlay");
    var themeGrid = document.getElementById("theme-grid");
    var btnTheme = document.getElementById("btn-theme-picker");
    var btnApply = document.getElementById("theme-apply");
    var btnCancel = document.getElementById("theme-cancel");
    var btnClose = document.getElementById("theme-modal-close");
    var selectedTheme = null;

    if (!overlay || !btnTheme) return;

    function openThemeModal() {
      overlay.classList.add("open");
      selectedTheme = null;
      if (btnApply) btnApply.disabled = true;
      loadThemes();
    }

    function closeThemeModal() {
      overlay.classList.remove("open");
    }

    btnTheme.addEventListener("click", openThemeModal);
    btnCancel.addEventListener("click", closeThemeModal);
    btnClose.addEventListener("click", closeThemeModal);
    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) closeThemeModal();
    });

    function loadThemes() {
      if (!cfg.themesListUrl) return;
      themeGrid.innerHTML = '<div style="text-align:center;padding:40px;color:#888;grid-column:1/-1;">Loading themes…</div>';
      fetch(cfg.themesListUrl, {
        headers: { "X-CSRFToken": cfg.csrf, "X-Requested-With": "XMLHttpRequest" }
      })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        themeGrid.innerHTML = "";
        (data.themes || []).forEach(function (t) {
          var card = document.createElement("div");
          card.className = "theme-card";
          card.dataset.slug = t.slug;

          // Build a tiny preview by fetching the theme HTML and rendering in an iframe
          var previewDiv = document.createElement("div");
          previewDiv.className = "theme-card-preview";
          var previewFrame = document.createElement("iframe");
          previewFrame.setAttribute("sandbox", "allow-same-origin");
          previewFrame.setAttribute("loading", "lazy");
          previewDiv.appendChild(previewFrame);

          var bodyDiv = document.createElement("div");
          bodyDiv.className = "theme-card-body";
          bodyDiv.innerHTML =
            '<div class="theme-card-name">' + escHtml(t.name) + '</div>' +
            '<div class="theme-card-desc">' + escHtml(t.desc) + '</div>';

          var check = document.createElement("div");
          check.className = "theme-card-check";
          check.textContent = "✓";

          card.appendChild(previewDiv);
          card.appendChild(bodyDiv);
          card.appendChild(check);
          themeGrid.appendChild(card);

          // Load preview via the preview endpoint with the theme's HTML
          fetchThemeHtml(t.slug, function (html) {
            previewFrame.srcdoc = html;
          });

          card.addEventListener("click", function () {
            themeGrid.querySelectorAll(".theme-card").forEach(function (c) { c.classList.remove("selected"); });
            card.classList.add("selected");
            selectedTheme = t.slug;
            if (btnApply) btnApply.disabled = false;
          });
        });
      })
      .catch(function () {
        themeGrid.innerHTML = '<div style="text-align:center;padding:40px;color:#c0392b;grid-column:1/-1;">Could not load themes.</div>';
      });
    }

    function fetchThemeHtml(slug, cb) {
      if (!cfg.applyThemeUrl) return;
      fetch(cfg.applyThemeUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": cfg.csrf,
          "X-Requested-With": "XMLHttpRequest"
        },
        body: JSON.stringify({ theme: slug })
      })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d.html) cb(d.html);
      });
    }

    // Apply selected theme
    if (btnApply) {
      btnApply.addEventListener("click", function () {
        if (!selectedTheme) return;
        fetchThemeHtml(selectedTheme, function (html) {
          if (ta) ta.value = html;
          // Uncheck "use default" so the custom template is used
          if (useDefault && useDefault.checked) {
            useDefault.checked = false;
            syncDefault();
          }
          refresh();
          closeThemeModal();
        });
      });
    }

    function escHtml(s) {
      var d = document.createElement("div");
      d.textContent = s;
      return d.innerHTML;
    }
  });
})();
