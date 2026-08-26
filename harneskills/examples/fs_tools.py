"""The three things this example does to a real filesystem: `ls`, `stat`,
`rename`. Each one takes the world and writes what it learned into it.

A tool is not a system. It has no query and is not called every tick -- a
system decides one is warranted and calls it, which keeps the "when" and
the "what" in different files: `fs.py` decides that a person asking to see
a folder means listing it, and this module knows what listing IS.

What a tool writes is OBSERVATION, as components on the entity the thing
already has: `Size`, `Modified`, `IsDir`, and `Entry` itself for something
seen for the first time. `Failed` is spawned on an entity of its own --
it did not work, and this is what the OS said. Nothing here decides what
to SAY about any of it; `fs.py` has a system that turns a `Failed` into a
reply.

⚠ Two invariants this module owns, and nothing else can:

* `Contents.by_name` is the folder's index, mutated in place. It is the
  one hand-kept structure in the domain, and every mutation here lands
  beside a `spawn`/`destroy` that moves `revision` on its own -- except
  the vanished-entry sweep, which says so with `world.changed()`.
* An entry that has gone from the disk is destroyed. Re-listing a folder
  is a refresh, not an accumulation, and a world still carrying an entity
  for a deleted file is one where every later system reasons about
  something that is not there.
"""

from __future__ import annotations

import os

from . import model as fs


def _reason(e: OSError) -> str:
    return str(e.strerror or e)


def _observe(w, path: str, entity, name: str) -> bool:
    """`Size`/`Modified`/`IsDir` for one entry. False if it is not there.

    ⚠ `st_mtime`, not `st_ctime`. On Linux `ctime` is the inode's last
    CHANGE time, not a creation time -- `chmod` moves it and a restored
    backup resets it -- so a system ageing files by it calls a file
    written years ago fresh the moment anything touches its metadata. What
    anyone asking "is this stale" means is when it was last written.
    """
    full = os.path.join(path, name)
    try:
        st = os.stat(full)
    except OSError:
        # Listed a moment ago and gone now, or in a directory we may read
        # but whose entries we may not stat. Neither is worth taking a
        # whole listing down for: the entity keeps its `Entry`, and a
        # system that needs a `Size` simply does not match it.
        return False
    w.attach(entity, fs.Size(st.st_size), fs.Modified(int(st.st_mtime)))
    if os.path.isdir(full):
        w.attach(entity, fs.IsDir())
    else:
        w.detach(entity, fs.IsDir)
    return True


def ls(w, folder):
    """Every entry of the folder, into the world. Returns how many, or None
    if the directory could not be read (`Failed` says why)."""
    path = w.get(folder, fs.Folder).path
    contents = w.get(folder, fs.Contents)
    try:
        names = sorted(os.listdir(path))
    except OSError as e:
        w.spawn(fs.Failed("list %s" % path, _reason(e)))
        return None
    for name in names:
        entity = contents.by_name.get(name)
        if entity is None:
            entity = w.spawn(fs.Entry(folder, name))
            contents.by_name[name] = entity
        _observe(w, path, entity, name)
    for gone in sorted(set(contents.by_name) - set(names)):
        w.destroy(contents.by_name.pop(gone))
        w.changed(folder)
    return len(names)


def stat(w, entity) -> bool:
    """One entry's size and age, into the world."""
    entry = w.get(entity, fs.Entry)
    path = w.get(entry.folder, fs.Folder).path
    if not _observe(w, path, entity, entry.name):
        w.spawn(fs.Failed("stat %s" % os.path.join(path, entry.name),
                          "cannot stat"))
        return False
    return True


def rename(w, entity, new_name: str) -> bool:
    """Rename on disk, then move the world along with it.

    The entity does not change -- it is the same file, now called
    something else, still carrying whatever any system had concluded about
    it. Only its `Entry` component is replaced, and the folder's index
    re-keyed. Announces `Renamed`, an occasion, taken by whichever system
    reports it.
    """
    entry = w.get(entity, fs.Entry)
    path = w.get(entry.folder, fs.Folder).path
    try:
        os.rename(os.path.join(path, entry.name), os.path.join(path, new_name))
    except OSError as e:
        w.spawn(fs.Failed("rename %s to %s" % (entry.name, new_name), _reason(e)))
        return False
    contents = w.get(entry.folder, fs.Contents)
    contents.by_name.pop(entry.name, None)
    contents.by_name[new_name] = entity
    was = entry.name
    w.attach(entity, fs.Entry(entry.folder, new_name))
    _observe(w, path, entity, new_name)
    w.spawn(fs.Renamed(entity, was))
    return True
