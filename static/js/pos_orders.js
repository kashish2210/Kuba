(function () {
  "use strict";

  var U = window.POS_ORDERS.urls;
  var allOrders = [];
  var activeStatus = "all";
  var searchQuery = "";

  // ── Helpers ───────────────────────────────────────────────────────────────
  function getCookie(name) {
    var m = document.cookie.match("(^|;)\\s*" + name + "\\s*=\\s*([^;]+)");
    return m ? m.pop() : "";
  }

  function api(url, method, body) {
    return fetch(url, {
      method: method || "GET",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: body ? JSON.stringify(body) : undefined,
    }).then(function (r) {
      return r.json().then(function (d) {
        if (!r.ok) throw (d && d.error ? d : { error: "Request failed" });
        return d;
      });
    });
  }

  function money(n) {
    return "₹" + Number(n).toFixed(2);
  }

  function statusBadge(s) {
    var map = {
      draft:           ["Draft",     "ord-status-draft"],
      sent_to_kitchen: ["Sent",      "ord-status-sent"],
      paid:            ["Paid",      "ord-status-paid"],
      cancelled:       ["Cancelled", "ord-status-cancelled"],
    };
    var m = map[s] || [s, "ord-status-draft"];
    return '<span class="ord-status-badge ' + m[1] + '">' + m[0] + "</span>";
  }

  function toast(msg, isErr) {
    var t = document.createElement("div");
    t.className = "pos-toast" + (isErr ? " pos-toast-err" : "");
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(function () { t.classList.add("pos-toast-show"); }, 10);
    setTimeout(function () { t.classList.remove("pos-toast-show"); setTimeout(function () { t.remove(); }, 300); }, 2500);
  }

  // ── Filter & search ───────────────────────────────────────────────────────
  function applyFilters() {
    var q = searchQuery.toLowerCase();
    return allOrders.filter(function (o) {
      var matchStatus = activeStatus === "all" || o.status === activeStatus;
      var matchSearch = !q ||
        o.number.toLowerCase().indexOf(q) > -1 ||
        (o.customer || "").toLowerCase().indexOf(q) > -1 ||
        (o.date || "").toLowerCase().indexOf(q) > -1 ||
        (o.table || "").toString().toLowerCase().indexOf(q) > -1;
      return matchStatus && matchSearch;
    });
  }

  // ── Render table ──────────────────────────────────────────────────────────
  function renderTable() {
    var filtered = applyFilters();
    var tbody = document.getElementById("orders-tbody");
    var emptyState = document.getElementById("orders-empty");
    var tableWrap = document.querySelector(".orders-table-wrap");

    if (allOrders.length === 0) {
      tbody.innerHTML = "";
      if (tableWrap) tableWrap.style.display = "none";
      emptyState.style.display = "flex";
      var emptySub = document.getElementById("orders-empty-sub");
      if (emptySub) {
        emptySub.textContent = "No orders in this session yet. Start taking orders from the POS terminal.";
      }
      return;
    }

    if (tableWrap) tableWrap.style.display = "";
    emptyState.style.display = "none";
    tbody.innerHTML = "";

    if (!filtered.length) {
      var tr = document.createElement("tr");
      tr.innerHTML = '<td colspan="6" style="text-align:center;padding:48px 24px;color:#9a948c;font-weight:500;">No orders match your search or filter.</td>';
      tbody.appendChild(tr);
      return;
    }

    filtered.forEach(function (o) {
      var tr = document.createElement("tr");
      tr.className = "orders-row";
      tr.innerHTML =
        "<td><span class='ord-date'>" + o.date + "</span></td>" +
        "<td><span class='ord-number-cell'>" + o.number + "</span></td>" +
        "<td><span class='ord-customer-cell'>" + (o.customer || "<span class='ord-walkin'>Walk-in</span>") + "</span></td>" +
        "<td><span class='ord-table-cell'>" + (o.table ? "Table " + o.table : "—") + "</span></td>" +
        "<td><span class='ord-amount-cell'>" + money(o.total) + "</span></td>" +
        "<td>" + statusBadge(o.status) + "</td>";
      tr.addEventListener("click", function () { openDetail(o.id); });
      tbody.appendChild(tr);
    });
  }

  // ── Load orders from API ──────────────────────────────────────────────────
  function loadOrders() {
    api(U.ordersData).then(function (d) {
      allOrders = d.orders || [];
      renderTable();
    }).catch(function () {
      toast("Could not load orders.", true);
    });
  }

  // ── Search input ──────────────────────────────────────────────────────────
  var searchInput = document.getElementById("order-search");
  if (searchInput) {
    searchInput.addEventListener("input", function () {
      searchQuery = this.value.trim();
      renderTable();
    });
  }

  // ── Status filter tabs ────────────────────────────────────────────────────
  document.querySelectorAll(".ofilter-tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      document.querySelectorAll(".ofilter-tab").forEach(function (t) {
        t.classList.remove("active");
      });
      tab.classList.add("active");
      activeStatus = tab.dataset.status;
      renderTable();
    });
  });

  // ── Detail modal ──────────────────────────────────────────────────────────
  function openDetail(orderId) {
    var modal = document.getElementById("order-detail-modal");
    modal.hidden = false;

    // Reset state
    document.getElementById("ord-detail-title").textContent = "Loading…";
    document.getElementById("ord-detail-date").textContent = "—";
    document.getElementById("ord-detail-customer").textContent = "—";
    document.getElementById("ord-detail-amount").textContent = "—";
    document.getElementById("ord-detail-status").innerHTML = "";
    document.getElementById("ord-detail-products").innerHTML = "<div class='ord-products-loading'>Loading…</div>";
    document.getElementById("ord-detail-totals").innerHTML = "";
    document.getElementById("ord-detail-actions").innerHTML = "";

    api(U.orderRoot + orderId + "/").then(function (order) {
      // Header
      document.getElementById("ord-detail-title").textContent = "Order " + order.order_number;

      // Meta
      document.getElementById("ord-detail-date").textContent = order.created_at || "—";
      document.getElementById("ord-detail-customer").textContent =
        order.customer ? order.customer.name : "Walk-in";
      document.getElementById("ord-detail-amount").textContent = money(order.total);
      document.getElementById("ord-detail-status").innerHTML = statusBadge(order.status);

      // Table
      var tableRow = document.getElementById("ord-detail-table-row");
      var tableText = document.getElementById("ord-detail-table-text");
      if (order.table_number) {
        tableText.textContent = "Table " + order.table_number;
        tableRow.hidden = false;
      } else {
        tableRow.hidden = true;
      }

      // Products
      var prodsEl = document.getElementById("ord-detail-products");
      if (order.lines && order.lines.length) {
        prodsEl.innerHTML = order.lines.map(function (l) {
          return (
            '<div class="ord-prod-row">' +
              '<div class="ord-prod-left">' +
                '<span class="ord-prod-qty">' + l.quantity + '×</span>' +
                '<span class="ord-prod-name">' + l.name + '</span>' +
              "</div>" +
              '<span class="ord-prod-price">' + money(l.line_total) + "</span>" +
            "</div>"
          );
        }).join("");
      } else {
        prodsEl.innerHTML = '<p class="ord-no-products">No products on this order.</p>';
      }

      // Totals
      var totalsEl = document.getElementById("ord-detail-totals");
      var discRow = Number(order.discount_amount) > 0
        ? '<div class="ord-total-row"><span>Discount</span><span class="ord-discount-val">−' + money(order.discount_amount) + "</span></div>"
        : "";
      totalsEl.innerHTML =
        '<div class="ord-total-row"><span>Subtotal</span><span>' + money(order.subtotal) + "</span></div>" +
        '<div class="ord-total-row"><span>Tax (GST)</span><span>' + money(order.tax_amount) + "</span></div>" +
        discRow +
        '<div class="ord-total-row ord-grand-total"><span>Total</span><span>' + money(order.total) + "</span></div>";

      // Actions — only for DRAFT orders
      var actionsEl = document.getElementById("ord-detail-actions");
      if (order.status === "draft") {
        var delBtn = document.createElement("button");
        delBtn.className = "ord-action-btn ord-action-delete";
        delBtn.innerHTML =
          '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px;vertical-align:-2px;"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/></svg>' +
          "Delete";
        delBtn.addEventListener("click", function () { confirmCancel(order.id, order.order_number); });

        var editBtn = document.createElement("button");
        editBtn.className = "ord-action-btn ord-action-edit";
        editBtn.innerHTML =
          '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" style="margin-right:6px;vertical-align:-2px;"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>' +
          "Edit Order";
        editBtn.addEventListener("click", function () {
          window.location = U.terminal + "?order=" + order.id;
        });

        actionsEl.appendChild(delBtn);
        actionsEl.appendChild(editBtn);
      }
    }).catch(function () {
      toast("Could not load order details.", true);
      document.getElementById("order-detail-modal").hidden = true;
    });
  }

  // ── Cancel / delete ───────────────────────────────────────────────────────
  function confirmCancel(orderId, orderNumber) {
    // Use a small inline confirm inside the modal instead of browser confirm()
    var actionsEl = document.getElementById("ord-detail-actions");
    actionsEl.innerHTML =
      '<div class="ord-confirm-row">' +
        '<span class="ord-confirm-msg">Cancel <strong>' + orderNumber + '</strong>?</span>' +
        '<button class="ord-action-btn ord-action-confirm-yes" id="confirm-yes">Yes, cancel</button>' +
        '<button class="ord-action-btn ord-action-confirm-no" id="confirm-no">Keep</button>' +
      '</div>';

    document.getElementById("confirm-yes").addEventListener("click", function () {
      api(U.orderRoot + orderId + "/cancel/", "POST")
        .then(function () {
          document.getElementById("order-detail-modal").hidden = true;
          toast("Order cancelled.");
          loadOrders();
        })
        .catch(function (err) {
          toast((err && err.error) || "Could not cancel order.", true);
        });
    });

    document.getElementById("confirm-no").addEventListener("click", function () {
      // Reload the detail to restore the normal buttons
      openDetail(orderId);
    });
  }

  // ── Modal close ───────────────────────────────────────────────────────────
  document.getElementById("ord-detail-close").addEventListener("click", function () {
    document.getElementById("order-detail-modal").hidden = true;
  });
  document.getElementById("order-detail-modal").addEventListener("click", function (e) {
    if (e.target === this) this.hidden = true;
  });

  // ── Auto-refresh every 15 s ───────────────────────────────────────────────
  setInterval(loadOrders, 15000);

  // ── Init ──────────────────────────────────────────────────────────────────
  document.addEventListener("DOMContentLoaded", function () {
    loadOrders();
    var tableInd = document.getElementById("table-indicator");
    if (tableInd) {
      tableInd.addEventListener("click", function () {
        window.location.href = U.terminal;
      });
    }
  });
})();
