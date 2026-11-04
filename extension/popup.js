const $ = (id) => document.getElementById(id);
let tabUrl = null;

const SVG_NS = "http://www.w3.org/2000/svg";
const ICONS = {
  video: ["M4 5h11a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z", "m17 10 5-3v10l-5-3"],
  audio: ["M9 18V5l12-2v13", "M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0z", "M21 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z"],
};
function makeIcon(name) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  for (const d of ICONS[name]) {
    const p = document.createElementNS(SVG_NS, "path");
    p.setAttribute("d", d);
    p.setAttribute("fill", "none");
    p.setAttribute("stroke", "currentColor");
    p.setAttribute("stroke-width", "1.5");
    p.setAttribute("stroke-linecap", "round");
    p.setAttribute("stroke-linejoin", "round");
    svg.appendChild(p);
  }
  return svg;
}

function msg(type, extra = {}) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage({ type, ...extra }, (res) => {
      resolve(chrome.runtime.lastError || !res ? { ok: false, error: "通信できません" } : res);
    });
  });
}

function showMessage(text, ok) {
  const m = $("message");
  m.hidden = false;
  m.textContent = text;
  m.className = `message ${ok ? "" : "ng"}`;
}

function setState(text, kind = "", recording = false) {
  $("stateText").textContent = text;
  $("state").className = `state ${kind}`;
  $("rec").hidden = !recording;
}

const STATUS_LABEL = { queued: "待機中", running: "ダウンロード中", post: "変換中", done: "完了", error: "失敗", cancelled: "キャンセル" };

function renderJobs(jobs) {
  const ul = $("jobs");
  ul.textContent = "";
  if (!jobs || !jobs.length) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "まだありません";
    ul.appendChild(li);
    return;
  }
  for (const j of jobs.slice(0, 5)) {
    const li = document.createElement("li");
    li.className = j.status;

    const t = document.createElement("div");
    t.className = "job-title";
    const name = document.createElement("span");
    name.textContent = j.title;
    t.append(makeIcon(j.mode === "audio" ? "audio" : "video"), name);

    const meta = document.createElement("div");
    meta.className = "job-meta";
    if (j.status === "running" || j.status === "post") {
      const dot = document.createElement("i");
      dot.className = "rec";
      meta.appendChild(dot);
    }
    const st = document.createElement("span");
    st.className = "st";
    st.textContent = j.status === "error" ? "失敗" : (j.stage || STATUS_LABEL[j.status] || j.status);
    meta.appendChild(st);
    if (j.status === "running") {
      const pct = document.createElement("span");
      pct.className = "pct";
      pct.textContent = `${Math.round(j.progress * 100)}%`;
      meta.appendChild(pct);
    }

    li.append(t, meta);
    if (j.status === "running" || j.status === "post" || j.status === "queued") {
      const bar = document.createElement("div");
      bar.className = "bar";
      const i = document.createElement("i");
      i.style.width = `${Math.round(j.progress * 100)}%`;
      bar.appendChild(i);
      li.appendChild(bar);
    }
    if (j.error) li.title = j.error;
    ul.appendChild(li);
  }
}

function setPrimary(defaultMode) {
  $("btnVideo").classList.toggle("primary", defaultMode !== "audio");
  $("btnAudio").classList.toggle("primary", defaultMode === "audio");
}

async function refresh() {
  const st = await msg("status");
  if (!st.ok) {
    setState("未起動", "ng");
    $("btnVideo").disabled = $("btnAudio").disabled = true;
    if (st.offline) showMessage("PC で YT Downloader を起動してください", false);
    renderJobs([]);
    return;
  }
  $("btnVideo").disabled = $("btnAudio").disabled = !tabUrl;
  setPrimary(st.default_mode);
  const running = (st.jobs || []).filter((j) => j.status === "running" || j.status === "post").length;
  if (running) setState(`${running} 件ダウンロード中`, "busy", true);
  else if (st.updating) setState("ツールを更新中");
  else if (!st.ready) setState("yt-dlp がありません", "ng");
  else setState("接続済み");
  renderJobs(st.jobs);
}

async function start(mode) {
  if (!tabUrl) return;
  $("btnVideo").disabled = $("btnAudio").disabled = true;
  const res = await msg("download", { url: tabUrl, mode, playlist: null });
  if (res.ok) showMessage(mode === "audio" ? "音声のダウンロードを始めました" : "動画のダウンロードを始めました", true);
  else showMessage(res.error || "失敗しました", false);
  setTimeout(() => { $("btnVideo").disabled = $("btnAudio").disabled = !tabUrl; }, 800);
  refresh();
}

function cleanUrl(raw) {
  // YouTube の URL は余計なパラメーター（自動ミックスの list など）を落として単体の動画にする
  try {
    const u = new URL(raw);
    if (/(^|\.)youtube\.com$/.test(u.hostname) && u.pathname === "/watch" && u.searchParams.get("v")) {
      return `${u.origin}/watch?v=${u.searchParams.get("v")}`;
    }
    return raw;
  } catch (_) {
    return raw;
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  for (const b of document.querySelectorAll(".actions button")) b.prepend(makeIcon(b.dataset.icon));
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab && tab.url && /^https?:/i.test(tab.url)) {
    tabUrl = cleanUrl(tab.url);
    $("pageTitle").textContent = tab.title || tab.url;
    $("pageUrl").textContent = tabUrl;
  } else {
    $("pageTitle").textContent = "このページはダウンロードできません";
  }
  $("btnVideo").addEventListener("click", () => start("video"));
  $("btnAudio").addEventListener("click", () => start("audio"));
  $("btnOpen").addEventListener("click", () => msg("show"));
  refresh();
  setInterval(refresh, 1000);
});
