"""HarneSkills -- a door onto a UGM machine.

UGM (the `ugm` package, an external dependency here -- see `pyproject.toml`)
is an agent that plans, acts, observes and explains itself on one graph
substrate. This package is not a second engine: it is UGM's own REPL,
carved out and promoted to be the thing this repository works on. Load a
`.ugm` corpus and talk to it:

    python -m harneskills corpus.ugm

See `harneskills.repl` for what typing at the prompt means.
"""

from __future__ import annotations

from . import repl

__version__ = "0.1.0"

__all__ = ["repl", "__version__"]
