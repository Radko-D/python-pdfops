# Architectural Decision Records: pdf-ops

> **Project:** Containerized PDF operations (merge, extract attachments) for workflow systems
> **Started:** 2026-08-31
> **Last updated:** 2026-09-01

This document is the authoritative register of all architectural decisions for this project. New decisions are appended with the next available `D-###`. See [DECISION_TRACKING_STANDARD.md](DECISION_TRACKING_STANDARD.md) for format, vocabularies, and workflow. CI validation: [`scripts/validate_decisions.py`](scripts/validate_decisions.py).

---

## Master Register

| ID | Status | Area | Title | Decided | Summary | Discussion | ADR |
|---|---|---|---|---|---|---|---|
| [`D-001`](#D-001) | 🟢 | project | Decision tracking framework adopted | 2026-08-31 | Adopted the `D-###` decision tracking framework with `🟢🟡⏸🔵⚪❌` status vocabulary, fixed area taxonomy, decide-under-assumption pattern, and CI-validated master register. | [`DECISION_TRACKING_STANDARD.md`](DECISION_TRACKING_STANDARD.md) | - |
| [`D-002`](#D-002) | 🟢 | pdf-engine | PDF engine: pypdf first behind a Protocol, planned pikepdf swap | 2026-08-31 | Engine isolated behind a narrow Protocol; the first iterations use pypdf (pure Python), with a planned swap to pikepdf (large files, corrupt-input robustness, AES-256) before production hardening; pypdf then becomes a dev-dependency test oracle. PyMuPDF rejected on AGPL licensing, not capability. | [`DESIGN_NOTES.md section 1`](DESIGN_NOTES.md) | - |
| [`D-003`](#D-003) | 🟢 | error-handling | Exit-code taxonomy: classes 0-6 + error_code strings | 2026-08-31 | 0 success, 1 unexpected, 2 config, 3 input missing, 4 invalid/corrupt PDF, 5 password, 6 output; defined fully up front because workflow retry policies build on it. Fine granularity via machine-readable error_code strings in the terminal JSON event, not more codes. | [`DESIGN_NOTES.md section 2`](DESIGN_NOTES.md) | - |
| [`D-004`](#D-004) | 🟢 | config | Env contract: PDFOPS_ prefix, fail-fast pure parsing, unknown-var rejection | 2026-08-31 | All config from PDFOPS_* env vars parsed by a pure function over Mapping[str,str] before any file is touched; os.environ only in __main__. Unknown PDFOPS_* vars are rejected as probable typos (exit 2 UNKNOWN_VAR); empty equals missing. | [`DESIGN_NOTES.md section 3`](DESIGN_NOTES.md) | - |
| [`D-005`](#D-005) | 🟢 | observability | Observability: JSON-lines on stdout via stdlib logging | 2026-08-31 | One JSON object per line on stdout (workflow engine captures step logs); stable event tokens with structured fields; exactly one terminal event per run from the single error boundary. Stdlib logging with a small formatter - no structlog/OTel dependency. | [`DESIGN_NOTES.md section 4`](DESIGN_NOTES.md) | - |
| [`D-006`](#D-006) | 🔵 | error-handling | Transient exit-code band (10+) for retryable failures | 2026-08-31 | Deferred (2026-08-31): the 0-6 map stands as-is with exit 1 the only maybe-retryable code. A dedicated 10+ transient band (e.g. transient I/O) would let Argo retryStrategy expressions retry precisely; revisit when retry semantics become load-bearing. | [`DESIGN_NOTES.md section 2`](DESIGN_NOTES.md) | - |
| [`D-007`](#D-007) | ⏸ | config | PDFOPS_INPUTS list separator | 2026-08-31 | Deferred (2026-08-31): the merge implementation ships the recommended default - os.pathsep (colon) with explicit ordered paths, no globs - as provisional. Alternatives (comma, newline, JSON array) parked; revisit if colon-in-path or workflow-templating friction appears. | [`DESIGN_NOTES.md section 3`](DESIGN_NOTES.md) | - |
| [`D-008`](#D-008) | ⏸ | config | Operation value case strictness | 2026-08-31 | Deferred (2026-08-31): strict lowercase merge/extract (whitespace tolerated) stands as implemented. Case-insensitive acceptance parked; revisit at README/contract freeze or on operator feedback. | [`DESIGN_NOTES.md section 3`](DESIGN_NOTES.md) | - |
| [`D-009`](#D-009) | ⏸ | config | Unknown PDFOPS_* variable hard rejection | 2026-08-31 | Deferred (2026-08-31): hard rejection (exit 2 UNKNOWN_VAR) stands as implemented. Softening to a warning parked; revisit if a platform legitimately injects foreign PDFOPS_* vars (e.g. when the deployment example is written). | [`DESIGN_NOTES.md section 3`](DESIGN_NOTES.md) | - |
| [`D-010`](#D-010) | 🟢 | reliability | Atomic output writes: temp file in destination dir + os.replace | 2026-08-31 | All output goes to a temp file in the destination directory (same filesystem), is fsynced, and is renamed over the final path in one step; the final path holds a complete PDF or nothing. Existing output refused (OUTPUT_EXISTS) until the overwrite/skip policy lands; missing output dir refused, never auto-created. | [`DESIGN_NOTES.md section 6`](DESIGN_NOTES.md) | - |
| [`D-011`](#D-011) | 🟢 | pdf-engine | Merge is pages-only; input attachments/bookmarks/metadata not carried | 2026-08-31 | The merged output carries pages only: bookmarks, form fields, metadata, and embedded attachments of the inputs are not copied (no mainstream Python library copies /Names/EmbeddedFiles on merge - attachments would drop silently). Documented limitation; detect-and-warn vs fail-loud vs qpdf --copy-attachments-from evaluated when attachment handling is built out. | [`DESIGN_NOTES.md section 5`](DESIGN_NOTES.md) | - |
| [`D-012`](#D-012) | 🟢 | error-handling | Merge input validation: collect-all, first problem sets exit class | 2026-08-31 | Every input is checked up front (exists, is a file, readable, %PDF- magic) before any write; all problems are reported in one failure event with the full list in context.problems, and the exit class follows the first problem in input order. Duplicate inputs are a hard config error; a single input is a valid merge. | [`DESIGN_NOTES.md section 6`](DESIGN_NOTES.md) | - |
| [`D-013`](#D-013) | 🔵 | security | Encrypted inputs refused with the password exit class | 2026-08-31 | Until password support lands, encrypted input PDFs are refused with exit 5 (PASSWORD_REQUIRED; UNSUPPORTED_ENCRYPTION when the AES backend is unavailable) instead of surfacing as corrupt-file or internal errors - the operator remedy for a locked file differs entirely from the remedy for a broken one. | [`DESIGN_NOTES.md section 5`](DESIGN_NOTES.md) | - |
| [`D-014`](#D-014) | 🟢 | security | Attachment names sanitized always, never trusted | 2026-09-01 | Every attachment name is reduced to a safe basename by a pure, table-tested sanitizer (separator normalization, basename, control-char strip, length cap, deterministic fallback); hostile names rename rather than fail the PDF, originals are logged when changed, and resolved write targets are re-verified to stay inside PDFOPS_OUTPUT_DIR. | [`DESIGN_NOTES.md section 7`](DESIGN_NOTES.md) | - |
| [`D-015`](#D-015) | 🟢 | error-handling | Extract semantics: deterministic order, all-or-nothing conflicts, zero-attachments success | 2026-09-01 | Extraction follows PDF name-tree order (deterministic across runs); duplicate names get -1/-2 suffixes; pre-existing files or symlinks at any target name fail the run before anything is written; zero attachments is exit 0 with attachments_extracted=0, flipped to exit 3 NO_ATTACHMENTS by PDFOPS_FAIL_ON_NO_ATTACHMENTS=true. | [`DESIGN_NOTES.md section 7`](DESIGN_NOTES.md) | - |
| [`D-016`](#D-016) | 🟢 | pdf-engine | Extract covers document-level attachments only | 2026-09-01 | Only the document-level /Names/EmbeddedFiles tree is extracted; page-level /FileAttachment annotations (sticky-note attachments) are a documented limitation and future work rather than a half-supported path. | [`DESIGN_NOTES.md section 7`](DESIGN_NOTES.md) | - |
| [`D-017`](#D-017) | 🟢 | security | Password channels with a layered, tested no-leak guarantee | 2026-09-01 | One password via mutually exclusive channels - PDFOPS_PASSWORD_FILE (mounted secret, preferred) or PDFOPS_PASSWORD (discouraged, documented why); parser stays filesystem-free by capturing the source and resolving in one step before dispatch. No-leak is layered: Secret wrapper renders ***, the log layer scrubs registered values incl. tracebacks, the entrypoint deletes secret vars from the live env, and leak tests assert the literal password appears in no output on success, failure, or crash paths. | [`DESIGN_NOTES.md section 8`](DESIGN_NOTES.md) | - |
| [`D-018`](#D-018) | 🟢 | pdf-engine | Decrypt semantics: empty-password auto-try, algorithm + password_type logged | 2026-09-01 | The plaintext /Encrypt dictionary yields the algorithm before any password work (logged per input); with no password supplied the spec-standard empty-password verification runs first - a side-effect-free hash check, the same thing every viewer does - so owner-only permissions-locked PDFs just work, and PASSWORD_REQUIRED fires only when the empty try fails. Successful opens log password_type user/owner/empty; a wrong password names the failing input; an unneeded password draws a password_unused warning. | [`DESIGN_NOTES.md section 8`](DESIGN_NOTES.md) | - |
| [`D-019`](#D-019) | 🟢 | security | Output encryption: never|inherit|always tri-state, AES-256, explicit-password fallback | 2026-09-01 | PDFOPS_OUTPUT_ENCRYPTION: never (default; plaintext output with a loud security_downgrade warning when inputs were encrypted), inherit (encrypt iff any input was encrypted - confidentiality never decreases), always. Output password from its own channel pair, falling back only to an explicitly supplied input password - never the empty auto-try (MISSING_OUTPUT_PASSWORD instead). Output always AES-256 regardless of input schemes; an output password with mode never is a hard error. | [`DESIGN_NOTES.md section 8`](DESIGN_NOTES.md) | - |
| [`D-020`](#D-020) | 🟢 | error-handling | Retryability contract: exit codes stay 0-6, retry guidance is documentation | 2026-09-01 | No 10+ transient exit-code band: the 0-6 map is a published API and nearly every failure class is deterministic, so retryability lives in the README - a per-code table (exit 1 the only default-retryable, DISK_FULL the judgment call) and an Argo retryStrategy.expression snippet, paired with PDFOPS_ON_EXISTS=skip for at-least-once safety. | [`DESIGN_NOTES.md section 9`](DESIGN_NOTES.md) | - |
| [`D-021`](#D-021) | 🟢 | reliability | PDFOPS_ON_EXISTS tri-state: merge whole-run skip, extract per-file completion | 2026-09-01 | fail (default) refuses; overwrite replaces atomically; skip treats existing output as completed prior work - merge short-circuits without reading inputs, extract writes only missing attachments (sound because every written file is atomic and therefore whole). Stale temp debris matching the run's own targets is removed at startup under a documented single-writer-per-output assumption. | [`DESIGN_NOTES.md section 9`](DESIGN_NOTES.md) | - |

**Counts:** 21 total decisions - 16 🟢 decided, 0 🟡 pending, 3 ⏸ deferred, 2 🔵 superseded.

### Index by area

> **Note:** these counts are recomputable from the master register `area` column. If the count and the IDs list disagree, the IDs list is authoritative. [`scripts/validate_decisions.py`](scripts/validate_decisions.py) recomputes both on every run and CI-fails on drift.

| Area | Count | IDs |
|---|---|---|
| error-handling | 5 | D-003, D-006, D-012, D-015, D-020 |
| config | 4 | D-004, D-007, D-008, D-009 |
| pdf-engine | 4 | D-002, D-011, D-016, D-018 |
| security | 4 | D-013, D-014, D-017, D-019 |
| reliability | 2 | D-010, D-021 |
| observability | 1 | D-005 |
| project | 1 | D-001 |
| **Total** | **21** | |

### Open decisions (🟡 Pending + ⏸ Deferred)

| ID | Status | Owner / Trigger |
|---|---|---|
| [`D-007`](#D-007) | ⏸ Deferred | Post-merge review, or `:`-in-path / templating friction |
| [`D-008`](#D-008) | ⏸ Deferred | Contract freeze, or mixed-case values seen in practice |
| [`D-009`](#D-009) | ⏸ Deferred | Platform injecting foreign `PDFOPS_*` vars (deployment-example watch) |

### Decisions scheduled for revisit

Derived from the `revisit_in` field on anchor pages. Update when the field changes. Purpose: one place to answer "what comes back on the table at milestone X?".

| Milestone | IDs |
|---|---|
| _(none yet)_ | |

---

## Decision Anchor Pages

Per-decision details: status, decided date, rationale, related decisions, and the discussion link.

<a id="D-001"></a>
### D-001
- **Title:** Decision tracking framework adopted
- **Status:** 🟢 Decided
- **Area:** project
- **Decided on:** 2026-08-31
- **Summary:** Adopted the `D-###` decision tracking framework with `🟢🟡⏸🔵⚪❌` status vocabulary, fixed area taxonomy, decide-under-assumption pattern, and CI-validated master register. Scaffolded from a reusable template.
- **Risk:** low
- **Reversibility:** expensive
- **Rationale TL;DR:** Informal note-taking and ad-hoc decision capture rot fast; standardizing now establishes discipline before the project accumulates dozens of in-flight decisions. The framework is CI-validated, so drift is caught early.
- **Where:** [`DECISION_TRACKING_STANDARD.md`](DECISION_TRACKING_STANDARD.md)

<a id="D-002"></a>
### D-002
- **Title:** PDF engine: pypdf first behind a Protocol, planned pikepdf swap
- **Status:** 🟢 Decided
- **Area:** pdf-engine
- **Decided on:** 2026-08-31
- **Summary:** Engine isolated behind a narrow Protocol; the first iterations use pypdf (pure Python), with a planned swap to pikepdf (large files, corrupt-input robustness, AES-256) before production hardening; pypdf then becomes a dev-dependency test oracle. PyMuPDF rejected on AGPL licensing, not capability.
- **Risk:** medium
- **Reversibility:** cheap
- **Where:** [`DESIGN_NOTES.md section 1`](DESIGN_NOTES.md)

<a id="D-003"></a>
### D-003
- **Title:** Exit-code taxonomy: classes 0-6 + error_code strings
- **Status:** 🟢 Decided
- **Area:** error-handling
- **Decided on:** 2026-08-31
- **Summary:** 0 success, 1 unexpected, 2 config, 3 input missing, 4 invalid/corrupt PDF, 5 password, 6 output; defined fully up front because workflow retry policies build on it. Fine granularity via machine-readable error_code strings in the terminal JSON event, not more codes.
- **Risk:** medium
- **Reversibility:** expensive
- **Where:** [`DESIGN_NOTES.md section 2`](DESIGN_NOTES.md)

<a id="D-004"></a>
### D-004
- **Title:** Env contract: PDFOPS_ prefix, fail-fast pure parsing, unknown-var rejection
- **Status:** 🟢 Decided
- **Area:** config
- **Decided on:** 2026-08-31
- **Summary:** All config from PDFOPS_* env vars parsed by a pure function over Mapping[str,str] before any file is touched; os.environ only in __main__. Unknown PDFOPS_* vars are rejected as probable typos (exit 2 UNKNOWN_VAR); empty equals missing.
- **Risk:** low
- **Reversibility:** expensive
- **Where:** [`DESIGN_NOTES.md section 3`](DESIGN_NOTES.md)

<a id="D-005"></a>
### D-005
- **Title:** Observability: JSON-lines on stdout via stdlib logging
- **Status:** 🟢 Decided
- **Area:** observability
- **Decided on:** 2026-08-31
- **Summary:** One JSON object per line on stdout (workflow engine captures step logs); stable event tokens with structured fields; exactly one terminal event per run from the single error boundary. Stdlib logging with a small formatter - no structlog/OTel dependency.
- **Risk:** low
- **Reversibility:** cheap
- **Where:** [`DESIGN_NOTES.md section 4`](DESIGN_NOTES.md)

<a id="D-006"></a>
### D-006
- **Title:** Transient exit-code band (10+) for retryable failures
- **Status:** 🔵 Superseded
- **Superseded by:** [D-020](#D-020)
- **Area:** error-handling
- **Decided on:** 2026-08-31
- **Summary:** Deferred (2026-08-31): the 0-6 map stands as-is with exit 1 the only maybe-retryable code. A dedicated 10+ transient band (e.g. transient I/O) would let Argo retryStrategy expressions retry precisely; revisit when retry semantics become load-bearing.
- **Risk:** medium
- **Reversibility:** expensive
- **Phase trigger:** Retry-semantics work documents the Argo retryStrategy expression - the retryable/permanent split becomes load-bearing there.
- **Where:** [`DESIGN_NOTES.md section 2`](DESIGN_NOTES.md)

<a id="D-007"></a>
### D-007
- **Title:** PDFOPS_INPUTS list separator
- **Status:** ⏸ Deferred
- **Area:** config
- **Decided on:** 2026-08-31
- **Summary:** Deferred (2026-08-31): the merge implementation ships the recommended default - os.pathsep (colon) with explicit ordered paths, no globs - as provisional. Alternatives (comma, newline, JSON array) parked; revisit if colon-in-path or workflow-templating friction appears.
- **Risk:** low
- **Reversibility:** expensive
- **Phase trigger:** Post-merge review, or the first path containing `:` / workflow-templating friction with the provisional os.pathsep separator.
- **Where:** [`DESIGN_NOTES.md section 3`](DESIGN_NOTES.md)

<a id="D-008"></a>
### D-008
- **Title:** Operation value case strictness
- **Status:** ⏸ Deferred
- **Area:** config
- **Decided on:** 2026-08-31
- **Summary:** Deferred (2026-08-31): strict lowercase merge/extract (whitespace tolerated) stands as implemented. Case-insensitive acceptance parked; revisit at README/contract freeze or on operator feedback.
- **Risk:** low
- **Reversibility:** cheap
- **Phase trigger:** README/contract freeze, or operator feedback that mixed-case operation values occur in practice.
- **Where:** [`DESIGN_NOTES.md section 3`](DESIGN_NOTES.md)

<a id="D-009"></a>
### D-009
- **Title:** Unknown PDFOPS_* variable hard rejection
- **Status:** ⏸ Deferred
- **Area:** config
- **Decided on:** 2026-08-31
- **Summary:** Deferred (2026-08-31): hard rejection (exit 2 UNKNOWN_VAR) stands as implemented. Softening to a warning parked; revisit if a platform legitimately injects foreign PDFOPS_* vars (e.g. when the deployment example is written).
- **Risk:** low
- **Reversibility:** cheap
- **Phase trigger:** A platform legitimately injecting foreign `PDFOPS_*` variables (watch when writing the deployment example).
- **Where:** [`DESIGN_NOTES.md section 3`](DESIGN_NOTES.md)

<a id="D-010"></a>
### D-010
- **Title:** Atomic output writes: temp file in destination dir + os.replace
- **Status:** 🟢 Decided
- **Area:** reliability
- **Decided on:** 2026-08-31
- **Summary:** All output goes to a temp file in the destination directory (same filesystem), is fsynced, and is renamed over the final path in one step; the final path holds a complete PDF or nothing. Existing output refused (OUTPUT_EXISTS) until the overwrite/skip policy lands; missing output dir refused, never auto-created.
- **Risk:** medium
- **Reversibility:** cheap
- **Where:** [`DESIGN_NOTES.md section 6`](DESIGN_NOTES.md)

<a id="D-011"></a>
### D-011
- **Title:** Merge is pages-only; input attachments/bookmarks/metadata not carried
- **Status:** 🟢 Decided
- **Area:** pdf-engine
- **Decided on:** 2026-08-31
- **Summary:** The merged output carries pages only: bookmarks, form fields, metadata, and embedded attachments of the inputs are not copied (no mainstream Python library copies /Names/EmbeddedFiles on merge - attachments would drop silently). Documented limitation; detect-and-warn vs fail-loud vs qpdf --copy-attachments-from evaluated when attachment handling is built out.
- **Risk:** medium
- **Reversibility:** expensive
- **Where:** [`DESIGN_NOTES.md section 5`](DESIGN_NOTES.md)

<a id="D-012"></a>
### D-012
- **Title:** Merge input validation: collect-all, first problem sets exit class
- **Status:** 🟢 Decided
- **Area:** error-handling
- **Decided on:** 2026-08-31
- **Summary:** Every input is checked up front (exists, is a file, readable, %PDF- magic) before any write; all problems are reported in one failure event with the full list in context.problems, and the exit class follows the first problem in input order. Duplicate inputs are a hard config error; a single input is a valid merge.
- **Risk:** low
- **Reversibility:** cheap
- **Where:** [`DESIGN_NOTES.md section 6`](DESIGN_NOTES.md)

<a id="D-013"></a>
### D-013
- **Title:** Encrypted inputs refused with the password exit class
- **Status:** 🔵 Superseded
- **Superseded by:** [D-017](#D-017)
- **Area:** security
- **Decided on:** 2026-08-31
- **Summary:** Until password support lands, encrypted input PDFs are refused with exit 5 (PASSWORD_REQUIRED; UNSUPPORTED_ENCRYPTION when the AES backend is unavailable) instead of surfacing as corrupt-file or internal errors - the operator remedy for a locked file differs entirely from the remedy for a broken one.
- **Risk:** low
- **Reversibility:** cheap
- **Where:** [`DESIGN_NOTES.md section 5`](DESIGN_NOTES.md)

<a id="D-014"></a>
### D-014
- **Title:** Attachment names sanitized always, never trusted
- **Status:** 🟢 Decided
- **Area:** security
- **Decided on:** 2026-09-01
- **Summary:** Every attachment name is reduced to a safe basename by a pure, table-tested sanitizer (separator normalization, basename, control-char strip, length cap, deterministic fallback); hostile names rename rather than fail the PDF, originals are logged when changed, and resolved write targets are re-verified to stay inside PDFOPS_OUTPUT_DIR.
- **Risk:** high
- **Reversibility:** cheap
- **Where:** [`DESIGN_NOTES.md section 7`](DESIGN_NOTES.md)

<a id="D-015"></a>
### D-015
- **Title:** Extract semantics: deterministic order, all-or-nothing conflicts, zero-attachments success
- **Status:** 🟢 Decided
- **Area:** error-handling
- **Decided on:** 2026-09-01
- **Summary:** Extraction follows PDF name-tree order (deterministic across runs); duplicate names get -1/-2 suffixes; pre-existing files or symlinks at any target name fail the run before anything is written; zero attachments is exit 0 with attachments_extracted=0, flipped to exit 3 NO_ATTACHMENTS by PDFOPS_FAIL_ON_NO_ATTACHMENTS=true.
- **Risk:** medium
- **Reversibility:** cheap
- **Amended by:** [D-021](#D-021) (conflict handling became policy-dependent; order, dedupe, and zero-attachment clauses stand)
- **Where:** [`DESIGN_NOTES.md section 7`](DESIGN_NOTES.md)

<a id="D-016"></a>
### D-016
- **Title:** Extract covers document-level attachments only
- **Status:** 🟢 Decided
- **Area:** pdf-engine
- **Decided on:** 2026-09-01
- **Summary:** Only the document-level /Names/EmbeddedFiles tree is extracted; page-level /FileAttachment annotations (sticky-note attachments) are a documented limitation and future work rather than a half-supported path.
- **Risk:** low
- **Reversibility:** cheap
- **Where:** [`DESIGN_NOTES.md section 7`](DESIGN_NOTES.md)

<a id="D-017"></a>
### D-017
- **Title:** Password channels with a layered, tested no-leak guarantee
- **Status:** 🟢 Decided
- **Area:** security
- **Decided on:** 2026-09-01
- **Summary:** One password via mutually exclusive channels - PDFOPS_PASSWORD_FILE (mounted secret, preferred) or PDFOPS_PASSWORD (discouraged, documented why); parser stays filesystem-free by capturing the source and resolving in one step before dispatch. No-leak is layered: Secret wrapper renders ***, the log layer scrubs registered values incl. tracebacks, the entrypoint deletes secret vars from the live env, and leak tests assert the literal password appears in no output on success, failure, or crash paths.
- **Risk:** high
- **Reversibility:** cheap
- **Supersedes:** [D-013](#D-013)
- **Where:** [`DESIGN_NOTES.md section 8`](DESIGN_NOTES.md)

<a id="D-018"></a>
### D-018
- **Title:** Decrypt semantics: empty-password auto-try, algorithm + password_type logged
- **Status:** 🟢 Decided
- **Area:** pdf-engine
- **Decided on:** 2026-09-01
- **Summary:** The plaintext /Encrypt dictionary yields the algorithm before any password work (logged per input); with no password supplied the spec-standard empty-password verification runs first - a side-effect-free hash check, the same thing every viewer does - so owner-only permissions-locked PDFs just work, and PASSWORD_REQUIRED fires only when the empty try fails. Successful opens log password_type user/owner/empty; a wrong password names the failing input; an unneeded password draws a password_unused warning.
- **Risk:** medium
- **Reversibility:** cheap
- **Where:** [`DESIGN_NOTES.md section 8`](DESIGN_NOTES.md)

<a id="D-019"></a>
### D-019
- **Title:** Output encryption: never|inherit|always tri-state, AES-256, explicit-password fallback
- **Status:** 🟢 Decided
- **Area:** security
- **Decided on:** 2026-09-01
- **Summary:** PDFOPS_OUTPUT_ENCRYPTION: never (default; plaintext output with a loud security_downgrade warning when inputs were encrypted), inherit (encrypt iff any input was encrypted - confidentiality never decreases), always. Output password from its own channel pair, falling back only to an explicitly supplied input password - never the empty auto-try (MISSING_OUTPUT_PASSWORD instead). Output always AES-256 regardless of input schemes; an output password with mode never is a hard error.
- **Risk:** medium
- **Reversibility:** cheap
- **Where:** [`DESIGN_NOTES.md section 8`](DESIGN_NOTES.md)

<a id="D-020"></a>
### D-020
- **Title:** Retryability contract: exit codes stay 0-6, retry guidance is documentation
- **Status:** 🟢 Decided
- **Area:** error-handling
- **Decided on:** 2026-09-01
- **Summary:** No 10+ transient exit-code band: the 0-6 map is a published API and nearly every failure class is deterministic, so retryability lives in the README - a per-code table (exit 1 the only default-retryable, DISK_FULL the judgment call) and an Argo retryStrategy.expression snippet, paired with PDFOPS_ON_EXISTS=skip for at-least-once safety.
- **Risk:** medium
- **Reversibility:** expensive
- **Supersedes:** [D-006](#D-006)
- **Where:** [`DESIGN_NOTES.md section 9`](DESIGN_NOTES.md)

<a id="D-021"></a>
### D-021
- **Title:** PDFOPS_ON_EXISTS tri-state: merge whole-run skip, extract per-file completion
- **Status:** 🟢 Decided
- **Area:** reliability
- **Decided on:** 2026-09-01
- **Summary:** fail (default) refuses; overwrite replaces atomically; skip treats existing output as completed prior work - merge short-circuits without reading inputs, extract writes only missing attachments (sound because every written file is atomic and therefore whole). Stale temp debris matching the run's own targets is removed at startup under a documented single-writer-per-output assumption.
- **Risk:** medium
- **Reversibility:** cheap
- **Amends:** [D-015](#D-015)
- **Where:** [`DESIGN_NOTES.md section 9`](DESIGN_NOTES.md)

---

## Architectural Decision Records (Full Analysis)

ADRs carry a dual ID - `D-###` (master register) and `ADR-###` (ADR-specific). ADR sections contain full Context / Decision / Alternatives Considered / Consequences analysis. ADR numbering starts at `ADR-001`.

_(none yet)_

---

## Framework Refinement Backlog

Sustainability improvements to the decision tracking framework itself. Add new entries as `FR-01`, `FR-02`, etc. Numbering is append-only and retained even after items are applied.

_(none yet)_
