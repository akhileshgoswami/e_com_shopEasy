(function () {
  "use strict";
  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-confirm]").forEach((form) => {
      form.addEventListener("submit", function (event) {
        if (!window.confirm(form.getAttribute("data-confirm"))) {
          event.preventDefault();
        }
      });
    });

    document.querySelectorAll("[data-auto-submit]").forEach((el) => {
      el.addEventListener("change", () => el.closest("form").submit());
    });
  });
})();
