"""Make the backend package root importable as ``app`` during tests."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
