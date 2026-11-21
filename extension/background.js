// PC の YT Downloader（127.0.0.1:47863）との通信を担当する。
// コンテンツスクリプト（ページ内のボタン）は直接 localhost に送れないので、ここが中継する。
const API = "http://127.0.0.1:47863";

async function call(path, body, timeoutMs = 4000) {
  const opts = body === undefined
    ? { method: "GET", cache: "no-store" }
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(API + path, { ...opts, signal: ctrl.signal });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) {
      return { ok: false, error: data.error || `エラー (${res.status})` };
    }
    return { ok: true, ...data };
  } catch (e) {
    return { ok: false, offline: true, error: "YT Downloader が起動していません" };
  } finally {
    clearTimeout(timer);
  }
}

// ---- Cookie ----
// YouTube はボット判定のため、ログイン中のブラウザの Cookie がないと取得できないことがある。
// yt-dlp はブラウザの起動中に Cookie のファイルを読めないので、ここで読んでアプリに渡す。
// 渡す先は PC 内のアプリ（127.0.0.1）だけで、対象は URL のサイトの Cookie に限る。
const COOKIE_SITES = [
  { hosts: /(^|\.)(youtube\.com|youtu\.be)$/, domains: ["youtube.com"] },
  { hosts: /(^|\.)(x\.com|twitter\.com)$/, domains: ["x.com"] },
];

async function cookiesFor(url) {
  let host = "";
  try { host = new URL(url).hostname.toLowerCase(); } catch (_) { return null; }
  const site = COOKIE_SITES.find((s) => s.hosts.test(host));
  if (!site || !chrome.cookies) return null;
  try {
    const lists = await Promise.all(site.domains.map((domain) => chrome.cookies.getAll({ domain })));
    const out = [];
    for (const c of lists.flat()) {
      out.push({
        domain: c.domain, hostOnly: !!c.hostOnly, path: c.path || "/", secure: !!c.secure,
        expires: c.session ? 0 : Math.floor(c.expirationDate || 0), name: c.name, value: c.value,
      });
    }
    return out.length ? out : null;
  } catch (_) {
    return null;
  }
}

async function download(url, mode, playlist, items) {
  const cookies = await cookiesFor(url);
  return call("/api/download", {
    url, mode: mode || "default", playlist: playlist ?? null, items: items ?? null, cookies,
  });
}

async function probe(url) {
  const cookies = await cookiesFor(url);
  return call("/api/probe", { url, cookies }, 25000);
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || typeof msg !== "object") return false;
  if (msg.type === "download") {
    download(msg.url, msg.mode, msg.playlist, msg.items).then(sendResponse);
    return true;
  }
  if (msg.type === "probe") {
    // X の投稿に動画が何本あるかを、アプリ（yt-dlp）に確かめてもらう
    probe(msg.url).then(sendResponse);
    return true;
  }
  if (msg.type === "status") {
    call("/api/status").then(sendResponse);
    return true;
  }
  if (msg.type === "show") {
    call("/api/show", {}).then(sendResponse);
    return true;
  }
  return false;
});

// ---- 右クリックメニュー（YouTube 以外のサイトでも使える） ----
chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    const contexts = ["page", "link", "video", "audio"];
    chrome.contextMenus.create({ id: "ytdl-root", title: "YT Downloader", contexts });
    chrome.contextMenus.create({ id: "ytdl-video", parentId: "ytdl-root", title: "動画としてダウンロード", contexts });
    chrome.contextMenus.create({ id: "ytdl-audio", parentId: "ytdl-root", title: "音声としてダウンロード", contexts });
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  const mode = info.menuItemId === "ytdl-audio" ? "audio" : info.menuItemId === "ytdl-video" ? "video" : null;
  if (!mode) return;
  const url = info.linkUrl || info.pageUrl || (tab && tab.url);
  if (!url || !/^https?:/i.test(url)) return;
  const res = await download(url, mode, null);
  setBadge(res.ok ? "↓" : "!", res.ok ? "#3ddc97" : "#ff6b6b");
});

function setBadge(text, color) {
  chrome.action.setBadgeBackgroundColor({ color });
  chrome.action.setBadgeText({ text });
  setTimeout(() => chrome.action.setBadgeText({ text: "" }), 2500);
}
