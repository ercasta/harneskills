"""Filesystem tools for the `fs` example (`docs/tools-approval.md`'s bet,
upstream in `ugm`: listing and bookkeeping compound into automations, over
one graph). Carved out of `ugm.repl_fs`, unmodified beyond the imports.

Three answerers -- `ls`, `stat`, `rename` -- and nothing else. `ls`/`stat` are
read-only and answer freely; `rename` is the one that touches the world, and
`examples/fs/fs_demo.ugm` holds it for approval the same way UGM's own
`tools_approval.ugm` holds `deploy` (§19 triggers, no new machinery).

A tool "builds in the corpus's name scope" (§22): `ls` deposits one
`file`/`size`/`created` fact per directory entry directly, through the same
Loader the corpus's own rules are read against, so a rule can query what it
found without a second round trip per file. What it *answers* -- `counted(n)`
or `failed(reason)` -- is the one thing a rule reacts to; the facts are read
because the loader index says something wrote them, same as any other belief.
"""

import os

from ugm.core.machine import Machine
from ugm.core.text import Loader


def _write(m: Machine, node) -> None:
    if not m.pad.holds(node):
        m.gate.write(node)


def register(ldr: Loader) -> None:
    """Bind `ls`, `stat` and `rename` as answerers in `ldr`'s scope."""
    m = ldr.m

    def deposit(head: str, *args: str):
        node = m.g.rel(ldr.atom(head), *[ldr.atom(a) for a in args])
        _write(m, node)
        return node

    def ls(mach: Machine, prop) -> object:
        (dirnode,) = mach.g.members(prop)
        dirpath = mach.g.show(dirnode)
        try:
            names = sorted(os.listdir(dirpath))
        except OSError as e:
            return deposit("failed", str(e.strerror or e))
        for name in names:
            full = os.path.join(dirpath, name)
            deposit("file", dirpath, name)
            try:
                st = os.stat(full)
            except OSError:
                continue
            deposit("size", dirpath, name, str(st.st_size))
            deposit("created", dirpath, name, str(int(st.st_ctime)))
            if os.path.isdir(full):
                deposit("is_dir", dirpath, name)
        return ldr.atom(str(len(names)))

    def stat(mach: Machine, prop) -> object:
        dirnode, namenode = mach.g.members(prop)
        dirpath, name = mach.g.show(dirnode), mach.g.show(namenode)
        try:
            st = os.stat(os.path.join(dirpath, name))
        except OSError as e:
            return deposit("failed", str(e.strerror or e))
        deposit("size", dirpath, name, str(st.st_size))
        deposit("created", dirpath, name, str(int(st.st_ctime)))
        return ldr.atom("done")

    def rename(mach: Machine, prop) -> object:
        dirnode, oldnode, newnode = mach.g.members(prop)
        dirpath, old, new = (mach.g.show(x) for x in (dirnode, oldnode, newnode))
        try:
            os.rename(os.path.join(dirpath, old), os.path.join(dirpath, new))
        except OSError:
            return ldr.atom("failed")
        return ldr.atom("done")

    ldr.answerer("ls", "ls", ls)
    ldr.answerer("stat", "stat", stat)
    ldr.answerer("rename", "rename", rename)
