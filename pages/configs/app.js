const bridge = window.AstrBotPluginPage;
const log = (...a) => console.log("[EarthMC Config]", ...a);
const el = (id) => document.getElementById(id);

let allConfigs = [];
let currentId = "";
let currentType = "group";
let vpThresholds = [];
let vpAt = [];
let vpAtLines = [];
let vpDndStart = "";
let vpDndEnd = "";

// ── 未保存更改追踪 ─────────────
let featureDirty = false;   // 功能开关改动未保存
let vpDirty = false;        // VP 提醒设置（阈值/@名单/免打扰）改动未保存
const isDirty = () => featureDirty || vpDirty;
function markDirty(area) {
  if (area === "vp") vpDirty = true;
  else featureDirty = true;
  updateDirtyBadge();
}
function markClean(area) {
  if (area === "vp") vpDirty = false;
  else featureDirty = false;
  updateDirtyBadge();
}
function updateDirtyBadge() {
  el("dirtyBadge").style.display = isDirty() ? "inline-block" : "none";
}
async function confirmDiscard() {
  return !isDirty() || await confirmDialog("⚠ 有未保存的更改，继续将丢弃。确定？");
}

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

async function selectConfig(id, type) {
  if (!(await confirmDiscard())) return false;
  currentId = id;
  currentType = type || "group";
  lockIdentity();
  el("configSelect").value = id + "|" + currentType;
  el("editSection").style.display = "block";
  el("featureSection").style.display = "block";
  el("vpSection").style.display = "block";
  el("watchSection").style.display = "block";
  el("editTitle").textContent = `${currentType === "friend" ? "私聊" : "群聊"}:${id}`;
  el("editType").value = currentType;
  el("editId").value = id;

  const c = allConfigs.find((x) => x.id === id && x.type === currentType);
  const f = (c && c.features) || {};
  el("featWatch").checked = f.watch !== false;
  el("featMarket").checked = f.market !== false;
  el("featMap").checked = f.map !== false;
  el("featCommands").checked = f.commands !== false;

  featureDirty = false;
  vpDirty = false;
  updateDirtyBadge();
  loadAll();
  return true;
}

function newConfig() {
  openNewModal();
}

// ── 新建配置浮窗 ─────────────────

let newConflict = null;   // 同类型冲突目标（供"打开已有配置"跳转）
let newTypeDup = null;    // 跨类型冲突的既有配置（二次确认用）

function openNewModal() {
  newConflict = null;
  newTypeDup = null;
  el("newOpen").style.display = "none";
  el("newMsg").textContent = "";
  el("newId").value = "";
  el("newModal").style.display = "flex";
  el("newId").focus();
}

function closeNewModal() {
  el("newModal").style.display = "none";
}

function lockIdentity() {
  el("editType").disabled = true;
  el("editId").readOnly = true;
}

async function enterConfig(id, type) {
  if (!(await confirmDiscard())) return false;
  currentId = id;
  currentType = type;
  lockIdentity();
  el("configSelect").value = "";
  el("editSection").style.display = "block";
  el("featureSection").style.display = "block";
  el("vpSection").style.display = "block";
  el("watchSection").style.display = "block";
  el("editTitle").textContent = `${type === "friend" ? "私聊" : "群聊"}:${id}`;
  el("editType").value = type;
  el("editId").value = id;
  ["featWatch", "featMarket", "featMap", "featCommands"].forEach((fid) => {
    el(fid).checked = true;
  });
  featureDirty = false;
  vpDirty = false;
  updateDirtyBadge();
  loadAll();
  return true;
}

// ── 功能开关 ─────────────────────

["featWatch", "featMarket", "featMap", "featCommands"].forEach((fid) => {
  el(fid).addEventListener("change", () => markDirty("feature"));
});

el("saveFeatureBtn").addEventListener("click", async () => {
  const id = el("editId").value.trim();
  if (!id) return setMsg("请输入 ID", true);
  const features = {
    watch: el("featWatch").checked,
    market: el("featMarket").checked,
    map: el("featMap").checked,
    commands: el("featCommands").checked,
  };
  try {
    await bridge.apiPost("configs/save", {
      id,
      type: el("editType").value,
      features,
    });
    setMsg("功能开关已保存 ✓");
    markClean("feature");
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
  if (!(await confirmDialog(`确认删除 ${currentType === "friend" ? "私聊" : "群聊"}:${currentId}？`))) return;
  try {
    await bridge.apiPost("configs/del", { id: currentId });
    el("featureSection").style.display = "none";
    el("vpSection").style.display = "none";
    el("watchSection").style.display = "none";
    await refreshList();
  } catch (e) {
    setMsg("删除失败: " + e.message, true);
  }
}

// ── 新建浮窗事件 ─────────────────

el("newOk").addEventListener("click", async () => {
  const id = el("newId").value.trim();
  const type = el("newType").value;
  const msg = el("newMsg");
  if (!id) { msg.textContent = "❌ 请输入 ID"; return; }
  if (!/^\d+$/.test(id)) { msg.textContent = "❌ ID 必须为数字（QQ群号或QQ号）"; return; }
  const dup = allConfigs.find((c) => c.id === id);
  if (dup && dup.type === type) {
    newConflict = { id, type };
    msg.textContent = `⚠ 该 ID 已存在（${type === "friend" ? "私聊" : "群聊"}配置）。可点击下方「打开已有配置」。`;
    el("newOpen").style.display = "inline-block";
    return;
  }
  if (dup && dup.type !== type) {
    if (!newTypeDup) {
      newTypeDup = dup;
      msg.textContent = `⚠ 该 ID 已作为${dup.type === "friend" ? "私聊" : "群聊"}配置存在。再次点击「创建」将并存新${type === "friend" ? "私聊" : "群聊"}配置。`;
      return;
    }
  }
  if (await enterConfig(id, type)) closeNewModal();
});

el("newOpen").addEventListener("click", async () => {
  if (!newConflict) return;
  if (await selectConfig(newConflict.id, newConflict.type)) closeNewModal();
});

el("newCancel").addEventListener("click", closeNewModal);

el("newType").addEventListener("change", () => { newTypeDup = null; });

el("newId").addEventListener("input", () => {
  newTypeDup = null;
  newConflict = null;
  el("newOpen").style.display = "none";
});

el("newId").addEventListener("keydown", (e) => {
  if (e.key === "Enter") el("newOk").click();
});

// ── 通用确认浮窗（替代原生 confirm，iframe 环境原生 confirm 会被禁用） ──

let confirmResolve = null;
function confirmDialog(msg, okText = "确认") {
  return new Promise((resolve) => {
    confirmResolve = resolve;
    el("confirmMsg").textContent = msg;
    el("confirmOk").textContent = okText;
    el("confirmModal").style.display = "flex";
  });
}
el("confirmOk").addEventListener("click", () => {
  el("confirmModal").style.display = "none";
  if (confirmResolve) { const r = confirmResolve; confirmResolve = null; r(true); }
});
el("confirmCancel").addEventListener("click", () => {
  el("confirmModal").style.display = "none";
  if (confirmResolve) { const r = confirmResolve; confirmResolve = null; r(false); }
});

// ── Watch 管理 ─────────────────────

// VP 提醒设置（独立于玩家/城镇监控）
async function loadVpStatus() {
  if (!currentId) return;
  let data = null;
  try {
    data = await bridge.apiGet("vp/status", { group_id: currentId });
  } catch (e) {
    log("VP 配置加载失败:", e.message);
  }
  const ok = data && !data.empty;
  vpThresholds = ok ? [...(data.vp_thresholds || [])] : [];
  vpAt = ok ? [...(data.vp_at || [])] : [];
  vpAtLines = ok ? [...(data.vp_at_lines || [])] : [];
  vpDndStart = (data && data.vp_dnd_start) || "";
  vpDndEnd = (data && data.vp_dnd_end) || "";
  el("vpDndStart").value = vpDndStart;
  el("vpDndEnd").value = vpDndEnd;
  vpDirty = false;
  updateDirtyBadge();
  renderVp();
  renderVpAt();
}

// 玩家/城镇监控
async function loadWatchStatus() {
  if (!currentId) return;
  let data = null;
  try {
    data = await bridge.apiGet("watch/status", { group_id: currentId });
  } catch (e) {
    log("监控配置加载失败:", e.message);
  }
  window._watchData = data || {};
  renderPlayers();
  renderTowns();
}

// 两个分区各取所需（切配置时全量刷新）
function loadAll() {
  loadVpStatus();
  loadWatchStatus();
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
      vpAtLines = vpAtLines.filter((x) => x !== t);   // 值变了，旧 @ 标记失效
      markDirty("vp");
    });
    const atCk = document.createElement("input");
    atCk.type = "checkbox";
    atCk.title = "该线触发时 @";
    atCk.checked = vpAtLines.includes(t);
    atCk.addEventListener("change", () => {
      if (atCk.checked) {
        if (!vpAtLines.includes(t)) vpAtLines.push(t);
      } else {
        vpAtLines = vpAtLines.filter((x) => x !== t);
      }
      markDirty("vp");
    });
    const btn = document.createElement("button");
    btn.className = "xbtn";
    btn.textContent = "×";
    btn.addEventListener("click", () => {
      vpThresholds.splice(i, 1);
      vpAtLines = vpAtLines.filter((x) => x !== t);
      markDirty("vp");
      renderVp();
    });
    line.append(input, atCk, btn);
    box.appendChild(line);
  });
}

function renderVpAt() {
  const box = el("vpAtList");
  box.innerHTML = "";
  if (!vpAt.length) box.innerHTML = '<div class="empty">未设置 @ 名单（触发时不 @）</div>';
  vpAt.forEach((qq) => {
    const line = document.createElement("div");
    line.className = "threshold-line";
    const label = document.createElement("span");
    label.className = "name";
    label.textContent = qq;
    const btn = document.createElement("button");
    btn.className = "xbtn";
    btn.textContent = "×";
    btn.addEventListener("click", () => {
      vpAt = vpAt.filter((x) => x !== qq);
      markDirty("vp");
      renderVpAt();
    });
    line.append(label, btn);
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
    row.innerHTML = `<span class="name">${escapeHtml(name)}</span>`;
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
    row.innerHTML = `<span class="name">${escapeHtml(name)}</span>`;
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
    markDirty("vp");
    renderVp();
  }
});

el("vpAtAdd").addEventListener("click", () => {
  const v = parseInt(el("vpAtInput").value);
  if (!isNaN(v) && v > 0 && !vpAt.includes(v)) {
    vpAt.push(v);
    el("vpAtInput").value = "";
    markDirty("vp");
    renderVpAt();
  }
});

el("vpDndOff").addEventListener("click", () => {
  vpDndStart = "";
  vpDndEnd = "";
  el("vpDndStart").value = "";
  el("vpDndEnd").value = "";
  markDirty("vp");
});

el("vpDndStart").addEventListener("change", () => {
  vpDndStart = el("vpDndStart").value || "";
  markDirty("vp");
});
el("vpDndEnd").addEventListener("change", () => {
  vpDndEnd = el("vpDndEnd").value || "";
  markDirty("vp");
});

el("vpSave").addEventListener("click", async () => {
  if (!currentId) return setMsg("请先选择/新建配置", true);
  const th = vpThresholds.filter((t) => t > 0);
  vpDndStart = (el("vpDndStart").value || "").slice(0, 5);
  vpDndEnd = (el("vpDndEnd").value || "").slice(0, 5);
  try {
    const res = await bridge.apiPost("vp/save", {
      group_id: currentId, type: currentType, thresholds: th,
      at: vpAt, at_lines: vpAtLines,
      dnd_start: vpDndStart, dnd_end: vpDndEnd,
    });
    vpThresholds = res.thresholds || th;
    vpAt = res.at || [];
    vpAtLines = res.at_lines || [];
    vpDndStart = res.dnd_start || "";
    vpDndEnd = res.dnd_end || "";
    el("vpDndStart").value = vpDndStart;
    el("vpDndEnd").value = vpDndEnd;
    setMsg("VP 设置已保存 ✓");
    markClean("vp");
    renderVp();
    renderVpAt();
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
  if (!(await confirmDialog(`确认停止监控玩家「${name}」？`))) return;
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
  if (!(await confirmDialog(`确认停止监控城镇「${name}」？`))) return;
  try {
    await bridge.apiPost("watch/town/del", { group_id: currentId, type: currentType, name });
    await loadWatchStatus();
  } catch (e) {
    setMsg("删除失败: " + e.message, true);
  }
}

el("vpOffBtn").addEventListener("click", async () => {
  if (!currentId) return setMsg("请先选择/新建配置", true);
  if (!(await confirmDialog(
        `确认清除 ${currentId} 的 VP 提醒线？\n@ 名单与免打扰将保留。`, "清除"))) return;
  try {
    await bridge.apiPost("vp/off", { group_id: currentId });
    setMsg("VP 提醒线已清除 ✓");
    await loadVpStatus();
  } catch (e) {
    setMsg("操作失败: " + e.message, true);
  }
});

el("offBtn").addEventListener("click", async () => {
  if (!currentId) return setMsg("请先选择/新建配置", true);
  if (!(await confirmDialog(
        `确认关闭 ${currentId} 的玩家/城镇监控？\nVP 提醒将保留。`))) return;
  try {
    await bridge.apiPost("watch/off", { group_id: currentId });
    setMsg("已关闭玩家/城镇监控 ✓");
    await loadWatchStatus();
  } catch (e) {
    setMsg("操作失败: " + e.message, true);
  }
});

// ── 刷新/关页兜底 ─────────────

window.addEventListener("beforeunload", (e) => {
  if (isDirty()) {
    e.preventDefault();
    e.returnValue = "";
  }
});

// ── 初始化 ─────────────────────

try {
  await bridge.ready();
  log("bridge 就绪");
} catch (e) {
  log("bridge 失败:", e.message);
}

el("configSelect").addEventListener("change", async (e) => {
  const parts = e.target.value.split("|");
  if (parts[0]) {
    const ok = await selectConfig(parts[0], parts[1]);
    // 取消"丢弃未保存"时，把下拉恢复到原配置
    if (!ok) el("configSelect").value = currentId ? currentId + "|" + currentType : "";
  }
});
el("newBtn").addEventListener("click", newConfig);
el("delBtn").addEventListener("click", deleteConfig);

await refreshList();
if (allConfigs.length > 0) {
  await selectConfig(allConfigs[0].id, allConfigs[0].type);
} else {
  newConfig();
}
