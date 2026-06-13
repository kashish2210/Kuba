(function () {
  "use strict";

  function ready(fn) {
    if (document.readyState !== "loading") fn();
    else document.addEventListener("DOMContentLoaded", fn);
  }

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
      var ct = r.headers.get("content-type") || "";
      if (ct.indexOf("application/json") > -1) {
        return r.json().then(function (d) {
          if (!r.ok) throw (d && d.error ? d : { error: "Request failed" });
          return d;
        });
      }
      if (!r.ok) throw { error: "Request failed (" + r.status + ")" };
      return {};
    });
  }

  function money(n) { return "₹" + Number(n).toFixed(2); }

  function toast(msg) {
    var t = document.createElement("div");
    t.textContent = msg;
    t.style.cssText = "position:fixed;bottom:24px;left:50%;transform:translateX(-50%);background:#2c3e50;color:#fff;padding:12px 20px;border-radius:10px;z-index:300;font-weight:600;box-shadow:0 8px 24px rgba(0,0,0,.2)";
    document.body.appendChild(t);
    setTimeout(function () { t.remove(); }, 2200);
  }

  ready(function () {
    // Hamburger menu (present on every POS page)
    var burger = document.getElementById("pos-hamburger");
    var menu = document.getElementById("pos-menu");
    if (burger && menu) {
      burger.addEventListener("click", function (e) {
        e.stopPropagation();
        menu.hidden = !menu.hidden;
      });
      document.addEventListener("click", function () { menu.hidden = true; });
      menu.addEventListener("click", function (e) { e.stopPropagation(); });
    }

    var grid = document.getElementById("product-grid");
    if (!grid || !window.POS) return; // session screen, nothing more to wire

    var U = window.POS.urls;
    var order = null;
    var method = null;

    var $ = function (id) { return document.getElementById(id); };
    var orderUrl = function (suffix) { return U.orderRoot + order.id + "/" + (suffix || ""); };

    // ── Rendering ──────────────────────────────────────────────────────────
    function renderCart() {
      var lines = $("cart-lines");
      if (!order) {
        $("cart-order-no").textContent = "No order";
        $("table-label").textContent = "No table";
        lines.innerHTML = '<div class="cart-placeholder">Pick a table, then tap products to add them.</div>';
        setSummary(0, 0, 0, 0);
        $("pay-amount").textContent = money(0);
        return;
      }
      $("cart-order-no").textContent = order.order_number + (order.status === "sent_to_kitchen" ? " · sent" : "");
      $("table-label").textContent = order.table_number ? "Table " + order.table_number : "No table";
      if (!order.lines.length) {
        lines.innerHTML = '<div class="cart-placeholder">Tap products to add them.</div>';
      } else {
        lines.innerHTML = "";
        order.lines.forEach(function (ln) {
          var row = document.createElement("div");
          row.className = "cart-line";
          row.dataset.line = ln.id;
          row.innerHTML =
            '<div><div class="cl-name">' + ln.name + '</div><div class="cl-each">' + money(ln.unit_price) + " each</div></div>" +
            '<div class="cl-qty"><button data-act="dec">−</button><span>' + ln.quantity + '</span><button data-act="inc">+</button></div>' +
            '<div class="cl-total">' + money(ln.line_total) + "</div>" +
            '<button class="cl-remove" data-act="rm">×</button>';
          lines.appendChild(row);
        });
      }
      setSummary(order.subtotal, order.tax_amount, order.discount_amount, order.total);
      $("pay-amount").textContent = money(order.total);
      updatePayDetail();
    }

    function setSummary(sub, tax, disc, total) {
      $("sum-subtotal").textContent = money(sub);
      $("sum-tax").textContent = money(tax);
      $("sum-total").textContent = money(total);
      var row = $("cs-discount-row");
      if (disc && Number(disc) > 0) { row.hidden = false; $("sum-discount").textContent = "−" + money(disc); }
      else { row.hidden = true; }
    }

    function setOrder(data) { order = data; renderCart(); }

    // ── Products: filter + add ───────────────────────────────────────────────
    document.querySelectorAll(".cat-tab").forEach(function (tab) {
      tab.addEventListener("click", function () {
        document.querySelectorAll(".cat-tab").forEach(function (t) { t.classList.remove("active"); });
        tab.classList.add("active");
        var cat = tab.dataset.cat;
        document.querySelectorAll(".product-card").forEach(function (card) {
          card.style.display = (cat === "all" || card.dataset.cat === cat) ? "" : "none";
        });
      });
    });

    var search = $("product-search");
    if (search) {
      search.addEventListener("input", function () {
        var q = search.value.trim().toLowerCase();
        document.querySelectorAll(".product-card").forEach(function (card) {
          card.style.display = card.dataset.name.indexOf(q) > -1 ? "" : "none";
        });
      });
    }

    grid.addEventListener("click", function (e) {
      var card = e.target.closest(".product-card");
      if (!card) return;
      if (!order) { openFloor(); toast("Select a table first"); return; }
      api(orderUrl("line/"), "POST", { product: card.dataset.id }).then(setOrder).catch(showErr);
    });

    // ── Cart line qty / remove ───────────────────────────────────────────────
    $("cart-lines").addEventListener("click", function (e) {
      var btn = e.target.closest("button[data-act]");
      if (!btn || !order) return;
      var row = e.target.closest(".cart-line");
      var lid = row.dataset.line;
      var line = order.lines.find(function (l) { return String(l.id) === lid; });
      var qty = line ? line.quantity : 1;
      var act = btn.dataset.act;
      if (act === "inc") qty += 1;
      else if (act === "dec") qty -= 1;
      else if (act === "rm") qty = 0;
      api(U.orderRoot + order.id + "/line/" + lid + "/", "POST", { quantity: qty }).then(setOrder).catch(showErr);
    });

    // ── Cart actions ─────────────────────────────────────────────────────────
    $("btn-send-kitchen").addEventListener("click", function () {
      if (!order) return;
      api(orderUrl("send-kitchen/"), "POST").then(function (d) { setOrder(d); toast("Sent to kitchen ✓"); }).catch(showErr);
    });

    $("btn-discount").addEventListener("click", function () {
      if (!order) { openFloor(); toast("Select a table first"); return; }
      promptModal("Apply discount", [{ name: "amount", label: "Discount amount (₹)", type: "number" }], function (vals) {
        api(orderUrl("discount/"), "POST", { amount: vals.amount || 0 }).then(setOrder).catch(showErr);
      });
    });

    $("btn-customer").addEventListener("click", function () {
      if (!order) { openFloor(); toast("Select a table first"); return; }
      promptModal("Assign customer", [
        { name: "name", label: "Name", type: "text" },
        { name: "phone", label: "Phone (optional)", type: "text" },
        { name: "email", label: "Email (optional)", type: "email" },
      ], function (vals) {
        api(orderUrl("customer/"), "POST", vals).then(function (d) { setOrder(d); toast("Customer assigned"); }).catch(showErr);
      });
    });

    // ── Table / floor popup ───────────────────────────────────────────────────
    $("table-indicator").addEventListener("click", openFloor);
    $("floor-close").addEventListener("click", function () { $("floor-modal").hidden = true; });

    function openFloor() {
      var modal = $("floor-modal");
      modal.hidden = false;
      api(U.tables).then(function (data) {
        var tabs = $("floor-tabs"), gridEl = $("floor-grid");
        tabs.innerHTML = ""; gridEl.innerHTML = "";
        if (!data.floors.length) { gridEl.innerHTML = '<p class="pos-empty">No floors/tables yet — add them in the admin dashboard.</p>'; return; }
        data.floors.forEach(function (fl, i) {
          var tab = document.createElement("button");
          tab.className = "floor-tab" + (i === 0 ? " active" : "");
          tab.textContent = fl.name;
          tab.addEventListener("click", function () {
            tabs.querySelectorAll(".floor-tab").forEach(function (t) { t.classList.remove("active"); });
            tab.classList.add("active");
            renderTables(fl.tables);
          });
          tabs.appendChild(tab);
        });
        renderTables(data.floors[0].tables);
      }).catch(showErr);
    }

    function renderTables(tables) {
      var gridEl = $("floor-grid");
      gridEl.innerHTML = "";
      tables.forEach(function (t) {
        var cell = document.createElement("button");
        cell.className = "floor-table" + (t.occupied ? " occupied" : "");
        cell.innerHTML = t.number + "<small>" + t.seats + " seats</small>";
        cell.addEventListener("click", function () {
          api(U.orderStart, "POST", { table: t.id }).then(function (d) {
            setOrder(d);
            $("floor-modal").hidden = true;
          }).catch(showErr);
        });
        gridEl.appendChild(cell);
      });
    }

    // ── Payment ───────────────────────────────────────────────────────────────
    document.querySelectorAll(".pay-method").forEach(function (btn) {
      btn.addEventListener("click", function () {
        document.querySelectorAll(".pay-method").forEach(function (b) { b.classList.remove("active"); });
        btn.classList.add("active");
        method = btn.dataset.method;
        $("pay-method-label").textContent = method.toUpperCase();
        updatePayDetail();
      });
    });

    function updatePayDetail() {
      var box = $("pay-detail");
      if (!order || !method) { box.innerHTML = ""; return; }
      if (method === "cash") {
        box.innerHTML = '<input id="pay-input" inputmode="decimal" placeholder="Amount tendered"><div class="change" id="change"></div>';
        $("pay-input").addEventListener("input", updateChange);
      } else if (method === "upi") {
        box.innerHTML = '<img id="upi-qr" alt="UPI QR"><div style="text-align:center;color:#9a948c;font-size:.85rem;">Scan to pay ' + money(order.total) + "</div>";
        $("upi-qr").src = orderUrl("upi-qr/") + "?t=" + Date.now();
      } else if (method === "card") {
        box.innerHTML = '<input id="pay-input" placeholder="Transaction reference">';
      } else if (method === "razorpay") {
        box.innerHTML = '<div style="text-align:center;color:#9a948c;font-size:.85rem;">Pay online via Razorpay</div>';
      }
    }

    function updateChange() {
      var inp = $("pay-input"); var ch = $("change");
      if (!inp || !ch || !order) return;
      var diff = Number(inp.value || 0) - Number(order.total);
      ch.textContent = diff >= 0 ? "Change: " + money(diff) : "Short by " + money(-diff);
      ch.style.color = diff >= 0 ? "#34b27b" : "#e05a4d";
    }

    // Keypad → active payment input
    $("keypad").addEventListener("click", function (e) {
      var btn = e.target.closest("button");
      if (!btn) return;
      var inp = $("pay-input");
      if (btn.dataset.key !== undefined) {
        if (inp) { inp.value += btn.dataset.key; updateChange(); }
      } else if (btn.dataset.act === "clear") {
        if (inp) { inp.value = inp.value.slice(0, -1); updateChange(); }
      } else if (btn.dataset.act === "disc") {
        $("btn-discount").click();
      }
      // "prices" and "qty" are reserved for future use
    });

    $("btn-pay").addEventListener("click", function () {
      if (!order || !order.lines.length) { toast("Cart is empty"); return; }
      if (!method) { toast("Select a payment method"); return; }
      
      if (method === "razorpay") {
        api(orderUrl("razorpay/create/"), "POST", {}).then(function (data) {
          if (!window.POS.razorpayKeyId) {
            toast("Razorpay key missing");
            return;
          }
          var options = {
            "key": window.POS.razorpayKeyId,
            "amount": data.amount,
            "currency": data.currency,
            "name": window.POS.cafeName || "Cafe",
            "order_id": data.razorpay_order_id,
            "handler": function (response) {
              api(orderUrl("razorpay/verify/"), "POST", {
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_order_id: response.razorpay_order_id,
                razorpay_signature: response.razorpay_signature
              }).then(showReceipt).catch(showErr);
            },
            "theme": { "color": "#0d6efd" }
          };
          var rzp1 = new Razorpay(options);
          rzp1.on('payment.failed', function (response){
             toast("Payment failed: " + response.error.description);
          });
          rzp1.open();
        }).catch(showErr);
        return;
      }

      var body = { method_type: method };
      var inp = $("pay-input");
      if (method === "cash") body.amount_tendered = inp ? inp.value || 0 : 0;
      if (method === "card") body.transaction_ref = inp ? inp.value : "";
      api(orderUrl("pay/"), "POST", body).then(showReceipt).catch(showErr);
    });

    var paidOrderId = null;
    var paidCustomerEmail = "";
    function showReceipt(d) {
      paidOrderId = order ? order.id : null;
      paidCustomerEmail = d.customer_email || "";
      $("receipt-body").innerHTML =
        "<div>Order <strong>" + d.order_number + "</strong></div>" +
        "<div>Method: " + d.method.toUpperCase() + "</div>" +
        "<div>Tendered: " + money(d.amount_tendered) + "</div>" +
        (d.change_due ? "<div>Change due: " + money(d.change_due) + "</div>" : "") +
        '<div class="r-total">Paid ' + money(d.total) + "</div>" +
        (d.receipt_emailed ? '<div style="color:#34b27b;font-size:.85rem;margin-top:6px;">✓ Receipt emailed to ' + paidCustomerEmail + "</div>" : "");
      $("receipt-modal").hidden = false;
    }

    $("btn-email-receipt").addEventListener("click", function () {
      if (!paidOrderId) return;
      promptModal("Email receipt", [{ name: "email", label: "Send to", type: "email" }], function (vals) {
        var to = (vals.email || paidCustomerEmail || "").trim();
        if (!to) { toast("Enter an email address"); return; }
        api(U.orderRoot + paidOrderId + "/email-receipt/", "POST", { email: to })
          .then(function () { toast("Receipt sent to " + to); })
          .catch(showErr);
      });
    });

    $("btn-new-order").addEventListener("click", function () {
      $("receipt-modal").hidden = true;
      order = null; method = null;
      document.querySelectorAll(".pay-method").forEach(function (b) { b.classList.remove("active"); });
      $("pay-method-label").textContent = "";
      $("pay-detail").innerHTML = "";
      renderCart();
      openFloor();
    });

    // ── Generic prompt modal ──────────────────────────────────────────────────
    function promptModal(title, fields, onSubmit) {
      var modal = $("prompt-modal");
      $("prompt-title").textContent = title;
      var body = $("prompt-body");
      body.innerHTML = fields.map(function (f) {
        return '<div class="prompt-field"><label>' + f.label + '</label><input data-name="' + f.name + '" type="' + f.type + '"></div>';
      }).join("") + '<button class="pay-confirm" id="prompt-ok">Confirm</button>';
      modal.hidden = false;
      var first = body.querySelector("input"); if (first) first.focus();
      $("prompt-ok").onclick = function () {
        var vals = {};
        body.querySelectorAll("input").forEach(function (i) { vals[i.dataset.name] = i.value; });
        modal.hidden = true;
        onSubmit(vals);
      };
    }
    $("prompt-close").addEventListener("click", function () { $("prompt-modal").hidden = true; });

    function showErr(err) { toast((err && err.error) || "Something went wrong"); }

    // If redirected from the orders page with ?order=<id>, load that order directly.
    var _params = new URLSearchParams(window.location.search);
    var _editId = _params.get("order");
    if (_editId) {
      api(U.orderRoot + _editId + "/").then(function (data) {
        setOrder(data);
        toast("Editing " + data.order_number);
      }).catch(openFloor);
    } else {
      // Open the floor popup on first load so staff pick a table.
      openFloor();
    }
  });
})();
