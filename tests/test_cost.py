import unittest

from typofix.cost import (
    INDEL,
    NEIGHBORS,
    SUB_DEFAULT,
    SUB_NEIGHBOR,
    TRANSPOSITION,
    edit_cost,
    substitution_cost,
)


class TestNeighborTable(unittest.TestCase):
    def test_spot_entries(self):
        self.assertEqual(NEIGHBORS[ord("q")], frozenset(map(ord, "asw")))
        self.assertEqual(NEIGHBORS[ord("p")], frozenset(map(ord, "lo")))
        self.assertEqual(NEIGHBORS[ord("m")], frozenset(map(ord, "hjkn")))
        # Raw table entries are all present...
        self.assertTrue(frozenset(map(ord, "bdfhnrtvy")) <= NEIGHBORS[ord("g")])
        # ...and one-way entries are closed symmetrically (j lists g).
        self.assertIn(ord("j"), NEIGHBORS[ord("g")])

    def test_symmetric(self):
        for code, others in NEIGHBORS.items():
            for other in others:
                self.assertIn(code, NEIGHBORS[other])

    def test_ascii_letters_only(self):
        for code in NEIGHBORS:
            self.assertTrue(ord("a") <= code <= ord("z"))

    def test_substitution_cost(self):
        self.assertEqual(substitution_cost("a", "a"), 0)
        self.assertEqual(substitution_cost("u", "i"), SUB_NEIGHBOR)
        self.assertEqual(substitution_cost("a", "b"), SUB_DEFAULT)
        self.assertEqual(substitution_cost("理", "里"), SUB_DEFAULT)
        self.assertEqual(substitution_cost("1", "2"), SUB_DEFAULT)


class TestEditCost(unittest.TestCase):
    def test_identity_and_empty(self):
        self.assertEqual(edit_cost("配置管理", "配置管理"), 0)
        self.assertEqual(edit_cost("", ""), 0)
        self.assertEqual(edit_cost("", "ab"), 2 * INDEL)
        self.assertEqual(edit_cost("abc", ""), 3 * INDEL)

    def test_readme_examples(self):
        self.assertEqual(edit_cost("配置管里", "配置管理"), SUB_DEFAULT)
        self.assertEqual(edit_cost("githbu", "github"), TRANSPOSITION)
        self.assertEqual(edit_cost("recieve", "receive"), TRANSPOSITION)
        self.assertEqual(edit_cost("typofux", "typofix"), SUB_NEIGHBOR)

    def test_indel_flat_price(self):
        self.assertEqual(edit_cost("配置", "配置管理"), 2 * INDEL)
        self.assertEqual(edit_cost("配置管理", "配置"), 2 * INDEL)
        self.assertEqual(edit_cost("配置管理", "配配置管理"), INDEL)
        self.assertEqual(edit_cost("配置管理", "置管理"), INDEL)

    def test_transposition_is_restricted(self):
        # OSA: transposed chars cannot be edited again, so "ca" -> "abc"
        # cannot use transpose+insert; best is delete + 2 inserts.
        self.assertEqual(edit_cost("ca", "abc"), INDEL * 3)

    def test_prefix_suffix_variants_priced_same(self):
        self.assertEqual(edit_cost("配置管理", "前配置管理"), INDEL)
        self.assertEqual(edit_cost("配置管理", "配置管理后"), INDEL)
        self.assertEqual(edit_cost("配置管理", "配置中管理"), INDEL)

    def test_symmetry(self):
        for a, b in [("配置管里", "配置管理"), ("githbu", "github"),
                     ("abc", "xyz"), ("", "hello"), ("周末", "周未")]:
            self.assertEqual(edit_cost(a, b), edit_cost(b, a))

    def test_limit_early_exit(self):
        # Values above the limit may be capped; values within are exact.
        self.assertGreater(edit_cost("abcdefgh", "wxyz", 8), 8)
        self.assertEqual(edit_cost("配置管里", "配置管理", 8), SUB_DEFAULT)
        self.assertGreater(edit_cost("aaaaaaaaaa", "bbbbbbbbbb", 3), 3)
        for limit in range(1, 9):
            got = edit_cost("配置管里", "配置管理", limit)
            if limit >= SUB_DEFAULT:
                self.assertEqual(got, SUB_DEFAULT)
            else:
                self.assertGreater(got, limit)


if __name__ == "__main__":
    unittest.main()
