# tests/conftest.py
# Shared fixtures and pytest configuration for the backend test suite.
import sys
from pathlib import Path

# Ensure the backend root is on sys.path so `from app.xxx` imports work
# without needing to install the package.
sys.path.insert(0, str(Path(__file__).parent.parent))
