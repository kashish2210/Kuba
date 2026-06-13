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
  });
})();
