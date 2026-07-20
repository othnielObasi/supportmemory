const toggle = document.querySelector(".nav-toggle");
const navigation = document.querySelector(".site-navigation");

toggle?.addEventListener("click", () => {
  const expanded = toggle.getAttribute("aria-expanded") === "true";
  toggle.setAttribute("aria-expanded", String(!expanded));
  navigation?.classList.toggle("open", !expanded);
});

navigation?.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => {
  toggle?.setAttribute("aria-expanded", "false");
  navigation.classList.remove("open");
}));

const revealTargets = document.querySelectorAll(
  ".section-heading, .outcome-grid article, .workflow-list li, .integration-grid article, .assurance-grid article, .content-card, .architecture-map article",
);

if ("IntersectionObserver" in window && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
  document.documentElement.classList.add("reveal-enabled");
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add("revealed");
      observer.unobserve(entry.target);
    });
  }, { threshold: 0.12, rootMargin: "0px 0px -36px" });
  revealTargets.forEach((target, index) => {
    target.style.setProperty("--reveal-delay", `${Math.min(index % 5, 4) * 55}ms`);
    observer.observe(target);
  });
}

const tourContent = {
  connect: { status: "Customer understood", kicker: "Customer understanding", heading: "The agent starts with the story—not an empty screen.", copy: "SupportMemory brings the current conversation, useful customer history, and the team workspace together so the customer does not have to repeat what the organisation already knows.", evidence: ["Current conversation", "Customer history", "Team workspace"], receipt: "A clear starting point" },
  retrieve: { status: "Trusted guidance found", kicker: "The right guidance", heading: "Useful answers arrive with the reasons behind them.", copy: "SupportMemory brings together relevant policies, similar cases, product details, and prior resolutions so the agent can understand what applies and review the supporting sources.", evidence: ["Relevant policy", "Similar resolution", "Customer history"], receipt: "A grounded answer to review" },
  act: { status: "Response ready for review", kicker: "A safer response", heading: "The team stays in control of important actions.", copy: "Permissions and approvals help ensure that sensitive or customer-facing actions happen intentionally, while delivery problems remain visible and can be retried safely.", evidence: ["Agent permission", "Required approval", "Delivery status"], receipt: "A controlled customer response" },
  retain: { status: "Learning retained", kicker: "Team memory", heading: "The next agent benefits from today’s resolution.", copy: "SupportMemory keeps the final answer connected to the supporting knowledge, decisions, and outcome so future investigations can reuse what the team has already learned.", evidence: ["Final resolution", "Supporting sources", "Case outcome"], receipt: "Reusable team knowledge" },
};

document.querySelectorAll("[data-tour-step]").forEach((button) => button.addEventListener("click", () => {
  const content = tourContent[button.dataset.tourStep];
  if (!content) return;
  document.querySelectorAll("[data-tour-step]").forEach((item) => item.setAttribute("aria-selected", String(item === button)));
  document.querySelector("#tour-status").textContent = content.status;
  document.querySelector("#tour-kicker").textContent = content.kicker;
  document.querySelector("#tour-heading").textContent = content.heading;
  document.querySelector("#tour-copy").textContent = content.copy;
  document.querySelector("#tour-evidence").innerHTML = content.evidence.map((item) => `<span>${item}</span>`).join("");
  document.querySelector("#tour-receipt").textContent = content.receipt;
}));
