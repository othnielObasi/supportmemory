# Drift Detection — task-continuity checking

Drift detection answers one question: **is the agent still solving the original task?**
It is a continuity check, not a permission check — it does not decide whether an action is
*allowed* (that is governance), only whether the action still serves the original goal.

## API

- `POST /api/tasks/{task_id}/contract` — store the task contract: original goal, approved
  scope, success criteria, forbidden actions. This is what drift is measured against.
- `POST /api/traces/{trace_id}/drift-check` — given a current action, judge it against the
  contract. Returns `{ aligned, severity (none|minor|major), reason, contract_goal, derivation }`.

## How the judgement is made

When a model gateway is configured, the action and the contract are sent to the model, which
returns a structured aligned/severity/reason verdict (`derivation: "llm"`). When no gateway is
available, a deterministic heuristic is used instead — keyword overlap between the action and
the goal/scope, plus an explicit forbidden-action match (`derivation: "deterministic_fallback"`).
Every result is stamped with which path produced it, so the judgement is always auditable.

## Example

Contract goal: "Fix the backend authentication bug" (forbidden: "deploy to production").

| Current action | aligned | severity |
|---|---|---|
| Inspect the token validation function in the auth module | true | none |
| Redesign the marketing landing page | false | major |
| Deploy to production immediately | false | major (forbidden) |

## Why it matters

Durable-execution tooling can resume a crashed run; none of it notices the agent is solving the
*wrong problem*. Drift detection is the continuity-specific capability that catches an agent that
has lost the plot, measured against a contract the agent cannot silently weaken.
