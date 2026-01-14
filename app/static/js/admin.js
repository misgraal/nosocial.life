document.addEventListener("DOMContentLoaded", () => {
  const tabs = Array.from(document.querySelectorAll("[data-tab]"));
  const panels = Array.from(document.querySelectorAll("[data-tab-panel]"));

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
});
