// Read-only dashboard. Every number and the candidate ordering come from
// data.json; nothing is recomputed or reordered in the browser.

const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

function metric(label, value, sub) {
  const card = el("div", "metric");
  card.append(el("div", "label", label), el("div", "value", String(value)));
  if (sub) card.append(el("div", "sub", sub));
  return card;
}

function renderMetrics(data) {
  const d = data.dict;
  const b = data.benchmark;
  const box = document.getElementById("metrics");
  box.replaceChildren();

  box.append(
    metric("词典文件", d.files.length, d.files.join("、")),
    metric("词条数", d.entries.toLocaleString("en")),
    metric("最大频次", d.max_freq.toLocaleString("en")),
    metric("加载耗时", `${d.load_ms} ms`),
    metric("内存峰值", `${d.memory_mb} MiB`),
    metric("p50 延迟", `${b.p50_ms} ms`, `${b.rounds} 轮 × ${b.count} 条`),
    metric("p95 延迟", `${b.p95_ms} ms`),
    metric("最坏延迟", `${b.max_ms} ms`),
  );

  let slowest = null;
  for (const q of data.queries) {
    if (!slowest || q.elapsed_ms > slowest.elapsed_ms) slowest = q;
  }
  if (slowest) {
    const card = metric(
      "最慢的查询", `${slowest.elapsed_ms} ms`, slowest.query);
    card.classList.add("slow");
    box.append(card);
  }
}

function candidateTable(cands) {
  const table = el("table", "cands");
  const thead = el("thead");
  const hr = el("tr");
  for (const h of ["#", "候选词", "频次", "代价", "总分", "频次项", "距离项", "前缀项"]) {
    hr.append(el("th", "", h));
  }
  thead.append(hr);
  table.append(thead);

  const tbody = el("tbody");
  cands.forEach((c, idx) => {
    const tr = el("tr");
    tr.append(
      el("td", "rank", String(idx + 1)),
      el("td", "word", c.word),
      el("td", null, c.freq.toLocaleString("en")),
      el("td", null, String(c.cost)),
      el("td", "score", String(c.score)),
      el("td", "parts", String(c.parts.freq)),
      el("td", "parts", String(c.parts.distance)),
      el("td", "parts", String(c.parts.prefix)),
    );
    tbody.append(tr);
  });
  table.append(tbody);
  return table;
}

function renderQueries(data) {
  const box = document.getElementById("queries");
  box.replaceChildren();
  for (const item of data.queries) {
    const card = el("div", "query-card");
    if (item.candidates.length === 0) card.classList.add("zero");

    const head = el("div", "query-head");
    head.append(el("div", "query-word", item.query));
    head.append(el("div", "query-meta",
      `耗时 ${item.elapsed_ms} ms · 命中 ${item.total_matched} · 展示 ${item.candidates.length}`));
    if (item.candidates.length === 0) head.append(el("span", "zero-badge", "零命中"));
    card.append(head);

    if (item.candidates.length > 0) card.append(candidateTable(item.candidates));
    box.append(card);
  }
}

async function main() {
  const res = await fetch("data.json", { cache: "no-store" });
  if (!res.ok) throw new Error(`data.json: HTTP ${res.status}`);
  const data = await res.json();
  renderMetrics(data);
  renderQueries(data);
}

main().catch((err) => {
  document.getElementById("queries").append(
    el("div", "query-card zero",
      `加载 data.json 失败：${err.message}。请用 python -m http.server 8000 --directory web 打开。`));
});
