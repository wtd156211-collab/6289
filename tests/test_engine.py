import glob
import os
import random
import unittest
from heapq import nsmallest

from typofix.cost import edit_cost
from typofix.engine import Engine, load_entries, normalize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DICT_DIR = os.path.join(ROOT, "samples", "dicts")
QUERIES_DIR = os.path.join(ROOT, "samples", "queries")
EXPECTED_DIR = os.path.join(ROOT, "samples", "expected")
CORE_COMMON = [os.path.join(DICT_DIR, "core.tsv"),
               os.path.join(DICT_DIR, "common.tsv")]


def brute_force(entries, max_freq, query, max_cost=8, top=8):
    """Reference: scan every entry, exact DP, fixed scoring and ordering."""
    qkey = normalize(query)
    scored = []
    for word, key, freq in entries:
        cost = edit_cost(qkey, key, max_cost)
        if cost > max_cost:
            continue
        lcp = 0
        for a, b in zip(qkey, key):
            if a != b:
                break
            lcp += 1
        f_part = (100 * freq.bit_length()) // max_freq.bit_length()
        d_part = max(0, 100 - 12 * cost)
        p_part = min(100, 25 * lcp)
        score = 40 * f_part + 45 * d_part + 15 * p_part
        scored.append(((-score, -freq, cost, word),
                       (word, cost, score, f_part, d_part, p_part)))
    total = len(scored)
    best = nsmallest(top, scored, key=lambda item: item[0])
    return [item[1] for item in best], total


class TestMergeRules(unittest.TestCase):
    def test_max_freq_and_casefold_dedup(self):
        entries, max_freq = load_entries(CORE_COMMON)
        by_key = {key: (word, freq) for word, key, freq in entries}
        # 'github' appears with 3 casings at equal freq: smallest wins.
        self.assertEqual(by_key["github"], ("GITHUB", 66000))
        # Same casefold key keeps the highest-frequency form.
        self.assertEqual(by_key["配置管理"], ("配置管理", 98000))
        self.assertEqual(max_freq, max(f for _, _, f in entries))

    def test_tie_breaks_on_smaller_word(self):
        entries, _ = load_entries(CORE_COMMON)
        by_key = {key: (word, freq) for word, key, freq in entries}
        # Equal-frequency casings keep the codepoint-smaller form.
        self.assertEqual(by_key["readme"], ("README", 54000))


class TestAgainstBruteForce(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entries, cls.max_freq = load_entries(CORE_COMMON)
        cls.engine = Engine(cls.entries, cls.max_freq)

    def check(self, query, max_cost=8, top=8):
        cands, total = self.engine.candidates(query, max_cost=max_cost, top=top)
        expected, exp_total = brute_force(
            self.entries, self.max_freq, query, max_cost=max_cost, top=top)
        self.assertEqual(total, exp_total, query)
        got = [(c["word"], c["cost"], c["score"], c["parts"]["freq"],
                c["parts"]["distance"], c["parts"]["prefix"]) for c in cands]
        self.assertEqual(got, expected, query)

    def test_handpicked_queries(self):
        for query in ["配置管里", "配置管理", "配置管", "配置管埋", "typofux",
                      "githbu", "recieve", "己经", "周未", "登入", "GitHub",
                      "readme", "龘龘龘", "a", "管", "配", "qw", "配管里",
                      "  配置管理  ", "配置管理　", "配直管理里"]:
            self.check(query)

    def test_cost_limits(self):
        for max_cost in (1, 2, 4, 6, 8):
            self.check("配置管里", max_cost=max_cost)
            self.check("typofux", max_cost=max_cost)

    def test_top_limits(self):
        for top in (1, 3, 8, 20, 50):
            self.check("己经", top=top)

    def test_random_queries(self):
        rng = random.Random(20261004)
        words = [w for w, _, _ in self.entries]
        for _ in range(60):
            base = rng.choice(words)
            if base and rng.random() < 0.7:
                pos = rng.randrange(len(base))
                query = base[:pos] + rng.choice("理里己已未末abc") + base[pos + 1:]
            else:
                query = base
            self.check(query)


@unittest.skipUnless(os.path.isdir(EXPECTED_DIR), "samples/expected missing")
class TestExpectedFiles(unittest.TestCase):
    """Acceptance: full merged dictionary, every sample query, order-sensitive."""

    @classmethod
    def setUpClass(cls):
        paths = sorted(glob.glob(os.path.join(DICT_DIR, "*.tsv")))
        cls.engine = Engine.from_files(paths)

    def test_all_queries_match_expected(self):
        failures = []
        for qpath in sorted(glob.glob(os.path.join(QUERIES_DIR, "*.txt"))):
            name = os.path.basename(qpath)
            with open(qpath, encoding="utf-8") as fh:
                queries = [s for line in fh
                           if (s := line.strip()) and not s.startswith("#")]
            epath = os.path.join(EXPECTED_DIR, name)
            with open(epath, encoding="utf-8") as fh:
                expected = [line.rstrip("\n") for line in fh
                            if not line.lstrip().startswith("#")]
            self.assertEqual(len(queries), len(expected), name)
            for query, exp_line in zip(queries, expected):
                cands, _ = self.engine.candidates(query)
                got = [c["word"] for c in cands]
                exp = exp_line.split("\t") if exp_line else []
                if got != exp:
                    failures.append((name, query, got, exp))
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
