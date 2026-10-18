#!/usr/bin/env python3
"""
Reel Automation - Main Entry Point
Run the automated weekly content pipeline.
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from automation.pipeline.orchestrator import main

if __name__ == "__main__":
    main()