# Operational behavior

The behavior contract for operators: paths and permissions, password semantics,
output policies, and what the log stream carries. The short reference tables
(environment variables, exit codes, retryability) live in the
[README](../README.md).

## Paths and permissions

- Input files and the output location are **mounted volumes**; use absolute
  in-container paths.
- The container runs as **non-root UID 10001**: input mounts need to be readable and
  the output mount writable by that UID (`chmod`/`chown` for plain Docker; `fsGroup`
  in a pod `securityContext` on Kubernetes).
- Outputs get regular `open()`-style permissions (the container umask, `0644` by
  default), so a later step running as a different user can read them from a shared
  volume.

## Passwords

- One password (via `PDFOPS_PASSWORD_FILE`, preferably) is tried against every
  encrypted input; owner-only "permissions-locked" PDFs open without a password via
  the spec-standard empty-password try, exactly like every PDF viewer. Wrong
  password -> exit 5 naming the failing input.
- The password itself never appears in any output: the in-process `Secret` wrapper
  renders as `***`, the logging layer scrubs registered secret values from every
  event including tracebacks, and the process scrubs `PDFOPS_PASSWORD` from its own
  environment on startup.
- Each `input_opened` event reports the encryption algorithm (read from the PDF's
  plaintext `/Encrypt` dictionary) and how the file opened (`user`/`owner`/`empty`).
- A permissions-locked input among user-locked ones never fails just because a
  password was supplied: the empty try still applies per input.
- Passwords containing control characters are rejected (exit 2) as encoding
  accidents.
- Note the env channel's inherent limit: the initial environment block stays visible
  to `docker inspect` and `/proc/<pid>/environ` - the file channel is the one that
  keeps the value out of the process's environment entirely.

## Output encryption

`PDFOPS_OUTPUT_ENCRYPTION`: `never` (default) writes a plaintext output and emits a
loud `security_downgrade` warning when inputs were encrypted; `inherit` encrypts the
output iff at least one input was encrypted - confidentiality never decreases through
this step; `always` encrypts unconditionally. The output password comes from
`PDFOPS_OUTPUT_PASSWORD_FILE`/`PDFOPS_OUTPUT_PASSWORD`, falling back to the
*explicitly supplied* input password (never the empty auto-try). Output encryption is
always AES-256, whatever the inputs used. Supplying an output password while the mode
is `never` is a hard configuration error.

## Atomic writes and existing outputs

- Merge order is exactly the order of `PDFOPS_INPUTS` - deterministic across retries.
- Output is written **atomically**: work goes to a temp file in the output directory,
  then a single rename. The final path either holds a complete PDF or nothing - a
  failed or killed run never leaves a partial file where a downstream step could
  read it.
- **Existing outputs** follow `PDFOPS_ON_EXISTS`: `fail` (default) refuses with exit
  6; `overwrite` replaces atomically (readers see old bytes or new bytes, never a
  mix); `skip` treats the existing output as a completed prior run. For merge, `skip`
  is a whole-run no-op - exit 0 with `skipped: true`, without even reading the
  inputs. For extract, `skip` is **per-file completion**: only missing attachments
  are written (`attachments_skipped` reports the rest), so a crashed run's partial
  set gets finished by the retry - sound because every file this tool writes is
  atomic and therefore whole. Both `skip` modes trust that an existing file is a
  completed prior output.
- Temp debris from a crashed prior run (`.name.*.tmp` matching this run's own
  targets) is removed at startup with a `stale_temp_removed` event. One writer per
  output path at a time is assumed - which a workflow engine guarantees per step.
- All inputs are validated (existence, readability, PDF header) **before anything is
  written**, and every bad input is reported in a single failure event.

## Attachment extraction

- **Attachment names are treated as untrusted input**: extraction reduces every name
  to a sanitized basename (path separators, traversal segments, and control
  characters removed; deterministic `attachment_<n>` fallback), so a hostile PDF can
  never write outside `PDFOPS_OUTPUT_DIR`. Duplicate names get deterministic
  `-1`/`-2` suffixes; the original name is logged whenever sanitization changed it.
- Extraction order is the PDF's name-tree order - deterministic across runs. Each
  file is written atomically; under the default `fail` policy any pre-existing file
  (or symlink) at a target name refuses the whole run **before** anything is written
  (exit 6) - see `PDFOPS_ON_EXISTS` above for the retry-friendly modes. A directory
  at an output path is refused under every policy (`OUTPUT_IS_DIRECTORY`). A PDF
  with zero attachments is a success with `attachments_extracted=0` unless
  `PDFOPS_FAIL_ON_NO_ATTACHMENTS` is set.

## Log events

One JSON object per line on stdout; stderr stays empty. Lifecycle events narrate
progress at their log levels (`config_loaded`, `input_opened`, `merge_written`,
`attachment_extracted`, `stale_temp_removed`, `pdf_library_message` for damage the
PDF engine repaired, `security_downgrade`, `password_unused`, ...). The terminal
event is never suppressed by `PDFOPS_LOG_LEVEL`:

- `operation_complete` - merge: `pages`, `bytes_written`, `output_path`,
  `output_encrypted`; extract: `attachments_extracted`, `bytes_written`, plus
  `attachments_skipped` under `skip`. Always: `exit_code`, `duration_s`.
- `operation_failed` - `error_code` (machine-readable, finer-grained than the exit
  code), `error_message`, `exit_code`, `context` (e.g. the failing input), and a
  `traceback` for unexpected errors.
