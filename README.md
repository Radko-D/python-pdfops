# pdf-ops

Containerized PDF operations for workflow systems (e.g. Argo Workflows): exactly one
operation per container run - **merge** multiple PDFs into one, or **extract** the
attachments embedded in a PDF - configured entirely through environment variables.

The design - architecture, library tradeoffs, security posture, limitations - is
summarized in [`docs/DESIGN.md`](docs/DESIGN.md); the working notes behind it are
[`docs/DESIGN_NOTES.md`](docs/DESIGN_NOTES.md), and individual choices, with their
alternatives and status, live in the decision register at
[`docs/DECISIONS.md`](docs/DECISIONS.md).

## Quick start

```sh
docker build -t pdf-ops .

# The container runs as UID 10001 - the output dir must be writable by it
mkdir -p in out && chmod 777 out

# Merge two PDFs from a mounted input dir into a mounted output dir
docker run --rm \
  -v "$PWD/in:/in:ro" -v "$PWD/out:/out" \
  -e PDFOPS_OPERATION=merge \
  -e PDFOPS_INPUTS=/in/a.pdf:/in/b.pdf \
  -e PDFOPS_OUTPUT=/out/merged.pdf \
  pdf-ops

# Extract the attachments embedded in a PDF
docker run --rm \
  -v "$PWD/in:/in:ro" -v "$PWD/out:/out" \
  -e PDFOPS_OPERATION=extract \
  -e PDFOPS_INPUT=/in/report.pdf \
  -e PDFOPS_OUTPUT_DIR=/out \
  pdf-ops

# Merge an encrypted PDF, re-encrypting the output with the same password
docker run --rm \
  -v "$PWD/in:/in:ro" -v "$PWD/out:/out" -v "$PWD/secret:/secret:ro" \
  -e PDFOPS_OPERATION=merge \
  -e PDFOPS_INPUTS=/in/locked.pdf:/in/plain.pdf \
  -e PDFOPS_OUTPUT=/out/merged.pdf \
  -e PDFOPS_PASSWORD_FILE=/secret/pw \
  -e PDFOPS_OUTPUT_ENCRYPTION=inherit \
  pdf-ops

# Invalid configuration fails fast (exit 2, machine-readable error event)
docker run --rm -e PDFOPS_OPERATION=bogus pdf-ops
```

The container needs no arguments and no interactive input: behavior comes entirely
from `PDFOPS_*` variables, and the mounted volumes provide inputs and receive outputs.

## Environment variables

| Variable | Operation | Required | Accepted values | Default |
|---|---|---|---|---|
| `PDFOPS_OPERATION` | - | yes | `merge`, `extract` | - |
| `PDFOPS_INPUTS` | merge | yes | ordered list of file paths, `:`-separated (explicit order - no globs) | - |
| `PDFOPS_OUTPUT` | merge | yes | path of the output PDF; its directory must exist | - |
| `PDFOPS_INPUT` | extract | yes | the PDF to extract attachments from | - |
| `PDFOPS_OUTPUT_DIR` | extract | yes | existing directory receiving the attachment files | - |
| `PDFOPS_FAIL_ON_NO_ATTACHMENTS` | extract | no | `true`, `false` (case-insensitive) - fail (exit 3) when the PDF has no attachments | `false` |
| `PDFOPS_PASSWORD_FILE` | both | no | path to a mounted secret file holding the password (preferred channel; one trailing newline stripped) | - |
| `PDFOPS_PASSWORD` | both | no | the password itself - discouraged: env values leak via `kubectl describe`, `/proc/<pid>/environ`, crash tooling | - |
| `PDFOPS_OUTPUT_ENCRYPTION` | merge | no | `never`, `inherit`, `always` (case-insensitive) - see below | `never` |
| `PDFOPS_OUTPUT_PASSWORD_FILE` | merge | no | secret file holding the password for the merged output | - |
| `PDFOPS_OUTPUT_PASSWORD` | merge | no | output password as a direct value (same caveats as `PDFOPS_PASSWORD`) | - |
| `PDFOPS_ON_EXISTS` | both | no | `fail`, `overwrite`, `skip` (case-insensitive) - see Retries | `fail` |
| `PDFOPS_LOG_LEVEL` | - | no | `debug`, `info`, `warning`, `error` (case-insensitive) | `info` |

Strictness rules, all exit 2: any other `PDFOPS_*` variable is rejected as a probable
typo (`UNKNOWN_VAR`); a variable belonging to the other operation is rejected
(`INAPPLICABLE_VAR`); duplicate merge inputs are rejected (`DUPLICATE_INPUTS`) - a
repeated path is almost always a templating bug that would silently duplicate content.

## Path conventions and output behavior

- Input files and the output location are **mounted volumes**; use absolute in-container paths.
- The container runs as **non-root UID 10001**: input mounts need to be readable and the
  output mount writable by that UID (`chmod`/`chown` for plain Docker; `fsGroup` in a pod
  `securityContext` on Kubernetes).
- **Passwords.** One password (via `PDFOPS_PASSWORD_FILE`, preferably) is tried against
  every encrypted input; owner-only "permissions-locked" PDFs open without a password via
  the spec-standard empty-password try, exactly like every PDF viewer. Wrong password ->
  exit 5 naming the failing input. The password itself never appears in any output: the
  in-process `Secret` wrapper renders as `***`, the logging layer scrubs registered secret
  values from every event including tracebacks, and the process scrubs `PDFOPS_PASSWORD`
  from its own environment on startup. Each `input_opened` event reports the encryption
  algorithm (read from the PDF's plaintext `/Encrypt` dictionary) and how the file opened
  (`user`/`owner`/`empty`). A permissions-locked input among user-locked ones never fails
  just because a password was supplied: the empty try still applies per input. Passwords
  containing control characters are rejected (exit 2) as encoding accidents. Note the env
  channel's inherent limit: the initial environment block stays visible to `docker
  inspect` and `/proc/<pid>/environ` - the file channel is the one that keeps the value
  out of the process's environment entirely.
- **Output encryption** (`PDFOPS_OUTPUT_ENCRYPTION`): `never` (default) writes a plaintext
  output and emits a loud `security_downgrade` warning when inputs were encrypted;
  `inherit` encrypts the output iff at least one input was encrypted - confidentiality
  never decreases through this step; `always` encrypts unconditionally. The output
  password comes from `PDFOPS_OUTPUT_PASSWORD_FILE`/`PDFOPS_OUTPUT_PASSWORD`, falling
  back to the *explicitly supplied* input password (never the empty auto-try). Output
  encryption is always AES-256, whatever the inputs used. Supplying an output password
  while the mode is `never` is a hard configuration error.
- Merge order is exactly the order of `PDFOPS_INPUTS` - deterministic across retries.
- Output is written **atomically**: work goes to a temp file in the output directory,
  then a single rename. The final path either holds a complete PDF or nothing - a
  failed or killed run never leaves a partial file where a downstream step could read it.
  Outputs get regular `open()`-style permissions (the container umask, `0644` by
  default), so a later step running as a different user can read them from a shared
  volume.
- **Existing outputs** follow `PDFOPS_ON_EXISTS`: `fail` (default) refuses with exit 6;
  `overwrite` replaces atomically (readers see old bytes or new bytes, never a mix);
  `skip` treats the existing output as a completed prior run. For merge, `skip` is a
  whole-run no-op - exit 0 with `skipped: true`, without even reading the inputs. For
  extract, `skip` is **per-file completion**: only missing attachments are written
  (`attachments_skipped` reports the rest), so a crashed run's partial set gets finished
  by the retry - sound because every file this tool writes is atomic and therefore whole.
  Both `skip` modes trust that an existing file is a completed prior output.
- Temp debris from a crashed prior run (`.name.*.tmp` matching this run's own targets)
  is removed at startup with a `stale_temp_removed` event. One writer per output path at
  a time is assumed - which a workflow engine guarantees per step.
- All inputs are validated (existence, readability, PDF header) **before anything is
  written**, and every bad input is reported in a single failure event.
- **Attachment names are treated as untrusted input**: extraction reduces every name to a
  sanitized basename (path separators, traversal segments, and control characters
  removed; deterministic `attachment_<n>` fallback), so a hostile PDF can never write
  outside `PDFOPS_OUTPUT_DIR`. Duplicate names get deterministic `-1`/`-2` suffixes;
  the original name is logged whenever sanitization changed it.
- Extraction order is the PDF's name-tree order - deterministic across runs. Each file is
  written atomically; under the default `fail` policy any pre-existing file (or symlink)
  at a target name refuses the whole run **before** anything is written (exit 6) - see
  `PDFOPS_ON_EXISTS` above for the retry-friendly modes. A directory at an output path is
  refused under every policy (`OUTPUT_IS_DIRECTORY`). A PDF with zero attachments is a
  success with `attachments_extracted=0` unless the strict flag is set.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | unexpected internal error (traceback in the log) |
| 2 | invalid configuration |
| 3 | input missing/unreadable |
| 4 | invalid or corrupt PDF |
| 5 | password required/wrong/unsupported |
| 6 | output conflict or output location unusable |

## Logging

Output is JSON lines on stdout - one event per line, stderr stays empty. Lifecycle
events (`config_loaded`, `input_opened`, `merge_written`, `stale_temp_removed`, ...)
narrate progress and respect `PDFOPS_LOG_LEVEL`; the config echo reports passwords as
presence only (`unset` / `set(env)` / `set(file)`), never as values. Every run ends
with exactly one terminal event - `operation_complete` (merge: `pages`,
`bytes_written`, `output_path`; extract: `attachments_extracted`, `bytes_written`) or
`operation_failed` (with `error_code`, `error_message`, `exit_code`) - which
`PDFOPS_LOG_LEVEL` never suppresses, so a workflow engine can always branch on the
last line:

```json
{"ts": "2026-09-02T17:55:15.661+00:00", "level": "info", "event": "operation_complete", "operation": "merge", "exit_code": 0, "duration_s": 0.001, "inputs_merged": 2, "pages": 3, "bytes_written": 728, "output_path": "/out/merged.pdf", "output_encrypted": false}
```

## Retries

Workflow engines retry at-least-once, and most failures here are deterministic -
retrying a wrong password or a corrupt PDF is pure waste. The retryability of each exit
code:

| Code | Retry? | Why |
|---|---|---|
| 1 | yes | unexpected internal error - the only class where a retry might see different behavior |
| 2 | no | configuration is immutable for a given pod spec |
| 3 | usually no | missing/unreadable input - permanent unless an upstream mount races |
| 4 | no | the PDF itself is bad; it will be bad again |
| 5 | no | the password will still be wrong |
| 6 | usually no | output conflict/location - `DISK_FULL` is the judgment call (space may free up) |

Argo example - retry only on unexpected errors, with `skip` making any retry after a
lost-but-successful pod a free no-op:

```yaml
retryStrategy:
  limit: "3"
  expression: "asInt(lastRetry.exitCode) == 1"
# and in the container env:
#   PDFOPS_ON_EXISTS: skip
```

## Development

```sh
uv sync                       # deps + venv
uv run pytest                 # unit + integration tests
uv run pytest -m container    # container-contract tests (needs Docker)
uv run ruff check .           # lint
uv run pyright                # strict type check
uv run pre-commit run -a      # full hook chain
```
