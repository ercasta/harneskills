"""Where a session's corpora come from when nobody types a path.

    ~/.config/harneskills/config

One folder per line, loaded in the order written; every `*.ugm` file
directly inside each one is loaded, alphabetically within the folder. A
line whose first non-blank character is `#` is a comment; a blank line is
nothing. `~` and `$VARS` are expanded, and a relative folder is taken
relative to the config file's own directory -- not the working directory,
because the thing most likely to read this file is a service whose cwd is
not yours.

The sweep is deliberately ONE level deep. `../ugm/ugm/rules/` and
`../ugm/ugm/rules/fs/` are different corpora that happen to nest, and a
harness that quietly pulled in the second because you asked for the first
would be choosing your rules for you. List the subfolder if you want it.

This module reads a path list and stats the filesystem. It does not open a
`.ugm` file, know what one contains, or import UGM -- loading is
`__main__`'s job, and the ordering above is the whole of the contract
between them.
"""

import os

APP = "harneskills"


def config_path() -> str:
    """The config file this session would read.

    `$HARNESKILLS_CONFIG` wins outright (a full path to a file, so a service
    or a test can point somewhere else). Otherwise the XDG location, which
    on a stock box is `~/.config/harneskills/config`.
    """
    override = os.environ.get("HARNESKILLS_CONFIG")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config")
    return os.path.join(os.path.expanduser(base), APP, "config")


def read_folders(path=None) -> "list[str]":
    """The folders named in `path`, expanded and absolute, in file order.

    No file is not an error -- it is the ordinary case for someone who has
    never written one, and it means "no standing corpora", exactly as if
    the file were empty.
    """
    if path is None:
        path = config_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = fh.read()
    except (FileNotFoundError, NotADirectoryError):
        return []
    here = os.path.dirname(os.path.abspath(path))
    folders = []
    for line in raw.splitlines():
        # Only a leading `#` comments a line out. `#` is a legal character
        # in a directory name, and stripping from the first one anywhere
        # would silently truncate a real path into a shorter real path.
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        folder = os.path.expanduser(os.path.expandvars(line.strip()))
        folders.append(os.path.normpath(os.path.join(here, folder)))
    return folders


def corpus_files(folders) -> "tuple[list[str], list[str]]":
    """Every `*.ugm` directly in each folder, plus what went wrong.

    Returns `(paths, problems)`. A folder that is missing, or is there but
    holds no corpus, is a `problem` string and not an exception: a config
    file outliving one of its checkouts should cost you that folder, not
    the session. The same file reached through two folders (a symlink, a
    bind mount) is loaded once -- loading a rule twice is not always
    harmless, and the second load is never what was meant.
    """
    paths, problems, seen = [], [], set()
    for folder in folders:
        if not os.path.isdir(folder):
            problems.append("%s: no such folder" % folder)
            continue
        try:
            names = sorted(n for n in os.listdir(folder) if n.endswith(".ugm"))
        except OSError as e:
            problems.append("%s: %s" % (folder, e.strerror or e))
            continue
        if not names:
            problems.append("%s: no .ugm files" % folder)
            continue
        for name in names:
            path = os.path.join(folder, name)
            key = os.path.realpath(path)
            if key in seen:
                continue
            seen.add(key)
            paths.append(path)
    return paths, problems
