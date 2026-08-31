"""Container entrypoint: ``python -m pdf_ops``.

The only module that touches the real process environment and exit status;
everything else operates on plain mappings and return values.
"""

from __future__ import annotations

import os
import sys

from pdf_ops.main import run


def main() -> None:
    sys.exit(run(os.environ))


if __name__ == "__main__":
    main()
