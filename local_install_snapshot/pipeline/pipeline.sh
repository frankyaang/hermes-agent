#!/usr/bin/env bash
# pipeline.sh — Plan (Claude Opus 4.7) → Exec (ONE Codex call) → Audit (GPT-5.5)
#
# Design note: all tasks are bundled into a single codex exec call to avoid
# ChatGPT OAuth refresh-token invalidation that occurs across serial processes.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=config.env
source "$SCRIPT_DIR/config.env"

# ── Usage ──────────────────────────────────────────────────────
usage() {
  echo "Usage: $0 \"<requirement>\" [target_project_dir]"
  echo ""
  echo "  requirement        Natural language description of the task"
  echo "  target_project_dir Directory Codex will work in (default: current dir)"
  echo ""
  echo "Examples:"
  echo "  $0 \"Add input validation to the login form\" ~/myproject"
  echo "  $0 \"Write unit tests for utils.py\""
  exit 1
}

[[ $# -lt 1 ]] && usage

REQUIREMENT="$1"
TARGET_DIR="$(cd "${2:-$(pwd)}" && pwd)"

RUN_ID=$(date +%Y%m%d_%H%M%S)
RUN_DIR="$SCRIPT_DIR/runs/$RUN_ID"
mkdir -p "$RUN_DIR"

# ── Logging ────────────────────────────────────────────────────
LOG_FILE="$RUN_DIR/pipeline.log"
log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG_FILE"; }
fail() { log "ERROR: $*"; exit 1; }

log "╔══════════════════════════════════════════════╗"
log "  Run ID    : $RUN_ID"
log "  Requirement: $REQUIREMENT"
log "  Target dir : $TARGET_DIR"
log "  Artifacts  : $RUN_DIR"
log "  Models     : plan=$PLAN_MODEL  exec=$EXEC_MODEL($EXEC_REASONING)  audit=$AUDIT_MODEL($AUDIT_REASONING)"
log "╚══════════════════════════════════════════════╝"

# ── Helper: extract JSON from claude --output-format json output ─
extract_claude_json() {
  local raw="$1"
  local content
  # claude wraps output in {"type":"result","result":"<text>", ...}
  if content=$(jq -r '.result // empty' "$raw" 2>/dev/null) && [[ -n "$content" ]]; then
    : # got the inner text
  else
    content=$(cat "$raw")
  fi
  # Strip markdown fences if Claude wrapped the JSON in ```json ... ```
  echo "$content" | sed '/^```/d' | jq '.' \
    || fail "JSON parse failed. Raw file: $raw"
}

# ══════════════════════════════════════════════════════════════
# Main retry loop
# ══════════════════════════════════════════════════════════════
RETRY=0
CONTEXT=""   # failure context fed back into the planner on retry

while [[ $RETRY -lt $MAX_RETRIES ]]; do
  ATTEMPT=$((RETRY + 1))
  log ""
  log "━━━ Attempt $ATTEMPT / $MAX_RETRIES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

  # ────────────────────────────────────────────────────────────
  # STAGE 1 · PLANNING  (Claude Opus 4.7)
  # ────────────────────────────────────────────────────────────
  log "[1/3 Plan] $PLAN_MODEL …"

  PLAN_PROMPT="You are a senior software architect. Decompose the requirement below into \
an ordered list of concrete, self-contained coding tasks for an AI coding agent.

Rules:
- Each task description must be natural language (NOT a shell command)
- Tasks are executed serially; later tasks may depend on earlier ones
- working_dir: use null to default to TARGET_DIR, or a relative path under TARGET_DIR
- success_criteria: must be objectively verifiable by a reviewer

REQUIREMENT:
$REQUIREMENT

TARGET_DIR: $TARGET_DIR

PREVIOUS FAILURE CONTEXT (apply corrections if non-empty):
${CONTEXT:-none}

Output ONLY a valid JSON object — no markdown fences, no commentary:
{
  \"goal\": \"<one-line summary>\",
  \"tasks\": [
    {
      \"task_id\": 1,
      \"description\": \"<natural language instruction for the AI agent>\",
      \"working_dir\": null,
      \"success_criteria\": \"<how to verify success>\"
    }
  ]
}"

  RAW_PLAN="$RUN_DIR/plan_raw_$RETRY.json"
  PLAN_FILE="$RUN_DIR/plan_$RETRY.json"

  if [[ "${MOCK:-0}" == "1" ]]; then
    log "[MOCK] Skipping claude call — injecting pre-baked plan"
    cat > "$RAW_PLAN" <<'EOF'
{"type":"result","result":"{\"goal\":\"Smoke test: verify three-stage model routing\",\"tasks\":[{\"task_id\":1,\"description\":\"Verify that the pipeline routing config is loaded correctly\",\"working_dir\":null,\"success_criteria\":\"Config file exists and model names match expected values\"}]}"}
EOF
  else
    claude --model "$PLAN_MODEL" \
      -p "$PLAN_PROMPT" \
      --output-format json \
      > "$RAW_PLAN" \
      || fail "Claude planning failed on attempt $ATTEMPT"
  fi

  extract_claude_json "$RAW_PLAN" > "$PLAN_FILE"

  TASK_COUNT=$(jq '.tasks | length' "$PLAN_FILE")
  log "[1/3 Plan] $TASK_COUNT tasks → $(basename "$PLAN_FILE")"
  jq -r '.tasks[] | "         [\(.task_id)] \(.description)"' "$PLAN_FILE" | tee -a "$LOG_FILE"

  # ────────────────────────────────────────────────────────────
  # STAGE 2 · EXECUTION  (single Codex exec call — all tasks bundled)
  #
  # All tasks are combined into ONE codex exec invocation to avoid
  # ChatGPT OAuth refresh-token invalidation across multiple processes.
  # ────────────────────────────────────────────────────────────
  log ""
  log "[2/3 Exec] $EXEC_MODEL | sandbox=$SANDBOX_MODE | bundled single call"

  # Build the bundled task prompt
  TASK_LIST=$(jq -r '
    .tasks[] |
    "Task \(.task_id): \(.description)\nSuccess criteria: \(.success_criteria // "N/A")\n"
  ' "$PLAN_FILE")

  EXEC_PROMPT="Execute the following tasks IN ORDER in the directory $TARGET_DIR.
Complete every task before moving to the next. Do not skip any task.

$TASK_LIST

After completing all tasks, output a JSON summary with this exact structure (no markdown fences):
{
  \"completed_tasks\": [
    {\"task_id\": 1, \"status\": \"done\", \"notes\": \"<what was done>\"},
    ...
  ],
  \"overall_status\": \"success\" | \"partial\" | \"failed\",
  \"failure_reason\": \"<empty string if overall_status is success>\"
}"

  EXEC_RESULT_FILE="$RUN_DIR/exec_result_$RETRY.json"
  EXEC_EVENTS_FILE="$RUN_DIR/exec_events_$RETRY.jsonl"

  EXEC_FAILED=false
  if [[ "${MOCK:-0}" == "1" ]]; then
    log "[MOCK] Skipping codex exec call — injecting pre-baked execution result"
    cat > "$EXEC_RESULT_FILE" <<'EOF'
{"completed_tasks":[{"task_id":1,"status":"done","notes":"Mock: verified config file exists and model names are correct"}],"overall_status":"success","failure_reason":""}
EOF
    log "[2/3 Exec] ✓ complete (mock)"
  elif codex exec \
      -m "$EXEC_MODEL" \
      -c "model_reasoning_effort=\"$EXEC_REASONING\"" \
      -s "$SANDBOX_MODE" \
      -C "$TARGET_DIR" \
      --skip-git-repo-check \
      -o "$EXEC_RESULT_FILE" \
      --json \
      "$EXEC_PROMPT" \
      > "$EXEC_EVENTS_FILE" 2>&1; then
    log "[2/3 Exec] ✓ complete"
  else
    log "[2/3 Exec] ✗ codex returned non-zero — checking result file anyway"
    EXEC_FAILED=true
  fi

  # ────────────────────────────────────────────────────────────
  # STAGE 3 · AUDIT  (Codex — refresh token before call)
  # ────────────────────────────────────────────────────────────
  log ""
  log "[3/3 Audit] $AUDIT_MODEL ($AUDIT_REASONING) …"

  EXEC_SUMMARY=""
  if [[ -f "$EXEC_RESULT_FILE" ]]; then
    EXEC_SUMMARY=$(cat "$EXEC_RESULT_FILE")
  fi

  AUDIT_PROMPT="You are a technical auditor. Review the plan and execution results below, \
then produce a structured audit report.

TARGET_DIR: $TARGET_DIR
CODEX_EXIT_FAILED: $EXEC_FAILED

IMPORTANT: All file verification must be done inside TARGET_DIR above. Do NOT look in other directories.

<plan>
$(cat "$PLAN_FILE")
</plan>

<execution_summary>
$EXEC_SUMMARY
</execution_summary>

Evaluation criteria:
1. Did Codex complete all tasks without errors?
2. Does each output satisfy its success_criteria?
3. Are there quality issues, missing files, or anomalies?

Set status=PASS ONLY if every task succeeded and every criterion is met.

Output ONLY a valid JSON object — no markdown fences, no commentary:
{
  \"status\": \"PASS\" | \"FAIL\",
  \"summary\": \"<one-paragraph summary>\",
  \"issues\": [\"<issue 1>\", \"<issue 2>\"],
  \"recommendation\": \"<next action>\"
}"

  AUDIT_FILE="$RUN_DIR/audit_$RETRY.json"
  AUDIT_EVENTS="$RUN_DIR/audit_events_$RETRY.jsonl"

  if [[ "${MOCK:-0}" == "1" ]]; then
    log "[MOCK] Skipping codex audit call — injecting pre-baked audit result"
    cat > "$AUDIT_FILE" <<'EOF'
{"status":"PASS","summary":"Mock smoke test: all tasks completed, model routing config verified (plan=claude-opus-4-7, exec=gpt-5.5/xhigh, audit=gpt-5.5/high).","issues":[],"recommendation":"Confirm completion — mock smoke test passed successfully."}
EOF
  else
    codex exec \
      -m "$AUDIT_MODEL" \
      -c "model_reasoning_effort=\"$AUDIT_REASONING\"" \
      -s read-only \
      -C "$TARGET_DIR" \
      --skip-git-repo-check \
      --output-schema "$SCRIPT_DIR/audit_schema.json" \
      -o "$AUDIT_FILE" \
      --json \
      "$AUDIT_PROMPT" \
      > "$AUDIT_EVENTS" 2>&1 \
      || log "[Audit] Codex returned non-zero — checking output file anyway"
  fi

  if ! AUDIT_STATUS=$(jq -r '.status // "UNKNOWN"' "$AUDIT_FILE" 2>/dev/null) || [[ -z "$AUDIT_STATUS" ]]; then
    AUDIT_STATUS="UNKNOWN"
    log "[Audit] Could not parse audit output — treating as FAIL"
  fi

  log "[Audit] Status: $AUDIT_STATUS"
  jq '.' "$AUDIT_FILE" 2>/dev/null | tee -a "$LOG_FILE" || true

  if [[ "$AUDIT_STATUS" == "PASS" ]]; then
    log ""
    log "╔══════════════════════════════════════════════╗"
    log "  Pipeline PASSED ✓  (attempt $ATTEMPT)"
    log "  Audit report : $AUDIT_FILE"
    log "  All artifacts: $RUN_DIR"
    log "╚══════════════════════════════════════════════╝"
    exit 0
  fi

  # Extract failure context to feed back into the planner
  CONTEXT=$(jq -r '
    (.summary // "No summary") + "\nIssues: " +
    ((.issues // []) | join("; "))
  ' "$AUDIT_FILE" 2>/dev/null || echo "Audit failed to parse")

  RETRY=$((RETRY + 1))

  if [[ $RETRY -lt $MAX_RETRIES ]]; then
    log ""
    log "Audit FAILED — retrying with context:"
    log "  $CONTEXT"
  fi
done

log ""
log "╔══════════════════════════════════════════════╗"
log "  Pipeline FAILED after $MAX_RETRIES attempts"
log "  Final audit : $RUN_DIR/audit_$((MAX_RETRIES - 1)).json"
log "  All artifacts: $RUN_DIR"
log "╚══════════════════════════════════════════════╝"
exit 1
