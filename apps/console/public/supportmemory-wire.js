/* SupportMemory dashboard API wiring — loaded by HACKATHON_UI.html */
(function () {
  const STEPS = ["Request", "Plan", "Route", "Checkpoint", "Tool", "Evidence", "Fallback", "Memory", "Answer"];
  const AGENT_ID = "ticket-investigation-agent";
  const SAMPLE = [{
    id: "tx-4891",
    title: "API auth failure",
    company: "Apex Cloud",
    ticket: "TX-4891",
    status: "Sample",
    customer: "Sarah Jenkins",
    requesterName: "Sarah Jenkins",
    requesterEmail: "sarah.jenkins@apexcloud.io",
    requesterCompany: "Apex Cloud",
    channel: "email",
    priority: "high",
    request: "We're seeing recurring 401 Unauthorized errors on our webhook endpoint after rotating the signing secret yesterday. Can you find the root cause?",
    requestAt: Date.now(),
    agent: "Sample thread — use Ask SupportMemory, Seed demo KB, or Run recovery demo to hit the live API.",
    log: "Waiting for live run…",
    messages: [],
    kbHits: [],
    step: 1,
    match: "—",
    similar: "—",
    model: "—",
    duration: "—",
    integrity: 0,
    taskId: null,
    traceId: null,
    checkpointId: null,
    live: false,
  }];

  let investigations = SAMPLE.map((x) => ({ ...x, messages: [] }));
  let activeId = investigations[0].id;
  let apiOnline = false;

  function esc(s) {
    return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function apiBase() {
    const q = new URLSearchParams(location.search).get("api");
    if (q) return q.replace(/\/$/, "");
    if (location.port === "3000" || location.port === "5173") return "http://localhost:8000";
    if (location.origin.includes(":8000")) return location.origin;
    return "http://localhost:8000";
  }

  async function apiGet(path) {
    const r = await fetch(apiBase() + path, { headers: { Accept: "application/json" } });
    if (!r.ok) throw new Error(await r.text().catch(() => String(r.status)));
    return r.json();
  }

  async function apiPost(path, body) {
    const r = await fetch(apiBase() + path, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body || {}),
    });
    if (!r.ok) throw new Error(await r.text().catch(() => String(r.status)));
    return r.json();
  }

  function slugify(s) {
    return String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  }

  // The customer is the identity SupportMemory should recall preferences/history for —
  // derived from the ticket's requester, not the operator's browser session, so each
  // customer's memory stays correctly separated from every other customer's.
  function customerUserId(inv) {
    const key = inv.requesterEmail || inv.customer || inv.id;
    return "cust_" + slugify(key).slice(0, 48) || "cust_unknown";
  }

  function initials(name) {
    const parts = String(name || "?").trim().split(/\s+/);
    return ((parts[0]?.[0] || "") + (parts[1]?.[0] || "")).toUpperCase() || "?";
  }

  function fmtTime(iso) {
    try {
      return new Date(iso || Date.now()).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch (_) {
      return "";
    }
  }

  const CHANNEL_LABEL = { email: "Email", chat: "Chat", phone: "Phone", sms: "SMS", unknown: "Unknown channel" };

  async function ensureConversation(inv) {
    if (inv.conversationId) return inv.conversationId;
    try {
      const conv = await apiPost("/api/conversations", {
        user_id: customerUserId(inv),
        title: inv.title || "Support conversation",
        channel: inv.channel || "chat",
      });
      inv.conversationId = conv.conversation_id;
    } catch (_) {
      // API unreachable or endpoint missing — task run still works without conversation memory.
    }
    return inv.conversationId;
  }

  async function apiPut(path, body) {
    const r = await fetch(apiBase() + path, {
      method: "PUT",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body || {}),
    });
    if (!r.ok) throw new Error(await r.text().catch(() => String(r.status)));
    return r.json();
  }

  async function loadProfile(inv) {
    try {
      inv.profile = await apiGet("/api/preferences/user/" + encodeURIComponent(customerUserId(inv)));
    } catch (_) {
      inv.profile = null;
    }
    // The helpdesk connector already knows the requester's identity — record it once so
    // SupportMemory never has to ask for it again, even on this customer's first message.
    if (inv.requesterName && (!inv.profile || inv.profile.source === "default")) {
      try {
        inv.profile = await apiPut("/api/preferences/user", {
          user_id: customerUserId(inv),
          display_name: inv.requesterName,
          company: inv.requesterCompany || undefined,
          contact_channel: inv.channel || undefined,
        });
      } catch (_) {}
    }
    if (activeInv() === inv) renderDashboard();
  }

  async function apiUpload(path, formData) {
    const r = await fetch(apiBase() + path, { method: "POST", body: formData });
    if (!r.ok) throw new Error(await r.text().catch(() => String(r.status)));
    return r.json();
  }

  function toast(msg) {
    const el = document.getElementById("toast");
    if (!el) return;
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => el.classList.remove("show"), 3400);
  }

  function setBusy(on) {
    document.getElementById("dash")?.classList.toggle("busy", !!on);
  }

  function setApiPill(ok, label) {
    apiOnline = !!ok;
    const pill = document.getElementById("api-pill");
    if (!pill) return;
    pill.classList.toggle("ok", !!ok);
    pill.innerHTML = `<i></i> ${esc(label || (ok ? "API live" : "API offline"))}`;
  }

  function activeInv() {
    return investigations.find((i) => i.id === activeId) || investigations[0];
  }

  window.showPage = function showPage(id) {
    document.querySelectorAll(".page").forEach((p) => p.classList.remove("active"));
    const page = document.getElementById("page-" + id);
    if (page) page.classList.add("active");
    if (id === "dashboard") {
      renderDashboard();
      pingApi();
      refreshKbDocs();
      loadProfile(activeInv());
    }
    if (id === "knowledge") {
      refreshKbDocs();
    }
    window.scrollTo(0, 0);
    history.replaceState(null, "", "#" + id);
  };

  window.filterInvestigations = function (q) {
    renderInvList(q);
  };

  function renderInvList(q = "") {
    const list = document.getElementById("inv-list");
    if (!list) return;
    const qq = q.trim().toLowerCase();
    list.innerHTML = "";
    investigations
      .filter((i) => !qq || (i.title + i.company + i.ticket).toLowerCase().includes(qq))
      .forEach((inv) => {
        const b = document.createElement("button");
        b.className = "inv" + (inv.id === activeId ? " active" : "");
        b.innerHTML = `<div class="t"><span class="dot"></span><span>${esc(inv.title)}</span></div><div class="c">${esc(inv.company)}${inv.live ? " · live" : ""}</div>`;
        b.onclick = () => {
          activeId = inv.id;
          renderDashboard();
          loadProfile(inv);
        };
        list.appendChild(b);
      });
  }

  function renderSteps(current) {
    // Compact single-line stage indicator above the thread — the full pipeline
    // breakdown lives in the Inspector so the conversation stays the focus.
    const line = document.getElementById("stage-line");
    if (line) {
      const name = STEPS[Math.min(current, STEPS.length - 1)] || STEPS[0];
      const pct = Math.round((Math.min(current, STEPS.length - 1) / (STEPS.length - 1)) * 100);
      line.innerHTML = `<span class="stage-label">Stage ${Math.min(current, STEPS.length - 1) + 1}/${STEPS.length} · ${esc(name)}</span>
        <span class="stage-bar"><i style="width:${pct}%"></i></span>`;
    }
    const root = document.getElementById("pipeline-list");
    if (!root) return;
    root.innerHTML = STEPS.map((name, idx) => {
      const state = idx < current ? "done" : idx === current ? "current" : "";
      return `<div class="pl-step ${state}"><span class="mark">${idx < current ? "✓" : String(idx + 1)}</span>${esc(name)}</div>`;
    }).join("");
  }

  function formatLog(log) {
    return String(log || "")
      .split("\n")
      .map((line) => {
        if (line.includes("WARN")) return `<span class="w">${esc(line)}</span>`;
        if (line.includes("ERROR")) return `<span class="e">${esc(line)}</span>`;
        return esc(line);
      })
      .join("\n");
  }

  function renderKbHits(hits, targetId = "kb-hits") {
    const box = document.getElementById(targetId);
    if (!box) return;
    if (!hits || !hits.length) {
      box.innerHTML = "";
      return;
    }
    box.innerHTML = hits
      .map(
        (h) => `
        <div class="kb-hit">
          <strong>${esc(h.title || "KB chunk")}</strong>
          <span class="score">score ${(Number(h.score) || 0).toFixed(3)}</span>
          <div style="margin-top:6px;color:var(--ink-soft)">${esc((h.text || "").slice(0, 180))}${(h.text || "").length > 180 ? "…" : ""}</div>
        </div>`
      )
      .join("");
  }

  function evidenceChip(log, receipt) {
    if (!log) return "";
    const lines = String(log).split("\n").filter(Boolean);
    const summary =
      lines.find((l) => l.startsWith("trace_id") || l.startsWith("task_id")) ||
      `${lines.length} evidence ${lines.length === 1 ? "line" : "lines"}`;
    return `<details class="evidence">
      <summary>View reasoning &amp; evidence — ${esc(summary)}</summary>
      <div class="log">${formatLog(log)}</div>
    </details>`;
  }

  const AGENT_MARK_SVG =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3c-2 3-5 4-5 8a5 5 0 0 0 10 0c0-4-3-5-5-8z"/></svg>';

  function messageRow(who, text, opts = {}) {
    const isAgent = opts.role === "agent";
    const isNote = !!opts.note;
    const name = isAgent ? "SupportMemory" : who;
    return `<div class="msg-row ${isAgent ? "agent" : "customer"}${isNote ? " note" : ""}">
        <div class="avatar" aria-hidden="true">${isAgent ? AGENT_MARK_SVG : esc(initials(name))}</div>
        <div class="msg">
          <div class="who">
            <strong>${esc(name)}</strong>
            ${isNote ? `<span class="tag-note">Internal note</span>` : opts.tag ? `<span class="tag-inv">${esc(opts.tag)}</span>` : ""}
            <span class="msg-time">${esc(fmtTime(opts.at))}</span>
          </div>
          <div class="bubble">${esc(text)}</div>
          ${opts.log ? evidenceChip(opts.log) : ""}
        </div>
      </div>`;
  }

  function renderCustomerCard(inv) {
    const el = document.getElementById("customer-card");
    if (!el) return;
    const profile = inv.profile;
    const known = profile && profile.source && profile.source !== "default";
    const name = (known && profile.display_name) || inv.requesterName || "Unknown customer";
    const channel = (known && profile.contact_channel !== "unknown" && profile.contact_channel) || inv.channel || "unknown";
    const tier = (known && profile.plan_tier !== "unknown" && profile.plan_tier) || null;
    el.innerHTML = `
      <div class="avatar cust-avatar" aria-hidden="true">${esc(initials(name))}</div>
      <div class="cust-meta">
        <div class="cust-name">${esc(name)}${inv.requesterCompany ? ` <span class="cust-company">· ${esc(inv.requesterCompany)}</span>` : ""}</div>
        <div class="cust-badges">
          <span class="chip chip-channel">${esc(CHANNEL_LABEL[channel] || channel)}</span>
          ${tier ? `<span class="chip chip-tier">${esc(tier)} plan</span>` : ""}
          ${inv.priority ? `<span class="chip chip-priority chip-priority-${esc(inv.priority)}">${esc(inv.priority)} priority</span>` : ""}
          <span class="chip ${known ? "chip-recall-known" : "chip-recall-new"}" title="Recalled from stored preferences — not re-asked">${known ? "✓ Recalled from memory" : "First contact — no profile yet"}</span>
        </div>
      </div>`;
  }

  function renderDashboard() {
    const inv = activeInv();
    document.getElementById("ticket-title").innerHTML = `Ticket #${esc(inv.ticket)} <span class="badge-ok">${esc(inv.status)}</span>`;
    document.getElementById("ticket-sub").textContent = `${inv.title} — ${inv.company}`;
    renderCustomerCard(inv);
    renderSteps(inv.step);

    let threadHtml = messageRow(inv.customer, inv.request, { role: "customer", at: inv.requestAt });
    if (inv.agent) {
      threadHtml += messageRow("SupportMemory", inv.agent, { role: "agent", tag: inv.live ? "LIVE" : "READY", log: inv.log, at: Date.now() });
    }
    (inv.messages || []).forEach((m) => {
      threadHtml += messageRow(m.who, m.text, { role: m.role, tag: m.tag, log: m.log, at: m.at, note: m.note });
    });
    document.getElementById("thread").innerHTML = threadHtml;
    const threadEl = document.getElementById("thread");
    threadEl.scrollTop = threadEl.scrollHeight;

    const top = (inv.kbHits && inv.kbHits[0]) || null;
    document.getElementById("mem-match").textContent = top
      ? `${((Number(top.score) || 0) * 100).toFixed(1)}% Match`
      : inv.match === "—"
        ? "No KB hits"
        : inv.match;
    document.getElementById("mem-note").textContent = top
      ? `Top hit: ${top.title} (${top.document_id || top.chunk_id || "kb"})`
      : "KB hits load automatically while SupportMemory investigates.";
    renderKbHits(inv.kbHits);

    document.getElementById("ckpt-label").textContent = inv.checkpointId
      ? `Saved · ${inv.checkpointId}`
      : inv.step >= 3
        ? "State saved safely"
        : "No checkpoint yet";
    document.getElementById("ckpt-note").textContent = inv.checkpointId
      ? "Recovery can resume from this trusted checkpoint without replaying completed tools."
      : "Checkpoint appears after a live task run or recovery demo.";
    document.getElementById("metric-model").textContent = inv.model || "—";
    document.getElementById("metric-dur").textContent = inv.duration || inv.status || "—";
    document.getElementById("metric-mem").textContent = (inv.integrity ?? 0) + "%";
    document.getElementById("mem-bar").style.width = (inv.integrity ?? 0) + "%";
    document.getElementById("sys-model").textContent = (inv.model || "—").toString().toUpperCase();
    document.getElementById("sys-id").textContent = inv.taskId || inv.traceId || "SM-" + inv.ticket;
    document.getElementById("sys-right").textContent = inv.traceId
      ? `trace ${inv.traceId} · ${inv.kbHits?.length || 0} KB hits · integrity ${inv.integrity ?? 0}%`
      : `API ${apiOnline ? "connected" : "offline"} · ${investigations.filter((i) => i.live).length} live runs`;
    const btn = document.getElementById("btn-receipt");
    if (btn) btn.disabled = !inv.traceId;
    renderInvList(document.getElementById("inv-search")?.value || "");
  }

  window.toggleInspector = function () {
    const dash = document.getElementById("dash");
    const hidden = dash?.classList.toggle("hide-inspector");
    const btn = document.getElementById("inspector-toggle");
    if (btn) btn.textContent = hidden ? "Show Inspector" : "Hide Inspector";
  };

  function applyTaskResponse(inv, resp, opts = {}) {
    const model = resp.model_trace?.customer_reply_model || resp.model_trace?.final_report_model || resp.model_trace?.plan_model || "Qwen";
    const hits = [];
    (resp.retrieved_rules || []).forEach((r) => {
      hits.push({
        title: r.title || r.rule_id || "Playbook rule",
        score: r.score ?? r.confidence ?? 0.8,
        text: r.rule_text || r.content || r.insight || JSON.stringify(r).slice(0, 200),
        chunk_id: r.rule_id,
        document_id: r.rule_id,
      });
    });
    inv.live = true;
    inv.status = opts.status || resp.status || "Active";
    inv.agent = resp.final_output || opts.agent || inv.agent;
    inv.log = [
      `task_id: ${resp.task_id || "—"}`,
      `trace_id: ${resp.trace_id || "—"}`,
      `checkpoint: ${resp.checkpoint_id || "—"}`,
      `recovery: ${resp.recovery_status || "none"}`,
      `rules: ${(resp.retrieved_rules || []).length}`,
      opts.extraLog || "",
      resp.tool_investigation_summary ? `\ntool investigation:\n${resp.tool_investigation_summary}` : "",
      resp.investigation_report ? `\ninvestigation report:\n${resp.investigation_report}` : "",
    ]
      .filter(Boolean)
      .join("\n");
    inv.taskId = resp.task_id || inv.taskId;
    inv.traceId = resp.trace_id || inv.traceId;
    inv.checkpointId = resp.checkpoint_id || inv.checkpointId;
    inv.model = model;
    inv.duration = resp.status || "done";
    inv.step = opts.step ?? (resp.checkpoint_id ? 8 : 5);
    inv.integrity = 100;
    inv.kbHits = opts.kbHits && opts.kbHits.length ? opts.kbHits : inv.kbHits || hits;
    if (hits.length && !(opts.kbHits && opts.kbHits.length)) inv.kbHits = hits;
    return inv;
  }

  async function runTaskFor(inv, taskDescription, extra = {}) {
    const started = performance.now();
    await ensureConversation(inv);
    const [taskResp, kbResp] = await Promise.all([
      apiPost("/api/tasks/run", {
        task_description: taskDescription,
        agent_id: AGENT_ID,
        dataset_type: "support_tickets",
        user_id: customerUserId(inv),
        conversation_id: inv.conversationId || undefined,
        ...extra,
      }),
      apiPost("/api/kb/search", {
        query: taskDescription.slice(0, 500),
        agent_id: AGENT_ID,
        top_k: 5,
      }).catch(() => ({ hits: [] })),
    ]);
    const ms = ((performance.now() - started) / 1000).toFixed(1) + "s";
    applyTaskResponse(inv, taskResp, {
      status: taskResp.status || "completed",
      step: 8,
      kbHits: kbResp.hits || [],
      extraLog: `duration: ${ms}`,
    });
    inv.duration = ms;
    inv.model = taskResp.model_trace?.customer_reply_model || taskResp.model_trace?.final_report_model || taskResp.model_trace?.plan_model || inv.model;
    return taskResp;
  }

  let composerMode = "reply";
  window.setComposerMode = function (mode) {
    composerMode = mode;
    document.querySelectorAll(".composer-mode button").forEach((b) => b.classList.toggle("active", b.dataset.mode === mode));
    const input = document.getElementById("composer");
    if (input) input.placeholder = mode === "note" ? "Add an internal note (not sent to the customer)…" : "Ask SupportMemory to take action...";
  };

  window.sendComposer = async function () {
    const input = document.getElementById("composer");
    const text = (input?.value || "").trim();
    if (!text) return;
    const inv = activeInv();
    inv.messages = inv.messages || [];
    input.value = "";

    if (composerMode === "note") {
      inv.messages.push({ role: "system", who: "Operator", text, note: true, at: Date.now() });
      renderDashboard();
      try {
        await ensureConversation(inv);
        if (inv.conversationId) {
          await apiPost(`/api/conversations/${encodeURIComponent(inv.conversationId)}/messages`, {
            role: "system",
            content: text,
            metadata: { internal: true, author: "operator" },
          });
        }
        toast("Internal note saved");
      } catch (e) {
        toast("Note not saved — API offline");
      }
      return;
    }

    inv.messages.push({ role: "user", who: "You", text, at: Date.now() });
    renderDashboard();
    setBusy(true);
    toast("Running task + KB retrieval…");
    try {
      const desc = `${inv.request}\n\nOperator follow-up: ${text}`;
      await runTaskFor(inv, desc);
      inv.messages.push({ role: "agent", who: "SupportMemory", tag: "LIVE", text: inv.agent, log: inv.log, at: Date.now() });
      inv.agent = "";
      inv.log = "";
      document.getElementById("sys-state").textContent = "ACTIVE";
      toast(`Task complete · ${(inv.kbHits || []).length} KB hits`);
      renderDashboard();
      refreshKbDocs();
      setApiPill(true, "API live");
      loadProfile(inv);
    } catch (e) {
      inv.messages.push({
        role: "agent",
        who: "SupportMemory",
        tag: "OFFLINE",
        text: "API unreachable. Start the stack (`docker compose up`) or set ?api=http://host:8000.",
        at: Date.now(),
      });
      renderDashboard();
      toast("Composer failed — API offline");
      setApiPill(false, "API offline");
    } finally {
      setBusy(false);
    }
  };

  window.quickAction = async function (action) {
    const inv = activeInv();
    inv.messages = inv.messages || [];
    const label = action === "resolve" ? "Marked ticket resolved" : "Escalated ticket to senior support";
    inv.status = action === "resolve" ? "Resolved" : "Escalated";
    inv.messages.push({ role: "system", who: "Operator", text: label, note: true, at: Date.now() });
    renderDashboard();
    try {
      await ensureConversation(inv);
      if (inv.conversationId) {
        await apiPost(`/api/conversations/${encodeURIComponent(inv.conversationId)}/messages`, {
          role: "system",
          content: label,
          metadata: { internal: true, author: "operator", action },
        });
      }
      toast(label);
    } catch (_) {
      toast(label + " (not synced — API offline)");
    }
  };

  window.startDemo = async function () {
    showPage("dashboard");
    setBusy(true);
    toast("Starting failure → recovery demo…");
    try {
      const result = await apiPost("/api/demo/failure-recovery", {});
      const task = result.task_response || result;
      const inv = {
        id: "live-" + (task.task_id || Date.now()),
        title: "Recovery demo",
        company: "SupportMemory",
        ticket: (task.task_id || "DEMO").slice(-8).toUpperCase(),
        status: "Recovered",
        customer: "Judge demo",
        requesterName: "Judge demo",
        channel: "chat",
        priority: "high",
        request:
          "Investigate support tickets, survive a simulated primary model failure, and produce an auditable recovery report.",
        requestAt: Date.now(),
        agent: result.final_report || task.final_output || "",
        log: (result.demo_steps || []).join("\n") || "recovery demo complete",
        messages: [],
        kbHits: [],
        step: 8,
        match: "—",
        similar: "recovery path",
        model: "—",
        duration: "—",
        integrity: 100,
        taskId: null,
        traceId: null,
        checkpointId: null,
        live: true,
      };
      applyTaskResponse(inv, task, { status: "Recovered", step: 8, agent: inv.agent });
      try {
        const kb = await apiPost("/api/kb/search", { query: inv.request, agent_id: AGENT_ID, top_k: 5 });
        inv.kbHits = kb.hits || [];
      } catch (_) {}
      investigations = [inv, ...investigations.filter((i) => i.id !== inv.id)];
      activeId = inv.id;
      loadProfile(inv);
      document.getElementById("sys-state").textContent = "RECOVERED";
      setApiPill(true, "API live");
      renderDashboard();
      toast("Recovery demo complete");
      refreshKbDocs();
    } catch (e) {
      toast("Recovery demo failed — is the API up?");
      setApiPill(false, "API offline");
    } finally {
      setBusy(false);
    }
  };

  const HELPDESK_PAGES = [null, "support_page_2", "support_page_3"];
  let helpdeskPageIndex = 0;

  window.newInvestigation = async function () {
    showPage("dashboard");
    setBusy(true);
    toast("Pulling mock helpdesk ticket…");
    try {
      const pageToken = HELPDESK_PAGES[helpdeskPageIndex % HELPDESK_PAGES.length];
      helpdeskPageIndex += 1;
      const mock = await apiPost("/api/connectors/helpdesk/mock", {
        source_system: "zendesk_mock",
        dataset_type: "support_tickets",
        page_token: pageToken,
      });
      const t = mock.ticket || {};
      const subject = t.subject || t.title || "Helpdesk ticket";
      const body =
        t.description || t.body || (mock.comments && mock.comments[0]?.body) || JSON.stringify(t).slice(0, 400);
      const ticketId = t.id || t.ticket_id || "HD-" + Date.now().toString().slice(-6);
      const requester = t.requester || {};
      const inv = {
        id: "hd-" + ticketId,
        title: String(subject).slice(0, 48),
        company: requester.company || t.organization || t.organization_id || mock.source_system || "Helpdesk",
        ticket: String(ticketId),
        status: "Investigating",
        customer: requester.name || requester.email || "Unknown customer",
        requesterName: requester.name || null,
        requesterEmail: requester.email || null,
        requesterCompany: requester.company || null,
        channel: mock.source_system === "freshdesk_mock" ? "chat" : "email",
        priority: t.priority || "normal",
        request: body,
        requestAt: Date.now(),
        agent: "",
        log: "",
        messages: [],
        kbHits: [],
        step: 2,
        match: "—",
        similar: "—",
        model: "—",
        duration: "…",
        integrity: 0,
        taskId: null,
        traceId: null,
        checkpointId: null,
        live: true,
      };
      investigations = [inv, ...investigations];
      activeId = inv.id;
      renderDashboard();
      loadProfile(inv);
      toast("Ticket loaded — running investigation…");
      await runTaskFor(inv, `${subject}\n\n${body}`);
      loadProfile(inv);
      document.getElementById("sys-state").textContent = "ACTIVE";
      setApiPill(true, "API live");
      renderDashboard();
      toast("Investigation complete");
      refreshKbDocs();
    } catch (e) {
      toast("Helpdesk/task failed — API offline?");
      setApiPill(false, "API offline");
    } finally {
      setBusy(false);
    }
  };

  window.loadLiveState = async function () {
    setBusy(true);
    try {
      const [state, status] = await Promise.all([apiGet("/api/demo/state"), apiGet("/api/system/status")]);
      setApiPill(true, status.connected === false ? "API · DB ?" : "API live");
      document.getElementById("sys-state").textContent = (status.status || "ACTIVE").toString().toUpperCase();
      const routing = status.model_routing || {};
      const model = routing.default || routing.primary || routing.qwen || "Qwen";
      document.getElementById("metric-model").textContent = model;
      document.getElementById("sys-model").textContent = String(model).toUpperCase();

      const traces = state.traces || [];
      if (traces.length) {
        const mapped = traces.slice(0, 12).map((tr, idx) => ({
          id: "tr-" + (tr.id || tr.task_id || idx),
          title: (tr.task_description || tr.final_output || "Run").toString().slice(0, 42),
          company: tr.agent_id || "agent",
          ticket: (tr.task_id || tr.id || "RUN").toString().slice(-8).toUpperCase(),
          status: tr.status || "live",
          customer: "Live run · " + (tr.agent_id || AGENT_ID),
          requesterEmail: (tr.metadata && tr.metadata.user_id) || null,
          conversationId: (tr.metadata && tr.metadata.conversation_id) || null,
          channel: "chat",
          request: tr.task_description || "Restored from /api/demo/state",
          requestAt: tr.created_at || Date.now(),
          agent: tr.final_output || "",
          log: `trace: ${tr.id || "—"}\ntask: ${tr.task_id || "—"}\nfailure: ${tr.failure_type || "none"}`,
          messages: [],
          kbHits: (tr.metadata && tr.metadata.kb_hits) || [],
          step: tr.status === "completed" ? 8 : 5,
          match: "—",
          similar: "live trace",
          model:
            (tr.metadata &&
              tr.metadata.model_routing &&
              (tr.metadata.model_routing.final_report_model || tr.metadata.model_routing.plan_model)) ||
            model,
          duration: tr.status || "—",
          integrity: 100,
          taskId: tr.task_id || null,
          traceId: tr.id || null,
          checkpointId: null,
          live: true,
        }));
        const ck = state.task_checkpoints || [];
        mapped.forEach((m) => {
          const hit = ck.find((c) => c.task_id === m.taskId);
          if (hit) m.checkpointId = hit.id || hit.checkpoint_id;
        });
        investigations = [...mapped, ...SAMPLE.map((x) => ({ ...x, messages: [] }))];
        activeId = investigations[0].id;
        toast(`Loaded ${mapped.length} live traces`);
      } else {
        toast("API live — no traces yet. Run recovery demo or ask in composer.");
      }
      renderDashboard();
      refreshKbDocs();
    } catch (e) {
      setApiPill(false, "API offline");
      toast("Live API unreachable");
    } finally {
      setBusy(false);
    }
  };

  window.viewReceipt = async function () {
    const inv = activeInv();
    if (!inv.traceId) return toast("No trace yet");
    setBusy(true);
    try {
      const receipt = await apiGet("/api/traces/" + encodeURIComponent(inv.traceId) + "/receipt");
      inv.messages = inv.messages || [];
      inv.messages.push({
        role: "agent",
        who: "Execution receipt",
        tag: "PROOF",
        text: "Signed receipt loaded from API.",
        log: JSON.stringify(receipt, null, 2).slice(0, 3500),
      });
      renderDashboard();
      toast(receipt.alibaba_oss_url ? "Receipt + OSS URL" : "Receipt loaded");
    } catch (e) {
      toast("Receipt fetch failed");
    } finally {
      setBusy(false);
    }
  };

  window.seedKb = async function () {
    setBusy(true);
    try {
      const res = await apiPost("/api/kb/seed-demo", {});
      toast(`KB seeded · ${res.seeded || 0} docs`);
      setApiPill(true, "API live");
      await refreshKbDocs();
    } catch (e) {
      toast("KB seed failed — API offline?");
      setApiPill(false, "API offline");
    } finally {
      setBusy(false);
    }
  };

  window.searchKb = async function () {
    const q = (document.getElementById("kb-query")?.value || "").trim();
    if (q.length < 3) return toast("Enter a longer KB query");
    setBusy(true);
    try {
      const res = await apiPost("/api/kb/search", { query: q, agent_id: AGENT_ID, top_k: 5 });
      renderKbHits(res.hits || [], "kb-page-hits");
      setApiPill(true, "API live");
      toast(`${(res.hits || []).length} KB hits`);
    } catch (e) {
      toast("KB search failed");
      setApiPill(false, "API offline");
    } finally {
      setBusy(false);
    }
  };

  window.ingestKbText = async function () {
    const title = (document.getElementById("kb-ingest-title")?.value || "Support policy").trim();
    const text = (document.getElementById("kb-ingest-text")?.value || "").trim();
    if (text.length < 20) return toast("Paste at least 20 characters");
    setBusy(true);
    try {
      const res = await apiPost("/api/kb/ingest", {
        title,
        text,
        source_type: "policy",
        tags: ["ui", "supportmemory"],
        agent_id: AGENT_ID,
      });
      toast(`Ingested · ${res.chunk_count} chunks`);
      document.getElementById("kb-ingest-text").value = "";
      await refreshKbDocs();
      setApiPill(true, "API live");
    } catch (e) {
      toast("Ingest failed");
    } finally {
      setBusy(false);
    }
  };

  window.ingestKbPdf = async function (input) {
    const file = input.files && input.files[0];
    if (!file) return;
    setBusy(true);
    toast("Uploading PDF…");
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("title", file.name.replace(/\.pdf$/i, ""));
      fd.append("agent_id", AGENT_ID);
      const res = await apiUpload("/api/kb/ingest/pdf", fd);
      toast(`PDF ingested · ${res.chunk_count} chunks`);
      await refreshKbDocs();
      setApiPill(true, "API live");
    } catch (e) {
      toast("PDF ingest failed");
    } finally {
      input.value = "";
      setBusy(false);
    }
  };

  async function refreshKbDocs() {
    try {
      const docs = await apiGet("/api/kb/documents");
      const ul = document.getElementById("kb-docs");
      if (!ul) return;
      if (!docs.length) {
        ul.innerHTML = "<li>No KB documents yet — Seed demo KB</li>";
        return;
      }
      ul.innerHTML = docs
        .slice(0, 12)
        .map((d) => `<li><strong style="color:var(--ink)">${esc(d.title)}</strong> · ${d.chunk_count} chunks</li>`)
        .join("");
    } catch (_) {}
  }

  async function pingApi() {
    try {
      const status = await apiGet("/api/system/status");
      setApiPill(true, status.connected === false ? "API · DB ?" : "API live");
      document.getElementById("sys-state").textContent = (status.status || "ACTIVE").toString().toUpperCase();
      const routing = status.model_routing || {};
      const model = routing.default || routing.primary || "Qwen";
      if (!activeInv().live) {
        document.getElementById("metric-model").textContent = model;
        document.getElementById("sys-model").textContent = String(model).toUpperCase();
      }
    } catch (_) {
      setApiPill(false, "API offline");
      document.getElementById("sys-state").textContent = "OFFLINE";
    }
  }

  // boot
  if (window.innerWidth <= 1100) {
    document.getElementById("dash")?.classList.add("hide-inspector");
    const btn = document.getElementById("inspector-toggle");
    if (btn) btn.textContent = "Show Inspector";
  }
  const hash = (location.hash || "#landing").replace("#", "");
  const known = ["landing", "capabilities", "architecture", "dashboard", "knowledge"];
  showPage(known.includes(hash) ? hash : "landing");
})();
