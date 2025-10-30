#!/usr/bin/env python3
"""
Poker Agentify - Main Entry Point
Delegates to the unified launcher
"""
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from launcher import main

if __name__ == "__main__":
    main()