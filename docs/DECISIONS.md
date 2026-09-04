# Architectural Decision Records: pdf-ops

> **Project:** Containerized PDF operations (merge, extract attachments) for workflow systems
> **Started:** 2026-08-31
> **Last updated:** 2026-09-04

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
| [`D-007`](#D-007) | 🟢 | config | PDFOPS_INPUTS list separator | 2026-09-03 | Settled (2026-09-03, deferred since 2026-08-31): os.pathsep (colon) with explicit ordered paths and no globs stands. It survived the container suite, the deployment example, and every walkthrough; colon-in-path never materialized and is pathological for mounted paths anyway (documented limitation). Alternatives (comma, newline, JSON array) rejected as churn without a driving case. | [`DESIGN_NOTES.md section 3`](DESIGN_NOTES.md) | - |
| [`D-008`](#D-008) | 🟢 | config | Operation value case strictness | 2026-09-03 | Settled (2026-09-03, deferred since 2026-08-31): strict lowercase merge/extract (whitespace tolerated) stands. Operation values come from workflow templates, not humans typing - case tolerance would add contract surface without value, and the error message already names the accepted values. | [`DESIGN_NOTES.md section 3`](DESIGN_NOTES.md) | - |
| [`D-009`](#D-009) | 🟢 | config | Unknown PDFOPS_* variable hard rejection | 2026-09-03 | Settled (2026-09-03, deferred since 2026-08-31): hard rejection (exit 2 UNKNOWN_VAR) stands. The revisit trigger - a platform injecting foreign PDFOPS_* variables - was tested by writing the deployment example, which injects none; typo protection keeps outweighing a hypothetical soft mode. | [`DESIGN_NOTES.md section 3`](DESIGN_NOTES.md) | - |
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
| [`D-022`](#D-022) | 🟢 | reliability | Output files honor the process umask, not mkstemp's 0600 | 2026-09-02 | atomic_output re-chmods its temp file to 0666 & ~umask at creation: mkstemp's private 0600 would ride through os.replace onto the published output, leaving it unreadable by a downstream step running as a different UID on a shared volume. Invisible under Docker Desktop's ownership-mapping mounts, real on native Linux bind mounts - caught by CI on the first Linux-host run. | [`DESIGN_NOTES.md section 6`](DESIGN_NOTES.md) | - |
| [`D-023`](#D-023) | 🟢 | pdf-engine | Engine swapped to pikepdf; pypdf demoted to dev-dependency test oracle | 2026-09-02 | engine_pikepdf.py (qpdf-backed) replaces engine_pypdf.py as the runtime engine, executing the D-002 plan: better large-file and corrupt-input behavior, native AES-256 (R=6 pinned). password_type user/owner/empty reporting survives via qpdf's password-matched flags; qpdf repairs light damage pypdf refused (pinned as behavior; warnings surface as events - at open via OpenedInput.warnings, after lazy reads/writes via collect_warnings); duplicate attachment names preserved by walking /Names/EmbeddedFiles directly with cycle and type guards (hostile shapes degrade or classify as data problems, never exit 1); the merged output is saved through the atomic layer's open temp file, keeping the single-temp cleanup contract; failed-open algorithm labels come from a best-effort raw /Encrypt scan. pypdf stays in the dev group building fixtures and verifying outputs - every test is a cross-library check. | [`DESIGN_NOTES.md section 1`](DESIGN_NOTES.md) | - |
| [`D-024`](#D-024) | 🟢 | security | Secrets stay stdlib, consolidated into one module | 2026-09-03 | All secret handling (Secret wrapper, EnvSecret/FileSecret source refs with resolve()/describe(), Secrets bundle, scrub registration) consolidated into secrets.py; config.py only parses which source is configured. Shelf options evaluated and rejected: pydantic SecretStr (compiled dependency for one masked-repr class), pydantic-settings (config-layer rewrite; secrets_dir expects field-named files in a fixed directory - a different contract from PDFOPS_PASSWORD_FILE=<any path>; ValidationError would need retranslation into the error_code taxonomy), scanner-style log redactors (pattern heuristics, weaker than the exact-value field-restricted scrub that avoids the password-oracle problem). | [`DESIGN_NOTES.md section 8`](DESIGN_NOTES.md) | - |
| [`D-025`](#D-025) | 🟢 | container | Hardened runtime image: digest-pinned multi-stage build, read-only rootfs | 2026-09-03 | The image is a two-stage build: a digest-pinned uv stage resolves the lockfile into a self-contained virtualenv with compiled bytecode; the runtime stage (digest-pinned python:3.14-slim) carries only that venv, uninstalls the base image's pip, removes stdlib ensurepip (its bundled wheel would restore pip in one command), and runs as fixed non-root UID 10001. Read-only root filesystem is proven by a container test running the golden merge under --read-only --cap-drop ALL --security-opt no-new-privileges (all writes land in the output mount by design). deploy/argo-example.yaml ships the full posture incl. fsGroup, secret-mounted password, a retry expression covering exit 1 plus pod-level Error nodes (which carry no exit code), and memory sized by the measured input+128MB rule. Distroless bases considered and not taken: pinned slim minus pip reaches most of the value while staying debuggable. | [`DESIGN_NOTES.md section 11`](DESIGN_NOTES.md) | - |
| [`D-026`](#D-026) | 🟢 | infra | One uv-locked toolchain with SHA-pinned, Dependabot-watched CI | 2026-09-04 | pre-commit runs ruff and pyright as local hooks through uv run --locked, so hooks, CI and a developer's shell all resolve the single version pinned in uv.lock (the remote-hook revs had drifted behind the lock). CI runs with a read-only token, per-ref concurrency, job timeouts and actions pinned to full commit SHAs; uv sync --locked replaces --frozen. scripts/ and docs/scripts/ join the ruff and pyright gates - the bare 'scripts' exclude had silently covered both, leaving the CI-run decision validator unlinted; the widened rule set (SIM, PTH, PIE, RET, PERF, FURB, N; ASYNC dropped, no async code exists) surfaced nine findings, fixed in place, and pyright now reports ignore comments that suppress nothing. Dependabot watches the three pinned surfaces weekly: the uv lockfile, the actions, the Docker digests. | [`DESIGN_NOTES.md section 12`](DESIGN_NOTES.md) | - |

**Counts:** 26 total decisions - 23 🟢 decided, 0 🟡 pending, 0 ⏸ deferred, 2 🔵 superseded.

### Index by area

> **Note:** these counts are recomputable from the master register `area` column. If the count and the IDs list disagree, the IDs list is authoritative. [`scripts/validate_decisions.py`](scripts/validate_decisions.py) recomputes both on every run and CI-fails on drift.

| Area | Count | IDs |
|---|---|---|
| error-handling | 5 | D-003, D-006, D-012, D-015, D-020 |
| config | 4 | D-004, D-007, D-008, D-009 |
| pdf-engine | 5 | D-002, D-011, D-016, D-018, D-023 |
| security | 5 | D-013, D-014, D-017, D-019, D-024 |
| reliability | 3 | D-010, D-021, D-022 |
| observability | 1 | D-005 |
| container | 1 | D-025 |
| project | 1 | D-001 |
| infra | 1 | D-026 |
| **Total** | **26** | |

### Open decisions (🟡 Pending + ⏸ Deferred)

| ID | Status | Owner / Trigger |
|---|---|---|
| _(none)_ | | |

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
- **Status:** 🟢 Decided
- **Area:** config
- **Decided on:** 2026-09-03
- **Summary:** Settled (2026-09-03, deferred since 2026-08-31): os.pathsep (colon) with explicit ordered paths and no globs stands. It survived the container suite, the deployment example, and every walkthrough; colon-in-path never materialized and is pathological for mounted paths anyway (documented limitation). Alternatives (comma, newline, JSON array) rejected as churn without a driving case.
- **Risk:** low
- **Reversibility:** expensive
- **Where:** [`DESIGN_NOTES.md section 3`](DESIGN_NOTES.md)

<a id="D-008"></a>
### D-008
- **Title:** Operation value case strictness
- **Status:** 🟢 Decided
- **Area:** config
- **Decided on:** 2026-09-03
- **Summary:** Settled (2026-09-03, deferred since 2026-08-31): strict lowercase merge/extract (whitespace tolerated) stands. Operation values come from workflow templates, not humans typing - case tolerance would add contract surface without value, and the error message already names the accepted values.
- **Risk:** low
- **Reversibility:** cheap
- **Where:** [`DESIGN_NOTES.md section 3`](DESIGN_NOTES.md)

<a id="D-009"></a>
### D-009
- **Title:** Unknown PDFOPS_* variable hard rejection
- **Status:** 🟢 Decided
- **Area:** config
- **Decided on:** 2026-09-03
- **Summary:** Settled (2026-09-03, deferred since 2026-08-31): hard rejection (exit 2 UNKNOWN_VAR) stands. The revisit trigger - a platform injecting foreign PDFOPS_* variables - was tested by writing the deployment example, which injects none; typo protection keeps outweighing a hypothetical soft mode.
- **Risk:** low
- **Reversibility:** cheap
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
- **Amended by:** [D-022](#D-022) (temp-file mode: published outputs honor the umask instead of inheriting mkstemp's 0600)
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

<a id="D-022"></a>
### D-022
- **Title:** Output files honor the process umask, not mkstemp's 0600
- **Status:** 🟢 Decided
- **Area:** reliability
- **Decided on:** 2026-09-02
- **Summary:** atomic_output re-chmods its temp file to 0666 & ~umask at creation: mkstemp's private 0600 would ride through os.replace onto the published output, leaving it unreadable by a downstream step running as a different UID on a shared volume. Invisible under Docker Desktop's ownership-mapping mounts, real on native Linux bind mounts - caught by CI on the first Linux-host run.
- **Risk:** low
- **Reversibility:** cheap
- **Amends:** [D-010](#D-010)
- **Where:** [`DESIGN_NOTES.md section 6`](DESIGN_NOTES.md)

<a id="D-023"></a>
### D-023
- **Title:** Engine swapped to pikepdf; pypdf demoted to dev-dependency test oracle
- **Status:** 🟢 Decided
- **Area:** pdf-engine
- **Decided on:** 2026-09-02
- **Summary:** engine_pikepdf.py (qpdf-backed) replaces engine_pypdf.py as the runtime engine, executing the D-002 plan: better large-file and corrupt-input behavior, native AES-256 (R=6 pinned). password_type user/owner/empty reporting survives via qpdf's password-matched flags; qpdf repairs light damage pypdf refused (pinned as behavior; warnings surface as events - at open via OpenedInput.warnings, after lazy reads/writes via collect_warnings); duplicate attachment names preserved by walking /Names/EmbeddedFiles directly with cycle and type guards (hostile shapes degrade or classify as data problems, never exit 1); the merged output is saved through the atomic layer's open temp file, keeping the single-temp cleanup contract; failed-open algorithm labels come from a best-effort raw /Encrypt scan. pypdf stays in the dev group building fixtures and verifying outputs - every test is a cross-library check.
- **Risk:** medium
- **Reversibility:** cheap
- **Where:** [`DESIGN_NOTES.md section 1`](DESIGN_NOTES.md)

<a id="D-024"></a>
### D-024
- **Title:** Secrets stay stdlib, consolidated into one module
- **Status:** 🟢 Decided
- **Area:** security
- **Decided on:** 2026-09-03
- **Summary:** All secret handling (Secret wrapper, EnvSecret/FileSecret source refs with resolve()/describe(), Secrets bundle, scrub registration) consolidated into secrets.py; config.py only parses which source is configured. Shelf options evaluated and rejected: pydantic SecretStr (compiled dependency for one masked-repr class), pydantic-settings (config-layer rewrite; secrets_dir expects field-named files in a fixed directory - a different contract from PDFOPS_PASSWORD_FILE=<any path>; ValidationError would need retranslation into the error_code taxonomy), scanner-style log redactors (pattern heuristics, weaker than the exact-value field-restricted scrub that avoids the password-oracle problem).
- **Risk:** low
- **Reversibility:** cheap
- **Where:** [`DESIGN_NOTES.md section 8`](DESIGN_NOTES.md)

<a id="D-025"></a>
### D-025
- **Title:** Hardened runtime image: digest-pinned multi-stage build, read-only rootfs
- **Status:** 🟢 Decided
- **Area:** container
- **Decided on:** 2026-09-03
- **Summary:** The image is a two-stage build: a digest-pinned uv stage resolves the lockfile into a self-contained virtualenv with compiled bytecode; the runtime stage (digest-pinned python:3.14-slim) carries only that venv, uninstalls the base image's pip, removes stdlib ensurepip (its bundled wheel would restore pip in one command), and runs as fixed non-root UID 10001. Read-only root filesystem is proven by a container test running the golden merge under --read-only --cap-drop ALL --security-opt no-new-privileges (all writes land in the output mount by design). deploy/argo-example.yaml ships the full posture incl. fsGroup, secret-mounted password, a retry expression covering exit 1 plus pod-level Error nodes (which carry no exit code), and memory sized by the measured input+128MB rule. Distroless bases considered and not taken: pinned slim minus pip reaches most of the value while staying debuggable.
- **Risk:** low
- **Reversibility:** cheap
- **Where:** [`DESIGN_NOTES.md section 11`](DESIGN_NOTES.md)

<a id="D-026"></a>
### D-026
- **Title:** One uv-locked toolchain with SHA-pinned, Dependabot-watched CI
- **Status:** 🟢 Decided
- **Area:** infra
- **Decided on:** 2026-09-04
- **Summary:** pre-commit runs ruff and pyright as local hooks through uv run --locked, so hooks, CI and a developer's shell all resolve the single version pinned in uv.lock (the remote-hook revs had drifted behind the lock). CI runs with a read-only token, per-ref concurrency, job timeouts and actions pinned to full commit SHAs; uv sync --locked replaces --frozen. scripts/ and docs/scripts/ join the ruff and pyright gates - the bare 'scripts' exclude had silently covered both, leaving the CI-run decision validator unlinted; the widened rule set (SIM, PTH, PIE, RET, PERF, FURB, N; ASYNC dropped, no async code exists) surfaced nine findings, fixed in place, and pyright now reports ignore comments that suppress nothing. Dependabot watches the three pinned surfaces weekly: the uv lockfile, the actions, the Docker digests.
- **Risk:** low
- **Reversibility:** cheap
- **Where:** [`DESIGN_NOTES.md section 12`](DESIGN_NOTES.md)

---

## Architectural Decision Records (Full Analysis)

ADRs carry a dual ID - `D-###` (master register) and `ADR-###` (ADR-specific). ADR sections contain full Context / Decision / Alternatives Considered / Consequences analysis. ADR numbering starts at `ADR-001`.

_(none yet)_

---

## Framework Refinement Backlog

Sustainability improvements to the decision tracking framework itself. Add new entries as `FR-01`, `FR-02`, etc. Numbering is append-only and retained even after items are applied.

_(none yet)_
