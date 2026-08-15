const bridge = window.AstrBotPluginPage;
const log = (...a) => console.log("[EarthMC Config]", ...a);
const el = (id) => document.getElementById(id);

let allConfigs = [];
let currentId = "";
let currentType = "group";
let vpThresholds = [];

const msg = el("msg");
function setMsg(text, isErr) {
  msg.textContent = text;
  msg.className = "msg" + (isErr ? " err" : "");
}
const setMsgAnd = (text, isErr) => setMsg(text, isErr);

// ── 配置列表 ─────────────────────

async function refreshList() {
  try {
    allConfigs = (await bridge.apiGet("configs/list")) || [];
  } catch (e) {
    log("加载配置失败:", e.message);
    allConfigs = [];
  }
  const sel = el("configSelect");
  sel.innerHTML = '<option value="">-- 选择配置 --</option>';
  allConfigs.forEach((c) => {
    const opt = document.createElement("option");
    opt.value = c.id + "|" + c.type;
    opt.textContent = `${c.type === "friend" ? "私聊" : "群聊"}:${c.id}`;
    sel.appendChild(opt);
  });
}

function selectConfig(id, type) {
  currentId = id;
  currentType = type || "group";
  el("configSelect").value = id + "|" + currentType;
  el("editSection").style.display = "block";
  el("featureSection").style.display = "block";
  el("watchSection").style.display = "block";
  el("editTitle").textContent = `${currentType === "friend" ? "私聊" : "群聊"}:${id}`;
  el("editType").value = currentType;
  el("editId").value = id;

  const c = allConfigs.find((x) => x.id === id && x.type === currentType);
  const f = (c && c.features) || {};
  el("featWatch").checked = f.watch !== false;
  el("featMarket").checked = f.market !== false;
  el("featMap").checked = f.map !== false;
  el("featScanner").checked = f.scanner !== false;
  el("featCommands").checked = f.commands !== false;

  loadWatchStatus();
}

function newConfig() {
  currentId = "";
  el("editSection").style.display = "block";
  el("featureSection").style.display = "block";
  el("watchSection").style.display = "block";
  el("editTitle").textContent = "新建配置";
  el("editType").value = "group";
  el("editId").value = "";
  el("featWatch").checked = true;
  el("featMarket").checked = true;
  el("featMap").checked = true;
  el("featScanner").checked = true;
  el("featCommands").checked = true;
  vpThresholds = [];
  renderWatch();
}

// ── 功能开关 ─────────────────────

el("saveFeatureBtn").addEventListener("click", async () => {
  const id = el("editId").value.trim();
  if (!id) return setMsg("请输入 ID", true);
  const features = {
    watch: el("featWatch").checked,
    market: el("featMarket").checked,
    map: el("featMap").checked,
    scanner: el("featScanner").checked,
    commands: el("featCommands").checked,
  };
  try {
    await bridge.apiPost("configs/save", {
      id,
      type: el("editType").value,
      features,
    });
    setMsg("功能开关已保存 ✓");
    currentId = id;
    currentType = el("editType").value;
    await refreshList();
    el("configSelect").value = id + "|" + currentType;
  } catch (e) {
    setMsg("保存失败: " + e.message, true);
  }
});

async function deleteConfig() {
  if (!currentId) return;
  if (!confirm(`确认删除 ${currentType === "friend" ? "私聊" : "群聊"}:${currentId}？`)) return;
  try {
    await bridge.apiPost("configs/del", { id: currentId });
    el("featureSection").style.display = "none";
    el("watchSection").style.display = "none";
    await refreshList();
  } catch (e) {
    setMsg("删除失败: " + e.message, true);
  }
}

// ── Watch 管理 ─────────────────────

async function loadWatchStatus() {
  if (!currentId) return;
  let data;
  try {
    data = await bridge.apiGet("watch/status", { group_id: currentId });
  } catch (e) {
    vpThresholds = [];
    renderWatch();
    return;
  }
  vpThresholds = data && !data.empty ? [...(data.vp_thresholds || [])] : [];
  window._watchData = data || {};
  renderWatch();
}

function renderWatch() {
  renderVp();
  renderPlayers();
  renderTowns();
}

function renderVp() {
  const box = el("vpList");
  box.innerHTML = "";
  if (!vpThresholds.length) box.innerHTML = '<div class="empty">未设置 VP 提醒</div>';
  vpThresholds.forEach((t, i) => {
    const line = document.createElement("div");
    line.className = "threshold-line";
    const input = document.createElement("input");
    input.type = "number";
    input.value = t;
    input.min = "1";
    input.addEventListener("change", () => {
      const v = parseInt(input.value);
      vpThresholds[i] = isNaN(v) || v < 1 ? 0 : v;
    });
    const btn = document.createElement("button");
    btn.className = "xbtn";
    btn.textContent = "×";
    btn.addEventListener("click", () => {
      vpThresholds.splice(i, 1);
      renderVp();
    });
    line.append(input, btn);
    box.appendChild(line);
  });
}

function renderPlayers() {
  const box = el("playerList");
  box.innerHTML = "";
  const players = (window._watchData && window._watchData.players) || {};
  const keys = Object.keys(players);
  if (!keys.length) box.innerHTML = '<div class="empty">未添加玩家</div>';
  keys.forEach((name) => {
    const row = document.createElement("div");
    row.className = "row";
    const on = players[name];
    row.innerHTML = `<span class="name">${escapeHtml(name)}</span>
      <span class="meta ${on ? "on" : "off"}">${on ? "🟢 在线" : "🔴 离线"}</span>`;
    const btn = document.createElement("button");
    btn.className = "xbtn";
    btn.textContent = "×";
    btn.addEventListener("click", () => delPlayer(name));
    row.appendChild(btn);
    box.appendChild(row);
  });
}

function renderTowns() {
  const box = el("townList");
  box.innerHTML = "";
  const towns = (window._watchData && window._watchData.towns) || {};
  const keys = Object.keys(towns);
  if (!keys.length) box.innerHTML = '<div class="empty">未添加城镇</div>';
  keys.forEach((name) => {
    const row = document.createElement("div");
    row.className = "row";
    const t = towns[name];
    row.innerHTML = `<span class="name">${escapeHtml(name)}</span>
      <span class="meta">${t.resident_count ?? "?"}人 ${t.blocks ?? "?"}/${t.maxBlocks ?? "?"}块</span>`;
    const btn = document.createElement("button");
    btn.className = "xbtn";
    btn.textContent = "×";
    btn.addEventListener("click", () => delTown(name));
    row.appendChild(btn);
    box.appendChild(row);
  });
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

el("vpAdd").addEventListener("click", () => {
  const v = parseInt(el("vpInput").value);
  if (!isNaN(v) && v > 0 && !vpThresholds.includes(v)) {
    vpThresholds.push(v);
    el("vpInput").value = "";
    renderVp();
  }
});

el("vpSave").addEventListener("click", async () => {
  if (!currentId) return setMsg("请先选择/新建配置", true);
  const th = vpThresholds.filter((t) => t > 0);
  try {
    const res = await bridge.apiPost("watch/vp/save", { group_id: currentId, type: currentType, thresholds: th });
    vpThresholds = res.thresholds || th;
    setMsg("VP 阈值已保存 ✓");
    renderVp();
  } catch (e) {
    setMsg("保存失败: " + e.message, true);
  }
});

el("playerAdd").addEventListener("click", async () => {
  if (!currentId) return setMsg("请先选择/新建配置", true);
  const name = el("playerInput").value.trim();
  if (!name) return;
  try {
    await bridge.apiPost("watch/player/add", { group_id: currentId, type: currentType, name });
    el("playerInput").value = "";
    setMsg("已添加玩家 ✓");
    await loadWatchStatus();
  } catch (e) {
    setMsg("添加失败: " + (e.message || "玩家不存在"), true);
  }
});

async function delPlayer(name) {
  if (!currentId) return;
  try {
    await bridge.apiPost("watch/player/del", { group_id: currentId, type: currentType, name });
    await loadWatchStatus();
  } catch (e) {
    setMsg("删除失败: " + e.message, true);
  }
}

el("townAdd").addEventListener("click", async () => {
  if (!currentId) return setMsg("请先选择/新建配置", true);
  const name = el("townInput").value.trim();
  if (!name) return;
  try {
    await bridge.apiPost("watch/town/add", { group_id: currentId, type: currentType, name });
    el("townInput").value = "";
    setMsg("已添加城镇 ✓");
    await loadWatchStatus();
  } catch (e) {
    setMsg("添加失败: " + (e.message || "城镇不存在"), true);
  }
});

async function delTown(name) {
  if (!currentId) return;
  try {
    await bridge.apiPost("watch/town/del", { group_id: currentId, type: currentType, name });
    await loadWatchStatus();
  } catch (e) {
    setMsg("删除失败: " + e.message, true);
  }
}

el("offBtn").addEventListener("click", async () => {
  if (!currentId) return setMsg("请先选择/新建配置", true);
  if (!confirm(`确认关闭 ${currentId} 的全部监控？`)) return;
  try {
    await bridge.apiPost("watch/off", { group_id: currentId });
    vpThresholds = [];
    setMsg("已关闭全部监控 ✓");
    await loadWatchStatus();
  } catch (e) {
    setMsg("操作失败: " + e.message, true);
  }
});

// ── 初始化 ─────────────────────

try {
  await bridge.ready();
  log("bridge 就绪");
} catch (e) {
  log("bridge 失败:", e.message);
}

el("configSelect").addEventListener("change", (e) => {
  const parts = e.target.value.split("|");
  if (parts[0]) selectConfig(parts[0], parts[1]);
});
el("newBtn").addEventListener("click", newConfig);
el("delBtn").addEventListener("click", deleteConfig);

await refreshList();
if (allConfigs.length > 0) {
  selectConfig(allConfigs[0].id, allConfigs[0].type);
} else {
  newConfig();
}
