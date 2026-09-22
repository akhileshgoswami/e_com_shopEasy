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
      event.preventDefault();
      const button = form.querySelector("button[type=submit]");
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

  document.addEventListener("DOMContentLoaded", function () {
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
