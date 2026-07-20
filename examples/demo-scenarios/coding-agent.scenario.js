/* TraceMemory demo scenario: Autonomous coding agent.
 *
 * Why this scenario: every judge in the room has watched a coding agent die
 * mid-task. It makes the "horizontal infrastructure" claim concrete — the same
 * recover / prove / learn loop that governs an enterprise agent governs a coding
 * agent too. Submit under Vultr; use this to demonstrate universality.
 *
 * Shape matches the `stages` array in HACKATHON_UI.html exactly:
 *   { id, label, progress, eyebrow, input, summary,
 *     messages:[[role,tag,text]...], terminal:[[type,text]...], evidence:[6] }
 *
 * Live-mode field mapping (handled by liveStage in the UI):
 *   execute.evidence[0] <- real trace_id
 *   recover  <- model-derived lesson (candidate_rule, confidence, derivation)
 *   extend   <- curated rule_id + retrieved rule/score
 */
const CODING_AGENT_SCENARIO = {
  id: "coding-agent",
  name: "Autonomous coding agent",
  runLabel: "Refactor auth module",
  task: "Refactor the auth module to async and make the full test suite pass.",
  stages: [
    {
      id: "ready",
      label: "Ready",
      progress: 0,
      eyebrow: "No active run",
      input: "Refactor the auth module to async and make the full test suite pass.",
      summary: "Start a long-running coding task that spans many file edits, test runs, and tool calls — the kind of run that loses everything on a mid-task crash.",
      messages: [],
      terminal: [["cmd", "> await coding agent task"], ["muted", "runtime continuity engine ready"], ["muted", "model and tool gateway registries ready"], ["muted", "no active execution trace"]],
      evidence: ["—", "Not selected", "No tool call yet", "—", "Not required", "No memory applied"]
    },
    {
      id: "plan",
      label: "Plan",
      progress: 32,
      eyebrow: "Planning checkpoint",
      input: "Refactor the auth module to async and make the full test suite pass.",
      summary: "The agent plans the multi-file refactor. TraceMemory saves a safe checkpoint before any edit or command runs, so a crash can resume instead of restarting 20 minutes of work.",
      messages: [
        ["user", "", "Refactor the auth module to async and make the full test suite pass."],
        ["agent", "Plan", "Map call sites, convert auth/* to async, update callers, run the test suite, fix failures until green."],
        ["agent", "Checkpoint", "Pre-edit repo state and plan saved so the run can resume safely if a later step fails."]
      ],
      terminal: [["cmd", "> create_plan auth-async-refactor"], ["ok", "repo and workspace context resolved"], ["ok", "model route selected"], ["ok", "checkpoint saved · chk_plan_001"]],
      evidence: ["plan_code_001", "Gateway route selected for planning", "0 tool calls executed", "chk_plan_001", "Ready if interruption occurs", "No prior memory needed"]
    },
    {
      id: "execute",
      label: "Execute",
      progress: 58,
      eyebrow: "Tool evidence recorded",
      input: "Apply the edits and run the test suite.",
      summary: "Every file edit, command, and test result becomes part of the run record — inputs, outputs, exit codes, and which tests passed or failed.",
      messages: [
        ["user", "", "Apply the edits and run the test suite."],
        ["agent", "Tool evidence", "edit_files changed 7 files in auth/*; run_tests started the suite as a recorded tool call."],
        ["agent", "Validation", "14 of 18 tests passed; 4 failures captured with stack traces as evidence, not discarded."],
        ["agent", "Execution memory", "A migration-order rule became an approved memory candidate from the failing run."]
      ],
      terminal: [["cmd", "> tool.edit_files auth/*"], ["ok", "7 files edited, diff recorded"], ["cmd", "> tool.run_tests"], ["warn", "4 failing: async db init before pool ready"], ["ok", "execution memory candidate stored"]],
      evidence: ["trace_code_001", "Planning route retained", "edit_files + run_tests (18 tests, 4 failed)", "chk_code_001", "Checkpoint available", "async_init_order_rule_001"]
    },
    {
      id: "recover",
      label: "Recover",
      progress: 78,
      eyebrow: "Failure recovery",
      input: "The agent crashed mid-run. Resume from the last safe state.",
      summary: "A context-overflow crash kills the agent mid-suite. TraceMemory restores the last checkpoint with edits and test evidence intact — and crucially, does NOT re-apply the migration it already ran.",
      messages: [
        ["user", "", "The agent crashed mid-run (context overflow). Resume from the last safe state."],
        ["agent", "Failure detected", "The run stopped after the test step, before fixes were applied."],
        ["agent", "Idempotency", "The already-applied schema migration was recognised from evidence and NOT run a second time."],
        ["agent", "Recovery", "Checkpoint restored repo state, prior edits, test failures, and memory context — no work repeated."]
      ],
      terminal: [["cmd", "> recover run trace_code_001"], ["warn", "interruption detected after test step"], ["ok", "idempotency key matched · migration skipped"], ["ok", "checkpoint restored · chk_code_001"], ["ok", "recovery_status=restored"]],
      evidence: ["recover_code_001", "Primary route → fallback route", "Prior edits + test evidence retained", "chk_code_001", "Restored from trusted checkpoint", "async_init_order_rule_001 available"]
    },
    {
      id: "extend",
      label: "Extend",
      progress: 100,
      eyebrow: "Learns across runs",
      input: "Run the same refactor on the billing module.",
      summary: "A second task starts. TraceMemory retrieves the lesson the first run learned, so the agent gets the migration order right the FIRST time — measurably fewer failed tests.",
      messages: [
        ["user", "", "Now run the same async refactor on the billing module."],
        ["agent", "Task version", "A new task version started, preserving evidence from the auth refactor."],
        ["agent", "Memory applied", "Approved memory retrieved: initialise the async DB pool before any module that runs migrations on import."],
        ["agent", "Result", "Billing refactor passed 18/18 on the first run — the init-order failure did not recur because the agent remembered it."],
        ["impact", "Outcome", "Same agent, second run, measurably better: recovery without repeated work, signed evidence, and a lesson reused across tasks."]
      ],
      terminal: [["cmd", "> run billing-async-refactor"], ["ok", "task_version advanced to 2"], ["ok", "approved execution memory retrieved"], ["ok", "init-order rule applied before edits"], ["ok", "18/18 tests passed first run"]],
      evidence: ["trace_billing_001", "Gateway-agnostic model route", "auth + billing traces", "chk_billing_001", "Task continued from restored state", "approved memory applied before planning"]
    }
  ]
};

if (typeof module !== "undefined" && module.exports) { module.exports = CODING_AGENT_SCENARIO; }
