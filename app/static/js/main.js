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

    if (window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
      stage.addEventListener("mousemove", (event) => {
        if (event.target.closest("[data-zoom-open]")) {
          stage.classList.remove("is-zoomed");
          return;
        }
        const rect = stage.getBoundingClientRect();
        const x = ((event.clientX - rect.left) / rect.width) * 100;
        const y = ((event.clientY - rect.top) / rect.height) * 100;
        main.style.transformOrigin = x + "% " + y + "%";
        stage.classList.add("is-zoomed");
      });
      stage.addEventListener("mouseleave", () => stage.classList.remove("is-zoomed"));
    }

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
