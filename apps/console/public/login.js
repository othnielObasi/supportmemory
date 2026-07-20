const form = document.getElementById("login-form");
const input = document.getElementById("access-key");
const submit = document.getElementById("login-submit");
const errorNode = document.getElementById("login-error");
const development = document.getElementById("development-access");
const safeDestinations = new Set(["/workspace.html", "/knowledge.html", "/integrations.html"]);
const requested = new URLSearchParams(location.search).get("next") || "/workspace.html";
const destination = safeDestinations.has(requested) ? requested : "/workspace.html";

function showError(message) {
  errorNode.textContent = message;
  errorNode.hidden = false;
}

async function context(token) {
  const response = await fetch("/api/enterprise/context", {
    headers: { Accept: "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(typeof payload?.detail === "string" ? payload.detail : "Access key could not be validated");
  }
  return response.json();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const token = input.value.trim();
  if (!token) return;
  errorNode.hidden = true;
  submit.disabled = true;
  submit.textContent = "Validating access…";
  try {
    await context(token);
    sessionStorage.setItem("supportmemory.access_token", token);
    location.replace(destination);
  } catch (error) {
    sessionStorage.removeItem("supportmemory.access_token");
    showError(error instanceof Error ? error.message : "Sign in failed");
  } finally {
    submit.disabled = false;
    submit.textContent = "Continue to workspace";
  }
});

development.querySelector("button").addEventListener("click", () => {
  sessionStorage.removeItem("supportmemory.access_token");
  location.replace(destination);
});

void context("").then((payload) => {
  if (payload.auth_required === false) development.hidden = false;
}).catch(() => {});
