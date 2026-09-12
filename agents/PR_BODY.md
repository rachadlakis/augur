<!-- Draft PR description for feat/agent-layer -> main. Delete this file after opening the PR. -->

## What this is

The Augur Tensors **agent layer** — five ADK agents that carry a model-development
project from an objective to a traceable evaluation report, with every expensive
or irreversible step behind an explicit approval. Plus the packaging and docs
work around it.

Replaces nothing: `dist_kit/` is untouched, and the previous multi-agent project
stays at `docs/agents/` (gitignored) as a reference for the A2A patterns.

**Real:** the agents, the A2A wiring, the lifecycle state machine, the
action-digest approval gate, per-agent model selection.
**Stubbed:** the tool *bodies* return realistic mock data — there are no MCP
capability servers and no GPU work yet. Swapping a stub for a real `*-mcp` keeps
the tool names and shapes, so the agents don't change.

## The five agents

| Agent | Port | Role | Writes? |
|---|---|---|---|
| Orchestrator | 8000 (`adk`) | Owns the lifecycle, routes every stage, holds the approval gate | no |
| Research | 10204 | Literature search/synthesis — advisory, never gates a stage | no |
| Data | 10201 | Inspect / validate / materialize datasets → `DatasetManifest` | yes |
| Training | 10202 | Recommend parallelism, plan, estimate, launch, monitor | yes |
| Evaluation | 10203 | Run benchmark suites, compare candidates against thresholds | no |

## Three design decisions worth reviewing

**The orchestrator keeps control.** It's an `LlmAgent` whose tools are
`dispatch_task` / `get_task` / `list_agents` — *not* ADK `sub_agents`. A worker is
called, answers, and control returns. `create_agent().sub_agents == []` is a test.

**Long runs outlive the turn.** `dispatch_task` returns the moment a task is
terminal *or* the patience budget expires — in the second case with the `working`
task id. The orchestrator persists `{stage, agent, task_id}` in a
`WorkflowRecord` and resumes via `get_task` on a later turn. `submit_training_job`
returns a job id immediately; the stub job advances on wall-clock and survives a
worker restart (SQLite job store) — so the polling path is real even though the
run is simulated.

**The approval gate is code, not prompt.** `check_policy` recomputes an action
digest from the parameters the tool was *actually* called with; a token granted
for "1 GPU, ~$6" is refused when the call says 64 GPUs, without anyone noticing.
`TrainingPlan.digest()` excludes the estimate and provenance, so attaching a cost
to a plan doesn't invalidate the approval for that cost.

## Also in this PR

- **uv workspace** — the repo had no package definition; the root `requirements.txt`
  agent pins (`a2a-sdk 1.1.0`, `google-adk 2.4.0`) had never been resolved.
  Now a virtual root `pyproject.toml` + the `agents/` member + one `uv.lock`.
  Resolved to the tested set: `a2a-sdk 1.1.2`, `google-adk 2.8.0`, `mcp 1.30`.
- **`docs/ultrascale_playbook.md`** — the two Ultra-Scale Playbook PDFs distilled
  into a diagram-heavy in-repo reference. Its §6 decision flowchart and §7
  formulas are what `training/parallelism.py` implements — verified against the
  playbook's own recipes (7B/8 GPUs → plain ZeRO-3, 405B/1024 → tp=8 + pp +
  ZeRO-2, long sequences → context parallelism, MoE → expert parallelism).
- **`agents/AGENTS.md`** — the authoritative wiring doc.
- `.gitattributes` pinning `*.sh eol=lf` (this repo trains on Linux; a CRLF in
  `dist_kit/launch.sh` breaks the shebang on a GPU box).

## Verification

- `uv run pytest agents/tests` → **190 passed**, offline, no LLM calls
- `uv run ruff check agents/` → clean
- `IS_A2A_V1 == True`; all four workers boot and serve schema-valid cards; the
  orchestrator's client discovers them by skill and completes a real
  dispatch → task id → `get_task` → terminal-state round trip on live A2A
- the full pipeline DATA → PLAN → approval → TRAIN → EVAL runs through the real
  tool functions (`test_pipeline_e2e.py`)
- `dist_kit` under uv: `uv sync --group training && uv pip install torch` then
  `CUDA_VISIBLE_DEVICES=-1 uv run pytest dist_kit/tests -m "not smoke"` →
  **66 passed, 1 skipped**, the documented baseline. The migration didn't break
  the kit.

## Not done / follow-ups

- LLM-driven end-to-end (orchestrator actually reasoning through the pipeline in
  `adk web`) — needs a real provider key; the wiring underneath it is verified.
- Real MCP capability servers, a real job manager, Postgres/object-store
  persistence, Safety + Release agents — see `docs/IMPLEMENTATION_PLAN.md`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

