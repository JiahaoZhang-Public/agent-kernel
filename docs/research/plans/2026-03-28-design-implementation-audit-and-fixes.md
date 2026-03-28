# Plan: Design-to-Implementation Audit & Alignment Fixes

**Date:** 2026-03-28
**Status:** In Progress
**Target Release:** v0.4.1
**Scope:** v2 + v2.1 design compliance, correctness fixes, test coverage

## 1. Background

A full design-to-implementation audit was conducted comparing the codebase against the v2 and v2.1 design specifications in `docs/research/design/`. The audit evaluated architecture, module boundaries, data flow, APIs, algorithms, state management, error handling, extensibility, and testing.

**Overall verdict:** High fidelity. The implementation faithfully realizes both designs.

## 2. Current Status

### 2.1 What Is Correctly Implemented

| Design Component | Design Reference | Code Reference | Verdict |
|---|---|---|---|
| Gate: single `submit()` API, 5-step flow | v2 §4, §10 | `kernel.py:61-100` | Match |
| Five log statuses: INVALID, DENIED, NO_PROVIDER, FAILED, OK | v2 §4.2 | `kernel.py:74-100` | Match |
| Every path produces one log record (no silent actions) | v2 §8.3 | `kernel.py:76,81,86,95,99` | Match |
| Policy: static YAML allow-list, glob matching, default deny | v2 §3 | `policy.py:60-73` | Match |
| Log: append-only JSONL, kernel-exclusive write | v2 §5 | `log.py:38-53` | Match |
| Object model: ActionRequest, ActionResult, Record | v2 §6 | `models.py` | Match |
| Provider contract: ABC with actions/execute, no auth/log writes | v2 §7 | `providers/base.py` | Match |
| Reversible layer above kernel, not inside | v2.1 structure | `reversible.py:135-206` | Match |
| Rollback goes through Gate (authorized + logged) | v2.1 rollback flow | `reversible.py:191` | Match |
| SnapshotStrategy ABC: supports, capture, restore | v2.1 §2.2 | `reversible.py:26-49` | Match |
| FsWriteSnapshotStrategy: capture/restore file content | v2.1 §2.2 example | `reversible.py:52-79` | Match |
| SnapshotStore: file-based KV with TTL | v2.1 §2.3 | `reversible.py:82-133` | Match |
| Snapshot only saved on OK | v2.1 §3.1 step 4 | `reversible.py:166` | Match |
| Snapshot persists on failed rollback | v2.1 §3.2 | `reversible.py:194-197` | Match |
| Agent loop: `kernel.submit()` is sole execution path | v2 §1, §8.1 | `agent_loop.py:132-160` | Match |
| ToolDef: metadata only, no execution logic | v2 §1 invariant | `agent_loop.py:26-47` | Match |

### 2.2 What Has Been Fixed (This Audit)

#### Fix 1: Missing Error Handling in ReversibleActionLayer (P0)

**Problem:** Design §7.1-7.2 specifies graceful degradation on capture/persistence failures. Implementation had no try/except around `strategy.capture()` or `store.save()`. A filesystem error during capture or a disk-full during save would crash the submit flow.

**Fix applied:**

```python
# §7.1: Capture failure → continue without snapshot
if strategy is not None:
    try:
        snapshot = strategy.capture(request)
    except Exception:
        logger.warning("Snapshot capture failed for %s:%s", ...)
        snapshot = None

# §7.2: Save failure → continue without record_id
try:
    self.store.save(record_id, request, snapshot)
    result.record_id = record_id
except Exception:
    logger.warning("Failed to save snapshot for %s:%s", ...)
```

**Files modified:** `src/agent_os_kernel/reversible.py`

#### Fix 2: Added Logging to ReversibleActionLayer (P1)

**Problem:** No observability into snapshot capture/save/rollback events.

**Fix applied:** Added `logging.getLogger(__name__)` with warning-level logs for failure paths.

**Files modified:** `src/agent_os_kernel/reversible.py`

#### Fix 3: Exported Reversible Layer Components (P1)

**Problem:** `ReversibleActionLayer`, `SnapshotStrategy`, `SnapshotStore`, `FsWriteSnapshotStrategy` were not in the package's public API exports.

**Fix applied:** Added all four to `__init__.py` `__all__`.

**Files modified:** `src/agent_os_kernel/__init__.py`

#### Fix 4: Added Failure Injection Tests (P0)

**Problem:** Design §10.6 specifies 5 failure injection tests. None existed.

**Tests added (5):**
1. `test_capture_raises_exception_action_continues` — strategy.capture() raises → action proceeds without snapshot
2. `test_store_save_raises_exception_action_completes` — store.save() raises → action completes without record_id
3. `test_store_load_returns_none_for_rollback` — rollback nonexistent record → error
4. `test_kernel_denies_restore_action` — policy changed between submit and rollback → restore denied, snapshot persists
5. `test_concurrent_modification_before_rollback` — file modified externally → rollback restores stale state (documents known limitation)

**Files modified:** `tests/test_reversible.py`

### 2.3 Test Results After Fixes

```
197 passed in 5.21s
Coverage: 96.61% (threshold: 80%)
```

All existing tests continue to pass. 5 new tests added (from 192 → 197 in full non-live suite).

## 3. Remaining Gaps

### 3.1 record_id Not Written to Log Records (Medium)

**Design reference:** v2.1 §11.1 — adds optional `record_id` to Record schema. Example log output shows `"record_id":"abc123def456"` on reversible action entries.

**Current state:** `Record` dataclass has the `record_id` field (`models.py:68`), and `Log.read_all()` deserializes it (`log.py:77`), but `Kernel._record()` never populates it.

**Design tension:** v2.1 also says "the kernel is unchanged." Writing `record_id` to the log requires modifying `Kernel._record()` — a kernel interface change. Options:

| Option | Pros | Cons |
|---|---|---|
| (a) Add `record_id` param to `_record()` | Log entries correlate to snapshots | Modifies kernel interface |
| (b) Post-annotate log from layer | No kernel change | Violates kernel-exclusive write |
| (c) Document as caller-side only | Design-consistent | External tools can't correlate |

**Recommendation:** Option (c) for now. Document that log-to-snapshot correlation is available via `ActionResult.record_id` at the caller level. Revisit if external tooling needs log-level correlation.

### 3.2 SnapshotStore JSON Schema Divergence (Low)

| Field | Design Spec | Implementation |
|---|---|---|
| Key for request | `"original_request"` | `"request"` |
| `created_at` format | ISO 8601 string | `time.time()` float |
| `expires_at` field | Present | Absent (computed at load) |

**Impact:** Functional behavior is correct. Divergence affects human readability and potential interop with external tools.

### 3.3 CLAUDE.md Stale Reference (Low)

The project's `CLAUDE.md` states: "The agent backbone must use OpenAI Agents SDK." This was true for v0.1-v0.3 but is stale since v0.4.0 replaced it with a kernel-native loop using LiteLLM. The framework survey at `docs/research/references/agent-frameworks.md` documents the rationale for this change.

### 3.4 Agent Loop Not Covered by Design Docs

`AgentLoop` and `ToolDef` implement the v2 §1 integration point but are not formally specified in any design document. They are a significant architectural component (kernel-native LLM loop with LiteLLM routing) that warrants a v2.2 or standalone design spec.

**Note:** The plan at `docs/research/plans/2026-03-27-kernel-native-agent-loop.md` serves as the de facto design document for this component.

## 4. Recommended Next Steps

### Immediate (before v0.4.1 tag)

| # | Action | Priority | Complexity | Files |
|---|---|---|---|---|
| 1 | ~~Add error handling to ReversibleActionLayer~~ | P0 | Small | ~~reversible.py~~ **Done** |
| 2 | ~~Add failure injection tests~~ | P0 | Small | ~~test_reversible.py~~ **Done** |
| 3 | ~~Export reversible components~~ | P1 | Small | ~~__init__.py~~ **Done** |
| 4 | ~~Add logging to ReversibleActionLayer~~ | P1 | Small | ~~reversible.py~~ **Done** |

### Short-Term (v0.4.x)

| # | Action | Priority | Complexity | Files |
|---|---|---|---|---|
| 5 | Update CLAUDE.md to remove stale OpenAI SDK reference | P1 | Small | `CLAUDE.md` |
| 6 | Document record_id log gap in code comments | P1 | Small | `reversible.py`, `models.py` |
| 7 | Align SnapshotStore JSON schema with design | P2 | Small | `reversible.py`, `test_reversible.py` |
| 8 | Add `SubmitFn` type alias | P2 | Small | `models.py` or `agent_loop.py` |

### Longer-Term (v0.5+)

| # | Action | Priority | Complexity |
|---|---|---|---|
| 9 | Write formal design doc for AgentLoop/ToolDef (v2.2 or standalone) | P2 | Medium |
| 10 | Decide on record_id-in-log strategy if external tooling needs it | P2 | Medium |
| 11 | Additional snapshot strategies (proc.exec, net.http) | P2 | Medium |

## 5. Audit Methodology

The audit was conducted by:

1. Reading all files in `docs/research/design/v2/` and `docs/research/design/v2.1/` completely
2. Reading all source files in `src/agent_os_kernel/` and `src/agent_os_kernel/providers/`
3. Reading all test files in `tests/`
4. Comparing design requirements point-by-point against implementation
5. Classifying each finding as: Match, Partial Match, Missing, Divergent
6. Distinguishing between: design mismatch, implementation bug, acceptable engineering deviation, design gap/ambiguity
7. Implementing fixes for P0 and P1 items
8. Verifying all 197 tests pass after changes

## 6. References

- Design v2: `docs/research/design/v2/Kernel_Design_v2.md`
- Design v2.1: `docs/research/design/v2.1/Kernel_Design_v2.1.md`
- Agent loop plan: `docs/research/plans/2026-03-27-kernel-native-agent-loop.md`
- Framework survey: `docs/research/references/agent-frameworks.md`
- Full audit report: `.claude/plans/majestic-marinating-fountain.md`
