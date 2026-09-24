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

    // Mobile: tables collapse into stacked cards (see .table-stack in
    // style.css). Each cell gets its column header as a label.
    document.querySelectorAll(".admin-main .table-responsive > table").forEach((table) => {
      if (table.hasAttribute("data-no-stack")) return;
      const headers = Array.from(table.querySelectorAll("thead th")).map((th) => th.textContent.trim());
      table.querySelectorAll("tbody tr").forEach((row) => {
        let col = 0;
        Array.from(row.children).forEach((cell) => {
          if (!cell.hasAttribute("colspan") && headers[col]) cell.setAttribute("data-label", headers[col]);
          col += parseInt(cell.getAttribute("colspan") || "1", 10);
        });
      });
      table.classList.add("table-stack");
    });

    document.querySelectorAll("[data-auto-submit]").forEach((el) => {
      el.addEventListener("change", () => el.closest("form").submit());
    });
  });
})();
