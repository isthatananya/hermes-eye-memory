"""Hermes Eye Memory: local visual memory for photos and camera frames."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def register(ctx):
    """Wire tools, the CLI, and the bundled skill into Hermes."""
    from . import tools

    tools.set_context(ctx)

    specs = tools.tool_specs()
    for schema, handler in specs:
        ctx.register_tool(
            name=schema["name"],
            toolset="eye_memory",
            schema=schema,
            handler=handler,
        )

    from .cli import handle, setup_argparse

    ctx.register_cli_command(
        name="eye-memory",
        help="Local visual memory: index photos, search, albums, receipts, and camera recall",
        setup_fn=setup_argparse,
        handler_fn=handle,
    )

    skill = Path(__file__).resolve().parent.parent / "skills" / "eye-memory" / "SKILL.md"
    if skill.exists():
        try:
            ctx.register_skill("eye-memory", skill)
        except Exception as exc:  # pragma: no cover - host API guard
            logger.warning("eye-memory skill registration failed: %s", exc)

    logger.info("hermes-eye-memory registered %d tools", len(specs))
