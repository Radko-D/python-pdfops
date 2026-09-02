# Design - pdf-ops

*The short version of [`DESIGN_NOTES.md`](DESIGN_NOTES.md) and the decision register
([`DECISIONS.md`](DECISIONS.md)); D-### references point at individual decisions.*

## Shape

pdf-ops is a single step for a workflow engine (Argo Workflows or similar): **exactly
one operation per container run** - merge N PDFs into one, or extract a PDF's embedded
attachments - configured only by `PDFOPS_*` environment variables, with mounted volumes
carrying inputs and outputs. Three consequences of that shape drive the design:

- **The exit code is the external API.** Engines branch on exit codes, so the taxonomy
  is small, class-based, and frozen (0-6); fine granularity travels as machine-readable
  `error_code` strings in the log rather than as more codes ([D-003](DECISIONS.md#D-003),
  [D-020](DECISIONS.md#D-020)).
- **Logs are the operator interface.** stdout is JSON-lines and stderr stays empty; every
  run ends with exactly one terminal event (`operation_complete`/`operation_failed`)
  that log-level filtering can never suppress - the engine can always branch on the last
  line ([D-005](DECISIONS.md#D-005)).
- **Steps retry at-least-once.** A pod can vanish after its work succeeded, so every
  output is written atomically and idempotency is an explicit policy
  (`PDFOPS_ON_EXISTS`), never an accident ([D-010](DECISIONS.md#D-010),
  [D-020](DECISIONS.md#D-020)).

## Architecture

Small modules with one-way dependencies:

| Module | Responsibility |
|---|---|
| `config.py` | `parse_config(env)` - pure function over a `Mapping`, filesystem-free; every configuration error surfaces before any file is touched |
| `errors.py` | the exit-code taxonomy and `error_code` vocabulary |
| `main.py` | `run(env) -> int` - the single error boundary; emits the one terminal event |
| `engine.py` | the `PdfEngine` Protocol - the library swap seam |
| `engine_pypdf.py` | the **only** module importing pypdf; translates its failure modes into the taxonomy |
| `merge.py` / `extract.py` | orchestration: validate everything, then write |
| `output.py` | atomic writes, existing-output policy, stale-temp cleanup |
| `logging_setup.py` / `secret.py` | JSON formatter, secret scrubbing, third-party log routing; the `Secret` wrapper |

Cross-cutting rules: unknown or operation-inapplicable `PDFOPS_*` variables are hard
errors - a silently ignored misspelling becomes a confusing downstream failure
([D-004](DECISIONS.md#D-004)). All inputs are validated up front and *every* problem is
reported in one failure event ([D-012](DECISIONS.md#D-012)). Output goes to a temp file
in the destination directory (same filesystem - `os.replace` is only atomic within
one), fsynced, then renamed: the final path holds a complete file or nothing.

## PDF library

**pypdf today, pikepdf next, behind the seam ([D-002](DECISIONS.md#D-002)).** pypdf
(BSD-3) is pure Python with the richest attachments API - list-valued, faithful to
duplicate names - and reports which password matched; its weaknesses are large-file
memory behavior and no repair path for damaged files. pikepdf (MPL-2.0, qpdf-backed,
self-contained wheels) is the stronger production engine on exactly those axes, but its
attachments mapping collapses duplicate names, so the swap walks the
`/Names/EmbeddedFiles` name tree directly. PyMuPDF was rejected on licensing, not
capability: shipping an AGPL container image as a workflow step is an exposure this
project does not accept. Because all library exceptions are translated in one module,
the swap is a single-module change, and pypdf then stays as a dev-dependency
cross-checking oracle in the tests.

Three pypdf traps are handled explicitly: it leaks *builtin* exceptions on pathological
files (classified as `CORRUPT_PDF`, not an internal error, so deterministic bad inputs
don't look retryable); `decrypt()` reports failure through its return value, not an
exception; and its write-side encryption defaults to legacy RC4 - AES-256 is passed
explicitly, so output encryption never downgrades.

## Operations and attachment security

**Merge** is pages-only ([D-011](DECISIONS.md#D-011)): order is exactly the
`PDFOPS_INPUTS` order (explicit, deterministic across retries; no globs), duplicates
are rejected as templating bugs, and readers are opened - page trees forced - before
the writer produces a byte.

**Extract** reads the document-level `/Names/EmbeddedFiles` name tree, the standard
attachment mechanism ([D-016](DECISIONS.md#D-016)); page-level `/FileAttachment`
annotations are a documented limitation. Its dominant risk is that **attachment names
are attacker-controlled strings written to a mounted filesystem** - `../../evil.txt`
would turn extract into a write-anywhere primitive. Every name therefore passes through
a pure sanitizer (separators, traversal, control characters, byte-length cap,
deterministic fallback) with the original name logged whenever it changed; duplicates
get deterministic suffixes deduplicated on **casefolded** names, because the output
volume may be case-insensitive and a naive plan would silently fold `Report.txt` into
`report.txt` there; and a containment re-check plus symlink-aware conflict handling
back the sanitizer up ([D-014](DECISIONS.md#D-014), [D-015](DECISIONS.md#D-015)). Zero
attachments is a success with a count the workflow can gate on -
`PDFOPS_FAIL_ON_NO_ATTACHMENTS=true` flips it to a failure for pipelines where an
attachment-less input means something upstream broke.

## Passwords

Two mutually exclusive channels; the mounted-file channel is the documented preference
because an env value stays visible in pod specs, `kubectl describe`, and
`/proc/<pid>/environ` ([D-017](DECISIONS.md#D-017)). The no-leak guarantee is layered
and *tested rather than promised*: structurally, the `Secret` wrapper renders as `***`
and the raw value is reachable only inside the engine module; as defense in depth, the
logging layer scrubs registered secrets from free-text fields only - token fields are
exempt, because rewriting a known constant like `merge_written` into `***_written`
would itself disclose the password; as hygiene, the entrypoint deletes secret variables
from the live process environment before any work; and leak tests assert the literal
password appears in no output across success, wrong-password, and crash paths.

Decrypt semantics follow what every PDF viewer does ([D-018](DECISIONS.md#D-018)): the
empty-password try runs first (owner-only "permissions-locked" files just open), and
still applies per input when a supplied password doesn't fit, so a mixed merge needs
only the one real password. Failures keep the password exit class - a locked file's
remedy is different from a corrupt file's. Output encryption is a tri-state
([D-019](DECISIONS.md#D-019)): `never` (default) warns loudly on downgrade, `inherit`
encodes "confidentiality never decreases through this step", `always` demands a
password at parse time; output encryption is always AES-256.

## Failures, logging, retries

| Exit | Class | Retry? |
|---|---|---|
| 0 | success (including skip no-ops and zero attachments) | - |
| 1 | unexpected internal error (traceback logged) | yes |
| 2 | invalid configuration | no |
| 3 | input missing/unreadable | usually no |
| 4 | invalid/corrupt/unprocessable PDF | no |
| 5 | password required/wrong/unsupported | no |
| 6 | output conflict or location unusable | `DISK_FULL` only |

Nearly every failure here is deterministic, which is why there is no "transient" exit
band ([D-020](DECISIONS.md#D-020)): retryability is documented per code and composed by
the operator into a `retryStrategy` expression, paired with `PDFOPS_ON_EXISTS=skip` so
a retry after a lost-but-successful pod is a free no-op - merge's skip short-circuits
without reading anything (not the inputs, not even the password file), extract's skip
completes a crashed run's partial set per file. Stale temp debris from a killed run is
removed at startup, matched **literally** (attachment names could otherwise widen a
glob onto another step's files) and never touching this run's own planned outputs.

## Limitations and next steps

Known limitations, in order of consequence: (1) **attachments inside merge inputs are
silently dropped** - no mainstream Python library copies them on a page-level merge;
detect-and-warn, an opt-in failure flag, or qpdf's `--copy-attachments-from` are the
candidate fixes. (2) One password serves all merge inputs; a per-input map is the
extension. (3) The extracted *set* is not transactional - files are individually
atomic, so a staging-directory handoff is the fix if a consumer needs all-or-nothing.
(4) `skip` trusts an existing file as completed prior output; a checksum-verified skip
is future work. (5) Resource behavior is unmeasured - the pikepdf swap comes with
generated large-file benchmarks feeding real K8s requests/limits guidance. (6) An
OOM-kill is a SIGKILL no in-process error boundary can catch; the workflow engine
reports it itself - documented rather than handled. Next in line beyond the
swap: container hardening (digest-pinned base, verified read-only rootfs, a shipped
Argo `WorkflowTemplate` example) and merge bookmark/metadata carry-over.
