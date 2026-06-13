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
  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch];
    });
  }

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
          
          var discountHtml = "";
          if (ln.line_discount && Number(ln.line_discount) > 0) {
              discountHtml = '<div style="grid-column: 1 / -1; font-size: 0.75rem; color: #e74c3c; border: 1px solid #fad6d3; background: #fff; padding: 2px 6px; border-radius: 4px; margin-top: 4px;">Discount: ' + money(ln.line_discount) + ' off</div>';
          }
          
          row.innerHTML =
            '<div><div class="cl-name">' + ln.name + '</div><div class="cl-each">' + money(ln.unit_price) + " each</div></div>" +
            '<div class="cl-qty"><button data-act="dec">−</button><span>' + ln.quantity + '</span><button data-act="inc">+</button></div>' +
            '<div class="cl-total">' + money(ln.line_total) + "</div>" +
            '<button class="cl-remove" data-act="rm">×</button>' + discountHtml;
          lines.appendChild(row);
        });
      }
      setSummary(order.subtotal, order.tax_amount, order.discount_amount, order.total, order.coupon_desc);
      $("pay-amount").textContent = money(order.total);
      updatePayDetail();

      var btnCust = $("btn-customer");
      if (btnCust) {
        if (order.customer) {
          var loyaltyLabel = order.customer.loyalty ? ' · L' + order.customer.loyalty.level : '';
          btnCust.innerHTML = '👤 ' + esc(order.customer.name) + loyaltyLabel + ' <span class="cust-remove-cross" title="Remove customer">✕</span>';
          btnCust.classList.add("cust-assigned");
        } else {
          btnCust.innerHTML = '👤 Customer';
          btnCust.classList.remove("cust-assigned");
        }
      }
    }

    function setSummary(sub, tax, disc, total, couponDesc) {
      $("sum-subtotal").textContent = money(sub);
      $("sum-tax").textContent = money(tax);
      $("sum-total").textContent = money(total);
      var row = $("cs-discount-row");
      if (disc && Number(disc) > 0) { 
          row.hidden = false; 
          var desc = couponDesc ? "(" + couponDesc + ")" : "";
          $("sum-discount").textContent = "− " + money(disc) + desc; 
      }
      else { row.hidden = true; }
    }

    function setOrder(data) {
      order = data;
      renderCart();
      autoApplyPromotion();
    }

    function autoApplyPromotion() {
      if (!order) return;
      /* Don't override a manually applied coupon or manual discount */
      if (order.coupon_id || (order.promotion_id && !order._auto_promo)) return;
      var promos = (window.POS.promotions || []).filter(function(p) {
        if (p.apply_to === 'order') {
          return p.min_order_amount !== null && order.subtotal >= p.min_order_amount;
        }
        if (p.apply_to === 'product') {
          var qty = (order.lines || [])
            .filter(function(l) { return l.product_id === p.product_id; })
            .reduce(function(s, l) { return s + l.quantity; }, 0);
          return p.min_quantity !== null && qty >= p.min_quantity;
        }
        return false;
      });
      if (!promos.length) {
        /* clear auto-promo if conditions no longer met */
        if (order.promotion_id && order.discount_amount > 0) {
          api(orderUrl("discount/"), "POST", { amount: 0 }).then(function(d) {
            order = d; renderCart();
          }).catch(function(){});
        }
        return;
      }
      /* pick best: highest potential discount */
      promos.sort(function(a, b) {
        var da = a.discount_type === 'percentage' ? order.subtotal * a.discount_value / 100 : a.discount_value;
        var db = b.discount_type === 'percentage' ? order.subtotal * b.discount_value / 100 : b.discount_value;
        return db - da;
      });
      var best = promos[0];
      if (order.promotion_id === best.id) return; /* already applied */
      api(orderUrl("discount/"), "POST", { promotion_id: best.id }).then(function(d) {
        d._auto_promo = true;
        order = d; renderCart();
      }).catch(function(){});
    }

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
      api(orderUrl("line/"), "POST", { product: card.dataset.id }).then(function(res) {
          setOrder(res);
          showCrossSells(card.dataset.crossSells);
      }).catch(showErr);
    });

    function showCrossSells(crossSellsStr) {
      var container = $("cross-sell-container");
      var items = $("cross-sell-items");
      if (!container || !items) return;
      
      if (!crossSellsStr) {
          container.style.display = "none";
          return;
      }
      
      var ids = crossSellsStr.split(",");
      items.innerHTML = "";
      var found = 0;
      ids.forEach(function(id) {
          var pCard = document.querySelector('.product-card[data-id="' + id + '"]');
          if (pCard) {
              var btn = document.createElement("button");
              btn.className = "btn btn-sm btn-secondary";
              btn.style.whiteSpace = "nowrap";
              btn.style.padding = "4px 10px";
              btn.textContent = "+ " + pCard.querySelector(".pc-name").textContent;
              btn.onclick = function() {
                  api(orderUrl("line/"), "POST", { product: id }).then(function(res) {
                      setOrder(res);
                      toast("Added " + btn.textContent.replace("+ ", ""));
                  }).catch(showErr);
              };
              items.appendChild(btn);
              found++;
          }
      });
      
      if (found > 0) {
          container.style.display = "block";
      } else {
          container.style.display = "none";
      }
    }

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

      var modal = $("prompt-modal");
      $("prompt-title").textContent = "Apply Discount";
      var body = $("prompt-body");

      var html = '<div class="prompt-field"><label style="font-weight:600;font-size:0.8rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;">Coupon Code</label>';
      html += '<input id="disc-coupon" type="text" class="form-input" placeholder="Enter Coupon Code" style="text-transform:uppercase;margin-top:6px;" autocomplete="off">';
      html += '</div>';

      var promos = window.POS.promotions || [];
      if (promos.length > 0) {
        html += '<div style="margin:12px 0 8px;font-weight:600;font-size:0.8rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;">Automated Promotions</div>';
        html += '<div id="disc-promo-list" style="display:flex;flex-direction:column;gap:6px;">';
        promos.forEach(function (p) {
          var desc = p.discount_value + (p.discount_type === "percentage" ? "%" : "₹") + " Discount";
          var cond = p.apply_to === "order"
            ? "Orders ≥ ₹" + p.min_order_amount
            : "Min " + p.min_quantity + "× " + (p.product_name || "product");
          html += '<label style="display:flex;align-items:center;gap:10px;padding:10px 12px;border:1px solid var(--border);border-radius:var(--radius);cursor:pointer;" class="disc-promo-row">';
          html += '<input type="radio" name="disc-promo" value="' + p.id + '" style="accent-color:var(--primary);">';
          html += '<span><strong>' + desc + '</strong><br><span style="font-size:0.78rem;color:var(--muted);">' + cond + '</span></span>';
          html += '</label>';
        });
        html += '</div>';
      }

      html += '<div style="margin:12px 0 8px;font-weight:600;font-size:0.8rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;">Manual Amount (₹)</div>';
      html += '<input id="disc-amount" type="number" class="form-input" placeholder="0" min="0" style="margin-bottom:14px;">';
      html += '<button class="pay-confirm" id="prompt-ok">Enter</button>';

      body.innerHTML = html;
      modal.hidden = false;

      /* clear promo selection when coupon or manual amount is typed */
      body.querySelector("#disc-coupon").addEventListener("input", function () {
        if (this.value) body.querySelectorAll("input[name='disc-promo']").forEach(function (r) { r.checked = false; });
      });
      body.querySelector("#disc-amount").addEventListener("input", function () {
        if (this.value) body.querySelectorAll("input[name='disc-promo']").forEach(function (r) { r.checked = false; });
      });

      $("prompt-ok").onclick = function () {
        var cpn = body.querySelector("#disc-coupon").value.trim();
        var amt = body.querySelector("#disc-amount").value;
        var promoRadio = body.querySelector("input[name='disc-promo']:checked");
        modal.hidden = true;
        var payload = {};
        if (cpn) {
          payload.coupon_code = cpn;
        } else if (promoRadio) {
          payload.promotion_id = parseInt(promoRadio.value, 10);
        } else {
          payload.amount = amt || 0;
        }
        api(orderUrl("discount/"), "POST", payload).then(setOrder).catch(showErr);
      };
    });

    // ── Dedicated Customer Modal logic ──────────────────────────────────────
    var custModal = $("customer-modal");
    var custListView = $("customer-list-view");
    var custFormView = $("customer-form-view");
    var custSearchInp = $("cust-search-input");
    var custListContainer = $("customer-list-container");
    
    $("btn-customer").addEventListener("click", function (e) {
      if (!order) { openFloor(); toast("Select a table first"); return; }
      
      // If clicked the cancel cross, unassign customer
      if (e.target.classList.contains("cust-remove-cross")) {
        e.stopPropagation();
        e.preventDefault();
        api(orderUrl("customer/"), "POST", { customer_id: "" }).then(function(newOrder) {
          setOrder(newOrder);
          toast("Customer removed");
        }).catch(showErr);
        return;
      }
      
      openCustomerModal();
    });

    $("cust-modal-close").addEventListener("click", closeCustomerModal);
    
    // Wire search input
    custSearchInp.addEventListener("input", function() {
      fetchCustomers(this.value.trim());
    });

    // Trigger adding customer
    $("cust-add-trigger").addEventListener("click", function() {
      openCustomerForm(null);
    });

    // Close form / discard
    $("cust-form-close").addEventListener("click", function() {
      showCustomerListMode();
    });
    $("cust-form-discard").addEventListener("click", function() {
      showCustomerListMode();
    });

    // Save Customer Form
    $("cust-form-save").addEventListener("click", function() {
      var id = $("cust-edit-id").value;
      var name = $("cust-form-name").value.trim();
      var email = $("cust-form-email").value.trim();
      var phone = $("cust-form-phone").value.trim();

      if (!name) { toast("Customer name is required"); return; }

      // Validate 10-digit number and auto prepend +91
      if (phone !== "") {
        var rawPhone = phone.replace(/\D/g, ""); // strip all non-digits
        // If they prefixed 91, strip it to check for 10 digits
        if (rawPhone.startsWith("91") && rawPhone.length === 12) {
          rawPhone = rawPhone.substring(2);
        }
        if (rawPhone.length !== 10) {
          toast("Phone number must be exactly 10 digits");
          return;
        }
        phone = "+91 " + rawPhone;
      }

      var payload = { name: name, email: email, phone: phone };
      var url = "/pos/customers/create/";
      if (id) {
        url = "/pos/customers/" + id + "/edit/";
      }

      api(url, "POST", payload).then(function(c) {
        // Automatically assign saved customer to order
        api(orderUrl("customer/"), "POST", { customer_id: c.id }).then(function(newOrder) {
          setOrder(newOrder);
          toast("Customer assigned ✓");
          closeCustomerModal();
        }).catch(showErr);
      }).catch(showErr);
    });

    // Delete Customer
    $("cust-form-delete").addEventListener("click", function() {
      var id = $("cust-edit-id").value;
      if (!id) return;
      if (!confirm("Are you sure you want to delete this customer?")) return;

      api("/pos/customers/" + id + "/delete/", "POST").then(function() {
        toast("Customer deleted");
        showCustomerListMode();
      }).catch(showErr);
    });

    function openCustomerModal() {
      custSearchInp.value = "";
      showCustomerListMode();
      custModal.hidden = false;
    }

    function closeCustomerModal() {
      custModal.hidden = true;
    }

    function showCustomerListMode() {
      custListView.hidden = false;
      custFormView.hidden = true;
      fetchCustomers("");
    }

    function openCustomerForm(customer) {
      custListView.hidden = true;
      custFormView.hidden = false;
      
      if (customer) {
        $("cust-form-title").textContent = "Edit Customer";
        $("cust-edit-id").value = customer.id;
        $("cust-form-name").value = customer.name;
        $("cust-form-email").value = customer.email;
        $("cust-form-phone").value = customer.phone;
        $("cust-form-delete").hidden = false;
      } else {
        $("cust-form-title").textContent = "Add Customer";
        $("cust-edit-id").value = "";
        $("cust-form-name").value = "";
        $("cust-form-email").value = "";
        $("cust-form-phone").value = "";
        $("cust-form-delete").hidden = true;
      }
    }

    function fetchCustomers(q) {
      api("/pos/customers/?q=" + encodeURIComponent(q)).then(function(data) {
        renderCustomerList(data.customers || []);
      }).catch(showErr);
    }

    function renderCustomerList(list) {
      custListContainer.innerHTML = "";
      if (!list.length) {
        custListContainer.innerHTML = '<div style="padding:24px;text-align:center;color:var(--muted);font-weight:500;">No customers found.</div>';
        return;
      }

      list.forEach(function(c) {
        var row = document.createElement("div");
        row.className = "cust-row" + (c.is_banned ? " cust-row-banned" : "");
        var loyalty = c.loyalty || { level: 0, points: 0, paid_orders: 0, next_level_orders: null };
        var nextLevel = loyalty.next_level_orders
          ? '<span class="cust-loyalty-next">Next at ' + loyalty.next_level_orders + '</span>'
          : '<span class="cust-loyalty-next">Top level</span>';
        var banHtml = c.is_banned
          ? '<div class="cust-ban-note">Banned' + (c.ban_reason ? ': ' + esc(c.ban_reason) : '') + '</div>'
          : '';
        
        var content = 
          '<div class="cust-row-left">' +
            '<div>' + esc(c.name) + '</div>' +
            '<div class="cust-loyalty-line">' +
              '<span class="cust-level-badge level-' + loyalty.level + '">Level ' + loyalty.level + '</span>' +
              '<span>' + loyalty.points + ' pts</span>' +
              '<span>' + loyalty.paid_orders + ' orders</span>' +
              nextLevel +
            '</div>' +
            banHtml +
          '</div>' +
          '<div class="cust-row-mid">' +
            '<div class="cust-meta-item">' +
              '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>' +
              '<span>' + esc(c.email) + '</span>' +
            '</div>' +
            (c.phone ? 
            '<div class="cust-meta-item">' +
              '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg>' +
              '<span>' + esc(c.phone) + '</span>' +
            '</div>' : '') +
          '</div>' +
          '<div class="cust-row-right">' +
            '<button class="cust-dots" title="Edit">⋮</button>' +
            '<div class="cust-actions-pop" id="pop-' + c.id + '">' +
              '<button class="cust-action-opt" id="edit-opt-' + c.id + '">Edit</button>' +
            '</div>' +
          '</div>';

        row.innerHTML = content;

        // Click row to assign customer to order
        row.addEventListener("click", function(e) {
          if (e.target.closest(".cust-dots") || e.target.closest(".cust-actions-pop")) {
            return;
          }
          if (c.is_banned) {
            toast("This customer is banned");
            return;
          }
          api(orderUrl("customer/"), "POST", { customer_id: c.id }).then(function(newOrder) {
            setOrder(newOrder);
            toast("Customer assigned ✓");
            closeCustomerModal();
          }).catch(showErr);
        });

        // Click three dots to open Popover edit menu
        var dots = row.querySelector(".cust-dots");
        var pop = row.querySelector(".cust-actions-pop");
        dots.addEventListener("click", function(e) {
          e.stopPropagation();
          // Hide all other open popovers first
          document.querySelectorAll(".cust-actions-pop").forEach(function(p) {
            if (p !== pop) p.classList.remove("show");
          });
          pop.classList.toggle("show");
        });

        // Edit option click handler
        row.querySelector("#edit-opt-" + c.id).addEventListener("click", function(e) {
          e.stopPropagation();
          pop.classList.remove("show");
          openCustomerForm(c);
        });

        custListContainer.appendChild(row);
      });
    }

    // Close any open popovers when clicking outside
    document.addEventListener("click", function() {
      document.querySelectorAll(".cust-actions-pop").forEach(function(pop) {
        pop.classList.remove("show");
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
            renderTables(fl);
          });
          tabs.appendChild(tab);
        });
        renderTables(data.floors[0]);
      }).catch(showErr);
    }

    function renderTables(floor) {
      var gridEl = $("floor-grid");
      gridEl.innerHTML = "";
      
      if (floor.canvas_mode) {
          gridEl.style.display = "block";
          gridEl.style.position = "relative";
          gridEl.style.height = "600px";
          gridEl.style.background = "#f9f8f6";
          gridEl.style.backgroundImage = "linear-gradient(rgba(0,0,0,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(0,0,0,0.05) 1px, transparent 1px)";
          gridEl.style.backgroundSize = "20px 20px";
          gridEl.style.border = "1px solid var(--border)";
          gridEl.style.borderRadius = "8px";
          gridEl.style.overflow = "auto";
      } else {
          gridEl.style = ""; // Reset styles
      }
      
      floor.tables.forEach(function (t) {
        var cell = document.createElement("div");
        cell.className = "floor-table" + (t.locked ? " locked" : t.occupied ? " occupied" : "");
        cell.title = t.locked ? "Table locked — guests still dining. Click to unlock." : t.occupied ? "Has active order" : "";
        
        if (floor.canvas_mode) {
            cell.style.position = "absolute";
            cell.style.left = t.pos_x + "px";
            cell.style.top = t.pos_y + "px";
            cell.style.width = Math.max(40, t.width) + "px";
            cell.style.height = Math.max(40, t.height) + "px";
            cell.style.margin = "0"; // Override grid margins
            cell.style.padding = "4px"; // Reduce padding for small custom sizes
            cell.style.borderRadius = (t.shape === "circle") ? "50%" : "8px";
        }

        if (t.locked) {
          cell.innerHTML =
            t.number + "<small>" + t.seats + " seats</small>" +
            "<button class=\"floor-unlock-btn\" title=\"Mark table as empty\"><svg viewBox=\"0 0 24 24\" width=\"12\" height=\"12\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2.5\" stroke-linecap=\"round\" stroke-linejoin=\"round\" style=\"vertical-align: middle; margin-right: 3px;\"><rect x=\"3\" y=\"11\" width=\"18\" height=\"11\" rx=\"2\" ry=\"2\"></rect><path d=\"M7 11V7a5 5 0 0 1 9.9-1\"></path></svg> Unlock</button>";
          cell.querySelector(".floor-unlock-btn").addEventListener("click", function (e) {
            e.stopPropagation();
            
            var modal = $("prompt-modal");
            $("prompt-title").textContent = "Unlock Table " + t.number;
            
            var html = '<p style="margin:0 0 16px;font-size:0.95rem;color:var(--muted);">Mark Table ' + t.number + ' as empty and unlock it?</p>';
            if (t.has_reviewed) {
                html += '<div style="padding:10px;background:#e7f6ec;color:#15803d;border-radius:8px;font-size:0.85rem;margin-bottom:16px;">✓ This customer has already submitted a review.</div>';
            }
            html += '<div class="prompt-field"><label style="font-weight:600;font-size:0.8rem;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;">Customer Email (Feedback Request)</label>';
            html += '<input id="unlock-email" type="email" class="form-input" placeholder="Optional" value="' + (t.customer_email || "") + '" style="margin-top:6px;" autocomplete="off">';
            html += '<p style="font-size:0.75rem;color:var(--muted);margin-top:6px;">If provided, we will send an email requesting feedback from the customer.</p></div>';
            html += '<button class="pay-confirm" id="unlock-ok" style="margin-top:16px;">Unlock Table</button>';
            
            $("prompt-body").innerHTML = html;
            modal.hidden = false;
            
            $("unlock-email").focus();
            
            $("unlock-ok").onclick = function() {
                var email = $("unlock-email").value.trim();
                modal.hidden = true;
                
                var url = U.tableRelease.replace("__pk__", t.id);
                api(url, "POST", { email_customer: email }).then(function () {
                  toast("Table " + t.number + " unlocked");
                  openFloor();
                }).catch(showErr);
            };
          });
          cell.addEventListener("click", function () {
            api(U.orderStart, "POST", { table: t.id, current_order: order ? order.id : null }).then(function (d) {
              setOrder(d);
              $("floor-modal").hidden = true;
            }).catch(showErr);
          });
        } else {
          cell.innerHTML = t.number + "<small>" + t.seats + " seats</small>";
          cell.addEventListener("click", function () {
            api(U.orderStart, "POST", { table: t.id, current_order: order ? order.id : null }).then(function (d) {
              setOrder(d);
              $("floor-modal").hidden = true;
            }).catch(showErr);
          });
        }

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
      var keypad = $("keypad");
      if (keypad) keypad.style.display = "grid";

      if (!order || !method) { box.innerHTML = ""; return; }

      var backHtml = '<div class="pay-detail-back-wrap"><button class="pay-detail-back" id="pay-back-btn">← Back to Payment Methods</button></div>';

      if (method === "cash") {
        box.innerHTML = backHtml + '<div class="cash-pay-wrap"><input id="pay-input" inputmode="decimal" placeholder="Amount tendered"><div class="change" id="change"></div></div>';
        $("pay-input").addEventListener("input", updateChange);
      } else if (method === "upi") {
        if (keypad) keypad.style.display = "none";

        var html = 
          backHtml +
          '<div class="upi-card-minimal">' +
            '<div class="upi-qr-box-minimal">' +
              '<img id="upi-qr" class="upi-qr-img-minimal" alt="UPI QR">' +
            '</div>' +
            '<div class="upi-details-minimal">' +
              '<div class="upi-status-minimal">Scan to pay · ₹' + (order ? Number(order.total).toFixed(2) : '0.00') + '</div>' +
            '</div>' +
          '</div>';

        box.innerHTML = html;
        $("upi-qr").src = orderUrl("upi-qr/") + "?t=" + Date.now();

        // Show green "Paid" button immediately when QR is displayed
        var payBtn = $("btn-pay");
        if (payBtn) {
          payBtn.textContent = "✔ Paid";
          payBtn.style.background = "#2e7d5e";
          payBtn.style.color = "#fff";
          payBtn.style.pointerEvents = "auto";
        }
      } else if (method === "card" || method === "razorpay") {
        box.innerHTML = backHtml + '<div style="text-align:center;color:#9a948c;font-size:.85rem;padding: 16px 0;">Pay online via Razorpay</div>';
      }

      // Attach back arrow handler
      var backBtn = $("pay-back-btn");
      if (backBtn) {
        backBtn.addEventListener("click", function () {
          method = null;
          document.querySelectorAll(".pay-method").forEach(function (b) { b.classList.remove("active"); });
          $("pay-method-label").textContent = "";
          box.innerHTML = "";
          if (keypad) keypad.style.display = "grid";
          // Reset Pay button
          var payBtn = $("btn-pay");
          if (payBtn) {
            payBtn.textContent = "Pay";
            payBtn.style.background = "";
            payBtn.style.color = "";
          }
        });
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
      if (!order.customer || !order.customer.name || !order.customer.email) {
          toast("Customer Name & Email are required for receipts!");
          $("btn-customer").click();
          return;
      }

      // UPI: show confirmation popup before marking paid
      if (method === "upi") {
        $("upi-confirm-modal").hidden = false;
        return;
      }

      if (method === "razorpay" || method === "card") {
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
      api(orderUrl("pay/"), "POST", body).then(showReceipt).catch(showErr);
    });

    // UPI confirmation modal
    $("upi-confirm-yes").addEventListener("click", function () {
      $("upi-confirm-modal").hidden = true;
      api(orderUrl("pay/"), "POST", { method_type: "upi" }).then(showReceipt).catch(showErr);
    });
    $("upi-confirm-no").addEventListener("click", function () {
      $("upi-confirm-modal").hidden = true;
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

      // For UPI: hide the email receipt button
      var emailBtn = $("btn-email-receipt");
      if (emailBtn) emailBtn.hidden = (d.method === "upi");

      // Lock the Pay button
      var payBtn = $("btn-pay");
      if (payBtn) {
        payBtn.textContent = "✔ Paid";
        payBtn.style.background = "#2e7d5e";
        payBtn.style.color = "#fff";
        payBtn.style.pointerEvents = "none";
      }

      $("receipt-modal").hidden = false;
    }

    $("btn-email-receipt").addEventListener("click", function () {
      if (!paidOrderId) return;
      promptModal("Email Receipt", [{ name: "email", label: "Send to", type: "email" }], function (vals) {
        var to = (vals.email || paidCustomerEmail || "").trim();
        if (!to) { toast("Enter an email address"); return; }
        api(U.orderRoot + paidOrderId + "/email-receipt/", "POST", { email: to })
          .then(function () { toast("Receipt sent to " + to); })
          .catch(showErr);
      });
    });

    $("btn-email-feedback").addEventListener("click", function () {
      if (!paidOrderId) return;
      promptModal("Send Feedback Request", [{ name: "email", label: "Send to", type: "email" }], function (vals) {
        var to = (vals.email || paidCustomerEmail || "").trim();
        if (!to) { toast("Enter an email address"); return; }
        api(U.orderRoot + paidOrderId + "/email-feedback/", "POST", { email: to })
          .then(function () { toast("Feedback request sent to " + to); })
          .catch(showErr);
      });
    });

    $("btn-new-order").addEventListener("click", function () {
      $("receipt-modal").hidden = true;
      order = null; method = null;
      document.querySelectorAll(".pay-method").forEach(function (b) { b.classList.remove("active"); });
      $("pay-method-label").textContent = "";
      $("pay-detail").innerHTML = "";
      // Reset Pay button state
      var payBtn = $("btn-pay");
      if (payBtn) {
        payBtn.textContent = "Pay";
        payBtn.style.background = "";
        payBtn.style.color = "";
        payBtn.style.pointerEvents = "";
      }
      // Restore keypad visibility
      var keypad = $("keypad");
      if (keypad) keypad.style.display = "grid";
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
