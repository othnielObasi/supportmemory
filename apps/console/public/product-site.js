/* SupportMemory public product navigation. Production data remains in authenticated app routes. */
(function () {
  const publicPages = new Set(["landing", "capabilities", "architecture"]);

  window.showPage = function showPage(id) {
    if (id === "dashboard") {
      window.location.assign("/workspace.html");
      return;
    }
    if (id === "knowledge") {
      window.location.assign("/knowledge.html");
      return;
    }
    const pageId = publicPages.has(id) ? id : "landing";
    document.querySelectorAll(".page").forEach((page) => page.classList.remove("active"));
    document.getElementById("page-" + pageId)?.classList.add("active");
    window.scrollTo(0, 0);
    history.replaceState(null, "", "#" + pageId);
  };

  const requested = (location.hash || "#landing").slice(1);
  window.showPage(requested);
})();
