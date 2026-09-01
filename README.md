# pdf-ops

Containerized PDF operations for workflow systems (e.g. Argo Workflows): exactly one
operation per container run - **merge** multiple PDFs into one, or **extract** the
attachments embedded in a PDF - configured entirely through environment variables.

> **Status: work in progress.** Both operations are implemented; next up are password
> support, an overwrite policy for retries, and container hardening. See
> [`docs/DECISIONS.md`](docs/DECISIONS.md) for the decision register and
> [`docs/DESIGN_NOTES.md`](docs/DESIGN_NOTES.md) for design notes.

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
- Encrypted input PDFs are currently refused (exit 5, `PASSWORD_REQUIRED` /
  `UNSUPPORTED_ENCRYPTION`); password support is the next piece of work.
- Merge order is exactly the order of `PDFOPS_INPUTS` - deterministic across retries.
- Output is written **atomically**: work goes to a temp file in the output directory,
  then a single rename. The final path either holds a complete PDF or nothing - a
  failed or killed run never leaves a partial file where a downstream step could read it.
- An existing file at `PDFOPS_OUTPUT` is refused (exit 6, `OUTPUT_EXISTS`); a
  configurable overwrite/skip policy is planned alongside retry semantics.
- All inputs are validated (existence, readability, PDF header) **before anything is
  written**, and every bad input is reported in a single failure event.
- **Attachment names are treated as untrusted input**: extraction reduces every name to a
  sanitized basename (path separators, traversal segments, and control characters
  removed; deterministic `attachment_<n>` fallback), so a hostile PDF can never write
  outside `PDFOPS_OUTPUT_DIR`. Duplicate names get deterministic `-1`/`-2` suffixes;
  the original name is logged whenever sanitization changed it.
- Extraction order is the PDF's name-tree order - deterministic across runs. Each file is
  written atomically, and any pre-existing file (or symlink) at a target name fails the
  whole run **before** anything is written (exit 6). A PDF with zero attachments is a
  success with `attachments_extracted=0` unless the strict flag is set.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | success |
| 1 | unexpected internal error (traceback in the log) |
| 2 | invalid configuration |
| 3 | input missing/unreadable |
| 4 | invalid or corrupt PDF |
| 5 | password required/wrong/unsupported (with password support) |
| 6 | output conflict or output location unusable |

Every run ends with exactly one terminal JSON event on stdout - `operation_complete`
(merge: `pages`, `bytes_written`, `output_path`; extract: `attachments_extracted`,
`bytes_written`) or `operation_failed` (with `error_code`, `error_message`,
`exit_code`). Terminal events are never suppressed by `PDFOPS_LOG_LEVEL`.

## Development

```sh
uv sync                       # deps + venv
uv run pytest                 # unit + integration tests
uv run pytest -m container    # container-contract tests (needs Docker)
uv run ruff check .           # lint
uv run pyright                # strict type check
uv run pre-commit run -a      # full hook chain
```
