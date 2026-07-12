#!/usr/bin/env python3
"""Compatibility wrapper for the Living/Dining local release hook."""
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.argv[0] = str(ROOT / "agent/factlayer/hooks/living_dining.py")
runpy.run_path(sys.argv[0], run_name="__main__")
