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
    customer: "Sarah Jenkins · Client Advocate @ Apex Cloud",
    request: "We're seeing recurring 401 Unauthorized errors on our webhook endpoint after rotating the signing secret yesterday. Can you find the root cause?",
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

  function userId() {
    const key = "supportmemory_user_id";
    let id = localStorage.getItem(key);
    if (!id) {
      id = "user_" + Math.random().toString(36).slice(2, 10);
      localStorage.setItem(key, id);
    }
    return id;
  }

  async function ensureConversation(inv) {
    if (inv.conversationId) return inv.conversationId;
    try {
      const conv = await apiPost("/api/conversations", {
        user_id: userId(),
        title: inv.title || "Support conversation",
        channel: "chat",
      });
      inv.conversationId = conv.conversation_id;
    } catch (_) {
      // API unreachable or endpoint missing — task run still works without conversation memory.
    }
    return inv.conversationId;
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
        };
        list.appendChild(b);
      });
  }

  function renderSteps(current) {
    const root = document.getElementById("steps");
    if (!root) return;
    root.innerHTML = "";
    STEPS.forEach((name, idx) => {
      const s = document.createElement("div");
      s.className = "step" + (idx < current ? " done" : idx === current ? " current" : "");
      s.innerHTML = `<span class="mark">${idx < current ? "✓" : String(idx + 1)}</span>${name}`;
      root.appendChild(s);
      if (idx < STEPS.length - 1) {
        const line = document.createElement("div");
        line.className = "step-line";
        root.appendChild(line);
      }
    });
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

  function renderKbHits(hits) {
    const box = document.getElementById("kb-hits");
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

  function renderDashboard() {
    const inv = activeInv();
    document.getElementById("ticket-title").innerHTML = `Ticket #${esc(inv.ticket)} <span class="badge-ok">${esc(inv.status)}</span>`;
    document.getElementById("ticket-sub").textContent = `${inv.title} — ${inv.company}`;
    renderSteps(inv.step);

    let threadHtml = `
        <div class="msg">
          <div class="who">${esc(inv.customer)}</div>
          <div class="bubble">${esc(inv.request)}</div>
        </div>`;
    if (inv.agent) {
      threadHtml += `
        <div class="msg agent">
          <div class="who">SupportMemory <span class="tag-inv">${inv.live ? "LIVE" : "READY"}</span></div>
          <div class="bubble">${esc(inv.agent)}<div class="log">${formatLog(inv.log)}</div></div>
        </div>`;
    }
    (inv.messages || []).forEach((m) => {
      threadHtml += `<div class="msg ${m.role === "agent" ? "agent" : ""}">
          <div class="who">${esc(m.who)}${m.tag ? ` <span class="tag-inv">${esc(m.tag)}</span>` : ""}</div>
          <div class="bubble">${esc(m.text)}${m.log ? `<div class="log">${formatLog(m.log)}</div>` : ""}</div>
        </div>`;
    });
    document.getElementById("thread").innerHTML = threadHtml;

    const top = (inv.kbHits && inv.kbHits[0]) || null;
    document.getElementById("mem-match").textContent = top
      ? `${((Number(top.score) || 0) * 100).toFixed(1)}% Match`
      : inv.match === "—"
        ? "No KB hits"
        : inv.match;
    document.getElementById("mem-note").textContent = top
      ? `Top hit: ${top.title} (${top.document_id || top.chunk_id || "kb"})`
      : "Seed demo KB + Search, or ask in the composer (tasks/run retrieves KB automatically).";
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
    document.getElementById("inspector")?.classList.toggle("open");
  };

  function applyTaskResponse(inv, resp, opts = {}) {
    const model = resp.model_trace?.final_report_model || resp.model_trace?.plan_model || "Qwen";
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
        user_id: userId(),
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
    inv.model = taskResp.model_trace?.final_report_model || taskResp.model_trace?.plan_model || inv.model;
    return taskResp;
  }

  window.sendComposer = async function () {
    const input = document.getElementById("composer");
    const text = (input?.value || "").trim();
    if (!text) return;
    const inv = activeInv();
    inv.messages = inv.messages || [];
    inv.messages.push({ role: "user", who: "You", text });
    input.value = "";
    renderDashboard();
    setBusy(true);
    toast("Running task + KB retrieval…");
    try {
      const desc = `${inv.request}\n\nOperator follow-up: ${text}`;
      await runTaskFor(inv, desc);
      inv.messages.push({ role: "agent", who: "SupportMemory", tag: "LIVE", text: inv.agent, log: inv.log });
      inv.agent = "";
      inv.log = "";
      document.getElementById("sys-state").textContent = "ACTIVE";
      toast(`Task complete · ${(inv.kbHits || []).length} KB hits`);
      renderDashboard();
      refreshKbDocs();
      setApiPill(true, "API live");
    } catch (e) {
      inv.messages.push({
        role: "agent",
        who: "SupportMemory",
        tag: "OFFLINE",
        text: "API unreachable. Start the stack (`docker compose up`) or set ?api=http://host:8000.",
      });
      renderDashboard();
      toast("Composer failed — API offline");
      setApiPill(false, "API offline");
    } finally {
      setBusy(false);
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
        customer: "Judge demo · failure → checkpoint → resume",
        request:
          "Investigate support tickets, survive a simulated primary model failure, and produce an auditable recovery report.",
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

  window.newInvestigation = async function () {
    showPage("dashboard");
    setBusy(true);
    toast("Pulling mock helpdesk ticket…");
    try {
      const mock = await apiPost("/api/connectors/helpdesk/mock", {
        source_system: "zendesk_mock",
        dataset_type: "support_tickets",
      });
      const t = mock.ticket || {};
      const subject = t.subject || t.title || "Helpdesk ticket";
      const body =
        t.description || t.body || (mock.comments && mock.comments[0]?.body) || JSON.stringify(t).slice(0, 400);
      const ticketId = t.id || t.ticket_id || "HD-" + Date.now().toString().slice(-6);
      const inv = {
        id: "hd-" + ticketId,
        title: String(subject).slice(0, 48),
        company: t.organization || t.organization_id || mock.source_system || "Helpdesk",
        ticket: String(ticketId),
        status: "Investigating",
        customer: (t.requester && (t.requester.name || t.requester.email)) || "Helpdesk requester",
        request: body,
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
      toast("Ticket loaded — running investigation…");
      await runTaskFor(inv, `${subject}\n\n${body}`);
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
          request: tr.task_description || "Restored from /api/demo/state",
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
    const q = (document.getElementById("kb-query")?.value || activeInv().request || "").trim();
    if (q.length < 3) return toast("Enter a longer KB query");
    setBusy(true);
    try {
      const res = await apiPost("/api/kb/search", { query: q, agent_id: AGENT_ID, top_k: 5 });
      const inv = activeInv();
      inv.kbHits = res.hits || [];
      inv.match = inv.kbHits[0] ? ((inv.kbHits[0].score || 0) * 100).toFixed(1) + "%" : "—";
      renderDashboard();
      setApiPill(true, "API live");
      toast(`${inv.kbHits.length} KB hits`);
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
  const hash = (location.hash || "#landing").replace("#", "");
  const known = ["landing", "capabilities", "architecture", "dashboard"];
  showPage(known.includes(hash) ? hash : "landing");
})();
