"""Weighted edit-cost model (restricted Damerau, a.k.a. OSA).

Costs (see README):
    substitution, any char                     -> 4
    substitution between QWERTY neighbor keys  -> 2 (ASCII letters only)
    insertion / deletion of one char           -> 3
    transposition of two adjacent chars        -> 2

Transposed characters may not take part in further edits (restricted
Damerau / optimal string alignment semantics).
"""

SUB_DEFAULT = 4
SUB_NEIGHBOR = 2
INDEL = 3
TRANSPOSITION = 2

# QWERTY neighborhood, lowercase ASCII letters only (from README).
_NEIGHBOR_TABLE = {
    "q": "asw", "w": "adeqs", "e": "dfrsw", "r": "defgt", "t": "fghry",
    "y": "ghjtu", "u": "hijky", "i": "jklou", "o": "iklp", "p": "lo",
    "a": "qswxz", "s": "adeqwxzc", "d": "cefrsvwx", "f": "bcdegrtv",
    "g": "bdfhnrtvy", "h": "bfgjmntuy", "j": "ghikmnuy", "k": "ijlmou",
    "l": "ikop", "z": "asx", "x": "acdsz", "c": "dfsvxz", "v": "bcdfgx",
    "b": "cfghnv", "n": "bghjm", "m": "hjkn",
}


def _build_neighbors():
    neigh = {}
    for key, chars in _NEIGHBOR_TABLE.items():
        neigh.setdefault(ord(key), set()).update(map(ord, chars))
    # The README table has a handful of one-way entries (e.g. g lists d
    # but d does not list g). Physical key adjacency is symmetric, so we
    # take the symmetric closure: a substitution is cheap when either
    # character lists the other as a neighbor.
    for code, others in list(neigh.items()):
        for other in others:
            neigh.setdefault(other, set()).add(code)
    return {code: frozenset(others) for code, others in neigh.items()}


# codepoint -> frozenset of neighbor codepoints
NEIGHBORS = _build_neighbors()
_EMPTY = frozenset()


def substitution_cost(a, b):
    """Cost of replacing char a with char b (str of length 1)."""
    if a == b:
        return 0
    if ord(b) in NEIGHBORS.get(ord(a), _EMPTY):
        return SUB_NEIGHBOR
    return SUB_DEFAULT


def edit_cost(query, word, limit=None):
    """Weighted restricted-Damerau cost between query and word.

    If limit is given, may return any value > limit as soon as the true
    cost is provably above limit (early exit); values <= limit are exact.
    """
    n = len(query)
    m = len(word)
    if limit is not None and abs(n - m) * INDEL > limit:
        return limit + 1
    qcodes = [ord(c) for c in query]
    wcodes = [ord(c) for c in word]
    neigh = [NEIGHBORS.get(c, _EMPTY) for c in qcodes]

    # prev[j] = cost(query[:j], word[:i]) for the current i.
    prevprev = None
    prev = [INDEL * j for j in range(n + 1)]
    prev_min = 0 if n == 0 else 0  # min of row 0 is 0
    wprev = -1
    for i in range(1, m + 1):
        wc = wcodes[i - 1]
        cur = [INDEL * i] + [0] * n
        row_min = cur[0]
        for j in range(1, n + 1):
            qc = qcodes[j - 1]
            if wc == qc:
                sub = 0
            elif wc in neigh[j - 1]:
                sub = SUB_NEIGHBOR
            else:
                sub = SUB_DEFAULT
            best = prev[j] + INDEL
            t = cur[j - 1] + INDEL
            if t < best:
                best = t
            t = prev[j - 1] + sub
            if t < best:
                best = t
            if (prevprev is not None and j >= 2
                    and wprev == qc and wc == qcodes[j - 2]):
                t = prevprev[j - 2] + TRANSPOSITION
                if t < best:
                    best = t
            cur[j] = best
            if best < row_min:
                row_min = best
        if limit is not None and row_min > limit and prev_min + TRANSPOSITION > limit:
            # Future rows can only stay above limit: every entry of the
            # next row is >= min(cur) except transposition terms, which
            # are >= min(prev) + TRANSPOSITION.
            return limit + 1
        prevprev, prev = prev, cur
        prev_min = row_min
        wprev = wc
    return prev[n]
