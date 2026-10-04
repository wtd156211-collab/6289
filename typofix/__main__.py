"""Command line interface: `python -m typofix candidates|web`."""

import argparse
import json
import math
import sys
import time
import tracemalloc
from pathlib import Path

from .engine import DEFAULT_MAX_COST, DEFAULT_TOP, Engine, timed_candidates


def resolve_dict_files(dict_paths, dict_dir):
    files = list(dict_paths or [])
    if dict_dir:
        files.extend(
            sorted(Path(dict_dir).glob("*.tsv"),
                   key=lambda p: p.name)
        )
    return [Path(p) for p in files]


def read_queries(queries_dir):
    """Returns [(file_name, query_text)] in filename/line order."""
    queries = []
    for path in sorted(Path(queries_dir).glob("*.txt"),
                       key=lambda p: p.name):
        with open(path, encoding="utf-8-sig") as fh:
            for line in fh:
                text = line.strip()
                if not text or text.startswith("#"):
                    continue
                queries.append((path.name, text))
    return queries


def percentile(sorted_values, pct):
    """Nearest-rank percentile on an ascending list."""
    rank = math.ceil(pct * len(sorted_values))
    return sorted_values[max(0, rank - 1)]


def cmd_candidates(ns):
    files = resolve_dict_files(ns.dict, ns.dict_dir)
    if not files:
        raise SystemExit("error: provide --dict-dir and/or --dict")
    engine = Engine.from_files(files)
    candidates, total, elapsed_ms = timed_candidates(
        engine, ns.query, max_cost=ns.max_cost, top=ns.top)
    payload = {
        "query": ns.query,
        "candidates": candidates,
        "stats": {
            "entries": engine.entry_count,
            "cost_limit": ns.max_cost,
            "top": ns.top,
            "elapsed_ms": round(elapsed_ms, 3),
        },
    }
    print(json.dumps(payload, ensure_ascii=False))


def cmd_web(ns):
    files = resolve_dict_files(ns.dict, ns.dict_dir)
    if not files:
        raise SystemExit("error: provide --dict-dir and/or --dict")
    # Time the load without instrumentation; measure the tracemalloc peak
    # in a second identical pass (tracing skews wall time heavily).
    t0 = time.perf_counter()
    engine = Engine.from_files(files)
    load_ms = (time.perf_counter() - t0) * 1000.0
    tracemalloc.start()
    traced = Engine.from_files(files)
    peak_bytes = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    del traced

    queries = read_queries(ns.queries_dir)

    # Warm up once; the first query is excluded from latency stats.
    if queries:
        engine.candidates(queries[0][1], max_cost=ns.max_cost, top=ns.top)

    results = []
    all_elapsed = []
    for rnd in range(ns.rounds):
        for _, query in queries:
            cands, total, elapsed_ms = timed_candidates(
                engine, query, max_cost=ns.max_cost, top=ns.top)
            all_elapsed.append(elapsed_ms)
            if rnd == 0:
                results.append({
                    "query": query,
                    "candidates": cands,
                    "total_matched": total,
                    "elapsed_ms": round(elapsed_ms, 3),
                })

    ordered = sorted(all_elapsed)
    benchmark = {
        "rounds": ns.rounds,
        "count": len(queries),
        "p50_ms": round(percentile(ordered, 0.50), 3),
        "p95_ms": round(percentile(ordered, 0.95), 3),
        "max_ms": round(ordered[-1], 3) if ordered else 0.0,
    }
    payload = {
        "dict": {
            "files": [p.name for p in files],
            "entries": engine.entry_count,
            "max_freq": engine.max_freq,
            "load_ms": round(load_ms, 3),
            "memory_mb": round(peak_bytes / (1024 ** 2), 1),
        },
        "queries": results,
        "benchmark": benchmark,
    }
    out_path = Path(ns.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")
    print(f"wrote {out_path} ({len(queries)} queries, "
          f"{benchmark['p95_ms']} ms p95)", file=sys.stderr)


def build_parser():
    parser = argparse.ArgumentParser(prog="typofix")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("candidates", help="print JSON candidates for a query")
    p.add_argument("--dict-dir")
    p.add_argument("--dict", action="append", help="dictionary .tsv path")
    p.add_argument("--query", required=True)
    p.add_argument("--max-cost", type=int, default=DEFAULT_MAX_COST,
                   choices=range(1, 9), metavar="1-8")
    p.add_argument("--top", type=int, default=DEFAULT_TOP,
                   choices=range(1, 51), metavar="1-50")
    p.set_defaults(func=cmd_candidates)

    p = sub.add_parser("web", help="generate web/data.json")
    p.add_argument("--dict-dir")
    p.add_argument("--dict", action="append", help="dictionary .tsv path")
    p.add_argument("--queries-dir", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--max-cost", type=int, default=DEFAULT_MAX_COST,
                   choices=range(1, 9), metavar="1-8")
    p.add_argument("--top", type=int, default=DEFAULT_TOP,
                   choices=range(1, 51), metavar="1-50")
    p.add_argument("--rounds", type=int, default=10)
    p.set_defaults(func=cmd_web)
    return parser


def main(argv=None):
    parser = build_parser()
    ns = parser.parse_args(argv)
    ns.func(ns)


if __name__ == "__main__":
    main()
