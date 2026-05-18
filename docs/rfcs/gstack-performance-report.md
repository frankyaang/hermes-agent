# GStack Control Performance Report

**Date:** 2026-05-18
**Version:** 0.2.0
**Status:** BLOCKED (gstack CLI not installed)

---

## Baseline (disabled mode)

| Metric | Value |
|--------|-------|
| Latency overhead | 0 ms (2-line `is_enabled()` noop) |
| Token overhead | 0 tokens |
| Memory overhead | None (lazy import, no side effects) |
| Gateway impact | Zero — Gateway code not modified |

`enabled=False` (default) → `_gstack_phase_gate()` returns immediately after `is_enabled()` check.

---

## Shadow mode

| Metric | Value |
|--------|-------|
| Latency overhead | Not yet measured — gstack CLI unavailable |
| Token overhead | 0 tokens (no prompt injection) |
| Adapter call | `subprocess.run(["gstack", cmd, "--dry-run"])` |
| Output change | None — shadow writes metrics only |
| Timeout | 30s hard limit |

**Status:** BLOCKED — gstack CLI not found at PATH.
Install `gstack` and re-run `python -m agent_system.gstack_control.ops smoke` to get real latency data.

---

## Advisory mode

| Metric | Value |
|--------|-------|
| Latency overhead | Not yet measured — gstack CLI unavailable |
| Token overhead | ~20 tokens (advisory note appended to output) |
| Output change | `[gstack advisory] ...` note appended |
| Blocking | Never — advisory only |

**Status:** BLOCKED — gstack CLI not found at PATH.

---

## Controlled mode (dry_run_only=True, MVP)

| Metric | Value |
|--------|-------|
| Latency overhead | Not yet measured — gstack CLI unavailable |
| Guards | kill_switch check + allowlist check + budget check |
| Execution | `subprocess.run(["gstack", cmd, "--dry-run"])` |
| Dry-run flag | Always True in MVP |
| Human approval | Required (controlled=False by default) |

**Status:** BLOCKED — gstack CLI not found at PATH.
**Additional blocker:** `controlled=False` by default; requires explicit opt-in + kill_switch=False + allowlist.

---

## Quarantined mode

Entered only on unhandled exception in adapter/state_machine.
Hermes original chain continues unchanged.
Evidence written to `$HERMES_HOME/gstack_control/metrics/quarantined_*.json`.

---

## Real Smoke Test Results

```
$ python -m agent_system.gstack_control.ops smoke
{
  "adapter_available": false,
  "blocked": true,
  "blocked_reason": "gstack CLI not found at PATH",
  "phase_smoke": [
    {"phase_id": "gstack.plan_eng_review", "available": false, ...},
    {"phase_id": "gstack.review",          "available": false, ...},
    {"phase_id": "gstack.qa",              "available": false, ...}
  ]
}
```

**Resolution:** Install gstack CLI, then re-run `ops smoke` to get live results.
Upstream: https://github.com/garrytan/gstack (not verified — document when CLI is installed).

---

## Conclusion

| Criterion | Status |
|-----------|--------|
| `production_ready` | `false` — no benchmark without real gstack CLI |
| `blocking` default | `false` — guaranteed by `ControlDecision.__post_init__` |
| Gateway impact | None — `git diff gateway/` = 0 lines |
| Hermes chain impact | None in disabled mode (default) |

**Recommended rollout path:** shadow → advisory → controlled (all require explicit manual gates).
No phase should advance to the next mode without a real smoke test showing `adapter_available: true`.

---

## Rollback Instructions

1. Set `feature_flags.enabled = False` (already default — verify)
2. Confirm `git diff gateway/` is empty
3. Confirm `~/.hermes/config.yaml` timestamp unchanged
4. `rm -rf agent_system/gstack_control/`
5. `git checkout agent_system/readiness_manifest.json`
6. `rm -rf $HERMES_HOME/gstack_control/metrics/`
7. `rm -rf tests/agent_system/test_gstack_control_*.py tests/agent_system/test_gstack_*.py`
8. `scripts/run_tests.sh` → must show 0 failures

Or use the automated report: `python -m agent_system.gstack_control.ops rollback-report`
