"""Hermes Eye Memory plugin entry point."""

try:  # loaded as a directory plugin package
    from .hermes_eye_memory import register
except ImportError:  # loaded as a top-level module by some test runners
    from hermes_eye_memory import register

__all__ = ["register"]
