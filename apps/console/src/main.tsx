import React, { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, ApiError, ApiState, ConversationMessage, GraphPath, KbHit, RetrievedRule, RunEvent, TaskRunResponse } from "./api";
import "./styles.css";

type Status = "open" | "pending" | "resolved" | "escalated";
type ComposerMode = "reply" | "note";
type EvidenceTab = "memory" | "graph" | "run";

interface Message extends ConversationMessage {
  pending?: boolean;
  failed?: boolean;
  evidence?: { rules: RetrievedRule[]; kb: KbHit[]; graph: GraphPath[] };
}

interface Investigation {
  id: string;
  ticket: string;
  title: string;
  customer: string;
  company: string;
  priority: "low" | "normal" | "high" | "urgent";
  status: Status;
  userId: string;
  conversationId?: string;
  taskId?: string;
  traceId?: string;
  checkpointId?: string;
  messages: Message[];
  rules: RetrievedRule[];
  kbHits: KbHit[];
  graphPaths: GraphPath[];
  events: RunEvent[];
  contextReceiptId?: string;
  updatedAt: number;
}

const tenant = {
  organisationId: localStorage.getItem("sm.organisation") || "org_default",
  workspaceId: localStorage.getItem("sm.workspace") || "wrk_default",
  projectId: localStorage.getItem("sm.project") || "prj_default",
};

const uid = (prefix: string) => `${prefix}_${crypto.randomUUID().slice(0, 8)}`;
const clock = (value?: string | number) => value ? new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit" }).format(new Date(value)) : "Now";

function newInvestigation(): Investigation {
  const id = uid("inv");
  return {
    id,
    ticket: "NEW",
    title: "New customer investigation",
    customer: "Unassigned customer",
    company: "No account selected",
    priority: "normal",
    status: "open",
    userId: uid("customer"),
    messages: [], rules: [], kbHits: [], graphPaths: [], events: [], updatedAt: Date.now(),
  };
}

function App() {
  const [items, setItems] = useState<Investigation[]>([]);
  const [activeId, setActiveId] = useState("");
  const [apiState, setApiState] = useState<ApiState>("checking");
  const [apiLabel, setApiLabel] = useState("Connecting");
  const [query, setQuery] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [evidenceOpen, setEvidenceOpen] = useState(true);
  const [evidenceTab, setEvidenceTab] = useState<EvidenceTab>("memory");
  const [composerMode, setComposerMode] = useState<ComposerMode>("reply");
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmAction, setConfirmAction] = useState<"resolve" | "escalate" | null>(null);
  const [receipt, setReceipt] = useState<Record<string, unknown> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const threadRef = useRef<HTMLDivElement>(null);

  const active = items.find((item) => item.id === activeId);
  const visibleItems = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return items;
    return items.filter((item) => `${item.ticket} ${item.title} ${item.customer} ${item.company}`.toLowerCase().includes(normalized));
  }, [items, query]);

  useEffect(() => {
    void bootstrap();
  }, []);

  useEffect(() => {
    const saved = activeId ? localStorage.getItem(`sm.draft.${activeId}`) : "";
    setDraft(saved || "");
  }, [activeId]);

  useEffect(() => {
    if (activeId) localStorage.setItem(`sm.draft.${activeId}`, draft);
  }, [draft, activeId]);

  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: "smooth" });
  }, [active?.messages.length, busy]);

  useEffect(() => {
    const closeTransientUi = (event: globalThis.KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setSidebarOpen(false);
      setConfirmAction(null);
      setReceipt(null);
    };
    window.addEventListener("keydown", closeTransientUi);
    return () => window.removeEventListener("keydown", closeTransientUi);
  }, []);

  async function bootstrap() {
    try {
      const status = await api.status();
      setApiState(status.connected ? "online" : "degraded");
      setApiLabel(status.connected ? `${status.environment} · connected` : "Database unavailable");
      await loadLiveInvestigations();
    } catch (cause) {
      setApiState("offline");
      setApiLabel("Service unavailable");
      setError(cause instanceof Error ? cause.message : "Unable to connect to SupportMemory");
    }
  }

  async function loadLiveInvestigations() {
    try {
      const state = await api.demoState();
      const traces = Array.isArray(state.traces) ? state.traces as Record<string, unknown>[] : [];
      const mapped = traces.slice(0, 30).map<Investigation>((trace) => ({
        id: String(trace._id || trace.id || uid("trace")),
        ticket: String(trace.metadata && typeof trace.metadata === "object" ? (trace.metadata as Record<string, unknown>).ticket_id || "TRACE" : "TRACE"),
        title: String(trace.task_description || "Support investigation"),
        customer: String(trace.metadata && typeof trace.metadata === "object" ? (trace.metadata as Record<string, unknown>).customer_name || "Support customer" : "Support customer"),
        company: String(trace.metadata && typeof trace.metadata === "object" ? (trace.metadata as Record<string, unknown>).company || "Customer account" : "Customer account"),
        priority: "normal",
        status: String(trace.status).includes("success") ? "resolved" : "open",
        userId: String(trace.metadata && typeof trace.metadata === "object" ? (trace.metadata as Record<string, unknown>).user_id || uid("customer") : uid("customer")),
        taskId: String(trace.task_id || ""), traceId: String(trace._id || trace.id || ""),
        messages: [
          { message_id: uid("msg"), role: "user", content: String(trace.task_description || "Support investigation"), created_at: String(trace.created_at || "") },
          { message_id: uid("msg"), role: "assistant", content: String(trace.final_output || "No response was recorded."), created_at: String(trace.created_at || "") },
        ],
        rules: [], kbHits: [], graphPaths: [], events: [], updatedAt: Date.parse(String(trace.created_at || "")) || Date.now(),
      }));
      setItems(mapped);
      if (mapped.length) setActiveId(mapped[0].id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Live investigations could not be loaded");
    }
  }

  function updateActive(updater: (current: Investigation) => Investigation) {
    updateItem(activeId, updater);
  }

  function updateItem(id: string, updater: (current: Investigation) => Investigation) {
    setItems((current) => current.map((item) => item.id === id ? updater(item) : item));
  }

  function createInvestigation() {
    const item = newInvestigation();
    setItems((current) => [item, ...current]);
    setActiveId(item.id);
    setSidebarOpen(false);
    setError(null);
  }

  async function ensureConversation(item: Investigation) {
    if (item.conversationId) return item.conversationId;
    const conversation = await api.createConversation({
      user_id: item.userId,
      title: item.title,
      channel: "chat",
      organisation_id: tenant.organisationId,
      workspace_id: tenant.workspaceId,
      metadata: { ticket_id: item.ticket },
    });
    updateItem(item.id, (current) => ({ ...current, conversationId: conversation.conversation_id }));
    return conversation.conversation_id;
  }

  async function send(event?: FormEvent) {
    event?.preventDefault();
    if (!active || !draft.trim() || busy) return;
    const text = draft.trim();
    const targetId = active.id;
    setDraft("");
    setError(null);
    const optimistic: Message = { message_id: uid("msg"), role: composerMode === "note" ? "system" : "user", content: text, created_at: new Date().toISOString(), pending: true, metadata: composerMode === "note" ? { internal: true } : {} };
    updateItem(targetId, (current) => ({ ...current, messages: [...current.messages, optimistic], updatedAt: Date.now() }));
    setBusy(true);
    try {
      const conversationId = await ensureConversation(active);
      if (composerMode === "note") {
        await api.addMessage(conversationId, { role: "system", content: text, metadata: { internal: true, author: "operator" } }, tenant.organisationId, tenant.workspaceId);
        updateItem(targetId, (current) => ({ ...current, messages: current.messages.map((message) => message.message_id === optimistic.message_id ? { ...message, pending: false } : message) }));
        showNotice("Internal note saved");
        return;
      }
      abortRef.current = new AbortController();
      const [response, kb, graph] = await Promise.all([
        api.runTask({
          task_description: text,
          agent_id: "ticket-investigation-agent",
          dataset_type: "support_tickets",
          user_id: active.userId,
          conversation_id: conversationId,
          persist_conversation: true,
          organisation_id: tenant.organisationId,
          workspace_id: tenant.workspaceId,
          project_id: tenant.projectId,
          idempotency_key: uid("ui"),
        }, abortRef.current.signal),
        api.searchKb({ query: text, agent_id: "ticket-investigation-agent", top_k: 5, organisation_id: tenant.organisationId, workspace_id: tenant.workspaceId }).catch(() => ({ hits: [], context_prefix: "" })),
        api.traverseGraph({ query: text, organisation_id: tenant.organisationId, workspace_id: tenant.workspaceId, max_depth: 2, max_paths: 8 }).catch(() => []),
      ]);
      applyResponse(targetId, response, kb.hits, graph, optimistic.message_id);
      showNotice("Response completed and evidence recorded");
    } catch (cause) {
      const message = cause instanceof ApiError ? `${cause.status}: ${cause.detail}` : cause instanceof Error ? cause.message : "Message failed";
      setError(message);
      updateItem(targetId, (current) => ({ ...current, messages: current.messages.map((item) => item.message_id === optimistic.message_id ? { ...item, pending: false, failed: true } : item) }));
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  function applyResponse(targetId: string, response: TaskRunResponse, kbHits: KbHit[], graphPaths: GraphPath[], optimisticId: string) {
    const assistant: Message = {
      message_id: uid("msg"), role: "assistant", content: response.final_output,
      created_at: new Date().toISOString(), evidence: { rules: response.retrieved_rules || [], kb: kbHits, graph: graphPaths },
    };
    updateItem(targetId, (current) => ({
      ...current,
      ticket: current.ticket === "NEW" ? response.task_id.slice(-8).toUpperCase() : current.ticket,
      title: current.title === "New customer investigation" ? current.messages.find((m) => m.message_id === optimisticId)?.content.slice(0, 70) || current.title : current.title,
      taskId: response.task_id, traceId: response.trace_id, checkpointId: response.checkpoint_id,
      contextReceiptId: response.context_receipt_id,
      status: response.status === "success" ? "resolved" : current.status,
      rules: response.retrieved_rules || [], kbHits, graphPaths, events: response.run_events || [],
      messages: [...current.messages.map((message) => message.message_id === optimisticId ? { ...message, pending: false } : message), assistant],
      updatedAt: Date.now(),
    }));
  }

  async function executeAction(action: "resolve" | "escalate") {
    if (!active?.taskId) {
      setError("Run the investigation before taking a governed action.");
      setConfirmAction(null);
      return;
    }
    const target = active;
    setBusy(true);
    setError(null);
    try {
      const result = await api.executeAction(target.taskId!, {
        tool_name: action === "resolve" ? "resolve_ticket" : "escalate_ticket",
        tool_type: "external_action",
        idempotency_key: uid(action),
        input: { ticket_id: target.ticket, requested_by: "operator" },
      });
      const decision = String(result.decision);
      if (decision === "needs_approval") {
        setError("This action requires human approval and was not executed.");
      } else if (decision === "allowed") {
        updateItem(target.id, (current) => ({ ...current, status: action === "resolve" ? "resolved" : "escalated", messages: [...current.messages, { message_id: uid("msg"), role: "system", content: `${action === "resolve" ? "Resolved" : "Escalated"} through governed action ${result.action_id}.`, created_at: new Date().toISOString() }] }));
        showNotice(`Ticket ${action === "resolve" ? "resolved" : "escalated"}`);
      } else {
        setError(`Action was ${decision}. No ticket state was changed.`);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Action failed");
    } finally {
      setBusy(false);
      setConfirmAction(null);
    }
  }

  async function loadReceipt() {
    if (!active?.traceId) return;
    try { setReceipt(await api.receipt(active.traceId)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Receipt could not be loaded"); }
  }

  function showNotice(message: string) {
    setNotice(message);
    window.setTimeout(() => setNotice(null), 3500);
  }

  function composerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void send();
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-block">
          <button className="icon-button mobile-only" aria-label="Open investigations" onClick={() => setSidebarOpen(true)}>☰</button>
          <div className="brand-mark" aria-hidden="true">S</div>
          <div><strong>SupportMemory</strong><span>Agent workspace</span></div>
        </div>
        <div className="workspace-switcher"><span className="eyebrow">Workspace</span><strong>{tenant.workspaceId.replace("wrk_", "")}</strong></div>
        <div className={`connection ${apiState}`} role="status"><i />{apiLabel}</div>
        <div className="avatar-button" aria-label="Signed in operator">OO</div>
      </header>

      <div className="workspace">
        <aside className={`inbox ${sidebarOpen ? "open" : ""}`} aria-label="Investigation inbox">
          <div className="inbox-head"><div><span className="eyebrow">Operations</span><h1>Investigations</h1></div><button className="icon-button mobile-only" aria-label="Close investigations" onClick={() => setSidebarOpen(false)}>×</button></div>
          <button className="primary-button full" onClick={createInvestigation}>＋ New investigation</button>
          <label className="search-field"><span aria-hidden="true">⌕</span><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search tickets or customers" aria-label="Search investigations" /></label>
          <div className="queue-meta"><span>{visibleItems.length} tickets</span><button onClick={() => void loadLiveInvestigations()}>Refresh</button></div>
          <nav className="ticket-list" aria-label="Investigations">
            {visibleItems.map((item) => <TicketRow key={item.id} item={item} active={item.id === activeId} onSelect={() => { setActiveId(item.id); setSidebarOpen(false); }} />)}
            {!visibleItems.length && <Empty compact title={apiState === "offline" ? "Service unavailable" : "No investigations"} body={apiState === "offline" ? "Reconnect to load live tickets." : "Create an investigation to start working."} />}
          </nav>
          <div className="inbox-foot"><span>Scoped to {tenant.organisationId}</span><span>{tenant.workspaceId}</span></div>
        </aside>

        <main className="conversation" aria-label="Conversation workspace">
          {active ? <>
            <header className="conversation-head">
              <div className="ticket-identity"><div className="customer-avatar" aria-hidden="true">{active.customer.slice(0, 2).toUpperCase()}</div><div><div className="title-row"><h2>{active.title}</h2><StatusPill status={active.status} /></div><p>#{active.ticket} · {active.customer} · {active.company}</p></div></div>
              <div className="head-actions"><button className="secondary-button" onClick={() => setConfirmAction("escalate")}>Escalate</button><button className="primary-button" onClick={() => setConfirmAction("resolve")}>Resolve</button><button className="icon-button" aria-label={evidenceOpen ? "Close evidence" : "Open evidence"} aria-expanded={evidenceOpen} onClick={() => setEvidenceOpen(!evidenceOpen)}>◫</button></div>
            </header>
            <RunStrip events={active.events} busy={busy} checkpoint={active.checkpointId} />
            {error && <div className="error-banner" role="alert"><div><strong>Action needed</strong><span>{error}</span></div><button onClick={() => setError(null)} aria-label="Dismiss error">×</button></div>}
            <div className="thread" ref={threadRef} aria-live="polite">
              {!active.messages.length && <Empty title="Start with the customer’s question" body="SupportMemory will retrieve customer context, policies, learned rules, and related graph evidence before answering." />}
              {active.messages.map((message) => <MessageBubble key={message.message_id} message={message} onEvidence={() => { setEvidenceTab("memory"); setEvidenceOpen(true); }} />)}
              {busy && <Thinking />}
            </div>
            <form className="composer" onSubmit={send}>
              <div className="composer-tabs" role="tablist" aria-label="Message type"><button type="button" role="tab" aria-selected={composerMode === "reply"} className={composerMode === "reply" ? "active" : ""} onClick={() => setComposerMode("reply")}>Customer reply</button><button type="button" role="tab" aria-selected={composerMode === "note"} className={composerMode === "note" ? "active" : ""} onClick={() => setComposerMode("note")}>Internal note</button><span>{draft.length}/4000</span></div>
              <div className="composer-box"><textarea value={draft} maxLength={4000} onChange={(e) => setDraft(e.target.value)} onKeyDown={composerKeyDown} placeholder={composerMode === "reply" ? "Ask SupportMemory or reply to the customer…" : "Add a private note for your team…"} aria-label={composerMode === "reply" ? "Customer reply" : "Internal note"} rows={2} /><button type={busy ? "button" : "submit"} className={busy ? "stop-button" : "send-button"} disabled={!busy && !draft.trim()} onClick={busy ? () => abortRef.current?.abort() : undefined}>{busy ? "Stop" : "Send"}</button></div>
              <p className="composer-hint">Enter to send · Shift + Enter for a new line · Draft saved on this device</p>
            </form>
          </> : <Empty title={apiState === "offline" ? "SupportMemory is offline" : "No investigation selected"} body={apiState === "offline" ? "Check the API connection and retry. Sample content is never substituted for live data." : "Choose a ticket from the inbox or create a new investigation."} action={apiState === "offline" ? () => void bootstrap() : createInvestigation} actionLabel={apiState === "offline" ? "Retry connection" : "New investigation"} />}
        </main>

        {active && evidenceOpen && <EvidencePanel item={active} tab={evidenceTab} setTab={setEvidenceTab} close={() => setEvidenceOpen(false)} receipt={() => void loadReceipt()} />}
      </div>

      {confirmAction && active && <ConfirmDialog action={confirmAction} ticket={active.ticket} busy={busy} cancel={() => setConfirmAction(null)} confirm={() => void executeAction(confirmAction)} />}
      {receipt && <JsonDialog title="Signed execution receipt" data={receipt} close={() => setReceipt(null)} />}
      {notice && <div className="toast" role="status" aria-live="polite">✓ {notice}</div>}
    </div>
  );
}

function TicketRow({ item, active, onSelect }: { item: Investigation; active: boolean; onSelect: () => void }) {
  return <button className={`ticket-row ${active ? "active" : ""}`} aria-current={active ? "page" : undefined} onClick={onSelect}><div className="ticket-row-top"><strong>#{item.ticket}</strong><span>{clock(item.updatedAt)}</span></div><h3>{item.title}</h3><p>{item.customer} · {item.company}</p><div className="ticket-row-bottom"><StatusPill status={item.status} /><span className={`priority ${item.priority}`}>{item.priority}</span></div></button>;
}

function StatusPill({ status }: { status: Status }) { return <span className={`status-pill ${status}`}><i />{status}</span>; }

function RunStrip({ events, busy, checkpoint }: { events: RunEvent[]; busy: boolean; checkpoint?: string }) {
  const complete = events.filter((event) => event.status === "complete").length;
  const label = busy ? "SupportMemory is investigating" : checkpoint ? "Checkpoint saved" : events.length ? `${complete}/${events.length} execution steps complete` : "Ready to investigate";
  return <div className={`run-strip ${busy ? "running" : ""}`} role="status"><span className="run-icon">{busy ? "●" : checkpoint ? "✓" : "◇"}</span><div><strong>{label}</strong><span>{checkpoint ? `Recovery point ${checkpoint}` : "Memory, tools and governance will appear here"}</span></div>{events.length > 0 && <div className="mini-progress"><i style={{ width: `${events.length ? complete / events.length * 100 : 0}%` }} /></div>}</div>;
}

function MessageBubble({ message, onEvidence }: { message: Message; onEvidence: () => void }) {
  const label = message.role === "assistant" ? "SupportMemory" : message.role === "system" ? "Internal note" : "You";
  return <article className={`message ${message.role} ${message.failed ? "failed" : ""}`}><div className="message-avatar" aria-hidden="true">{message.role === "assistant" ? "S" : message.role === "system" ? "N" : "YO"}</div><div className="message-content"><header><strong>{label}</strong>{message.role === "system" && <span className="private-tag">Private</span>}<time>{message.pending ? "Sending…" : message.failed ? "Not sent" : clock(message.created_at)}</time></header><div className="bubble">{message.content}</div>{message.failed && <p className="failed-text">Delivery failed. Copy the message and retry when the service is available.</p>}{message.evidence && (message.evidence.kb.length + message.evidence.rules.length + message.evidence.graph.length > 0) && <button className="evidence-link" onClick={onEvidence}>◈ {message.evidence.kb.length + message.evidence.rules.length + message.evidence.graph.length} evidence items used</button>}</div></article>;
}

function Thinking() { return <div className="thinking" role="status"><div className="message-avatar">S</div><div><strong>SupportMemory</strong><p><i /><i /><i /> Retrieving memory and validating evidence</p></div></div>; }

function EvidencePanel({ item, tab, setTab, close, receipt }: { item: Investigation; tab: EvidenceTab; setTab: (tab: EvidenceTab) => void; close: () => void; receipt: () => void }) {
  return <aside className="evidence-panel" aria-label="Investigation evidence"><header><div><span className="eyebrow">Trace intelligence</span><h2>Evidence & memory</h2></div><button className="icon-button" onClick={close} aria-label="Close evidence">×</button></header><div className="evidence-tabs" role="tablist"><button role="tab" aria-selected={tab === "memory"} className={tab === "memory" ? "active" : ""} onClick={() => setTab("memory")}>Memory</button><button role="tab" aria-selected={tab === "graph"} className={tab === "graph" ? "active" : ""} onClick={() => setTab("graph")}>Graph</button><button role="tab" aria-selected={tab === "run"} className={tab === "run" ? "active" : ""} onClick={() => setTab("run")}>Run</button></div><div className="evidence-body">
    {tab === "memory" && <><EvidenceSection title="Knowledge base" count={item.kbHits.length}>{item.kbHits.map((hit) => <EvidenceCard key={hit.chunk_id} title={hit.title} score={hit.score} body={hit.text} meta={hit.source_type || "KB chunk"} />)}</EvidenceSection><EvidenceSection title="Operating lessons" count={item.rules.length}>{item.rules.map((rule) => <EvidenceCard key={rule.rule_id} title={rule.category || "Learned rule"} score={rule.score} body={rule.rule_text} meta={rule.evidence_ids?.join(", ") || "Approved memory"} />)}</EvidenceSection></>}
    {tab === "graph" && <EvidenceSection title="Relationship paths" count={item.graphPaths.length}>{item.graphPaths.map((path, index) => <div className="graph-card" key={`${path.node_ids.join("-")}-${index}`}><span className="score-badge">{Math.round(path.score * 100)}%</span><div className="graph-chain">{path.node_ids.map((node, nodeIndex) => <React.Fragment key={`${node}-${nodeIndex}`}><span>{node.replace(/^node_/, "Entity ")}</span>{path.relations[nodeIndex] && <b>— {path.relations[nodeIndex].replace(":reverse", "").replace(/_/g, " ").toLowerCase()} →</b>}</React.Fragment>)}</div><small>Evidence: {path.evidence_ids.join(", ") || "relationship record"}</small></div>)}</EvidenceSection>}
    {tab === "run" && <><div className="run-summary"><Info label="Task" value={item.taskId || "Not started"} /><Info label="Trace" value={item.traceId || "Not recorded"} /><Info label="Checkpoint" value={item.checkpointId || "Not saved"} /><Info label="Context receipt" value={item.contextReceiptId || "Not created"} /></div><EvidenceSection title="Execution timeline" count={item.events.length}>{item.events.map((event) => <div className={`event-row ${event.status}`} key={event.code}><i /><div><strong>{event.label}</strong><p>{event.description}</p></div></div>)}</EvidenceSection>{item.traceId && <button className="secondary-button full" onClick={receipt}>View signed receipt</button>}</>}
    {(tab === "memory" && !item.kbHits.length && !item.rules.length) || (tab === "graph" && !item.graphPaths.length) ? <Empty compact title="No evidence retrieved yet" body="Run the investigation to retrieve governed memory and relationship paths." /> : null}
  </div></aside>;
}

function EvidenceSection({ title, count, children }: { title: string; count: number; children: React.ReactNode }) { return <section className="evidence-section"><header><h3>{title}</h3><span>{count}</span></header>{children}</section>; }
function EvidenceCard({ title, score, body, meta }: { title: string; score: number; body: string; meta: string }) { return <article className="evidence-card"><div><strong>{title}</strong><span>{Math.round(score * 100)}% match</span></div><p>{body}</p><small>{meta}</small></article>; }
function Info({ label, value }: { label: string; value: string }) { return <div className="info-row"><span>{label}</span><code>{value}</code></div>; }

function Empty({ title, body, compact, action, actionLabel }: { title: string; body: string; compact?: boolean; action?: () => void; actionLabel?: string }) { return <div className={`empty-state ${compact ? "compact" : ""}`}><div className="empty-mark" aria-hidden="true">◎</div><h2>{title}</h2><p>{body}</p>{action && <button className="primary-button" onClick={action}>{actionLabel}</button>}</div>; }

function ConfirmDialog({ action, ticket, busy, cancel, confirm }: { action: "resolve" | "escalate"; ticket: string; busy: boolean; cancel: () => void; confirm: () => void }) { return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && cancel()}><div className="dialog" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title"><span className={`dialog-icon ${action}`}>{action === "resolve" ? "✓" : "↑"}</span><h2 id="confirm-title">{action === "resolve" ? "Resolve" : "Escalate"} ticket #{ticket}?</h2><p>This sends a governed, idempotent action to the runtime. The ticket changes only after server confirmation.</p><div className="dialog-actions"><button autoFocus className="secondary-button" onClick={cancel}>Cancel</button><button className="primary-button" disabled={busy} onClick={confirm}>{busy ? "Checking policy…" : `Confirm ${action}`}</button></div></div></div>; }
function JsonDialog({ title, data, close }: { title: string; data: Record<string, unknown>; close: () => void }) { return <div className="modal-backdrop"><div className="dialog wide" role="dialog" aria-modal="true" aria-labelledby="json-title"><div className="dialog-head"><h2 id="json-title">{title}</h2><button className="icon-button" onClick={close} aria-label="Close receipt">×</button></div><pre>{JSON.stringify(data, null, 2)}</pre></div></div>; }

createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
