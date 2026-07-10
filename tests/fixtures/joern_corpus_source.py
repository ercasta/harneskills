# Labeled mutate-during-iteration corpus. Function name prefix = ground truth:
#   pos_*  -> a real MDI bug, the analyzer SHOULD flag it.
#   neg_*  -> safe, the analyzer should STAY SILENT.
#   hard_* -> a real bug we expect to MISS (documented limitation), counted separately.
# Distinct collection names per function so a hazard maps unambiguously to its function.
# (Aliasing `a = xs; for x in xs: a.remove(x)` was formerly a hard_ miss; the `same_as` alias
#  resolution in cpg.py now catches it, so it is a pos_ — see pos_alias_mutate below.)


def pos_list_remove(xs):
    for x in xs:
        xs.remove(x)


def pos_dict_pop(d):
    for k in d:
        d.pop(k)


def pos_set_discard(s):
    for e in s:
        s.discard(e)


def pos_list_append(xs):
    for x in xs:
        xs.append(x)


def pos_nested_inner_mutates_outer(xs, ys):
    for x in xs:
        for y in ys:
            xs.remove(x)


def pos_list_insert(xs):
    for x in xs:
        xs.insert(0, x)


def neg_copy_list(xs):
    for x in list(xs):
        xs.remove(x)


def neg_copy_slice(xs):
    for x in xs[:]:
        xs.remove(x)


def neg_accumulator(xs):
    out = []
    for x in xs:
        out.append(x)
    return out


def neg_other_collection(xs, ys):
    for x in xs:
        ys.remove(x)


def neg_readonly(xs):
    for x in xs:
        print(x)


def neg_comprehension(xs):
    return [x for x in xs if x]


def neg_mutate_before_loop(xs):
    xs.append(1)
    for x in xs:
        print(x)


def pos_nested_inner_mutates_inner(xs, ys):
    for x in xs:
        for y in ys:
            ys.remove(y)          # inner loop mutates the collection IT iterates -> real MDI bug


def pos_alias_mutate(xs):
    alias = xs                    # plain alias (not a copy) -> resolved via `same_as`
    for x in xs:
        alias.remove(x)


def neg_readloop_nested_in_mutating_loop(items):
    # SAFE: the outer loop iterates `items` and appends to a SEPARATE accumulator `acc`; the read-only
    # `for a in acc` is NESTED inside. Pre-fix the outer loop absorbed acc's iterator via `ast_star`
    # (looptmp bound transitively) -> outer appeared to iterate acc -> acc.append false-flagged. Pins the
    # bounded-looptmp fix (finding-real-corpus-django; the django/utils translation/template.py FP shape).
    acc = []
    for it in items:
        acc.append(it)
        for a in acc:
            print(a)
