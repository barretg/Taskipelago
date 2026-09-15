"""Shared paths and module loaders for the Python tests (no Archipelago install needed)."""
from __future__ import annotations

import importlib.util
import os
import sys

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(TESTS)
WORLD = os.path.join(REPO, "custom_worlds", "taskipelago")
WEB_CLIENT = os.path.join(WORLD, "web-client")
FIXTURES = os.path.join(TESTS, "fixtures")


def load_world_module(name: str):
    """Import a stdlib-only module from the world package by file path."""
    key = f"_taskipelago_test_{name}"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, os.path.join(WORLD, f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module
