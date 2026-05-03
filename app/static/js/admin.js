document.addEventListener("DOMContentLoaded", () => {
  const tabs = Array.from(document.querySelectorAll("[data-tab]"));
  const panels = Array.from(document.querySelectorAll("[data-tab-panel]"));
  const filters = Array.from(document.querySelectorAll("[data-admin-filter]"));
  const diskSelectionForm = document.querySelector("[data-confirm-disk-selection]");

  if (!tabs.length || !panels.length) {
    return;
  }

  const setActiveTab = (name) => {
    tabs.forEach((tab) => {
      const isActive = tab.dataset.tab === name;
      tab.classList.toggle("active", isActive);
      tab.setAttribute("aria-selected", String(isActive));
    });

    panels.forEach((panel) => {
      const isActive = panel.dataset.tabPanel === name;
      panel.classList.toggle("is-active", isActive);
      panel.hidden = !isActive;
    });
  };

  tabs.forEach((tab) => {
    tab.addEventListener("click", (event) => {
      event.preventDefault();
      setActiveTab(tab.dataset.tab);
    });
  });

  const initial = tabs.find((tab) => tab.classList.contains("active")) || tabs[0];
  setActiveTab(initial.dataset.tab);

  filters.forEach((input) => {
    input.addEventListener("input", () => {
      const tableName = input.dataset.adminFilter;
      const table = document.querySelector(`[data-admin-table="${tableName}"] tbody`);
      if (!table) {
        return;
      }

      const query = String(input.value || "").trim().toLowerCase();
      const rows = Array.from(table.querySelectorAll("tr"));

      rows.forEach((row) => {
        const text = row.textContent.toLowerCase();
        row.hidden = Boolean(query) && !text.includes(query);
      });
    });
  });

  if (diskSelectionForm) {
    diskSelectionForm.addEventListener("submit", (event) => {
      const checkedDisks = diskSelectionForm.querySelectorAll('input[name="selected_disks"]:checked');
      if (!checkedDisks.length) {
        event.preventDefault();
        window.alert("Select at least one disk for uploads.");
        return;
      }

      if (!window.confirm(diskSelectionForm.dataset.confirmDiskSelection)) {
        event.preventDefault();
      }
    });
  }
});
