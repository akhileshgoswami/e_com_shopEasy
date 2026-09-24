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

    initSizeEditor();
  });

  // Product form: pick a product type and/or add sizes by hand, tick every
  // size the product is sold in and give each its stock. Posted as size_on,
  // size_stock__<name> and size_custom (see AdminProductService).
  function initSizeEditor() {
    const editor = document.querySelector("[data-size-editor]");
    const dataEl = document.getElementById("size-editor-data");
    const typeSelect = document.querySelector(".js-product-type");
    if (!editor || !dataEl || !typeSelect) return;

    const data = JSON.parse(dataEl.textContent);
    const rows = editor.querySelector("[data-size-rows]");
    const total = editor.querySelector("[data-size-total]");
    const customInputs = editor.querySelector("[data-size-custom-inputs]");
    const newInput = editor.querySelector("[data-size-new]");
    const singleStock = document.querySelector("[data-single-stock]");
    // Stock typed and boxes ticked so far survive switching types.
    const stock = Object.assign({}, data.stock);
    const checked = new Set(Object.keys(data.stock));
    const custom = data.custom.slice();
    const seenTypes = new Set([typeSelect.value]);

    const lower = (list) => list.map((n) => n.toLowerCase());

    function offeredNames() {
      const type = data.types[typeSelect.value];
      const names = type ? type.sizes.slice() : [];
      data.current.concat(custom).forEach((name) => {
        if (!lower(names).includes(name.toLowerCase())) names.push(name);
      });
      return names;
    }

    function updateTotal() {
      let sum = 0;
      rows.querySelectorAll("input[type=number]").forEach((input) => {
        if (!input.disabled) sum += parseInt(input.value || "0", 10) || 0;
      });
      total.textContent = sum;
    }

    function syncCustomInputs() {
      customInputs.replaceChildren();
      custom.forEach((name) => {
        const hidden = document.createElement("input");
        hidden.type = "hidden";
        hidden.name = "size_custom";
        hidden.value = name;
        customInputs.appendChild(hidden);
      });
    }

    function render() {
      const type = data.types[typeSelect.value];
      const names = offeredNames();
      const hasSizes = names.length > 0;
      editor.querySelector("[data-size-label]").textContent = type ? type.label : "Size";
      editor.querySelector("[data-size-bulk]").classList.toggle("d-none", !hasSizes);
      editor.querySelector("[data-size-help]").classList.toggle("d-none", !hasSizes);
      editor.querySelector("[data-size-empty]").classList.toggle("d-none", hasSizes);
      if (singleStock) singleStock.classList.toggle("d-none", hasSizes);
      rows.replaceChildren();

      names.forEach((name, index) => {
        const id = "size-" + index;
        const col = document.createElement("div");
        col.className = "col-6 col-md-4 col-xl-3";
        const group = document.createElement("div");
        group.className = "input-group input-group-sm";

        const toggle = document.createElement("div");
        toggle.className = "input-group-text";
        const box = document.createElement("input");
        box.type = "checkbox";
        box.className = "form-check-input mt-0 me-1";
        box.name = "size_on";
        box.value = name;
        box.id = id;
        box.checked = checked.has(name);
        const label = document.createElement("label");
        label.htmlFor = id;
        label.className = "mb-0";
        label.textContent = name;
        toggle.append(box, label);

        const qty = document.createElement("input");
        qty.type = "number";
        qty.min = "0";
        qty.className = "form-control";
        qty.name = "size_stock__" + name;
        qty.value = stock[name] !== undefined ? stock[name] : 0;
        qty.disabled = !box.checked;
        qty.setAttribute("aria-label", "Stock for " + name);

        box.addEventListener("change", () => {
          qty.disabled = !box.checked;
          if (box.checked) checked.add(name); else checked.delete(name);
          updateTotal();
        });
        qty.addEventListener("input", () => { stock[name] = qty.value; updateTotal(); });

        group.append(toggle, qty);
        if (custom.includes(name)) {
          const remove = document.createElement("button");
          remove.type = "button";
          remove.className = "btn btn-outline-danger";
          remove.setAttribute("aria-label", "Remove " + name);
          remove.textContent = "\u00d7";
          remove.addEventListener("click", () => {
            custom.splice(custom.indexOf(name), 1);
            checked.delete(name);
            syncCustomInputs();
            render();
          });
          group.appendChild(remove);
        }
        col.appendChild(group);
        rows.appendChild(col);
      });
      updateTotal();
    }

    function setAll(on) {
      offeredNames().forEach((name) => { if (on) checked.add(name); else checked.delete(name); });
      render();
    }

    function addSizes() {
      const known = lower(offeredNames());
      newInput.value.split(",").forEach((raw) => {
        const name = raw.trim().replace(/\s+/g, " ").slice(0, 30);
        if (!name || known.includes(name.toLowerCase())) return;
        known.push(name.toLowerCase());
        custom.push(name);
        checked.add(name);
      });
      newInput.value = "";
      syncCustomInputs();
      render();
      newInput.focus();
    }

    editor.querySelector("[data-size-all]").addEventListener("click", () => setAll(true));
    editor.querySelector("[data-size-none]").addEventListener("click", () => setAll(false));
    editor.querySelector("[data-size-add]").addEventListener("click", addSizes);
    newInput.addEventListener("keydown", (event) => {
      // Enter adds the size instead of submitting the product form.
      if (event.key === "Enter") {
        event.preventDefault();
        addSizes();
      }
    });
    typeSelect.addEventListener("change", () => {
      // First time a type is picked, tick all its sizes as a starting point.
      if (!seenTypes.has(typeSelect.value)) {
        seenTypes.add(typeSelect.value);
        const type = data.types[typeSelect.value];
        if (type) type.sizes.forEach((name) => checked.add(name));
      }
      render();
    });

    // New product with a type already selected (e.g. rejected form) and
    // nothing ticked yet: start with all of the type's sizes.
    if (!checked.size && data.types[typeSelect.value]) {
      data.types[typeSelect.value].sizes.forEach((name) => checked.add(name));
    }
    syncCustomInputs();
    render();
  }
})();
