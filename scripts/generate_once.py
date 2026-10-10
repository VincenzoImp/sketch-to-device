#!/usr/bin/env python3
"""Run the reviewed generation CLI from any terminal working directory."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).absolute().parent.parent))
from backend.generator import main

if __name__ == "__main__":
    sys.exit(main())
