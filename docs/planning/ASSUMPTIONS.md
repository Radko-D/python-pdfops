# pdf-ops: Assumptions to Validate and Open Questions

> **Status:** Living document - update as items are confirmed or resolved.
> **Last updated:** 2026-08-31

---

## 1. Assumptions to Validate (Must Do Before Implementation)

Assumptions made during design that still need confirmation from real usage or external signals. Each row should cross-link to the corresponding `D-###` decision in `../DECISIONS.md` whose Status carries ` - assumed YYYY-MM-DD (revisit if X)` (see the decide-under-assumption pattern in `../DECISION_TRACKING_STANDARD.md`).

| # | Assumption | Current Basis | Validate With | Impact If Wrong | Blocks |
|---|-----------|---------------|---------------|-----------------|-------------|
|   |           |               |               |                 |             |

---

## 2. Design Items Deferred to Implementation

These are details that will be resolved during development, not blockers.

| # | Item | Deferred To | Notes |
|---|------|-------------|-------|
| 1 | Transient exit-code band (10+) | Retry-semantics work | [`D-006`](../DECISIONS.md#D-006) - 0-6 map stands; exit 1 only maybe-retryable until then |
| 2 | `PDFOPS_INPUTS` separator | Post-merge review | [`D-007`](../DECISIONS.md#D-007) - merge ships provisional `os.pathsep` (colon) |
| 3 | Operation value case strictness | Contract freeze | [`D-008`](../DECISIONS.md#D-008) - strict lowercase stands |
| 4 | Unknown `PDFOPS_*` var hard rejection | Deployment example | [`D-009`](../DECISIONS.md#D-009) - hard exit 2 stands |

---

## 3. Nice-to-Have (Non-Blocking, Answer Anytime)

| # | Question | Context |
|---|----------|---------|
|   |          |         |

---

## 4. Validation Tracker

Use this section to record answers as they come in.

| # | Item | Status | Answer | Date |
|---|------|--------|--------|------|
|   |      |        |        |      |
