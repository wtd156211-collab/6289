import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DICT_A = """\
# comment line
配置管理	98000
配置	92000
管理	96500
GitHub	66000
github	66000
"""

DICT_B = """\
配置管理	100000
配置项	57000
"""

QUERIES = """\
# comment
配置管里

github
龘龘龘
"""


def write(tmp, name, text):
    path = os.path.join(tmp, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return path


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "typofix", *args],
        cwd=ROOT, capture_output=True, text=True, timeout=120)


class TestCandidatesCli(unittest.TestCase):
    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            ddir = os.path.join(tmp, "dicts")
            write(tmp, "dicts/a.tsv", DICT_A)
            write(tmp, "dicts/b.tsv", DICT_B)
            proc = run_cli("candidates", "--dict-dir", ddir,
                           "--query", "配置管里")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(payload["query"], "配置管里")
            self.assertEqual(payload["stats"]["cost_limit"], 8)
            self.assertEqual(payload["stats"]["top"], 8)
            self.assertEqual(payload["stats"]["entries"], 5)
            words = [c["word"] for c in payload["candidates"]]
            self.assertEqual(words[0], "配置管理")  # merged freq 100000 wins
            self.assertIn("配置", words)
            for cand in payload["candidates"]:
                self.assertEqual(
                    cand["score"],
                    40 * cand["parts"]["freq"]
                    + 45 * cand["parts"]["distance"]
                    + 15 * cand["parts"]["prefix"])

    def test_dict_flag_and_casefold(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "d.tsv", DICT_A)
            proc = run_cli("candidates", "--dict", path, "--query", "GITHUB")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            payload = json.loads(proc.stdout)
            # Equal-frequency casings collapse to the codepoint-smallest.
            self.assertEqual(payload["candidates"][0]["word"], "GitHub")
            self.assertEqual(payload["candidates"][0]["cost"], 0)

    def test_requires_dict(self):
        proc = run_cli("candidates", "--query", "x")
        self.assertNotEqual(proc.returncode, 0)


class TestWebCli(unittest.TestCase):
    def test_data_json_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "dicts/a.tsv", DICT_A)
            write(tmp, "dicts/b.tsv", DICT_B)
            qdir = os.path.join(tmp, "queries")
            write(tmp, "queries/q1.txt", QUERIES)
            out = os.path.join(tmp, "web", "data.json")
            proc = run_cli("web", "--dict-dir", os.path.join(tmp, "dicts"),
                           "--queries-dir", qdir, "--out", out,
                           "--rounds", "2")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            data = json.load(open(out, encoding="utf-8"))

            self.assertEqual(data["dict"]["files"], ["a.tsv", "b.tsv"])
            self.assertEqual(data["dict"]["entries"], 5)
            self.assertEqual(data["dict"]["max_freq"], 100000)
            self.assertGreater(data["dict"]["load_ms"], 0)
            self.assertGreater(data["dict"]["memory_mb"], 0)

            self.assertEqual([q["query"] for q in data["queries"]],
                             ["配置管里", "github", "龘龘龘"])
            zero = data["queries"][2]
            self.assertEqual(zero["candidates"], [])
            self.assertEqual(zero["total_matched"], 0)
            for q in data["queries"]:
                self.assertIn("elapsed_ms", q)
                self.assertLessEqual(len(q["candidates"]), 8)

            bench = data["benchmark"]
            self.assertEqual(bench["rounds"], 2)
            self.assertEqual(bench["count"], 3)
            self.assertLessEqual(bench["p50_ms"], bench["p95_ms"])
            self.assertLessEqual(bench["p95_ms"], bench["max_ms"])


if __name__ == "__main__":
    unittest.main()
