"""Which domains a session installs when nobody types anything, and where
the world is kept between runs.

    ~/.config/harneskills/config          the domains
    ~/.local/state/harneskills/world.json the world itself

One `module:callable` per line, installed in the order written::

    # ~/.config/harneskills/config -- standing domains
    harneskills.examples.fs:install
    mykitchen:install

A line whose first non-blank character is `#` is a comment; a blank line is
nothing. That is the entire file format.

A domain is a Python callable taking the `Loop` -- `install(loop)` -- and
expected to register systems and spawn what they read. There is no other
kind of line, because there is no other kind of content: a system is
Python, so a domain's model and its behaviour are the same import, and a
config that named folders of data would be naming files nothing reads.

⚠ This module resolves NOTHING. It reads a path and returns the strings it
found, in file order; importing them, calling them, and saying what went
wrong is `__main__`'s job. Keeping it that way is what lets the config file
be tested without importing anything it names.
"""

from __future__ import annotations

import os

APP = "harneskills"


def config_path() -> str:
    """The config file this session would read.

    `$HARNESKILLS_CONFIG` wins outright (a full path to a file, so a
    service or a test can point somewhere else). Otherwise the XDG
    location, which on a stock box is `~/.config/harneskills/config`.
    """
    override = os.environ.get("HARNESKILLS_CONFIG")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config")
    return os.path.join(os.path.expanduser(base), APP, "config")


def state_path() -> str:
    """Where the world is kept between runs (see `harneskills.save`).

    `$HARNESKILLS_STATE` wins outright. Otherwise the XDG STATE location
    -- `~/.local/state/harneskills/world.json` on a stock box -- which is
    the right one of the four: this is neither configuration you would
    edit nor a cache you could throw away without losing something, it is
    what the program knew last time.
    """
    override = os.environ.get("HARNESKILLS_STATE")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    base = os.environ.get("XDG_STATE_HOME") or os.path.join(
        os.path.expanduser("~"), ".local", "state")
    return os.path.join(os.path.expanduser(base), APP, "world.json")


def read_domains(path=None) -> "list[str]":
    """Every `module:callable` named in `path`, in file order.

    No file is not an error -- it is the ordinary case for someone who has
    never written one, and it means "no standing domains", exactly as if
    the file were empty. The same spec named twice is kept once:
    installing a domain twice registers its systems twice, and every one
    of them would then run twice a tick.
    """
    if path is None:
        path = config_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read()
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError, PermissionError):
        return []
    specs, seen = [], set()
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line in seen:
            continue
        seen.add(line)
        specs.append(line)
    return specs
