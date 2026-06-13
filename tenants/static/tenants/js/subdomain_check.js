// Live subdomain availability check on the Cafe admin add/change form.
(function () {
  "use strict";
  document.addEventListener("DOMContentLoaded", function () {
    var input = document.getElementById("id_subdomain");
    if (!input) return;

    // Endpoint is registered at /admin/<app>/cafe/check-subdomain/.
    var path = window.location.pathname;
    var base = path.split("/cafe/")[0] + "/cafe/check-subdomain/";

    // Try to exclude the current object (change form: /cafe/<pk>/change/).
    var m = path.match(/\/cafe\/(\d+)\/change\//);
    var excludePk = m ? m[1] : null;

    var status = document.createElement("div");
    status.style.marginTop = "6px";
    status.style.fontWeight = "600";
    status.style.fontSize = "0.85rem";
    input.parentNode.appendChild(status);

    var timer = null;
    function check() {
      var value = input.value.trim();
      if (!value) {
        status.textContent = "Leave blank to auto-generate a subdomain.";
        status.style.color = "#6b7280";
        return;
      }
      var url = base + "?value=" + encodeURIComponent(value);
      if (excludePk) url += "&exclude=" + excludePk;
      status.textContent = "Checking…";
      status.style.color = "#6b7280";
      fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          status.textContent = (data.available ? "✓ " : "✗ ") + data.reason +
            (data.normalized && data.normalized !== value ? " (will be saved as “" + data.normalized + "”)" : "");
          status.style.color = data.available ? "#15803d" : "#b91c1c";
        })
        .catch(function () {
          status.textContent = "";
        });
    }

    input.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(check, 300);
    });
    check();
  });
})();
