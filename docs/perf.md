# 性能实测

机器：当前环境（Linux，Python 3.13，单进程、单线程、串行查询）。
数据：`samples/dicts` 全量合并后 310,139 条，`samples/queries` 10,147 条。

## 结果（以 `web/data.json` 为准）

| 指标 | 实测 | 预算 |
| --- | --- | --- |
| 加载 + 建索引（不含 trace 开销） | ≈ 2.7 s | ≤ 15 s |
| `tracemalloc` 峰值（加载 + 建索引） | ≈ 207 MiB | ≤ 400 MiB |
| p50（10 轮 × 10,147 条，首条预热不计时） | ≈ 0.52 ms | — |
| p95 | ≈ 2.30 ms | ≤ 200 ms |
| 单次最坏 | ≈ 28 ms | ≤ 800 ms |

最慢的一条是 `keyboard.txt` 里的 `keybosrd`（纯 ASCII、多个邻键位置同时
产生变体），约 25–28 ms；长串 `abcdefghijklmnopqrst` 走等长桶扫描，
约 25 ms。中文查询多为亚毫秒级。

## 说明

`tracemalloc` 会显著拖慢分配密集的建索引过程（本仓约 8 倍，
开着 trace 加载约 21 s），它只影响墙钟计时、不影响峰值数值，因此
`python -m typofix web` 分两遍加载：第一遍记 `load_ms`（不开 trace），
第二遍开 `tracemalloc` 只取 `memory_mb`，查询统一用第一遍的引擎。

## 复现命令

```sh
# 单条查询（JSON 打到 stdout，耗时在 stats.elapsed_ms）
python -m typofix candidates --dict-dir samples/dicts --query 配置管里

# 生成页面数据（内部完成 10 轮基准）
python -m typofix web --dict-dir samples/dicts \
  --queries-dir samples/queries --out web/data.json

# 看页面
python -m http.server 8000 --directory web
# 浏览器打开 http://localhost:8000/

# 测试（含全量词典 × 全部查询对 samples/expected 的顺序敏感校验）
python -m unittest discover -s tests -v
```

## 抽样复算

`tests/test_engine.py` 中 `TestAgainstBruteForce` 对 core+common 词典
逐条跑无早退的全量 DP 作为参考实现，比较候选序列、`total_matched` 与
`cost / score / 三项分解`；`TestExpectedFiles` 在 31 万全量词典上把
10,147 条查询的候选序列与 `samples/expected` 逐条对齐校验。
