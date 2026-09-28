# 拼写纠错候选（从 0 实现）

起始环境里只有这份说明和 `samples/` 下的素材：给定一份或多份「词 + 频次」词典，为一条错词查询给出按可信度排序的候选词。引擎用 Python 3.13 标准库实现，包名固定 `typofix`，入口 `python -m typofix`；另外交一个只读展示页（原生 HTML/ES module）。引擎与页面都从零写，不引第三方依赖，不加构建步骤。

## 一、范围

要做：读词典、合并去重；按下面的固定代价口径检索候选；按固定公式打分、按固定规则排序；命令行输出 JSON；批量生成 `web/data.json`；页面按数据渲染每条查询的候选，并给出整轮性能指标。

不做：全角半角与繁简转换；拼音、注音等输入法层转换；分词与句级上下文纠错；词典在线更新与任何网络访问；页面上的交互式编辑（页面只读）；多线程与并发调度（延迟一律按单进程串行查询计）。

## 二、口径与公式

**归一化**：查询与词条都去掉首尾空白，再用 `str.casefold()` 比较；输出与页面一律用词典里的原始词形。同一 casefold 键对应多条词条时只留频次最高的一条，同频留码点序更小的一条。

**编辑代价**（在 casefold 后的串上按最优路径计算；基本操作是插入、删除、替换、相邻换位，换位后两个字符不再参与其它编辑）：

| 操作 | 代价 |
| --- | --- |
| 替换 1 个字符（含所有非 ASCII 字符） | 4 |
| 替换为 QWERTY 邻键（仅 ASCII 字母） | 2 |
| 插入或删除 1 个字符（词首、词尾、词中同价） | 3 |
| 相邻两字符换位 | 2 |

候选 = 合并词典里所有 `cost ≤ 上限` 的词条；上限默认 8，可用 `--max-cost` 在 1–8 之间调整。词首或词尾增删 1–2 个字符得到的**前后缀变体**按同一张表计价，没有折扣也没有额外惩罚，实现不得漏掉这类词条。

**QWERTY 邻域**（只对小写 ASCII 字母生效，其余字符没有邻键；下表每项是 `键:邻键集合`）：

```
q:asw w:adeqs e:dfrsw r:defgt t:fghry y:ghjtu u:hijky i:jklou o:iklp p:lo
a:qswxz s:adeqwxzc d:cefrsvwx f:bcdegrtv g:bdfhnrtvy h:bfgjmntuy j:ghikmnuy
k:ijlmou l:ikop z:asx x:acdsz c:dfsvxz v:bcdfgx b:cfghnv n:bghjm m:hjkn
```

**打分**：三个分项都取 0–100 的整数，总分 = 40×频次项 + 45×距离项 + 15×前缀项，范围 0–10000。

- 频次项 `F = ⌊100 × bit_length(freq) / bit_length(Fmax)⌋`，按二进制位数分档，压掉高频短词对长词的碾压；`Fmax` 是合并后词典的最大频次。
- 距离项 `D = max(0, 100 − 12 × cost)`。
- 前缀项 `P = min(100, 25 × L)`，`L` 是查询与候选的最长公共前缀长度（casefold 后按码点比较）。

**排序**：总分降序 → 频次降序 → 代价升序 → 词条按 Unicode 码点序升序。等频、同代价的候选由最后一级定序，顺序唯一。

**候选上限**：每次最多返回 8 条（`--top` 可调，范围 1–50）；命中不足就返回实际条数，零命中返回空列表。

## 三、数据结构与检索

词条记录 `(词形, 归一键, 频次)`；候选记录 `{word, freq, cost, score, parts:{freq, distance, prefix}}`，批量结果再带 `total_matched` 与 `elapsed_ms`。检索结构自定（签名索引、前缀树、删减索引都可以），硬性约束只有两条：不得漏掉任何 `cost ≤ 上限` 的词条；排序结果必须与逐条比较全量词典得到的结果完全一致。

## 四、输入输出与文件格式

**词典** `samples/dicts/*.tsv`：UTF-8（可带 BOM）。正文行是 `<词>\t<频次>`，频次为正整数；空行与 `#` 开头行忽略。多份词典合并成一张表，同词取最大频次。

**查询** `samples/queries/*.txt`：UTF-8，每行一条查询；空行与 `#` 开头行忽略。

**期望** `samples/expected/<同名>.txt`：忽略注释与空行后与查询逐条对应，每行是该查询的期望候选词，按顺序用制表符连接；期望为空写一个空行。文件用 LF 换行、末尾留一个换行。

**命令行**（实现放仓库根目录的 `typofix/` 包，页面放 `web/`；`web/data.json` 与 `var/` 都是运行期产物，不入库）：

- `python -m typofix candidates --dict-dir samples/dicts --query 配置管里`：往 stdout 打一行 JSON `{"query":…,"candidates":[…],"stats":{"entries":…,"cost_limit":8,"top":8,"elapsed_ms":…}}`。`--dict <路径>` 可重复，与 `--dict-dir`（目录下全部 `*.tsv`，按文件名字典序）等价，两者可以同时给。
- `python -m typofix web --dict-dir samples/dicts --queries-dir samples/queries --out web/data.json`：生成页面数据。

**data.json**：`{"dict":{"files":[…],"entries":…,"max_freq":…,"load_ms":…,"memory_mb":…},"queries":[{"query":…,"candidates":[…],"total_matched":…,"elapsed_ms":…}],"benchmark":{"rounds":…,"count":…,"p50_ms":…,"p95_ms":…,"max_ms":…}}`；`queries` 的顺序等于查询文件名升序、文件内行序。

**页面**：`python -m http.server 8000 --directory web`，浏览器打开 `http://localhost:8000/`。页面只读，数字全部取自 `data.json`，不得在前端重算：顶部指标板列出词典文件、词条数、最大频次、加载耗时、内存占用与 p50/p95/最坏延迟；下方按序渲染每条查询——查询词、候选有序表（词、频次、代价、总分、三项分解），零命中的查询用醒目样式单独标出。

## 五、性能与验收口径

在 `samples/dicts` 全量（30 万余条）上：加载并建好索引 ≤ 15 s、`tracemalloc` 峰值 ≤ 400 MiB；索引就绪后把 `samples/queries` 全部查询连跑 10 轮，p95 ≤ 200 ms、单次最坏 ≤ 800 ms（首次查询不计时）。

判定：

1. 每条查询的候选词序列与 `samples/expected` 对应行逐项一致，顺序敏感，空即空；
2. 随机抽 20 条候选复算，`cost`、`score` 与三项分解和公式一致；
3. 上述加载、内存与延迟达标；
4. 页面能打开，数字与 `data.json` 一致，零命中样式生效。

## 六、样例说明

`samples/dicts/core.tsv` 是手工整理的核心词表，含「登录/登陆」「账号/帐号」等**等频并列词**和「已经/己经」等**形近词**；`samples/dicts/common.tsv` 是常用界面词；`samples/dicts/big.tsv` 最大，30 万条，覆盖大量组合词、形近变体与天然等频项。`samples/queries/` 与 `samples/expected/` 一一对应，覆盖：运营投诉的「配置管里」、键盘邻键与换位（`typofux`、`recieve`、`githbu`、`develpoer`）、形近字（己/已、末/未、村/存）、等频并列（「登入」→ 登录/登陆）、大小写归一（`GitHub`→`github`、`readme`→`README`）、零命中（`龘龘龘`）、长串与代价上限边界。所有查询都在合并后的全量词典上执行；`samples/notes.md` 是现场记录，只描述现象，不构成额外要求。

## 七、待补的文档

实现完成后补 `docs/design.md`（索引结构、复杂度、取舍）和 `docs/perf.md`（本机实测：加载、内存、p50/p95 与复现命令）；页面字段若与本节描述有出入，以 `data.json` 为准并同步更新。
