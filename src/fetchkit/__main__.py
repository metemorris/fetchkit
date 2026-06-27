"""Enable ``python -m fetchkit`` as an alias for the ``fetchkit`` CLI."""

import sys

from fetchkit.cli import main

if __name__ == "__main__":
    sys.exit(main())
