"""Candidate retrieval engine.

Index: SymSpell-style deletion signatures. Every dictionary key contributes
all strings obtainable by deleting 0, 1 or 2 characters; a query looks up
the same signatures of itself and of its 1- and 2-cheap-op variants.

Why this is complete: with the README cost table, a "cheap" op
(transposition or QWERTY-neighbor substitution) costs 2, an indel 3 and
any other substitution 4, so cost <= 8 allows at most 4 ops. Counting
ops: 0-2 ops are covered directly, since unit distance <= 2 guarantees a
common delete-<=2 signature on both sides. Any 3-op combination within
budget contains a cheap op, and any 4-op combination consists of cheap
ops only; applying one (resp. two) of those cheap ops to the query first
leaves a residual of at most 2 ops, again covered by the signatures.
Every candidate found is verified with the exact DP, so the result is
identical to scanning the whole dictionary.
"""

import time
from array import array
from bisect import bisect_left
from heapq import nsmallest

from .cost import NEIGHBORS, edit_cost

HASH_BITS = 44
HASH_MASK = (1 << HASH_BITS) - 1
ID_BITS = 19
ID_MASK = (1 << ID_BITS) - 1
SHARD_BITS = 6
SHARDS = 1 << SHARD_BITS
SHARD_SHIFT = HASH_BITS - SHARD_BITS
LOW_MASK = (1 << SHARD_SHIFT) - 1

DEFAULT_MAX_COST = 8
DEFAULT_TOP = 8
MAX_TOP = 50


def normalize(text):
    """Normalization shared by queries and entries: strip, then casefold."""
    return text.strip().casefold()


def load_entries(paths):
    """Load and merge dictionaries. Returns (entries, max_freq) where
    entries is a list of (word, key, freq) sorted by key."""
    merged = {}
    for path in paths:
        with open(path, encoding="utf-8-sig") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                word, sep, freq_s = line.rpartition("\t")
                if not sep:
                    raise ValueError(f"{path}:{lineno}: missing TAB separator")
                word = word.strip()
                try:
                    freq = int(freq_s.strip())
                except ValueError:
                    raise ValueError(f"{path}:{lineno}: bad frequency {freq_s!r}")
                if freq <= 0:
                    raise ValueError(f"{path}:{lineno}: frequency must be positive")
                if not word:
                    continue
                key = word.casefold()
                cur = merged.get(key)
                if cur is None or freq > cur[0] or (freq == cur[0] and word < cur[1]):
                    merged[key] = (freq, word)
    entries = sorted((word, key, freq) for key, (freq, word) in merged.items())
    max_freq = max((freq for _, _, freq in entries), default=1)
    return entries, max_freq


def _deletes2(s):
    """All strings obtainable from s by deleting 0, 1 or 2 chars."""
    yield s
    n = len(s)
    for i in range(n):
        yield s[:i] + s[i + 1:]
    for i in range(n):
        si = s[:i] + s[i + 1:]
        for j in range(i, n - 1):
            yield si[:j] + si[j + 1:]


def _cheap_ops(s):
    """All cheap (cost 2) edit ops on s as (start, end, replacement).

    A transposition at i spans {i, i+1}; a neighbor substitution at i
    spans {i}. Only ASCII letters have neighbor substitutions.
    """
    ops = []
    for i in range(len(s) - 1):
        ops.append((i, i + 2, s[i + 1] + s[i]))
    for i, ch in enumerate(s):
        for nb in NEIGHBORS.get(ord(ch), ()):
            ops.append((i, i + 1, chr(nb)))
    return ops


def _apply_op(s, op):
    start, end, repl = op
    return s[:start] + repl + s[end:]


class Engine:
    def __init__(self, entries, max_freq):
        if len(entries) > ID_MASK:
            raise ValueError("dictionary too large for the index")
        self.words = [w for w, _, _ in entries]
        # Reuse the word object when casefold is a no-op to save memory.
        self.keys = [w if k == w else k for w, k, _ in entries]
        self.freqs = array("i", [f for _, _, f in entries])
        self.max_freq = max_freq
        bits = max_freq.bit_length()
        self.freq_parts = array("i", [(100 * f.bit_length()) // bits for f in self.freqs])
        self.entry_count = len(entries)
        self._shards = [array("q") for _ in range(SHARDS)]
        by_length = {}
        for eid, key in enumerate(self.keys):
            by_length.setdefault(len(key), []).append(eid)
        self._by_length = {n: array("i", ids) for n, ids in by_length.items()}
        self._build_index()

    @classmethod
    def from_files(cls, paths):
        entries, max_freq = load_entries(paths)
        return cls(entries, max_freq)

    def _build_index(self):
        shards = self._shards
        for eid, key in enumerate(self.keys):
            n = len(key)
            h = hash(key) & HASH_MASK
            shards[h >> SHARD_SHIFT].append(((h & LOW_MASK) << ID_BITS) | eid)
            for i in range(n):
                si = key[:i] + key[i + 1:]
                h = hash(si) & HASH_MASK
                shards[h >> SHARD_SHIFT].append(((h & LOW_MASK) << ID_BITS) | eid)
                for j in range(i, n - 1):
                    h = hash(si[:j] + si[j + 1:]) & HASH_MASK
                    shards[h >> SHARD_SHIFT].append(((h & LOW_MASK) << ID_BITS) | eid)
        self._shards = [array("q", sorted(shard)) for shard in shards]

    def _lookup(self, h, out):
        shard = self._shards[h >> SHARD_SHIFT]
        lo = (h & LOW_MASK) << ID_BITS
        i = bisect_left(shard, lo)
        j = bisect_left(shard, lo + (1 << ID_BITS))
        for k in range(i, j):
            out.add(shard[k] & ID_MASK)

    def _candidate_ids(self, qkey):
        ids = set()
        seen = set()
        n = len(qkey)
        ops = _cheap_ops(qkey)
        # The 2-cheap-op layer only produces candidates of length exactly n
        # (4 in-budget ops are always length-preserving). When the length-n
        # bucket is smaller than the variant explosion, scan it directly.
        npairs = len(ops) * (len(ops) - 1) // 2
        bucket = self._by_length.get(n)
        scan_bucket = False
        if npairs:
            if bucket is None:
                # No length-n words at all, so no 4-cheap-op candidates.
                scan_bucket = True
            else:
                deletes_count = 1 + n + n * (n - 1) // 2
                if len(bucket) * 3 * (n + 1) < npairs * deletes_count:
                    scan_bucket = True
                    ids.update(bucket)
        variants = [qkey]
        for op in ops:
            variants.append(_apply_op(qkey, op))
        if not scan_bucket:
            for a in range(len(ops)):
                start_a, end_a, _ = ops[a]
                va = variants[1 + a]
                for b in range(a + 1, len(ops)):
                    start_b, _, _ = ops[b]
                    if start_b < end_a:
                        continue
                    variants.append(_apply_op(va, ops[b]))
        for variant in variants:
            for sig in _deletes2(variant):
                h = hash(sig) & HASH_MASK
                if h in seen:
                    continue
                seen.add(h)
                self._lookup(h, ids)
        return ids

    def candidates(self, query, max_cost=DEFAULT_MAX_COST, top=DEFAULT_TOP):
        """Returns (candidates, total_matched). candidates is a list of
        dicts sorted by the fixed ranking rule, truncated to top."""
        if not 1 <= max_cost <= 8:
            raise ValueError("max_cost must be in 1..8")
        if not 1 <= top <= MAX_TOP:
            raise ValueError(f"top must be in 1..{MAX_TOP}")
        qkey = normalize(query)
        n = len(qkey)
        matched = []
        for eid in self._candidate_ids(qkey):
            key = self.keys[eid]
            if abs(len(key) - n) * 3 > max_cost:
                continue
            cost = edit_cost(qkey, key, max_cost)
            if cost <= max_cost:
                matched.append((eid, cost))
        total = len(matched)
        scored = (self._score(eid, cost, qkey) for eid, cost in matched)
        best = nsmallest(top, scored, key=lambda item: item[0])
        return [item[1] for item in best], total

    def _score(self, eid, cost, qkey):
        key = self.keys[eid]
        lcp = 0
        for a, b in zip(qkey, key):
            if a != b:
                break
            lcp += 1
        f_part = self.freq_parts[eid]
        d_part = max(0, 100 - 12 * cost)
        p_part = min(100, 25 * lcp)
        score = 40 * f_part + 45 * d_part + 15 * p_part
        word = self.words[eid]
        freq = self.freqs[eid]
        record = {
            "word": word,
            "freq": freq,
            "cost": cost,
            "score": score,
            "parts": {"freq": f_part, "distance": d_part, "prefix": p_part},
        }
        return ((-score, -freq, cost, word), record)


def timed_candidates(engine, query, max_cost=DEFAULT_MAX_COST, top=DEFAULT_TOP):
    start = time.perf_counter()
    candidates, total = engine.candidates(query, max_cost=max_cost, top=top)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return candidates, total, elapsed_ms
