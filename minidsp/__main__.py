"""Package entry point: allows ``python -m minidsp ...``.

Dispatches to :func:`minidsp.cli.main`, which provides the ``dump``,
``levels``, ``mute``, and ``unmute`` subcommands.
"""
from __future__ import annotations

from .cli import main

main()
