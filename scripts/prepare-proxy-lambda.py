#!/usr/bin/env python3
"""Prepare the agent proxy Lambda package by copying agents/ and tools/ into it.

SAM builds each Lambda from its CodeUri directory only. The proxy Lambda needs
access to agents/ and tools/ directories, so we copy them in before sam build.
"""
import shutil
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROXY_DIR = ROOT / "tools" / "agent_proxy"

# Directories to copy into the proxy Lambda package
COPY_DIRS = ["agents", "tools"]

for d in COPY_DIRS:
    src = ROOT / d
    dst = PROXY_DIR / d
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns(
        "__pycache__", "*.pyc", "test_*", ".gitkeep", "agent_proxy"  # avoid recursion
    ))
    print(f"Copied {src} -> {dst}")

print("Proxy Lambda package prepared.")
