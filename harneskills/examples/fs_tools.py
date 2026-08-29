"""The three things this example does to a real filesystem: `ls`, `stat`,
`rename`. Each one reads the world, does real I/O, and writes back onto
the entity the thing already has -- `Size`, `Modified`, `IsDir`, and a
freshly `spawn`ed `Entry` for something seen for the first time.
`Failed` is `spawn`ed as an entity of its own -- it did not work, and
this is what the OS said. Nothing here decides what to SAY about any of
it; `fs.py` has a rule that turns a `Failed` into a reply.

A tool is not a rule. It has no query and is not called every tick -- a
rule decides one is warranted and calls it, which keeps the "when" and
the "what" in different files: `fs.py` decides that a person asking to see
a folder means listing it, and this module knows what listing IS.

⚠ Two invariants this module owns, and nothing else can:

* `Contents.by_name` is the folder's index -- computed fresh here, every
  time, and put on with `world.replace` rather than edited in place.
  `World.attach`/`replace` comparing before it stores is what makes
  re-listing an unchanged folder cost a dict comparison, not a revision.
* An entry that has gone from the disk is destroyed. Re-listing a folder
  is a refresh, not an accumulation, and a world still carrying an entity
  for a deleted file is one where every later rule reasons about
  something that is not there.
"""

from __future__ import annotations

import os

from . import model as fs


def _reason(e: OSError) -> str:
    return str(e.strerror or e)


def _observe(w, path: str, entity, name: str):
    """`(size, modified, is_dir)` for one entry, off the real disk --
    `size`/`modified` are `None` if it could not be `stat`'d. Nothing
    here decides what that MEANS, `ls` and `stat` do.

    ⚠ `st_mtime`, not `st_ctime`. On Linux `ctime` is the inode's last
    CHANGE time, not a creation time -- `chmod` moves it and a restored
    backup resets it -- so ageing files by it calls a file written years
    ago fresh the moment anything touches its metadata. What anyone
    asking "is this stale" means is when it was last written.
    """
    full = os.path.join(path, name)
    try:
        st = os.stat(full)
    except OSError:
        # Listed a moment ago and gone now, or in a directory we may read
        # but whose entries we may not stat. Neither is worth taking a
        # whole listing down for: the entity keeps its `Entry`, and a
        # rule that needs a `Size` simply does not match it.
        return None, None, False
    is_dir = os.path.isdir(full)
    # `replace`, not `attach`: an entity is re-`_observe`d every listing,
    # and `Size`/`Modified` are meant to stay singular -- `attach` would
    # leave the old value standing alongside the new one.
    w.replace(entity, fs.Size(st.st_size), fs.Modified(int(st.st_mtime)))
    if is_dir:
        w.attach(entity, fs.IsDir())
    else:
        w.detach(entity, fs.IsDir)
    return st.st_size, int(st.st_mtime), is_dir


def ls(w, folder):
    """`(entries, count)` -- every entry of the folder. `count` is `None`
    if the directory could not be read (`Failed` is spawned then, and
    `entries` is empty). `entries` is `(entity, name, size, modified,
    is_dir)` per name found, in sorted order.
    """
    path = w.get(folder, fs.Folder).path
    contents = w.get(folder, fs.Contents)
    try:
        names = sorted(os.listdir(path))
    except OSError as e:
        w.spawn(fs.Failed("list %s" % path, _reason(e)))
        return [], None
    by_name = dict(contents.by_name)
    entries = []
    for name in names:
        entity = by_name.get(name)
        if entity is None:
            entity = w.spawn(fs.Entry(folder, name))
            by_name[name] = entity
        size, modified, is_dir = _observe(w, path, entity, name)
        entries.append((entity, name, size, modified, is_dir))
    for gone in sorted(set(by_name) - set(names)):
        w.destroy(by_name.pop(gone))     # a plain id or a handle -- either works
    # `replace`: the folder's index is meant to stay singular, and this is
    # THE place `Contents`'s own module note calls out -- computed fresh
    # every time, never edited in place, and comparing before it stores
    # (which `replace` still does) is what makes re-listing an unchanged
    # folder cost a dict comparison, not a revision.
    w.replace(folder, fs.Contents(by_name))
    return entries, len(names)


def stat(w, entity):
    """`ok` -- one entry's size and age, freshly `_observe`d. `False` if
    it could not be `stat`'d (`Failed` is spawned then)."""
    entry = w.get(entity, fs.Entry)
    path = w.get(entry.folder, fs.Folder).path
    size, _modified, _is_dir = _observe(w, path, entity, entry.name)
    if size is None:
        w.spawn(fs.Failed("stat %s" % os.path.join(path, entry.name),
                          "cannot stat"))
        return False
    return True


def rename(w, entity, new_name: str):
    """`ok` -- rename on disk, then move the world along with it.

    The entity does not change -- it is the same file, now called
    something else, still carrying whatever any rule had concluded about
    it. Only its `Entry` is replaced, and the folder's index re-keyed.
    `False` if the OS refused (`Failed` is spawned then). Spawns
    `Renamed`, an occasion, for whichever rule reports it.
    """
    entry = w.get(entity, fs.Entry)
    path = w.get(entry.folder, fs.Folder).path
    try:
        os.rename(os.path.join(path, entry.name), os.path.join(path, new_name))
    except OSError as e:
        w.spawn(fs.Failed("rename %s to %s" % (entry.name, new_name),
                          _reason(e)))
        return False
    contents = w.get(entry.folder, fs.Contents)
    by_name = dict(contents.by_name)
    by_name.pop(entry.name, None)
    by_name[new_name] = entity
    was = entry.name
    # Both `replace`: the entity already carries an `Entry` (the one being
    # renamed) and `entry.folder` already carries a `Contents` -- `attach`
    # would leave the pre-rename value standing alongside the new one.
    w.replace(entry.folder, fs.Contents(by_name))
    w.replace(entity, fs.Entry(entry.folder, new_name))
    _observe(w, path, entity, new_name)
    w.spawn(fs.Renamed(entity, was))
    return True
