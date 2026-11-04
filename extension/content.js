// YouTube / YouTube Music の画面にダウンロードボタンを差し込む。
// YouTube はページ遷移しても再読み込みされない（SPA）ため、画面の変化を見張って毎回確認する。
(() => {
  if (window.__ytdlxInjected) return;
  window.__ytdlxInjected = true;

  const IS_MUSIC = location.hostname === "music.youtube.com";
  const { makeIcon, openMenu, closeMenu, stopAll } = window.__ytdlx;
  const ID_RE = /^[\w-]{11}$/;

  // ---------- 今見ている動画・曲 ----------
  function currentTarget() {
    let id = null;
    let list = null;
    try {
      const u = new URL(location.href);
      if (u.pathname === "/watch") id = u.searchParams.get("v");
      const m = u.pathname.match(/^\/(shorts|live)\/([\w-]{11})/);
      if (m) id = m[2];
      list = u.searchParams.get("list");
    } catch (_) { /* noop */ }

    if (!id || !ID_RE.test(id)) {
      // YouTube Music でアルバム等を見ながら再生しているとき：プレーヤーのタイトルリンクから取る
      const a = document.querySelector("#movie_player .ytp-title-link[href*='v=']");
      if (a) {
        try { id = new URL(a.href).searchParams.get("v"); } catch (_) { id = null; }
      }
    }
    if (!id || !ID_RE.test(id)) return null;

    const base = IS_MUSIC ? "https://music.youtube.com" : "https://www.youtube.com";
    // RD〜 は自動生成のミックス（終わりがない）なのでプレイリスト扱いしない
    const realList = list && /^[\w-]{10,}$/.test(list) && !/^(RD|UL|LL$|WL$)/.test(list) ? list : null;
    return {
      id,
      url: `${base}/watch?v=${id}`,
      playlistUrl: realList ? `${base}/playlist?list=${realList}` : null,
    };
  }

  // ---------- メニュー ----------
  function menuItems() {
    const t = currentTarget();
    if (!t) return [{ note: "動画が見つかりません", error: true }];
    const items = [
      { label: "動画でダウンロード", sub: "映像＋音声", mode: "video", url: t.url, playlist: false },
      { label: "音声でダウンロード", sub: "曲だけ", mode: "audio", url: t.url, playlist: false },
    ];
    if (t.playlistUrl) {
      items.push({ sep: true });
      items.push({ label: "プレイリストを全部（動画）", mode: "video", url: t.playlistUrl, playlist: true });
      items.push({ label: "プレイリストを全部（音声）", mode: "audio", url: t.playlistUrl, playlist: true });
    }
    return items;
  }

  // ---------- ボタン ----------
  function makeButton(kind) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = `ytdlx-btn ytdlx-${kind}`;
    if (kind === "player") b.classList.add("ytp-button");
    b.title = "YT Downloader でダウンロード";
    b.setAttribute("aria-label", "YT Downloader でダウンロード");
    b.appendChild(makeIcon());
    const stop = (e) => { e.stopPropagation(); };
    b.addEventListener("mousedown", stop);
    b.addEventListener("dblclick", stop);
    b.addEventListener("click", (e) => {
      stopAll(e);
      openMenu(b, menuItems);
    });
    return b;
  }

  function findContainer() {
    if (IS_MUSIC) {
      return { el: document.querySelector("ytmusic-player-bar .right-controls-buttons"), kind: "music" };
    }
    if (location.pathname.startsWith("/shorts/")) return { el: null, kind: "floating" };
    // 2025年以降の新しいプレーヤーは右側が左右2つのグループに分かれている
    const el = document.querySelector("#movie_player .ytp-right-controls-left")
      || document.querySelector("#movie_player .ytp-right-controls");
    return { el, kind: "player" };
  }

  function ensure() {
    const target = currentTarget();
    const existing = document.querySelectorAll(".ytdlx-btn");
    if (!target) {
      existing.forEach((n) => n.remove());
      closeMenu();
      return;
    }
    const { el, kind } = findContainer();
    if (el) {
      let btn = el.querySelector(`:scope > .ytdlx-${kind}`);
      if (!btn) {
        btn = makeButton(kind);
        el.insertBefore(btn, el.firstChild);
      }
      existing.forEach((n) => { if (n !== btn) n.remove(); });
    } else {
      let fl = document.querySelector(".ytdlx-floating");
      if (!fl) {
        fl = makeButton("floating");
        if (IS_MUSIC) fl.classList.add("ytdlx-floating-music");
        document.documentElement.appendChild(fl);
      }
      existing.forEach((n) => { if (n !== fl) n.remove(); });
    }
  }

  // ---------- 見張り ----------
  let scheduled = false;
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    setTimeout(() => { scheduled = false; ensure(); }, 400);
  }
  let lastHref = location.href;
  const obs = new MutationObserver(() => {
    if (location.href !== lastHref) { lastHref = location.href; closeMenu(); }
    schedule();
  });
  obs.observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener("yt-navigate-finish", schedule);
  window.addEventListener("popstate", schedule);
  setInterval(ensure, 3000);
  ensure();
})();
