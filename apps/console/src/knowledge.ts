import "./knowledge.css";
import { authenticatedFetch, signOut } from "./session";

type DocumentSummary = { document_id: string; title: string; source_type: string; source_system: string; chunk_count: number; tags: string[]; created_at: string; agent_id: string };
type SearchHit = { chunk_id: string; document_id: string; title: string; score: number; text: string; source_type?: string };
type TenantContext = { organisation_id: string; workspace_id: string; project_id: string; environment_id: string };
type EnterpriseContext = { principal: TenantContext; role: string; scopes: string[]; auth_required: boolean };

const apiBase = (new URLSearchParams(location.search).get("api") || import.meta.env.VITE_API_BASE_URL || location.origin).replace(/\/$/, "");
const token = sessionStorage.getItem("supportmemory.access_token");
let tenant: TenantContext = { organisation_id: localStorage.getItem("sm.organisation") || "org_default", workspace_id: localStorage.getItem("sm.workspace") || "wrk_default", project_id: localStorage.getItem("sm.project") || "prj_default", environment_id: localStorage.getItem("sm.environment") || "dev" };
const headers = (json = true): HeadersInit => ({ Accept: "application/json", ...(json ? { "Content-Type": "application/json" } : {}), ...(token ? { Authorization: `Bearer ${token}` } : {}), "X-Organisation-Id": tenant.organisation_id, "X-Workspace-Id": tenant.workspace_id, "X-Project-Id": tenant.project_id, "X-Environment-Id": tenant.environment_id });
const root = document.getElementById("knowledge-root")!;

root.innerHTML = `
  <header class="private-topbar">
    <a class="private-brand" href="/workspace.html"><span>S</span><div><strong>SupportMemory</strong><small>Private workspace</small></div></a>
    <nav aria-label="Application navigation"><a href="/workspace.html">Investigations</a><a class="active" href="/knowledge.html" aria-current="page">Knowledge</a><a href="/integrations.html">Integrations</a></nav>
    <div class="private-session"><span id="api-state">Connecting</span><div id="operator-avatar" aria-label="Signed in operator">OO</div><button id="sign-out">Sign out</button></div>
  </header>
  <main class="knowledge-page">
    <header class="knowledge-head"><div><span class="eyebrow">Knowledge operations</span><h1>Knowledge Base</h1><p>Manage the governed sources SupportMemory can retrieve during customer investigations.</p></div><div class="scope-card"><span id="organisation-label">Organisation</span><strong id="workspace-label">Resolving workspace…</strong><small id="role-label">Private application surface</small></div></header>
    <section class="knowledge-stats" aria-label="Knowledge summary"><article><span>Documents</span><strong id="stat-docs">—</strong><small>Indexed sources</small></article><article><span>Chunks</span><strong id="stat-chunks">—</strong><small>Retrievable passages</small></article><article><span>Coverage</span><strong id="stat-types">—</strong><small>Source types</small></article></section>
    <div id="notice" class="notice" hidden role="status"></div>
    <div class="knowledge-layout">
      <section class="library-panel" aria-labelledby="library-title"><header class="section-head"><div><span class="eyebrow">Library</span><h2 id="library-title">Indexed knowledge</h2></div><button id="refresh" class="button secondary">Refresh</button></header>
        <form id="search-form" class="search-bar"><label><span class="sr-only">Search knowledge</span><input id="query" type="search" minlength="3" placeholder="Test retrieval across policies, SOPs, and product docs" /></label><button class="button primary" type="submit">Run search</button></form>
        <section id="results" class="results" hidden><header><strong>Retrieval preview</strong><button id="clear-search">Clear</button></header><div id="hits"></div></section>
        <div class="table-head"><span>Document</span><span>Type</span><span>Chunks</span><span>Added</span></div><div id="documents" class="document-list" aria-live="polite"><div class="state">Loading indexed documents…</div></div>
      </section>
      <aside class="ingest-panel" aria-labelledby="ingest-title"><header class="section-head"><div><span class="eyebrow">Add source</span><h2 id="ingest-title">Ingest knowledge</h2></div></header><p>New sources are chunked, indexed, and scoped to this workspace.</p>
        <label class="upload-zone" for="pdf"><span class="upload-icon">↑</span><strong>Upload a PDF</strong><small id="file-label">Choose a verified source document</small><span class="button secondary">Choose file</span><input id="pdf" type="file" accept=".pdf,application/pdf" hidden /></label>
        <div class="divider"><span>or paste text</span></div><form id="text-form"><label class="field"><span>Document title</span><input id="title" required maxlength="160" placeholder="e.g. Refund approval policy" /></label><label class="field"><span>Policy or procedure</span><textarea id="text" required minlength="20" maxlength="100000" placeholder="Paste verified source material"></textarea></label><div class="ingest-footer"><small>Source: Policy<br />Scope: Ticket investigation</small><button class="button primary" type="submit">Ingest source</button></div></form>
      </aside>
    </div>
  </main>`;

const escapeHtml = (value: unknown) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]!));
const element = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const setBusy = (busy: boolean) => root.classList.toggle("busy", busy);
function notify(message: string, error = false) { const node = element<HTMLDivElement>("notice"); node.textContent = message; node.className = `notice ${error ? "error" : "success"}`; node.hidden = false; window.setTimeout(() => { node.hidden = true; }, 4200); }
async function request<T>(path: string, init: RequestInit = {}): Promise<T> { const response = await authenticatedFetch(apiBase + path, { ...init, headers: { ...headers(!(init.body instanceof FormData)), ...init.headers } }); if (!response.ok) throw new Error((await response.json().catch(() => null))?.detail || `Request failed (${response.status})`); return response.json(); }

async function loadTenantContext() {
  const context = await request<EnterpriseContext>("/api/enterprise/context");
  tenant = context.principal;
  localStorage.setItem("sm.organisation", tenant.organisation_id); localStorage.setItem("sm.workspace", tenant.workspace_id); localStorage.setItem("sm.project", tenant.project_id); localStorage.setItem("sm.environment", tenant.environment_id);
  element("organisation-label").textContent = tenant.organisation_id;
  element("workspace-label").textContent = tenant.workspace_id;
  element("role-label").textContent = `Private · ${context.role} access`;
}

async function loadDocuments() {
  const list = element<HTMLDivElement>("documents"); list.innerHTML = '<div class="state">Loading indexed documents…</div>';
  try {
    const docs = await request<DocumentSummary[]>("/api/kb/documents");
    element("api-state").textContent = "Connected"; element("api-state").className = "online";
    element("stat-docs").textContent = String(docs.length); element("stat-chunks").textContent = String(docs.reduce((sum, doc) => sum + Number(doc.chunk_count || 0), 0)); element("stat-types").textContent = String(new Set(docs.map((doc) => doc.source_type)).size);
    if (!docs.length) { list.innerHTML = '<div class="state"><strong>No knowledge sources yet</strong><br />Upload a PDF or ingest verified text to begin.</div>'; return; }
    list.innerHTML = docs.map((doc) => `<article class="document-row"><div><strong>${escapeHtml(doc.title || "Untitled")}</strong><small>${escapeHtml(doc.document_id)}</small></div><span class="type">${escapeHtml(doc.source_type || "text")}</span><span class="chunks">${Number(doc.chunk_count || 0)}</span><time>${doc.created_at ? new Date(doc.created_at).toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" }) : "Unknown"}</time></article>`).join("");
  } catch (error) { element("api-state").textContent = "Unavailable"; element("api-state").className = "offline"; list.innerHTML = `<div class="state error"><strong>Library unavailable</strong><br />${escapeHtml(error instanceof Error ? error.message : "Check the API connection")}</div>`; }
}

element<HTMLButtonElement>("refresh").addEventListener("click", () => void loadDocuments());
element<HTMLButtonElement>("sign-out").addEventListener("click", signOut);
element<HTMLButtonElement>("clear-search").addEventListener("click", () => { element<HTMLInputElement>("query").value = ""; element("results").hidden = true; });
element<HTMLFormElement>("search-form").addEventListener("submit", async (event) => { event.preventDefault(); const query = element<HTMLInputElement>("query").value.trim(); if (query.length < 3) return notify("Enter at least three characters.", true); setBusy(true); try { const response = await request<{ hits: SearchHit[] }>("/api/kb/search", { method: "POST", body: JSON.stringify({ query, agent_id: "ticket-investigation-agent", top_k: 5 }) }); const hits = element("hits"); hits.innerHTML = response.hits.length ? response.hits.map((hit) => `<article class="hit"><header><strong>${escapeHtml(hit.title)}</strong><span>${Math.round(hit.score * 100)}% match</span></header><p>${escapeHtml(hit.text)}</p><small>${escapeHtml(hit.source_type || "Knowledge chunk")} · ${escapeHtml(hit.chunk_id)}</small></article>`).join("") : '<div class="state">No relevant passages found. Try a broader query.</div>'; element("results").hidden = false; } catch (error) { notify(error instanceof Error ? error.message : "Search failed", true); } finally { setBusy(false); } });
element<HTMLFormElement>("text-form").addEventListener("submit", async (event) => { event.preventDefault(); const title = element<HTMLInputElement>("title").value.trim(); const text = element<HTMLTextAreaElement>("text").value.trim(); if (text.length < 20) return notify("Source text must contain at least 20 characters.", true); setBusy(true); try { const response = await request<{ chunk_count: number }>("/api/kb/ingest", { method: "POST", body: JSON.stringify({ title, text, source_type: "policy", tags: ["ui", "supportmemory"], agent_id: "ticket-investigation-agent" }) }); element<HTMLFormElement>("text-form").reset(); notify(`Source indexed in ${response.chunk_count} chunk${response.chunk_count === 1 ? "" : "s"}.`); await loadDocuments(); } catch (error) { notify(error instanceof Error ? error.message : "Ingestion failed", true); } finally { setBusy(false); } });
element<HTMLInputElement>("pdf").addEventListener("change", async (event) => { const input = event.currentTarget as HTMLInputElement; const file = input.files?.[0]; if (!file) return; element("file-label").textContent = file.name; if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) { notify("Only PDF documents are supported.", true); input.value = ""; return; } setBusy(true); try { const data = new FormData(); data.append("file", file); data.append("title", file.name.replace(/\.pdf$/i, "")); data.append("agent_id", "ticket-investigation-agent"); const response = await request<{ chunk_count: number }>("/api/kb/ingest/pdf", { method: "POST", body: data }); notify(`PDF indexed in ${response.chunk_count} chunks.`); input.value = ""; element("file-label").textContent = "Choose a verified source document"; await loadDocuments(); } catch (error) { notify(error instanceof Error ? error.message : "Upload failed", true); } finally { setBusy(false); } });

void (async () => { try { await loadTenantContext(); await loadDocuments(); } catch (error) { element("api-state").textContent = "Authentication required"; element("api-state").className = "offline"; element("documents").innerHTML = `<div class="state error"><strong>Workspace context unavailable</strong><br />${escapeHtml(error instanceof Error ? error.message : "Sign in again")}</div>`; } })();
