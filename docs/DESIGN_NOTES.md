# Design Notes - pdf-ops

> Working notes behind the entries in [`DECISIONS.md`](DECISIONS.md). These sections accumulate
> as the project iterates and are distilled into the final 1-2 page `DESIGN.md` deliverable.

---

## 1. PDF engine strategy (per [D-002](DECISIONS.md#D-002))

**Decision:** start with `pypdf` behind a narrow engine seam; swap the engine to `pikepdf`
before the large-file/robustness hardening work; after the swap `pypdf` is demoted to a
dev-dependency test oracle. `PyMuPDF` is rejected outright.

Verified facts (researched 2026-08-31; every candidate fully supports Python 3.14 today):

- **pypdf 6.16.2** - BSD-3-Clause, pure Python (`py3-none-any`), richest attachments API
  (list-valued: faithful to duplicate attachment names), reports which password matched
  (user vs owner). Weaknesses: documented multi-GB memory blowups on pathological merges,
  no repair path for damaged files, AES needs the `[crypto]` extra.
- **pikepdf 10.12.0** - MPL-2.0, C++ qpdf backend, cp314-abi3 wheels bundling qpdf (no
  compiler, no apt packages on `python:3.14-slim`). Far better large-file memory behavior,
  robust corrupt-file detection, AES-256 read and write. Gap: `Pdf.attachments` is a Mapping,
  collapsing duplicate attachment names - the swap will walk `/Names/EmbeddedFiles` directly.
- **PyMuPDF** - technically the most capable single library, **rejected on licensing, not
  capability**: AGPL-3.0-or-later (or paid Artifex commercial license). Shipping an AGPL
  container image as a workflow step is a licensing exposure this project does not accept.
- **qpdf CLI** - Apache-2.0; not a primary engine (subprocess error mapping is a second
  failure surface) but kept in mind as a test oracle (`qpdf --check`) and as the only tool
  with native attachment-preserving merge (`--copy-attachments-from`).

**Why start-then-swap rather than picking one:** pypdf's pure-Python profile gives the
fastest, lowest-risk start for the core operations; pikepdf is the right production engine
for the resource-behavior and corrupt-input quality dimensions. Keeping the engine behind
one seam (`engine.py`) makes the swap a single-module change and forces library exceptions
to be translated into the application taxonomy in exactly one place.

## 2. Exit-code taxonomy (per [D-003](DECISIONS.md#D-003))

The process exit code is the application's external API toward the workflow engine. Classes,
not fine-grained codes - workflow engines branch on codes, and codes are a scarce, stable
namespace. Fine granularity travels as machine-readable `error_code` strings in the terminal
JSON event.

| Code | Class | Examples (`error_code`) |
|---|---|---|
| 0 | success | includes zero-attachments extraction under the default policy |
| 1 | unexpected internal error | `UNEXPECTED_ERROR` (bug or unhandled condition; traceback logged) |
| 2 | invalid configuration | `MISSING_VAR`, `INVALID_OPERATION`, `INVALID_LOG_LEVEL`, `INVALID_FLAG`, `UNKNOWN_VAR`, `INAPPLICABLE_VAR`, `INVALID_INPUTS`, `DUPLICATE_INPUTS`, `CONFLICTING_PASSWORD_SOURCES`, `PASSWORD_FILE_UNREADABLE`, `EMPTY_PASSWORD`, `INVALID_OUTPUT_ENCRYPTION`, `OUTPUT_PASSWORD_WITHOUT_ENCRYPTION`, `MISSING_OUTPUT_PASSWORD`, `INVALID_ON_EXISTS` |
| 3 | input missing/unreadable | `INPUT_MISSING`, `INPUT_IS_DIRECTORY`, `INPUT_UNREADABLE`, `NO_ATTACHMENTS` (opt-in strict flag only) |
| 4 | invalid/corrupt/unprocessable PDF | `NOT_A_PDF`, `CORRUPT_PDF`, `UNSUPPORTED_PDF_FEATURE` (e.g. a stream filter the build cannot decode) |
| 5 | password | `PASSWORD_REQUIRED`, `WRONG_PASSWORD`, `UNSUPPORTED_ENCRYPTION` |
| 6 | output | `OUTPUT_EXISTS`, `OUTPUT_DIR_MISSING`, `OUTPUT_IS_DIRECTORY`, `OUTPUT_NOT_WRITABLE`, `DISK_FULL` |

Rationale for separating 3 from 4: a missing input may be a transient mount/ordering issue
(plausibly retryable); a corrupt PDF is permanent (retrying is pure waste). The distinction is
exactly what an Argo `retryStrategy.expression` needs. The once-open question of a
dedicated `10+` transient band was resolved with the retry-semantics work
([D-020](DECISIONS.md#D-020), superseding [D-006](DECISIONS.md#D-006)): the map stays
0-6 - it is a published API two iterations deep, nearly every failure class here is
deterministic, and retryability is better expressed as documentation the operator
composes (README's per-code table + retryStrategy expression) than as more codes.

## 3. Environment-variable contract (per [D-004](DECISIONS.md#D-004))

Conventions:

- Prefix `PDFOPS_`; operation values are lowercase `merge` / `extract` (strict; surrounding
  whitespace tolerated because templated env values often carry it).
- Configuration is parsed and validated **entirely before any file is touched** - a pure
  function over a `Mapping[str, str]`, so tests drive it with plain dicts and `os.environ`
  is referenced only in `__main__`. The parser is deliberately filesystem-free: whether a
  path exists is an operation-stage question, not a configuration one.
- **Unknown `PDFOPS_*` variables are rejected** (exit 2, `UNKNOWN_VAR`): a silently ignored
  misspelling (`PDFOPS_OPERATOIN=...`) would otherwise surface as a confusing downstream error
  or, worse, silently wrong behavior. The registry of known variables grows as features land.
  The same logic rejects variables that don't apply to the selected operation
  (`INAPPLICABLE_VAR`) - merge vars on an extract run are the same class of templating bug.
- Missing and empty values are treated identically (`MISSING_VAR`) - an empty value almost
  always means a broken template substitution upstream.
- `PDFOPS_INPUTS` is an **explicit ordered list** (`os.pathsep`-separated - the `PATH`
  convention; see deferred [D-007](DECISIONS.md#D-007)). No glob support, deliberately:
  merge order must be explicit, not lexicographic luck, or retries and re-runs can produce
  different documents. Duplicates are rejected (`DUPLICATE_INPUTS`). A single input is
  allowed - workflows fan in variable-length lists that can be of length one.

## 4. Observability (per [D-005](DECISIONS.md#D-005))

One JSON object per line on stdout; the workflow engine captures stdout as the step log.
Stdlib `logging` with a ~40-line formatter - no structlog/OTel dependency, which would add
concepts with zero payoff for a run-once batch container.

Event schema: `ts` (ISO-8601 UTC), `level`, `event` (stable machine token: `config_loaded`,
`operation_started`, `merge_written`, `attachment_extracted`, `operation_complete`,
`operation_failed`, `pdf_library_message`), plus event-specific fields (`operation`,
`pages`, `bytes_written`, `output_path`, `attachments_extracted`, `attachment`,
`original_name`, `error_code`, `error_message`, `exit_code`, `context`, `exc_type`,
`traceback`; password work adds `input_opened`, `password_unused`, `security_downgrade`,
`output_encrypted` - see section 8; retry work adds `output_skipped`, `output_overwritten`,
`attachments_skipped`, `stale_temp_removed`, and `duration_s` on terminal events - see
section 9). The human-readable text lives in `error_message`; `event` stays greppable.

A single error boundary in `main.run()` produces exactly one terminal event per run -
`operation_complete` or `operation_failed` - so an operator can alert on
`event=operation_failed` alone. **Terminal events are exempt from `PDFOPS_LOG_LEVEL`
filtering** (emitted via `Logger.handle`, which skips the level check): the level tunes
lifecycle/diagnostic verbosity, but the completion signal must never be silenceable -
at `PDFOPS_LOG_LEVEL=error` a successful run still emits its one `operation_complete`
line. (Caught in review: the naive `logger.info` emission made a successful run at
`warning`/`error` produce zero output.)

The library's own log output is part of the contract too: pypdf logs recoverable-corruption
warnings ("Object 9 0 not defined") through its own logger, which would otherwise fall
through to `logging.lastResort` and print plain text on **stderr** - breaking the
JSON-only/empty-stderr contract on inputs that merge *successfully*. `setup_logging`
therefore routes the `pypdf` logger (and Python warnings, via `logging.captureWarnings`)
into the same stdout JSON stream as `event=pdf_library_message` with the original text in
`detail` and the emitting logger in `source`. The same layer scrubs registered secret
values from every record - see section 8.

## 5. Engine seam (per [D-002](DECISIONS.md#D-002), [D-011](DECISIONS.md#D-011))

`engine.py` defines the Protocol (`merge(inputs, destination) -> MergeStats` and
`list_attachments(source) -> list[Attachment]`) and the `get_engine()` factory - the single
swap point. `engine_pypdf.py` is the only module
that imports pypdf and translates its failure modes into the application taxonomy. Readers
are opened - and their page trees forced - **before** the writer produces a single byte, so
a corrupt later input aborts the run before any output work.

Two translation subtleties found in review, both worth knowing about pypdf:

- **It leaks builtin exceptions on pathological files.** A PDF with a valid header and xref
  but a catalog missing `/Pages` raises a bare `AttributeError` deep in page-tree
  flattening - not a `PyPdfError`. The engine therefore catches a small set of builtin
  exception types *around pypdf calls only* and classifies them as `CORRUPT_PDF`
  (exit 4); without that, deterministic bad inputs would exit 1 and look retryable.
- **Encryption failures keep the password exit class** (originally
  [D-013](DECISIONS.md#D-013), now superseded by full password support -
  [D-017](DECISIONS.md#D-017), section 8): an undecryptable input maps to exit 5
  (`PASSWORD_REQUIRED`/`WRONG_PASSWORD`/`UNSUPPORTED_ENCRYPTION`) rather than
  masquerading as a corrupt file - the operator's fix for a locked file is entirely
  different from the fix for a broken one.

**Merge is pages-only for now ([D-011](DECISIONS.md#D-011)):** bookmarks/outlines, form
fields, document metadata, and embedded attachments of the *inputs* are not carried into
the merged output. Attachments deserve the loudest flag: no mainstream Python PDF library
copies `/Names/EmbeddedFiles` on a page-level merge, so attachments in merge inputs are
silently dropped - options (detect-and-warn, fail-loud flag, qpdf's
`--copy-attachments-from`) are evaluated when attachment handling is built out.

## 6. Input validation and atomic output (per [D-010](DECISIONS.md#D-010), [D-012](DECISIONS.md#D-012))

**Collect-all validation ([D-012](DECISIONS.md#D-012)):** every input is checked up front
(exists, is a file, readable, starts with `%PDF-`) and *all* problems are reported in one
failure event - an operator fixing a broken workflow learns about every bad input from a
single run, not one per retry. The exit class follows the first problem in input order
(deterministic); the full list travels in `context.problems`.

**Atomic output ([D-010](DECISIONS.md#D-010)):** all output is written to a temp file
created *in the destination directory* - same filesystem, because `os.replace` is only
atomic within one - then fsynced and renamed over the final path in a single step (plus a
directory fsync). The final path either holds a complete PDF or nothing: a failed, killed,
or OOM-ed run never leaves a partial file where a downstream workflow step could glob it.
This invariant is what any retry/overwrite policy can safely build on. Existing outputs
follow the `PDFOPS_ON_EXISTS` policy (section 9); a missing output directory is refused rather
than created - output locations are mounts, and a missing mount is a workflow bug worth
failing loudly on.

## 7. Extract and attachment-name security (per [D-014](DECISIONS.md#D-014), [D-015](DECISIONS.md#D-015), [D-016](DECISIONS.md#D-016))

Extraction's dominant risk is not parsing - it's that **attachment names are
attacker-controlled strings written to a mounted filesystem**. A name like `../../evil.txt`
or `/etc/passwd` would otherwise turn extract into a write-anywhere primitive on whatever
the operator mounted.

**Sanitize-always ([D-014](DECISIONS.md#D-014)):** every name passes through a pure
`sanitize_attachment_name` function - normalize both separator conventions (names written
on Windows carry backslashes), take the basename, strip control characters, cap the byte
length under filesystem NAME_MAX, deterministic `attachment_<n>` fallback when nothing safe
remains. Rejecting whole PDFs for hostile names was considered and dropped: it would break
legitimate extraction, and renaming is lossless (the original name is logged whenever it
changed). Because the function is pure, the whole security behavior is one table-driven
test suite. Defense in depth: the resolved parent of every write target is re-checked to be
the output directory, and a pre-existing symlink at a target name counts as a conflict.

**Semantics ([D-015](DECISIONS.md#D-015)):** duplicate names - which the PDF name tree
permits and real PDFs contain - get deterministic `-1`/`-2` suffixes in name-tree order
(also the extraction order, deterministic across runs). Collisions are detected on
**casefolded** names: the output volume may be case-insensitive (macOS, SMB mounts),
where `Report.txt` and `report.txt` are one file - a naive case-sensitive plan would
silently overwrite the first payload there while reporting both as extracted. Suffixing
on the casefolded key keeps every payload on every filesystem and keeps the plan
byte-identical across platforms. Zero attachments is a success with
`attachments_extracted=0` - it's data-dependent, so the workflow gates on the count -
with `PDFOPS_FAIL_ON_NO_ATTACHMENTS=true` flipping it to exit 3 / `NO_ATTACHMENTS` for
pipelines where an attachment-less input means something upstream broke. Any pre-existing
file at a target name fails the whole run before a single byte is written (all-or-nothing
conflict check); each file is then written via the same atomic temp-and-rename path as
merge. Known limitation: the *set* of files is not transactional - a mid-run crash leaves
a partial set of individually-complete files; a staging-directory handoff is the noted
future fix if a downstream consumer needs all-or-nothing.

**Scope ([D-016](DECISIONS.md#D-016)):** document-level `/Names/EmbeddedFiles` only.
Page-level `/FileAttachment` annotations are a distinct, rarer mechanism (sticky-note
attachments); pypdf's `attachment_list` does not surface them. Documented as a limitation
rather than half-supported.

## 8. Passwords and output encryption (per [D-017](DECISIONS.md#D-017), [D-018](DECISIONS.md#D-018), [D-019](DECISIONS.md#D-019))

**Channels ([D-017](DECISIONS.md#D-017)):** one password, two mutually exclusive sources -
`PDFOPS_PASSWORD_FILE` (a mounted secret, the preferred channel: it never appears in pod
specs, `kubectl describe`, or `/proc/<pid>/environ`) and `PDFOPS_PASSWORD` (kept for local
runs, documented as discouraged). The parser stays filesystem-free: it captures the
*source*; the file is read in one resolution step before dispatch, so unreadable/empty
secret files still classify as configuration errors.

**The no-leak guarantee is layered, and tested rather than promised:**

1. *By construction*: the `Secret` wrapper renders as `***` through `repr`/`str`/f-strings;
   the raw value is reachable only via an explicit accessor called in exactly one module
   (the engine).
2. *Defense in depth*: the logging layer scrubs registered secret values (and their
   repr-escaped spellings) from the **free-text fields** of every record - `traceback`,
   `detail`, `error_message`, `context` - longest secret first so overlapping values
   can't leave partial reveals. Code-controlled token fields (`event`, `error_code`,
   `operation`, ...) are deliberately exempt: workflow engines branch on them, and
   rewriting known constants would itself disclose the password (a log reader seeing
   `***_written` where `merge_written` belongs learns the password is "merge").
   Secrets shorter than 4 characters are not scrubbed (they'd shred the free text
   without adding protection) - flagged with a `redaction_degraded` warning.
3. *Process hygiene*: the entrypoint snapshots the environment and deletes the secret
   variables from the live process env before any work - child processes and later
   readers see nothing, though the initial environment block remains visible to
   `/proc/<pid>/environ` and `docker inspect`, which is precisely why the file channel
   is the preferred one. Password *files* must be valid UTF-8 (a binary file is refused
   without echoing any of its bytes), and passwords containing control characters are
   rejected outright - they're encoding accidents, and downstream cryptographic
   normalization would otherwise warn about them naming the exact codepoint.
4. *Proof*: leak tests run success, wrong-password, and crash-with-secret-in-exception
   scenarios and assert the literal password appears nowhere in any captured output.

**Decrypt semantics ([D-018](DECISIONS.md#D-018)):** the `/Encrypt` dictionary is
plaintext, so each `input_opened` event reports the algorithm (RC4-40/128, AES-128,
AES-256) before any password work. When no password is supplied, the spec-standard
empty-password verification runs first - a pure hash computation with no side effects,
and exactly what every PDF viewer does on open - so the extremely common owner-only
"permissions-locked" files just work; `PASSWORD_REQUIRED` fires only when the empty try
fails. The same courtesy applies when a password *was* supplied but doesn't fit a given
input: the empty try still runs before `WRONG_PASSWORD`, so a merge mixing user-locked
and permissions-locked files needs only the one real password. An encryption scheme the
build can't process at all (certificate security handlers, exotic revisions) classifies
as `UNSUPPORTED_ENCRYPTION` - exit 5, not a corrupt-file 4: the remedy is different. pypdf's `decrypt()` reports failure through its *return value*, not an exception -
the explicit check is load-bearing, and its result also yields the logged
`password_type` (`user`/`owner`/`empty`). A password that fits one merge input but not
another fails naming the input, never echoing the password. A supplied password with no
encrypted input draws a `password_unused` warning.

**Output encryption ([D-019](DECISIONS.md#D-019)):** `PDFOPS_OUTPUT_ENCRYPTION` is a
tri-state. `never` (default) keeps plaintext output but emits a `security_downgrade`
warning when encrypted inputs flowed in - visible, never silent. `inherit` encrypts the
output iff any input was encrypted, encoding "confidentiality never decreases through
this step" without per-workflow thought. `always` encrypts unconditionally and fails at
config parse if no password exists anywhere. The output password comes from its own
channel pair, falling back to the *explicitly supplied* input password - never the empty
auto-try, which carries no real secret (an empty-password lock is a lock made of paper);
that gap is a fail-fast `MISSING_OUTPUT_PASSWORD`. Output encryption is always **AES-256**
regardless of input schemes (pypdf's write default is legacy RC4 - passed explicitly), so
an RC4-locked input under `inherit` comes out upgraded. An output password supplied while
the mode is `never` is a hard error, same philosophy as the unknown-var check. Honest
caveat for the design doc: the fallback means input and output share a secret - right for
re-locking same-owner documents; cross-tenant pipelines should set
`PDFOPS_OUTPUT_PASSWORD_FILE` explicitly.

## 9. Retry semantics and the existing-output policy (per [D-020](DECISIONS.md#D-020), [D-021](DECISIONS.md#D-021))

Workflow engines are at-least-once: a pod can vanish after the work succeeded, and the
retry must be predictable. Atomic writes are the foundation - the final path holds a
complete file or nothing - and `PDFOPS_ON_EXISTS` builds the policy on top:

- **`fail`** (default): refuse, exit 6. Retry-friendliness is opt-in; silent clobbering
  never is.
- **`overwrite`**: replace atomically, with an `output_overwritten` event. Serves
  reprocessing pipelines.
- **`skip`**: the idempotency mode. For merge, an existing output short-circuits the
  whole run - exit 0, `skipped: true`, and the inputs are not even read, so a retry
  after success still succeeds when upstream artifacts are already gone. For extract,
  per-file completion: existing files are skipped (each was written atomically, so it is
  whole), only missing ones are written - a crashed run's partial set gets *finished* by
  the retry rather than refused. Reported as `attachments_extracted` +
  `attachments_skipped`.

Both `skip` modes trust an existing file as completed prior output - the deliberate
[D-010](DECISIONS.md#D-010) tradeoff (a checksum-verified skip remains future work).

**Stale-temp cleanup:** a run killed mid-write leaves `.name.<rand>.tmp` debris. At
startup, temp files matching *this run's own target names* are removed
(`stale_temp_removed`). The narrow scope is deliberate: it encodes the single-writer-
per-output-path assumption (guaranteed by workflow engines per step) while making it
impossible to touch another step's files.

**Retryability ([D-020](DECISIONS.md#D-020)):** exit codes stay 0-6 - no transient band.
The README documents per-code retryability (exit 1 the only default-retryable;
`DISK_FULL` the judgment call) plus the Argo `retryStrategy.expression` snippet, paired
with `PDFOPS_ON_EXISTS=skip` so a retry after a lost-but-successful pod is a free no-op.
Terminal events now carry `duration_s` for operator dashboards.

**Filesystem edge semantics, decided in review:** a *directory* at an output path is
refused under every policy (`OUTPUT_IS_DIRECTORY`, exit 6) - it can be neither skipped
as completed work nor atomically replaced. A *dangling symlink* is debris, not completed
work: `skip` falls through and produces the output (the rename replaces the link itself,
never writing through it), while a live symlink target counts as existing. The
stale-temp matcher compares names **literally**, never as glob patterns - attachment
names are attacker-supplied, and a name like `b[1].txt` must not widen the match onto
another target's temps - and a run's own planned outputs are structurally excluded from
cleanup, which happens entirely before the first write. Merge's `skip` short-circuit
reads nothing at all: not the inputs, and not the mounted password file (secrets resolve
lazily, after the skip decision).
