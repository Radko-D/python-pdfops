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
| 2 | invalid configuration | `MISSING_VAR`, `INVALID_OPERATION`, `INVALID_LOG_LEVEL`, `INVALID_FLAG`, `UNKNOWN_VAR`, `INAPPLICABLE_VAR`, `INVALID_INPUTS`, `DUPLICATE_INPUTS` |
| 3 | input missing/unreadable | `INPUT_MISSING`, `INPUT_IS_DIRECTORY`, `INPUT_UNREADABLE`, `NO_ATTACHMENTS` (opt-in strict flag only) |
| 4 | invalid/corrupt/unprocessable PDF | `NOT_A_PDF`, `CORRUPT_PDF`, `UNSUPPORTED_PDF_FEATURE` (e.g. a stream filter the build cannot decode) |
| 5 | password | `PASSWORD_REQUIRED`, `WRONG_PASSWORD`, `UNSUPPORTED_ENCRYPTION` (with password support) |
| 6 | output | `OUTPUT_EXISTS`, `OUTPUT_DIR_MISSING`, `OUTPUT_NOT_WRITABLE`, `DISK_FULL` |

Rationale for separating 3 from 4: a missing input may be a transient mount/ordering issue
(plausibly retryable); a corrupt PDF is permanent (retrying is pure waste). The distinction is
exactly what an Argo `retryStrategy.expression` needs. Open point (deferred, [D-006](DECISIONS.md#D-006)):
a dedicated `10+` transient band versus keeping 1 as the only maybe-retryable code.

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
`traceback`). The human-readable text lives in `error_message`; `event` stays greppable.

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
`detail` and the emitting logger in `source`. The secret-redaction filter lands in this
layer together with password support.

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
- **Encrypted inputs are refused, not mangled ([D-013](DECISIONS.md#D-013)).** Until
  password support lands, an encrypted input maps to exit 5 (`PASSWORD_REQUIRED`, or
  `UNSUPPORTED_ENCRYPTION` when pypdf needs the missing AES backend) rather than
  masquerading as a corrupt file - the operator's fix (supply a password / wait for the
  feature) is entirely different from the fix for a broken file.

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
This invariant is what any retry/overwrite policy can safely build on. An existing output
is refused (`OUTPUT_EXISTS`) until the configurable overwrite/skip policy lands with the
retry-semantics work; a missing output directory is refused rather than created - output
locations are mounts, and a missing mount is a workflow bug worth failing loudly on.

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
