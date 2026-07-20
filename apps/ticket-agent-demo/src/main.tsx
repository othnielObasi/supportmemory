// @ts-nocheck
import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const learnedRule =
  "When analysing records from a paginated source, continue fetching until next_page_token is null before producing a final answer.";

const nextLabels = [
  "Start investigation",
  "Run governed tools",
  "Simulate restart",
  "Add compliance scope",
  "Demo complete",
];

const heroTracePreview = [
  { type: "cmd", text: "> start long_running_ticket_investigation" },
  { type: "ok", text: "plan prepared before tool execution" },
  { type: "ok", text: "Runtime Governor allowed read-only retrieval" },
  { type: "warn", text: "tool signalled more records" },
  { type: "ok", text: "PostgreSQL checkpoint saved" },
  { type: "warn", text: "interruption detected" },
  { type: "ok", text: "checkpoint restored from PostgreSQL" },
  { type: "cmd", text: "> add compliance_tickets scope" },
  { type: "ok", text: "execution memory retrieved before planning" },
  { type: "ok", text: "task completed with adapted retrieval" },
];

const conversationHistory = [
  { id: "thread_support", title: "Support ticket analysis", subtitle: "Run 1 · memory created" },
  { id: "thread_compliance", title: "Compliance blockers", subtitle: "Run 2 · memory applied" },
  { id: "thread_vendor", title: "Vendor evidence review", subtitle: "Draft · not started" },
  { id: "thread_refunds", title: "Refund escalation themes", subtitle: "Completed · pattern reused" },
  { id: "thread_onboarding", title: "Onboarding friction", subtitle: "Completed · evidence checked" },
  { id: "thread_privacy", title: "Privacy request blockers", subtitle: "Completed · governed run" },
  { id: "thread_billing", title: "Billing delay analysis", subtitle: "Completed · memory candidate" },
  { id: "thread_incidents", title: "Incident follow-up queue", subtitle: "Completed · no update" },
  { id: "thread_access", title: "Access request tickets", subtitle: "Completed · approval pattern" },
  { id: "thread_renewals", title: "Renewal support themes", subtitle: "Completed · summary" },
  { id: "thread_kyc", title: "KYC review blockers", subtitle: "Completed · validation used" },
  { id: "thread_sla", title: "SLA breach tickets", subtitle: "Completed · trace stored" },
];

const runEvents = [
  { code: "request_received", label: "Request", description: "User submits a long-running investigation task." },
  { code: "understanding_generated", label: "Understand", description: "Agent confirms task goal, scope, data source, and completion condition." },
  { code: "plan_prepared", label: "Plan", description: "Agent prepares the retrieval and validation plan before tools run." },
  { code: "runtime_decision", label: "Approve", description: "Runtime Governor approves, blocks, or escalates the tool action." },
  { code: "tool_execution_started", label: "Execute", description: "Approved tools execute and return observable signals." },
  { code: "trace_recorded", label: "Trace", description: "Tool calls, decisions, observations, and validation signals are recorded." },
  { code: "checkpoint_saved", label: "Checkpoint", description: "PostgreSQL stores task state, trace state, and continuation context." },
  { code: "interruption_detected", label: "Interrupt", description: "A restart/failure event is detected during the long-running workflow." },
  { code: "checkpoint_restored", label: "Recover", description: "Agent resumes from the PostgreSQL checkpoint without losing task consistency." },
  { code: "task_modified", label: "Modify", description: "User changes the task scope while preserving prior context." },
  { code: "memory_created_or_retrieved", label: "Memory", description: "Approved execution memory is created, retrieved, or applied." },
  { code: "final_answer", label: "Answer", description: "Agent returns the result after validation conditions are satisfied." },
];

const stageEventCodes = {
  ready: ["request_received"],
  plan: ["request_received", "understanding_generated", "plan_prepared", "runtime_decision"],
  execute: [
    "request_received",
    "understanding_generated",
    "plan_prepared",
    "runtime_decision",
    "tool_execution_started",
    "trace_recorded",
    "checkpoint_saved",
  ],
  recover: [
    "request_received",
    "understanding_generated",
    "plan_prepared",
    "runtime_decision",
    "tool_execution_started",
    "trace_recorded",
    "checkpoint_saved",
    "interruption_detected",
    "checkpoint_restored",
  ],
  improve: [
    "request_received",
    "checkpoint_restored",
    "task_modified",
    "memory_created_or_retrieved",
    "understanding_generated",
    "plan_prepared",
    "runtime_decision",
    "tool_execution_started",
    "trace_recorded",
    "checkpoint_saved",
    "final_answer",
  ],
};

const stages = [
  {
    id: "ready",
    label: "Ready",
    input: "Analyse all support tickets and summarise recurring customer issues.",
    progress: 0,
    eyebrow: "Waiting",
    headline: "No active run.",
    summary: "Idle. No execution trace has started.",
    terminal: [
      { type: "cmd", text: "> await task" },
      { type: "muted", text: "no active execution trace" },
      { type: "muted", text: "no PostgreSQL memory applied" },
    ],
    messages: [],
    side: {
      decision: "No runtime action yet",
      memory: "No memory applied",
      validation: "No execution condition checked yet",
    },
    evidence: {
      traceId: "—",
      toolEvidence: "0 tool calls",
      mongoRecord: "—",
      receipt: "—",
      observedSignal: "No task signal observed yet",
      response: "No execution response yet",
    },
  },
  {
    id: "plan",
    label: "Plan",
    input: "Analyse all support tickets and summarise recurring customer issues.",
    progress: 34,
    eyebrow: "Plan before tools",
    headline: "The agent commits to a complete retrieval path.",
    summary: "Plan prepared. Retrieval path and completion condition set.",
    terminal: [
      { type: "cmd", text: "> analyse support_tickets" },
      { type: "ok", text: "goal understood: recurring customer issues" },
      { type: "ok", text: "completion condition: terminal next_page_token" },
      { type: "ok", text: "runtime decision: read-only · allowed" },
    ],
    messages: [
      { role: "user", text: "Analyse all support tickets and summarise recurring customer issues." },
      { role: "agent", eyebrow: "Understanding", text: "You want a complete support-ticket analysis that identifies recurring customer issues across the available records." },
      { role: "agent", eyebrow: "Plan", text: "Plan: retrieve ticket records, follow continuation signals, stop at terminal response, then summarise recurring issues." },
      { role: "agent", eyebrow: "Runtime decision", text: "Runtime decision: read-only retrieval approved. No write, delete, send, or external disclosure requested." },
    ],
    side: {
      decision: "Low risk · read-only · auto-approved",
      memory: "No prior memory needed",
      validation: "Plan includes terminal next_page_token check",
    },
    evidence: {
      traceId: "plan_support_001",
      toolEvidence: "0 planned / 0 executed",
      mongoRecord: "No lesson stored yet",
      receipt: "plan:8f21c4",
      observedSignal: "Planning stage only; no tool signal observed yet",
      response: "Agent commits to inspect next_page_token before answering",
    },
  },
  {
    id: "execute",
    label: "Execute",
    input: "Analyse all support tickets and summarise recurring customer issues.",
    progress: 56,
    eyebrow: "Governed execution",
    headline: "The support-ticket trace becomes approved execution memory.",
    summary: "Support phase complete. PostgreSQL checkpoint and approved execution memory stored.",
    terminal: [
      { type: "cmd", text: "> fetch_support_tickets" },
      { type: "ok", text: "Runtime Governor allowed read-only retrieval" },
      { type: "warn", text: "tool returned next_page_token=page_2" },
      { type: "ok", text: "continued until next_page_token=null" },
      { type: "ok", text: "summary produced from complete retrieved set" },
      { type: "ok", text: "approved lesson stored in PostgreSQL" },
    ],
    messages: [
      { role: "user", text: "Analyse all support tickets and summarise recurring customer issues." },
      { role: "agent", eyebrow: "Governed tool use", text: "Runtime Governor approved fetch_support_tickets. Tool returned next_page_token=page_2." },
      { role: "agent", eyebrow: "Execution", text: "Fetched subsequent pages until next_page_token=null." },
      { role: "agent", eyebrow: "Result", text: "Recurring issues across all pages: billing delays, login failures, refund-status confusion, onboarding friction, and slow response times." },
      { role: "agent", eyebrow: "Memory created", text: "Approved execution memory stored in PostgreSQL." },
    ],
    side: {
      decision: "Runtime Governor allowed and traced the read-only tool call",
      memory: "New approved execution memory stored in PostgreSQL",
      validation: "Terminal next_page_token=null reached before summary",
    },
    evidence: {
      traceId: "trace_support_001",
      toolEvidence: "fetch_support_tickets until next_page_token=null",
      mongoRecord: "execution_memory.rule_support_pagination_001",
      receipt: "sha256:9f2c7d6c54e6",
      observedSignal: "Tool returned next_page_token=page_2",
      response: "Agent continued retrieval until next_page_token=null before summary",
    },
    memory: {
      title: "Execution memory created",
      text: learnedRule,
      meta: "PostgreSQL · trace_support_001 · approved · confidence 92%",
    },
  },
  {
    id: "recover",
    label: "Recover",
    input: "Resume the investigation after interruption.",
    progress: 78,
    eyebrow: "Checkpoint restored",
    headline: "The agent resumes from PostgreSQL context.",
    summary: "Interruption handled. Task state, trace state, and memory context restored from PostgreSQL.",
    terminal: [
      { type: "cmd", text: "> simulate_restart" },
      { type: "warn", text: "interruption detected after support-ticket checkpoint" },
      { type: "ok", text: "PostgreSQL checkpoint restored" },
      { type: "ok", text: "task_version=1 · recovery_status=restored" },
      { type: "ok", text: "prior retrieval lesson available for next scope" },
    ],
    messages: [
      { role: "user", text: "The run was interrupted. Resume from the last safe state." },
      { role: "agent", eyebrow: "Recovery", text: "Checkpoint restored from PostgreSQL. Support-ticket trace, task version, and approved retrieval memory are available." },
      { role: "agent", eyebrow: "Consistency", text: "The investigation can continue without restarting from scratch or losing the terminal retrieval rule." },
    ],
    side: {
      decision: "Recovery allowed from trusted PostgreSQL checkpoint",
      memory: "Approved execution memory available after restore",
      validation: "checkpoint_restored after checkpoint_saved",
    },
    evidence: {
      traceId: "recover_support_001",
      toolEvidence: "checkpoint_saved → interruption_detected → checkpoint_restored",
      mongoRecord: "task_checkpoints.chk_support_001",
      receipt: "sha256:checkpoint9f2c7d",
      observedSignal: "Recovered task_version=1 from PostgreSQL checkpoint",
      response: "Agent resumed with prior trace, state, and approved retrieval memory",
    },
    memory: {
      title: "Checkpoint restored",
      text: "PostgreSQL restored the latest task state, tool trace state, and approved execution memory.",
      meta: "PostgreSQL · chk_support_001 · recovery_status=restored",
    },
  },
  {
    id: "improve",
    label: "Improve",
    input: "Modify the resumed investigation to include compliance tickets and identify recurring blockers.",
    progress: 100,
    eyebrow: "Memory-guided run",
    headline: "The resumed investigation adapts to the new compliance scope.",
    summary: "Task modified. Approved execution memory applied before the compliance-ticket retrieval plan.",
    terminal: [
      { type: "cmd", text: "> modify task: include compliance_tickets" },
      { type: "ok", text: "task_version advanced to 2" },
      { type: "ok", text: "PostgreSQL memory retrieved before planning" },
      { type: "ok", text: "same completion rule applied" },
      { type: "ok", text: "Runtime Governor allowed read-only retrieval" },
      { type: "ok", text: "terminal signal reached before answer" },
      { type: "ok", text: "recurring blockers summarised" },
    ],
    messages: [
      { role: "user", text: "Now extend the resumed investigation to include compliance tickets and identify recurring blockers." },
      { role: "agent", eyebrow: "Memory applied", text: "Approved memory retrieved: continue retrieval until next_page_token=null before answering." },
      { role: "agent", eyebrow: "Plan with memory", text: "Plan: apply retrieval rule, fetch compliance tickets to terminal signal, then identify recurring blockers." },
      { role: "agent", eyebrow: "Improved result", text: "Across all pages, recurring blockers include missing evidence, delayed approvals, policy exceptions, unresolved vendor documentation, and review handoff delays." },
      { role: "impact", eyebrow: "Impact", text: "Execution memory applied. Incomplete-retrieval risk avoided." },
    ],
    side: {
      decision: "Runtime Governor approved read-only retrieval with memory applied",
      memory: "Approved execution memory reused from PostgreSQL",
      validation: "Final answer delayed until terminal page signal",
    },
    evidence: {
      traceId: "trace_compliance_001",
      toolEvidence: "fetch_compliance_tickets until next_page_token=null",
      mongoRecord: "retrieval_events.retrieval_compliance_001",
      receipt: "sha256:42bd11a09e7f",
      observedSignal: "PostgreSQL returned approved execution rule",
      response: "Agent applied the rule before analysing compliance tickets",
    },
    memory: {
      title: "Execution memory applied",
      text: learnedRule,
      meta: "Retrieved from PostgreSQL · reused on compliance_tickets_001",
    },
  },
];

function Badge({ children, tone = "neutral" }) {
  const tones = {
    neutral: "bg-neutral-100 text-neutral-700",
    green: "bg-emerald-100 text-emerald-700",
    blue: "bg-sky-100 text-sky-700",
    amber: "bg-amber-100 text-amber-700",
    white: "bg-white/10 text-white ring-1 ring-white/15",
    purple: "bg-violet-100 text-violet-700",
  };
  return (
    <span className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-black ${tones[tone] || tones.neutral}`}>
      {children}
    </span>
  );
}

function Icon({ name, size = 18, className = "" }) {
  const commonProps = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    className,
    "aria-hidden": "true",
  };
  const paths = {
    arrow: (
      <>
        <path d="M5 12h14" />
        <path d="m13 5 7 7-7 7" />
      </>
    ),
    spark: (
      <>
        <path d="M12 3 9.7 8.7 4 11l5.7 2.3L12 19l2.3-5.7L20 11l-5.7-2.3L12 3Z" />
        <path d="M19 3v4" />
        <path d="M21 5h-4" />
      </>
    ),
  };
  return <svg {...commonProps}>{paths[name] || paths.spark}</svg>;
}

function TerminalLine({ item }) {
  const colorMap = {
    cmd: "text-neutral-100",
    ok: "text-emerald-300",
    warn: "text-amber-300",
    muted: "text-neutral-500",
  };
  const prefixMap = {
    cmd: "$",
    ok: "✓",
    warn: "›",
    muted: "·",
  };
  const color = colorMap[item.type] || "text-neutral-300";
  const prefix = prefixMap[item.type] || "·";
  return (
    <div className={`flex gap-3 font-mono text-sm leading-6 ${color}`}>
      <span className="w-4 shrink-0 text-neutral-500">{prefix}</span>
      <span>{item.text}</span>
    </div>
  );
}

function ProofTerminal({ lines, animated = false, speed = 650, loop = false, pause = 1800 }) {
  const [visibleCount, setVisibleCount] = useState(animated ? 1 : lines.length);

  useEffect(() => {
    if (!animated) {
      setVisibleCount(lines.length);
      return undefined;
    }
    if (visibleCount >= lines.length) {
      if (!loop) return undefined;
      const resetTimer = window.setTimeout(() => setVisibleCount(1), pause);
      return () => window.clearTimeout(resetTimer);
    }
    const revealTimer = window.setTimeout(() => {
      setVisibleCount((count) => Math.min(count + 1, lines.length));
    }, speed);
    return () => window.clearTimeout(revealTimer);
  }, [animated, lines.length, loop, pause, speed, visibleCount]);

  useEffect(() => {
    setVisibleCount(animated ? 1 : lines.length);
  }, [animated, lines]);

  const visibleLines = lines.slice(0, visibleCount);
  return (
    <div className="overflow-hidden rounded-[1.75rem] border border-neutral-800 bg-neutral-950 shadow-2xl shadow-neutral-950/20">
      <div className="flex items-center gap-2 border-b border-white/10 px-5 py-3">
        <span className="h-3 w-3 rounded-full bg-red-400" />
        <span className="h-3 w-3 rounded-full bg-amber-400" />
        <span className="h-3 w-3 rounded-full bg-emerald-400" />
        <span className="ml-2 font-mono text-xs text-neutral-500">runtime trace</span>
      </div>
      <div className="min-h-[300px] p-5">
        {visibleLines.map((line, index) => (
          <TerminalLine key={`${line.text}-${index}`} item={line} />
        ))}
        {animated && visibleCount < lines.length ? (
          <div className="mt-2 flex gap-3 font-mono text-sm leading-6 text-emerald-300">
            <span className="w-4 shrink-0 text-neutral-500">▌</span>
            <span>running trace...</span>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function Nav({ page, setPage }) {
  return (
    <nav className="mx-auto flex max-w-7xl items-center justify-between px-5 py-5 md:px-8">
      <button type="button" onClick={() => setPage("landing")} className="flex items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-neutral-950 text-white">
          <Icon name="spark" size={17} />
        </span>
        <span className="text-left">
          <span className="block text-sm font-black tracking-tight text-neutral-950">TraceMemory</span>
          <span className="block text-xs font-bold text-neutral-500">execution memory for agents</span>
        </span>
      </button>
      <div className="flex rounded-full bg-white p-1 shadow-sm ring-1 ring-neutral-200">
        <button
          type="button"
          onClick={() => setPage("landing")}
          className={`rounded-full px-4 py-2 text-sm font-black ${page === "landing" ? "bg-neutral-950 text-white" : "text-neutral-500"}`}
        >
          Home
        </button>
        <button
          type="button"
          onClick={() => setPage("workspace")}
          className={`rounded-full px-4 py-2 text-sm font-black ${page === "workspace" ? "bg-neutral-950 text-white" : "text-neutral-500"}`}
        >
          Workspace
        </button>
      </div>
    </nav>
  );
}

function LandingPage({ setPage }) {
  return (
    <main className="min-h-screen bg-[#f5f1e8] text-neutral-950">
      <Nav page="landing" setPage={setPage} />
      <section className="mx-auto grid max-w-7xl gap-12 px-5 pb-20 pt-10 md:px-8 lg:grid-cols-[1fr_.9fr] lg:items-center lg:pt-20">
        <div>
          <div className="mb-6 flex flex-wrap gap-2">
            <Badge tone="green">PostgreSQL Agentic Evolution</Badge>
            <Badge tone="blue">Runtime evidence</Badge>
            <Badge tone="purple">Prolonged coordination</Badge>
          </div>
          <h1 className="max-w-5xl text-6xl font-black leading-[0.9] tracking-[-0.07em] md:text-8xl">
            Make every agent run improve the next.
          </h1>
          <p className="mt-7 max-w-2xl text-xl leading-9 text-neutral-600">
            TraceMemory turns governed tool traces into approved execution memory, so future agent runs start with evidence from what already worked.
          </p>
          <div className="mt-6 rounded-3xl bg-white/70 p-4 text-sm font-bold leading-6 text-neutral-700 ring-1 ring-neutral-200">
            Built for Prolonged Coordination: PostgreSQL stores task state, tool traces, checkpoints, task changes, and execution memory across long-running workflows.
          </div>
          <div className="mt-9 flex flex-wrap items-center gap-4">
            <button
              type="button"
              onClick={() => setPage("workspace")}
              className="inline-flex items-center gap-2 rounded-full bg-neutral-950 px-7 py-4 text-sm font-black text-white shadow-xl shadow-neutral-900/10"
            >
              See the same run unfold <Icon name="arrow" size={16} />
            </button>
            <p className="text-sm font-bold text-neutral-500">Landing trace previews the workspace run.</p>
          </div>
        </div>
        <ProofTerminal lines={heroTracePreview} animated loop speed={720} pause={2200} />
      </section>
      <section className="mx-auto max-w-7xl px-5 pb-20 md:px-8">
        <div className="mb-5 flex items-end justify-between gap-4">
          <div>
            <p className="text-sm font-black uppercase tracking-[0.18em] text-emerald-700">Proof path</p>
            <h2 className="mt-2 text-4xl font-black tracking-[-0.045em] text-neutral-950">One run creates memory. A restart proves coordination. The next scope adapts.</h2>
          </div>
          <button
            type="button"
            onClick={() => setPage("workspace")}
            className="hidden rounded-full bg-neutral-950 px-5 py-3 text-sm font-black text-white md:inline-flex"
          >
            Open workspace
          </button>
        </div>
        <div className="rounded-[2.5rem] bg-white p-6 shadow-sm ring-1 ring-neutral-200 md:p-8">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="rounded-[2rem] bg-neutral-50 p-5 transition duration-300 hover:-translate-y-1 hover:shadow-xl hover:shadow-neutral-900/10">
              <Badge tone="amber">Run 1</Badge>
              <h3 className="mt-5 text-2xl font-black tracking-tight">Support tickets</h3>
              <p className="mt-3 text-sm leading-6 text-neutral-600">
                The agent plans, retrieves records, observes tool continuation signals, and summarises recurring issues.
              </p>
            </div>
            <div className="rounded-[2rem] bg-neutral-950 p-5 text-white transition duration-300 hover:-translate-y-1 hover:shadow-xl hover:shadow-neutral-900/20">
              <Badge tone="white">Memory</Badge>
              <h3 className="mt-5 text-2xl font-black tracking-tight">PostgreSQL record</h3>
              <p className="mt-3 text-sm leading-6 text-neutral-300">
                PostgreSQL stores checkpoint state, trace evidence, and approved execution memory.
              </p>
            </div>
            <div className="rounded-[2rem] bg-emerald-50 p-5 ring-1 ring-emerald-100 transition duration-300 hover:-translate-y-1 hover:shadow-xl hover:shadow-emerald-900/10">
              <Badge tone="green">Run 2</Badge>
              <h3 className="mt-5 text-2xl font-black tracking-tight">Compliance tickets</h3>
              <p className="mt-3 text-sm leading-6 text-neutral-600">
                After recovery, the user changes scope and the agent applies memory before planning.
              </p>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}

function ProcessRail({ currentId }) {
  const activeCodes = stageEventCodes[currentId] ?? [];
  const activeCode = activeCodes[activeCodes.length - 1];
  return (
    <div className="mx-auto mb-6 max-w-3xl rounded-2xl border border-neutral-200 bg-white/80 px-4 py-3 shadow-sm">
      <div className="mb-2 flex items-center justify-between gap-3">
        <p className="text-xs font-semibold uppercase tracking-wider text-neutral-400">Task execution process</p>
        <p className="text-xs font-medium text-neutral-400">backend-ready run states</p>
      </div>
      <div className="flex items-center gap-2 overflow-x-auto">
        {runEvents.map((event, index) => {
          const complete = activeCodes.includes(event.code);
          const active = activeCode === event.code;
          return (
            <div key={event.code} className="flex min-w-fit items-center gap-2" title={event.description}>
              <span
                className={`rounded-full px-3 py-1 text-xs font-semibold ${
                  active ? "bg-neutral-950 text-white" : complete ? "bg-emerald-50 text-emerald-700" : "bg-neutral-100 text-neutral-400"
                }`}
              >
                {event.label}
              </span>
              {index < runEvents.length - 1 ? <span className="text-neutral-300">→</span> : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ChatMessage({ message }) {
  const isUser = message.role === "user";
  const isImpact = message.role === "impact";
  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[78%] rounded-[1.35rem] bg-neutral-950 px-4 py-3 text-sm leading-6 text-white shadow-sm">
          {message.text}
        </div>
      </div>
    );
  }
  return (
    <div className="flex gap-3">
      <div className={`mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-black ${isImpact ? "bg-emerald-100 text-emerald-700" : "bg-neutral-950 text-white"}`}>
        {isImpact ? "✓" : "T"}
      </div>
      <div className="max-w-[82%]">
        {message.eyebrow ? <p className="mb-1 text-[11px] font-black uppercase tracking-wider text-emerald-700">{message.eyebrow}</p> : null}
        <div className={`${isImpact ? "rounded-2xl bg-emerald-50 px-4 py-3 text-emerald-950 ring-1 ring-emerald-100" : "px-1 py-1 text-neutral-800"} text-sm leading-7`}>
          {message.text}
        </div>
      </div>
    </div>
  );
}

function EmptyChat({ input }) {
  return (
    <div className="flex min-h-[520px] items-center justify-center px-5 text-center">
      <div className="max-w-xl">
        <h2 className="text-4xl font-black tracking-[-0.045em] text-neutral-950">Start a ticket-analysis run.</h2>
        <p className="mt-4 text-base leading-7 text-neutral-500">{input}</p>
      </div>
    </div>
  );
}

function EvidenceDetails({ evidence }) {
  const rows = [
    ["Trace ID", evidence.traceId],
    ["Tool evidence", evidence.toolEvidence],
    ["PostgreSQL memory record", evidence.mongoRecord],
    ["Evidence receipt", evidence.receipt],
    ["Observed tool signal", evidence.observedSignal],
    ["Agent response", evidence.response],
  ];
  return (
    <details className="mt-2 border-t border-neutral-100 pt-4">
      <summary className="cursor-pointer text-sm font-semibold text-neutral-700">Trace evidence</summary>
      <div className="mt-4 divide-y divide-neutral-100 text-sm">
        {rows.map(([label, value]) => (
          <div key={label} className="grid grid-cols-[120px_1fr] gap-4 py-3">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-neutral-400">{label}</p>
            <p className="font-medium leading-5 text-neutral-800">{value}</p>
          </div>
        ))}
      </div>
    </details>
  );
}

function InspectorDrawer({ current, onClose }) {
  const eventPath = (stageEventCodes[current.id] ?? []).join(" → ");
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-neutral-950/20 backdrop-blur-sm">
      <button type="button" className="absolute inset-0 cursor-default" aria-label="Close inspector overlay" onClick={onClose} />
      <aside className="relative z-10 flex h-full w-full max-w-[420px] flex-col bg-white shadow-2xl shadow-neutral-950/20">
        <div className="border-b border-neutral-100 px-5 py-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-semibold text-neutral-950">Run Inspector</p>
              <p className="mt-1 font-mono text-xs text-neutral-400">{current.evidence.traceId}</p>
              <p className="mt-1 text-xs font-medium text-neutral-400">{eventPath}</p>
            </div>
            <button type="button" onClick={onClose} className="rounded-full px-3 py-1.5 text-sm font-medium text-neutral-500 hover:bg-neutral-100">
              Close
            </button>
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
          <div className="border-b border-neutral-100 pb-5">
            <div className="flex items-center justify-between gap-3">
              <span className="rounded-full bg-neutral-100 px-3 py-1 text-xs font-semibold text-neutral-700">{current.eyebrow}</span>
              <span className="text-xs font-medium text-neutral-400">{Math.round(current.progress)}%</span>
            </div>
            <h2 className="mt-4 text-xl font-semibold tracking-tight text-neutral-950">{current.headline}</h2>
            <p className="mt-2 text-sm leading-6 text-neutral-500">{current.summary}</p>
          </div>
          <div className="divide-y divide-neutral-100">
            {[
              ["Decision", current.side.decision],
              ["Memory", current.side.memory],
              ["Validation", current.side.validation],
            ].map(([label, value]) => (
              <div key={label} className="grid grid-cols-[88px_1fr] gap-4 py-4">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-neutral-400">{label}</p>
                <p className="text-sm font-medium leading-5 text-neutral-900">{value}</p>
              </div>
            ))}
          </div>
          {current.memory ? (
            <div className="border-t border-neutral-100 py-4">
              <p className="text-[11px] font-semibold uppercase tracking-wider text-emerald-700">{current.memory.title}</p>
              <p className="mt-2 text-sm leading-6 text-neutral-800">{current.memory.text}</p>
              <p className="mt-2 text-xs font-medium text-neutral-500">{current.memory.meta}</p>
            </div>
          ) : null}
          <details className="border-t border-neutral-100 py-4">
            <summary className="cursor-pointer text-sm font-semibold text-neutral-700">Trace</summary>
            <div className="mt-3 rounded-xl bg-neutral-950 p-3">
              {current.terminal.map((line, index) => (
                <TerminalLine key={`${line.text}-${index}`} item={line} />
              ))}
            </div>
          </details>
          <EvidenceDetails evidence={current.evidence} />
        </div>
      </aside>
    </div>
  );
}

function Workspace({ setPage }) {
  const [step, setStep] = useState(0);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const current = stages[step];
  const tests = useMemo(() => {
    const results = [];
    const assert = (name, condition) => results.push({ name, passed: Boolean(condition) });
    assert("has five demo stages", stages.length === 5);
    assert("brand promise is reflected", heroTracePreview.some((line) => line.text.includes("PostgreSQL")));
    assert("uses support ticket proof case", stages[1].input.includes("support tickets"));
    assert("uses checkpoint recovery stage", stages[3].id === "recover");
    assert("uses compliance ticket second run", stages[4].input.includes("compliance tickets"));
    assert("learned rule includes terminal condition", learnedRule.includes("next_page_token"));
    assert("each stage exposes terminal trace lines", stages.every((stage) => stage.terminal.length > 0));
    assert("landing trace has enough lines for animated proof", heroTracePreview.length >= 6);
    assert("each stage exposes evidence", stages.every((stage) => stage.evidence && stage.evidence.traceId));
    assert("dynamic actions match stages", nextLabels.length === stages.length);
    assert(
      "run event model supports real task execution",
      runEvents.some((event) => event.code === "plan_prepared") &&
        runEvents.some((event) => event.code === "runtime_decision") &&
        runEvents.some((event) => event.code === "memory_created_or_retrieved") &&
        runEvents.some((event) => event.code === "checkpoint_saved") &&
        runEvents.some((event) => event.code === "checkpoint_restored"),
    );
    assert("each UI stage maps to backend run events", stages.every((stage) => stageEventCodes[stage.id]?.length > 0));
    assert("chat has clean empty state", stages[0].messages.length === 0);
    assert("history rail has enough items to scroll", conversationHistory.length >= 10);
    assert("inspector can open without replacing chat", typeof inspectorOpen === "boolean");
    assert("all jsx-critical collections are arrays", Array.isArray(stages) && Array.isArray(runEvents) && Array.isArray(conversationHistory));
    return results;
  }, [inspectorOpen]);
  const allTestsPassed = tests.every((test) => test.passed);
  const isComplete = step === stages.length - 1;
  return (
    <main className="min-h-screen bg-[#f7f7f5] text-neutral-950">
      <Nav page="workspace" setPage={setPage} />
      <section className="grid min-h-[calc(100vh-84px)] grid-cols-1 lg:grid-cols-[260px_1fr]">
        <aside className="hidden min-h-[calc(100vh-84px)] max-h-[calc(100vh-84px)] flex-col border-r border-neutral-200 bg-[#f7f7f5] lg:flex">
          <div className="p-3">
            <button
              type="button"
              onClick={() => setStep(0)}
              className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left text-sm font-semibold text-neutral-950 hover:bg-neutral-200/70"
            >
              <span className="text-lg leading-none">＋</span>
              New run
            </button>
            <button
              type="button"
              className="mt-1 flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left text-sm font-semibold text-neutral-700 hover:bg-neutral-200/70"
            >
              <span className="text-lg leading-none">⌕</span>
              Search runs
            </button>
          </div>
          <div className="px-3 pb-2 pt-4">
            <p className="px-3 text-xs font-black uppercase tracking-wider text-neutral-400">Recent</p>
          </div>
          <div className="min-h-0 flex-1 space-y-1 overflow-y-auto px-3 pb-3 [scrollbar-color:#d4d4d4_transparent] [scrollbar-width:thin]">
            {conversationHistory.map((item, index) => {
              const active =
                (current.id === "ready" && index === 0) ||
                (current.id === "plan" && item.id === "thread_support") ||
                (current.id === "execute" && item.id === "thread_support") ||
                (current.id === "improve" && item.id === "thread_compliance");
              return (
                <button
                  key={item.id}
                  type="button"
                  className={`w-full rounded-xl px-3 py-2.5 text-left transition ${active ? "bg-neutral-200/80" : "hover:bg-neutral-200/60"}`}
                >
                  <p className="truncate text-sm font-medium text-neutral-900">{item.title}</p>
                  <p className="mt-1 truncate text-xs font-medium text-neutral-500">{item.subtitle}</p>
                </button>
              );
            })}
          </div>
        </aside>
        <div className="flex min-h-[calc(100vh-84px)] flex-col bg-white">
          <div className="flex items-center justify-between gap-3 px-5 py-3">
            <p className="text-sm font-semibold text-neutral-950">TraceMemory</p>
            <div className="flex items-center gap-2">
              <Badge tone={allTestsPassed ? "green" : "amber"}>{current.eyebrow}</Badge>
              <button
                type="button"
                onClick={() => setInspectorOpen(true)}
                className="rounded-full px-3 py-1.5 text-sm font-medium text-neutral-600 hover:bg-neutral-100"
                aria-label="Open run inspector"
              >
                Inspector
              </button>
            </div>
          </div>
          <div className="h-px bg-neutral-100">
            <div className="h-full bg-emerald-500 transition-all" style={{ width: `${current.progress}%` }} />
          </div>
          {current.id !== "ready" ? (
            <div className="border-b border-neutral-100 px-5 py-2">
              <div className="mx-auto flex max-w-3xl items-center gap-2 overflow-x-auto text-xs font-medium text-neutral-500">
                <span className="rounded-full bg-neutral-100 px-3 py-1">Run states visible</span>
                <span className="rounded-full bg-neutral-100 px-3 py-1">Runtime decision logged</span>
                <button
                  type="button"
                  onClick={() => setInspectorOpen(true)}
                  className="rounded-full bg-emerald-50 px-3 py-1 font-bold text-emerald-700 hover:bg-emerald-100"
                >
                  View trace evidence
                </button>
              </div>
            </div>
          ) : null}
          <div className="flex-1 overflow-y-auto bg-white px-5 py-8">
            {current.messages.length > 0 ? (
              <div className="mx-auto max-w-3xl space-y-8 py-4">
                <ProcessRail currentId={current.id} />
                {current.messages.map((message, index) => (
                  <ChatMessage key={`${message.role}-${index}`} message={message} />
                ))}
              </div>
            ) : (
              <EmptyChat input={current.input} />
            )}
          </div>
          <div className="bg-white px-5 pb-7 pt-3">
            <div className="mx-auto max-w-3xl">
              <div className="rounded-[1.75rem] bg-white p-3 shadow-[0_12px_45px_rgba(0,0,0,0.08)] ring-1 ring-neutral-200">
                <div className="flex items-end gap-3">
                  <div className="min-h-[44px] flex-1 px-2 py-2 text-sm leading-6 text-neutral-500">
                    {current.id === "ready" ? "Analyse all support tickets and summarise recurring customer issues." : current.input}
                  </div>
                  <button
                    type="button"
                    disabled={isComplete}
                    onClick={() => setStep((value) => Math.min(value + 1, stages.length - 1))}
                    className={`flex h-10 w-10 items-center justify-center rounded-full text-white transition ${isComplete ? "bg-neutral-400" : "bg-neutral-950 hover:bg-neutral-800"}`}
                    aria-label={nextLabels[step]}
                  >
                    <Icon name="arrow" size={18} />
                  </button>
                </div>
                <div className="mt-2 flex items-center justify-between border-t border-neutral-100 px-2 pt-2">
                  <span className="text-xs font-medium text-neutral-400">{nextLabels[step]}</span>
                  <span className="text-xs font-medium text-neutral-400">Trace evidence available from Inspector</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
      {inspectorOpen ? <InspectorDrawer current={current} onClose={() => setInspectorOpen(false)} /> : null}
    </main>
  );
}

export default function App() {
  const [page, setPage] = useState("landing");
  return page === "landing" ? <LandingPage setPage={setPage} /> : <Workspace setPage={setPage} />;
}

createRoot(document.getElementById("root")!).render(<App />);
