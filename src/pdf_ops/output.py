"""Output-path policy and atomic writes.

The reliability cornerstone: the final output path either holds a complete
file or nothing. Work is written to a temp file in the *destination
directory* (same filesystem - ``os.replace`` is only atomic within one) and
renamed over in one step, so a crashed or failed run never leaves a partial
PDF where a downstream workflow step could read it.
"""

from __future__ import annotations

import errno
import os
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import NoReturn

from pdf_ops.errors import OutputError


def check_output_dir(directory: Path) -> None:
    """Fail fast when the extraction target directory is absent."""
    if not directory.is_dir():
        raise OutputError(
            f"output directory {directory} does not exist "
            "(output locations are mounted; a missing directory is a workflow bug)",
            error_code="OUTPUT_DIR_MISSING",
            context={"output_dir": str(directory)},
        )


def check_output_path(path: Path) -> None:
    """Fail fast on unusable output locations, before any work is done."""
    parent = path.parent
    if not parent.is_dir():
        raise OutputError(
            f"output directory {parent} does not exist "
            "(output locations are mounted; a missing directory is a workflow bug)",
            error_code="OUTPUT_DIR_MISSING",
            context={"output": str(path)},
        )
    if path.exists():
        raise OutputError(
            f"output {path} already exists (refusing to overwrite)",
            error_code="OUTPUT_EXISTS",
            context={"output": str(path)},
        )


@contextmanager
def atomic_output(path: Path) -> Generator[Path]:
    """Yield a temp path in the destination directory; publish it on success.

    On success the temp file is fsynced and renamed onto ``path`` (and the
    directory entry fsynced). On any failure the temp file is removed and the
    final path is left untouched.
    """
    try:
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    except OSError as err:
        _raise_translated(err, path)
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        yield tmp_path
        with tmp_path.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        _fsync_dir(path.parent)
    except OSError as err:
        _cleanup(tmp_path)
        _raise_translated(err, path)
    except BaseException:
        _cleanup(tmp_path)
        raise


def _raise_translated(err: OSError, path: Path) -> NoReturn:
    translated = _translate_os_error(err, path)
    if translated is err:
        raise err
    raise translated from err


def _translate_os_error(err: OSError, path: Path) -> Exception:
    """Map I/O failures around the output location onto the taxonomy.

    Anything not recognizably an output-environment problem is returned
    unchanged so the unexpected-error boundary reports it honestly.
    """
    if err.errno == errno.ENOSPC:
        return OutputError(
            f"no space left on device while writing {path}",
            error_code="DISK_FULL",
            context={"output": str(path)},
        )
    if err.errno in (errno.EACCES, errno.EPERM, errno.EROFS):
        return OutputError(
            f"output location {path} is not writable",
            error_code="OUTPUT_NOT_WRITABLE",
            context={"output": str(path)},
        )
    return err


def _cleanup(tmp_path: Path) -> None:
    try:
        tmp_path.unlink(missing_ok=True)
    except OSError:  # best effort - never mask the original failure
        pass


def _fsync_dir(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
