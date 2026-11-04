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

function download(url, mode, playlist, items) {
  return call("/api/download", { url, mode: mode || "default", playlist: playlist ?? null, items: items ?? null });
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || typeof msg !== "object") return false;
  if (msg.type === "download") {
    download(msg.url, msg.mode, msg.playlist, msg.items).then(sendResponse);
    return true;
  }
  if (msg.type === "probe") {
    // X の投稿に動画が何本あるかを、アプリ（yt-dlp）に確かめてもらう
    call("/api/probe", { url: msg.url }, 25000).then(sendResponse);
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
