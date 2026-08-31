# Decision Tracking Standard

> **Project:** pdf-ops
> **Started:** 2026-08-31
> **Last updated:** 2026-08-31

This document defines the format and workflow for tracking architectural decisions in this repo. Companion files: [`DECISIONS.md`](DECISIONS.md) (the data), [`planning/ASSUMPTIONS.md`](planning/ASSUMPTIONS.md) (open questions). CI validation: [`scripts/validate_decisions.py`](scripts/validate_decisions.py).

The controlled vocabularies described in prose throughout this document are formalized in the machine-parseable section at the bottom - `scripts/_standard_parser.py` reads from there, and `validate_decisions.py` imports the resulting frozen sets. Edit the bottom section to change vocabularies; the rest of the document is human-readable companion prose.

---

## ID scheme

Every decision has a stable primary key of the form `D-###` (zero-padded 3-digit sequential).

- `D-001` through the last row in the [Master Register](DECISIONS.md#master-register) are the authoritative IDs.
- New decisions get the next available number. IDs are never re-used, never renumbered.
- ADRs (full Context / Alternatives / Consequences analysis) carry a dual ID: `D-###` is the master ID, `ADR-###` is the ADR-specific ID. The mapping is documented in the master register.

**Why `D-###`:** grep-friendly, sorts lexicographically, unambiguous vs Markdown `#N` headings, stable under edits, 7 characters fits cleanly inline.

---

## Status vocabulary

| Icon | Status | Meaning |
|---|---|---|
| 🟢 | **Decided** | Committed. Being implemented or already implemented. |
| 🟡 | **Pending** | Awaiting external input (measurements, a spike, an upstream answer). Has a tracked `owner` and unblock condition. |
| ⏸ | **Deferred** | Explicitly parked. Non-breaking to add later. Includes a `phase_trigger` - the observable condition that would reopen it. |
| 🔵 | **Superseded** | Replaced by another decision. Row stays for historical record. `superseded_by` points forward. |
| ⚪ | **Draft** | Being proposed, not yet committed. Used during a walkthrough before approval. |
| ❌ | **Rejected** | Considered and declined. Kept so we don't re-debate it. Includes a one-line reason. |

---

## Required fields (every decision)

Every decision row in the master register carries these **7 required fields**, which appear as columns in the master table AND as field lines in the per-decision anchor page:

| Field | Purpose | Example |
|---|---|---|
| `id` | Stable primary key | `D-042` |
| `status` | Lifecycle state | 🟢 Decided |
| `area` | Subsystem / concern (fixed taxonomy, see below) | `error-handling` |
| `title` | Short human name | Static client error messages |
| `summary` | One-line decision content | Client-facing `error_message` is a static template; raw exceptions only in DLQ + observability platform. |
| `decided` | ISO date when the decision was confirmed. For 🟡 Pending and ⏸ Deferred entries, this is the date the *deferral* was confirmed (not a future date). | 2026-04-07 |
| `discussion` | Link to the full discussion - **subsystem doc only** (no ADR link, no ` - `). Every decision must have a durable home somewhere in `docs/`. | [`DESIGN_NOTES.md section 2`](DESIGN_NOTES.md) |

---

## Optional fields (when applicable)

| Field | Purpose | When present |
|---|---|---|
| `adr` | Link to a full ADR section | For decisions warranting full Context / Alternatives / Consequences analysis |
| `owner` | Who drives the unblock | **Required for 🟡 Pending** |
| `phase_trigger` | Observable condition that would unblock (🟡) or reopen (⏸) | **Required for 🟡 Pending and ⏸ Deferred** |
| `supersedes` / `superseded_by` | Forward/backward pointers between evolving decisions | When a decision replaces or is replaced by another |
| `amends` / `amended_by` | Partial-update relation - the decision still stands but a parameter has been tuned | Retune scenarios (distinct from `supersedes`) |
| `related` | Other `D-###` IDs that relate to this one | Cross-references |
| `blocks` / `blocked_by` | Dependencies | When a decision cannot be implemented until something else lands |
| `revisit_in` | Planned revisit milestone | For decisions marked "Phase N retune candidate" or similar |
| `revisit_trigger` | The observable condition that prompts re-evaluation | **Required for decide-under-assumption** (see workflow below) |
| `implementation_phase` | Which phase the decision lands in | Planning / scheduling lens |
| `risk` | Impact of being wrong: `low` / `medium` / `high` | Planning lens - informs review depth and test coverage |
| `reversibility` | Cost to undo: `cheap` (env-var) / `expensive` (code + data) / `one-way-door` (breaking contract) | Planning lens - informs how much up-front certainty is worth chasing |

**Schema rules:**

- `discussion` must NOT be ` - `. Every decision has a home somewhere in `docs/`. If the home is shared with other decisions, link to the file and cite the section heading closest to the relevant prose.
- `adr` is separate from `discussion`. A decision can have both, only `discussion`, or neither.
- `decided` is a real date for every entry - never blank, never TBD.

---

## Area taxonomy

The fixed area taxonomy is enumerated in the [Controlled vocabularies (machine-parseable)](#controlled-vocabularies-machine-parseable) section at the bottom of this document. Each area's intent is described inline in the codebase by the docs that own it - areas don't have stand-alone definitions. Edit the machine-parseable section to add or remove areas; `validate_decisions.py` picks up the change automatically.

---

## Workflow - adding a new decision

1. **Propose** - during discussion, write the decision inline in the relevant subsystem doc as a ⚪ Draft with rationale.
2. **Assign ID** - once approved, take the next `D-###` (check the [master register](DECISIONS.md#master-register) for the last used ID).
3. **Register** - add a row to the master table with the required fields.
4. **Anchor page** - add a per-decision anchor page below the table with the full fields.
5. **Link** - add inline `[D-###](DECISIONS.md#D-###)` breadcrumbs wherever the decision affects code or spec.
6. **ADR (optional)** - if the decision warrants full Context / Alternatives / Consequences analysis, write an ADR section. Use a dual ID (`D-### / ADR-###`). ADR numbering starts at `ADR-001`.

---

## Workflow - changing an existing decision

There are **two** change operations and they mean different things. Pick the right one:

| Operation | When to use | Old row status | New row status | Breadcrumb behavior |
|---|---|---|---|---|
| **Supersede** (`supersedes` / `superseded_by`) | The architectural choice itself changes (approach, provider, contract). The old decision is no longer correct. | 🔵 Superseded | 🟢 Decided | Update to point to the new ID |
| **Amend** (`amends` / `amended_by`) | The approach stands, but a parameter is tuned (cap value, threshold, retry count). Original decision is still correct. | 🟢 Decided *(unchanged)* | 🟢 Decided | Stay on the original ID for historical continuity; the original's anchor page lists all `amended_by` IDs |

**Never edit a row's content in place.** History matters - both supersede and amend create a new `D-###`.

### Supersede - worked example (synthetic)

*Scenario: D-002 chose pypdf as the PDF engine. Later, large-file memory limits force a move to the qpdf-backed pikepdf, changing the dependency set and the container image. This is an architectural change, not a tuning.*

**Step 1** - add a new decision, e.g. `D-047`, with `supersedes: D-002`:

```markdown
### D-047
- **Title:** PDF engine - switch to pikepdf
- **Status:** 🟢 Decided
- **Area:** pdf-engine
- **Decided on:** 2026-10-15
- **Summary:** Replace pypdf with pikepdf behind the engine seam for both operations.
- **Risk:** high
- **Reversibility:** expensive
- **Supersedes:** [D-002](#D-002)
- **Where:** [`DESIGN_NOTES.md section 1`](DESIGN_NOTES.md)
```

**Step 2** - flip the old row 🔵 Superseded in the master register and add `superseded_by` to the D-002 anchor page.

**Step 3** - update inline breadcrumbs in code and docs from `[D-002](DECISIONS.md#D-002)` to `[D-047](DECISIONS.md#D-047)`. The D-002 row stays in place for history.

### Amend - worked example (synthetic)

*Scenario: measurements show a merge input-count cap of 50 (D-024) is safe to raise to 100. The cap still exists, the approach is unchanged, only the number differs. This is an amendment, not a supersede.*

**Step 1** - add a new decision, e.g. `D-098`, with `amends: D-024`:

```markdown
### D-098
- **Title:** Merge input-count cap retuned to 100
- **Status:** 🟢 Decided
- **Area:** config
- **Decided on:** 2026-08-01
- **Summary:** Raise the merge input-count cap from 50 -> 100 based on measurements (p95 well under the cap).
- **Risk:** low
- **Reversibility:** cheap
- **Amends:** [D-024](#D-024)
```

**Step 2** - leave D-024 **🟢 Decided** (not superseded). Add an `Amended by` line to its anchor page.

**Step 3** - inline breadcrumbs continue to point to [D-024](#D-024) for historical context, because the *reasoning* is still there.

**Rule of thumb:** if the *why* from the original anchor page is still valid, you're amending. If the *why* has to be rewritten, you're superseding.

---

## Workflow - rejecting a decision

Use ❌ Rejected status with a one-line reason in the Summary cell. Don't delete - the whole point is to avoid re-debating.

### Reject - worked example (synthetic)

*Scenario: someone proposes adding Component X. After evaluation, an existing component already handles the use case - no new infra justified.*

**Master register row** (the Summary cell carries the one-line reason):

```markdown
| [`D-111`](#D-111) | ❌ | infra | Component X for use case Y | 2026-06-01 | Rejected - existing Component Z handles this; no additional infra needed. | [`planning/INFRA_CHECKLIST.md section 5`](planning/INFRA_CHECKLIST.md) | - |
```

**Anchor page** (minimal - no need for rationale beyond the rejection reason):

```markdown
### D-111
- **Title:** Component X for use case Y
- **Status:** ❌ Rejected
- **Area:** infra
- **Decided on:** 2026-06-01
- **Summary:** Rejected - existing Component Z handles this; no additional infra needed.
- **Where:** [`planning/INFRA_CHECKLIST.md section 5`](planning/INFRA_CHECKLIST.md)
```

Do not fill in Risk / Reversibility / Implementation phase - the decision was rejected, those fields are nonsensical. The row stays for the record.

---

## Workflow - decide under assumption

When a decision must be made while a key input is still unconfirmed, mark it 🟢 Decided rather than 🟡 Pending - but flag the assumption explicitly. This unblocks implementation while preserving auditability.

**Status string format:** `🟢 Decided - assumed YYYY-MM-DD (revisit if X)`

**Required anchor-page field:** `Revisit trigger:` - the observable condition that would prompt re-evaluation.

**Required cross-link:** A matching entry in [`planning/ASSUMPTIONS.md`](planning/ASSUMPTIONS.md) section 1 (Assumptions to Validate) with the same revisit trigger and a `Where` link back to the decision's anchor.

**Why prefer 🟢 over 🟡:** a 🟡 Pending decision blocks implementation - it has no committed direction. A 🟢-with-assumption commits to a default and unblocks work, while transparently flagging the input that may invalidate it. Implementation proceeds against the default; if the assumption is later disproved, an amendment is added (using the `amends` workflow above) - not a supersede, because the original reasoning was correct *given the assumption*.

**Validator gate:** [`scripts/validate_decisions.py`](scripts/validate_decisions.py) enforces that every decision whose Status contains the substring `assumed` has the `Revisit trigger:` field populated AND a corresponding row in `planning/ASSUMPTIONS.md` section 1.

### Decide-under-assumption - worked example (synthetic)

*Scenario: feature `X` needs a cap value. Telemetry doesn't yet exist to set it empirically. Block on telemetry would delay implementation by weeks; pick a reasonable default and revisit post-launch.*

**Master register row:**

```markdown
| [`D-060`](#D-060) | 🟢 | config | Merge input-count cap | 2026-04-20 | **Assumed 50.** Observed workflows fan in 2-10 inputs; 50 gives headroom without inviting memory blowups. Revisit if a real workflow exceeds it. | [`planning/ASSUMPTIONS.md section 1 item 13`](planning/ASSUMPTIONS.md) | - |
```

**Anchor page:**

```markdown
### D-060
- **Title:** Merge input-count cap
- **Status:** 🟢 Decided - assumed 2026-04-20 (revisit if real workflows exceed it)
- **Area:** config
- **Decided on:** 2026-04-20
- **Summary:** **Assumed 50.** Unbounded input lists risk memory blowups; observed workflows fan in 2-10 inputs. Env-configurable. Revisit if a real workflow exceeds it.
- **Risk:** low
- **Reversibility:** cheap
- **Revisit trigger:** A workflow legitimately needing more than 50 inputs, or measurements showing headroom.
- **Where:** [`planning/ASSUMPTIONS.md section 1 item 13`](planning/ASSUMPTIONS.md)
```

**ASSUMPTIONS.md section 1 row:**

```markdown
| 13 | Merge input-count cap = 50 | **ASSUMED 2026-04-20.** ... See [D-060](../DECISIONS.md#D-060). | A real workflow exceeding the cap | Raise via env var | - (non-blocking) |
```

---

## Historical sub-table policy (auto-split)

**Trigger:** when 5+ decisions reach 🔵 or ❌ status (combined), split the master register into two tables in `DECISIONS.md`:

- **Active Decisions** - `🟢`, `🟡`, `⏸`, `⚪`
- **Historical Decisions** - `🔵`, `❌`, with a one-line intro linking back to the active table

Both tables stay in `DECISIONS.md`. The split keeps the active view scannable while preserving the audit trail. Order is not sacred - ID order is fine for both.

No automation needed - do it manually when the threshold trips. `validate_decisions.py` continues to verify counts against whichever table each row lives in.

---

## Inline breadcrumb pattern (across all docs)

Every reference to a decision from another doc follows this exact pattern:

```markdown
Some prose about a design choice (per [D-042](DECISIONS.md#D-042)).
```

- The link text is **only** the ID - no prose inside the brackets.
- This keeps `grep -r "D-042"` trivial.
- Use a relative path appropriate to the citing file's depth (`DECISIONS.md#D-042` from `docs/`, `../DECISIONS.md#D-042` from `docs/<sub>/`, `../../DECISIONS.md#D-042` from `docs/<sub>/<sub>/`).

---

## Controlled vocabularies (machine-parseable)

> This section is parsed by [`scripts/_standard_parser.py`](scripts/_standard_parser.py). `validate_decisions.py` imports vocabularies from here - it does NOT carry hardcoded duplicates. Edit the backtick-quoted items below to change vocabularies; the validator picks up changes automatically. **Do not change the H2 header wording or the H3 subsection headers.** Each item must be on its own line beginning with `` - `<value>` ``.

### Areas

- `pdf-engine`
- `config`
- `error-handling`
- `security`
- `observability`
- `reliability`
- `container`
- `testing`
- `infra`
- `project`

### Status icons

- `🟢`
- `🟡`
- `⏸`
- `🔵`
- `⚪`
- `❌`

### Risk values

- `low`
- `medium`
- `high`

### Reversibility values

- `cheap`
- `expensive`
- `one-way-door`

### Implementation phases

- `0`
- `1`
- `2`
- `3`
- `4`
- `5`
- `6`
- `7`
