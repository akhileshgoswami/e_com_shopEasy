(function () {
  "use strict";

  function updateCartBadges(count) {
    document.querySelectorAll(".cart-badge-count").forEach((el) => {
      el.textContent = count;
      el.classList.toggle("d-none", !count);
    });
  }

  function handleAddToCartForm(form) {
    form.addEventListener("submit", function (event) {
      // "Buy now" shares the form but must navigate to checkout normally.
      if (event.submitter && event.submitter.hasAttribute("data-buy-now")) return;
      event.preventDefault();
      const button = event.submitter || form.querySelector("button[type=submit]");
      const originalHtml = button ? button.innerHTML : null;
      if (button) {
        button.disabled = true;
        button.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
      }

      fetch(form.action, {
        method: "POST",
        headers: {
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": window.CSRF_TOKEN || "",
        },
        body: new FormData(form),
      })
        .then((res) => res.json().then((data) => ({ status: res.status, data })))
        .then(({ status, data }) => {
          if (data.auth_required && data.redirect) {
            window.location.href = data.redirect;
            return;
          }
          if (data.success) {
            updateCartBadges(data.item_count);
            showToast(data.message || "Added to cart.", "success");
          } else {
            showToast(data.message || "Could not add item to cart.", "danger");
          }
        })
        .catch(() => showToast("Network error. Please try again.", "danger"))
        .finally(() => {
          if (button) {
            button.disabled = false;
            button.innerHTML = originalHtml;
          }
        });
    });
  }

  function showToast(message, type) {
    let container = document.getElementById("toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "toast-container";
      container.className = "position-fixed bottom-0 end-0 p-3";
      container.style.zIndex = 1080;
      document.body.appendChild(container);
    }
    const toastEl = document.createElement("div");
    toastEl.className = `toast align-items-center text-bg-${type === "danger" ? "danger" : "success"} border-0`;
    toastEl.setAttribute("role", "alert");
    toastEl.innerHTML = `<div class="d-flex"><div class="toast-body">${message}</div><button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>`;
    container.appendChild(toastEl);
    const toast = new bootstrap.Toast(toastEl, { delay: 3000 });
    toast.show();
    toastEl.addEventListener("hidden.bs.toast", () => toastEl.remove());
  }

  // Product page: each size has its own stock, so the quantity limit and
  // the "only N left" note follow the selected size.
  function initSizePicker(picker) {
    const form = picker.closest("form");
    const qty = form.querySelector("input[name=quantity]");
    const status = picker.querySelector("[data-size-status]");
    const lowAt = parseInt(picker.dataset.lowThreshold || "0", 10);

    function update() {
      const chosen = picker.querySelector("input[name=size]:checked");
      if (!chosen) {
        status.textContent = "";
        return;
      }
      const stock = parseInt(chosen.dataset.stock || "0", 10);
      if (qty) {
        qty.max = stock;
        if (parseInt(qty.value || "1", 10) > stock) qty.value = stock;
      }
      status.className = "small mt-2 mb-0 " + (stock <= lowAt ? "text-warning" : "text-success");
      status.textContent = stock <= lowAt ? "Only " + stock + " left in " + chosen.value + " – order soon." : chosen.value + " is in stock.";
    }

    picker.querySelectorAll("input[name=size]").forEach((radio) => radio.addEventListener("change", update));
    update();
  }

  // Product page images: hover magnifies under the cursor (mouse only);
  // clicking opens a full-screen viewer where click/tap zooms, drag pans,
  // the wheel zooms, and arrows / swipe move between images.
  function initGallery(gallery) {
    const images = JSON.parse(gallery.dataset.images || "[]");
    const stage = gallery.querySelector("[data-zoom-stage]");
    const main = gallery.querySelector("[data-zoom-image]");
    const thumbs = gallery.querySelectorAll("[data-thumb]");
    const modalEl = document.getElementById("imageLightbox");
    if (!images.length || !stage || !main) return;
    let current = Math.max(0, images.indexOf(main.getAttribute("src")));

    function show(index) {
      current = (index + images.length) % images.length;
      main.src = images[current];
      thumbs.forEach((btn) => {
        btn.querySelector("img").classList.toggle("active", Number(btn.dataset.thumb) === current);
      });
    }
    thumbs.forEach((btn) => btn.addEventListener("click", () => show(Number(btn.dataset.thumb))));

    // Magnify the spot under (clientX, clientY).
    function magnifyAt(clientX, clientY) {
      const rect = stage.getBoundingClientRect();
      const x = Math.min(100, Math.max(0, ((clientX - rect.left) / rect.width) * 100));
      const y = Math.min(100, Math.max(0, ((clientY - rect.top) / rect.height) * 100));
      main.style.transformOrigin = x + "% " + y + "%";
      stage.classList.add("is-zoomed");
    }

    if (window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
      stage.addEventListener("mousemove", (event) => {
        if (event.target.closest("[data-zoom-open]")) {
          stage.classList.remove("is-zoomed");
          return;
        }
        magnifyAt(event.clientX, event.clientY);
      });
      stage.addEventListener("mouseleave", () => stage.classList.remove("is-zoomed"));
    }

    // Touch: the same magnifier on press-and-hold, following the finger until
    // it lifts. A quick swipe still scrolls the page and a tap still opens
    // the full-screen viewer.
    const HOLD_MS = 220;
    let hold = null;
    let suppressClick = false;
    stage.addEventListener("touchstart", (event) => {
      if (event.touches.length !== 1 || event.target.closest("[data-zoom-open]")) return;
      const touch = event.touches[0];
      hold = { x: touch.clientX, y: touch.clientY, active: false };
      hold.timer = setTimeout(() => {
        if (!hold) return;
        hold.active = true;
        magnifyAt(hold.x, hold.y);
      }, HOLD_MS);
    }, { passive: true });
    stage.addEventListener("touchmove", (event) => {
      if (!hold) return;
      const touch = event.touches[0];
      if (hold.active) {
        event.preventDefault(); // keep the page still while magnifying
        magnifyAt(touch.clientX, touch.clientY);
      } else if (Math.abs(touch.clientX - hold.x) + Math.abs(touch.clientY - hold.y) > 10) {
        clearTimeout(hold.timer); // it's a scroll, not a hold
        hold = null;
      } else {
        hold.x = touch.clientX;
        hold.y = touch.clientY;
      }
    }, { passive: false });
    function endHold() {
      if (!hold) return;
      clearTimeout(hold.timer);
      if (hold.active) {
        stage.classList.remove("is-zoomed");
        suppressClick = true; // the lift shouldn't also open the viewer
        setTimeout(() => { suppressClick = false; }, 400);
      }
      hold = null;
    }
    stage.addEventListener("touchend", endHold);
    stage.addEventListener("touchcancel", endHold);
    stage.addEventListener("contextmenu", (event) => {
      if (stage.classList.contains("is-zoomed")) event.preventDefault();
    });

    if (!modalEl || !window.bootstrap) return;
    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    const box = modalEl.querySelector("[data-lightbox-stage]");
    const big = modalEl.querySelector("[data-lightbox-image]");
    const count = modalEl.querySelector("[data-lightbox-count]");
    const zoomBtn = modalEl.querySelector("[data-lightbox-zoom]");
    const MAX = 4;
    const ZOOM = 2.5;
    let view = { scale: 1, x: 0, y: 0 };

    function clamp() {
      const maxX = (big.clientWidth * (view.scale - 1)) / 2;
      const maxY = (big.clientHeight * (view.scale - 1)) / 2;
      view.x = Math.min(maxX, Math.max(-maxX, view.x));
      view.y = Math.min(maxY, Math.max(-maxY, view.y));
    }

    function apply() {
      clamp();
      big.style.transform = "translate(" + view.x + "px, " + view.y + "px) scale(" + view.scale + ")";
      box.classList.toggle("is-zoomed", view.scale > 1);
      zoomBtn.innerHTML = view.scale > 1 ? '<i class="bi bi-zoom-out"></i>' : '<i class="bi bi-zoom-in"></i>';
    }

    // Zoom to `scale`, keeping the point under (clientX, clientY) in place.
    function zoomAt(scale, clientX, clientY) {
      const rect = big.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const px = clientX === undefined ? 0 : clientX - cx;
      const py = clientY === undefined ? 0 : clientY - cy;
      const ratio = scale / view.scale;
      view.x = view.x * ratio - px * (ratio - 1);
      view.y = view.y * ratio - py * (ratio - 1);
      view.scale = scale;
      if (scale === 1) view = { scale: 1, x: 0, y: 0 };
      apply();
    }

    function open(index) {
      show(index);
      big.src = images[current];
      count.textContent = images.length > 1 ? current + 1 + " / " + images.length : "";
      view = { scale: 1, x: 0, y: 0 };
      apply();
    }

    function step(delta) {
      if (images.length > 1) open(current + delta);
    }

    stage.addEventListener("click", () => {
      if (suppressClick) return;
      open(current);
      modal.show();
    });

    const prev = modalEl.querySelector("[data-lightbox-prev]");
    const next = modalEl.querySelector("[data-lightbox-next]");
    if (prev) prev.addEventListener("click", () => step(-1));
    if (next) next.addEventListener("click", () => step(1));
    zoomBtn.addEventListener("click", () => zoomAt(view.scale > 1 ? 1 : ZOOM));

    modalEl.addEventListener("keydown", (event) => {
      if (event.key === "ArrowLeft") step(-1);
      if (event.key === "ArrowRight") step(1);
    });

    box.addEventListener("wheel", (event) => {
      event.preventDefault();
      const scale = Math.min(MAX, Math.max(1, view.scale * (event.deltaY < 0 ? 1.2 : 1 / 1.2)));
      zoomAt(scale < 1.05 ? 1 : scale, event.clientX, event.clientY);
    }, { passive: false });

    // One pointer handler covers click-to-zoom, drag-to-pan and swipe.
    let drag = null;
    box.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      drag = { startX: event.clientX, startY: event.clientY, x: view.x, y: view.y, moved: false };
      box.setPointerCapture(event.pointerId);
    });
    box.addEventListener("pointermove", (event) => {
      if (!drag) return;
      const dx = event.clientX - drag.startX;
      const dy = event.clientY - drag.startY;
      if (Math.abs(dx) + Math.abs(dy) > 6) drag.moved = true;
      if (view.scale > 1 && drag.moved) {
        box.classList.add("is-dragging");
        view.x = drag.x + dx;
        view.y = drag.y + dy;
        apply();
      }
    });
    function endDrag(event) {
      if (!drag) return;
      const dx = event.clientX - drag.startX;
      box.classList.remove("is-dragging");
      if (!drag.moved) {
        zoomAt(view.scale > 1 ? 1 : ZOOM, event.clientX, event.clientY);
      } else if (view.scale === 1 && Math.abs(dx) > 50) {
        step(dx < 0 ? 1 : -1);
      }
      drag = null;
    }
    box.addEventListener("pointerup", endDrag);
    box.addEventListener("pointercancel", () => {
      box.classList.remove("is-dragging");
      drag = null;
    });
    modalEl.addEventListener("hidden.bs.modal", () => {
      view = { scale: 1, x: 0, y: 0 };
      apply();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-gallery]").forEach(initGallery);
    document.querySelectorAll("[data-size-picker]").forEach(initSizePicker);
    document.querySelectorAll(".add-to-cart-form").forEach(handleAddToCartForm);

    document.querySelectorAll("[data-confirm]").forEach((form) => {
      form.addEventListener("submit", function (event) {
        if (!window.confirm(form.getAttribute("data-confirm"))) {
          event.preventDefault();
        }
      });
    });
  });

  window.shopUtils = { showToast, updateCartBadges };
})();

// Home "finder": category tabs pick the category in the search card, like
// switching product type before searching.
document.addEventListener("DOMContentLoaded", function () {
  var finder = document.querySelector(".sky-finder");
  if (!finder) return;
  var select = finder.querySelector(".sky-category-select");
  var tabs = finder.querySelectorAll(".sky-tab[data-category]");

  function activate(slug) {
    tabs.forEach(function (tab) {
      var on = tab.dataset.category === slug;
      tab.classList.toggle("active", on);
      tab.setAttribute("aria-selected", on ? "true" : "false");
    });
  }

  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      activate(tab.dataset.category);
      if (select) select.value = tab.dataset.category;
    });
  });
  if (select) {
    select.addEventListener("change", function () { activate(select.value); });
  }
});

// Home hero: let the header sit transparently over it, turning solid on scroll.
document.addEventListener("DOMContentLoaded", function () {
  const header = document.querySelector(".sky-header");
  const hero = document.querySelector("main > .sky-hero:first-child");
  if (!header || !hero) return;

  const topbar = document.querySelector(".sky-topbar");
  const root = document.documentElement;
  function measure() {
    const topbarH = topbar && topbar.offsetParent !== null ? topbar.offsetHeight : 0;
    root.style.setProperty("--chrome-h", topbarH + header.offsetHeight + "px");
  }
  function onScroll() {
    header.classList.toggle("is-scrolled", window.scrollY > 8);
  }

  measure();
  onScroll();
  document.body.classList.add("header-overlay");
  window.addEventListener("scroll", onScroll, { passive: true });
  // Header grows when the mobile search row opens or the viewport changes.
  if ("ResizeObserver" in window) {
    const observer = new ResizeObserver(measure);
    observer.observe(header);
    if (topbar) observer.observe(topbar);
  } else {
    window.addEventListener("resize", measure);
  }
});

// Wishlist hearts: toggle in place instead of reloading the page.
document.addEventListener("submit", function (event) {
  const form = event.target.closest("[data-wishlist-form]");
  if (!form) return;
  event.preventDefault();
  const button = form.querySelector("button");
  button.disabled = true;

  fetch(form.action, {
    method: "POST",
    headers: { "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": window.CSRF_TOKEN || "" },
    body: new FormData(form),
  })
    .then((res) => res.json())
    .then((data) => {
      if (data.auth_required && data.redirect) {
        window.location.href = data.redirect;
        return;
      }
      if (!data.success) {
        form.submit(); // let the server flash the reason
        return;
      }
      const productId = form.querySelector("input[name=product_id]").value;
      // The same product can appear twice on a page (detail + related).
      document.querySelectorAll("[data-wishlist-form]").forEach((other) => {
        if (other.querySelector("input[name=product_id]").value !== productId) return;
        const btn = other.querySelector("button");
        btn.classList.toggle("is-active", data.in_wishlist);
        btn.setAttribute("aria-pressed", data.in_wishlist ? "true" : "false");
        btn.title = data.in_wishlist ? "Remove from wishlist" : "Save to wishlist";
        btn.querySelector("i").className = "bi " + (data.in_wishlist ? "bi-heart-fill" : "bi-heart");
      });
      document.querySelectorAll(".wishlist-badge-count").forEach((el) => {
        el.textContent = data.count;
        el.classList.toggle("d-none", !data.count);
      });

      const page = document.querySelector("[data-wishlist-page]");
      if (page && !data.in_wishlist) {
        const col = form.closest(".col-6");
        if (col) col.remove();
        if (!page.querySelector("[data-wishlist-form]")) {
          page.querySelector("[data-wishlist-empty]").classList.remove("d-none");
        }
      }
    })
    .catch(() => form.submit())
    .finally(() => { button.disabled = false; });
});

// Auth forms (forgot / reset password): client-side validation that mirrors
// the server rules, a loading state on submit, and show/hide password.
(function () {
  "use strict";

  const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

  function passwordRules(form) {
    const password = form.querySelector("input[name=password]");
    const confirm = form.querySelector("input[name=confirm_password]");
    if (!password || !confirm) return null;
    const value = password.value;
    return {
      length: value.length >= 8 && value.length <= 128,
      letter: /[A-Za-z]/.test(value),
      number: /\d/.test(value),
      match: value.length > 0 && value === confirm.value,
    };
  }

  function renderRules(form) {
    const rules = passwordRules(form);
    const list = form.querySelector("[data-password-rules]");
    if (!rules || !list) return rules;
    Object.entries(rules).forEach(([name, ok]) => {
      const item = list.querySelector(`[data-rule="${name}"]`);
      if (!item) return;
      item.classList.toggle("text-success", ok);
      item.classList.toggle("text-muted", !ok);
      item.querySelector("i").className = "bi " + (ok ? "bi-check-circle-fill" : "bi-circle");
    });
    return rules;
  }

  document.querySelectorAll("[data-password-form]").forEach((form) => {
    form.addEventListener("input", () => renderRules(form));
    renderRules(form);
  });

  document.querySelectorAll("[data-password-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const input = document.getElementById(button.dataset.passwordToggle);
      if (!input) return;
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      button.setAttribute("aria-pressed", show ? "true" : "false");
      button.setAttribute("aria-label", show ? "Hide password" : "Show password");
      button.querySelector("i").className = "bi " + (show ? "bi-eye-slash" : "bi-eye");
    });
  });

  document.querySelectorAll("[data-loading-form]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      const email = form.querySelector("input[type=email]");
      if (email) {
        const valid = EMAIL_RE.test(email.value.trim());
        email.classList.toggle("is-invalid", !valid);
        const hint = form.querySelector("[data-client-error]");
        if (hint) hint.classList.toggle("d-block", !valid);
        if (!valid) {
          event.preventDefault();
          email.focus();
          return;
        }
      }
      const rules = form.hasAttribute("data-password-form") ? renderRules(form) : null;
      if (rules && !Object.values(rules).every(Boolean)) {
        event.preventDefault();
        form.querySelector("input[name=password]").focus();
        return;
      }
      const button = form.querySelector("button[type=submit]");
      if (button) {
        button.dataset.originalHtml = button.innerHTML;
        button.disabled = true;
        button.innerHTML =
          '<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>' +
          (button.dataset.loadingText || "Please wait…");
      }
    });
  });

  // Coming back via the browser's back button restores the page from cache
  // with the button still spinning.
  window.addEventListener("pageshow", () => {
    document.querySelectorAll("[data-loading-form] button[type=submit][data-original-html]").forEach((button) => {
      button.disabled = false;
      button.innerHTML = button.dataset.originalHtml;
    });
  });
})();
