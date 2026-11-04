// YouTube / YouTube Music の画面にダウンロードボタンを差し込む。
// YouTube はページ遷移しても再読み込みされない（SPA）ため、画面の変化を見張って毎回確認する。
(() => {
  if (window.__ytdlxInjected) return;
  window.__ytdlxInjected = true;

  const IS_MUSIC = location.hostname === "music.youtube.com";
  // YouTube は innerHTML を禁止している（Trusted Types）ので、SVG は DOM で組み立てる
  const SVG_NS = "http://www.w3.org/2000/svg";
  const ICONS = {
    download: ["M12 4.5v10.2m0 0-4.3-4.3m4.3 4.3 4.3-4.3M5.5 19.5h13"],
    video: ["M4 5h11a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z", "m17 10 5-3v10l-5-3"],
    audio: ["M9 18V5l12-2v13", "M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0z", "M21 16a3 3 0 1 1-6 0 3 3 0 0 1 6 0z"],
  };
  function makeIcon(name = "download", stroke = 2) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    for (const d of ICONS[name]) {
      const path = document.createElementNS(SVG_NS, "path");
      path.setAttribute("d", d);
      path.setAttribute("fill", "none");
      path.setAttribute("stroke", "currentColor");
      path.setAttribute("stroke-width", String(stroke));
      path.setAttribute("stroke-linecap", "round");
      path.setAttribute("stroke-linejoin", "round");
      svg.appendChild(path);
    }
    return svg;
  }
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

  // ---------- 送信 ----------
  function send(url, mode, playlist) {
    if (!chrome.runtime || !chrome.runtime.id) {
      toast("拡張機能が更新されました。ページを再読み込みしてください。", "error");
      return;
    }
    toast(mode === "audio" ? "音声のダウンロードを依頼中…" : "動画のダウンロードを依頼中…", "info", 1200);
    try {
      chrome.runtime.sendMessage({ type: "download", url, mode, playlist }, (res) => {
        if (chrome.runtime.lastError || !res) {
          toast("拡張機能と通信できません。ページを再読み込みしてください。", "error");
        } else if (res.ok) {
          toast(mode === "audio" ? "音声のダウンロードを開始しました" : "動画のダウンロードを開始しました", "ok");
        } else {
          toast(res.offline ? "YT Downloader が起動していません。PC でアプリを起動してください。" : res.error, "error", 4500);
        }
      });
    } catch (_) {
      toast("拡張機能が更新されました。ページを再読み込みしてください。", "error");
    }
  }

  // ---------- トースト ----------
  let toastEl = null;
  let toastTimer = 0;
  function toast(text, kind = "info", ms = 2600) {
    if (!toastEl) {
      toastEl = document.createElement("div");
      toastEl.className = "ytdlx-toast";
      document.documentElement.appendChild(toastEl);
    }
    toastEl.textContent = text;
    toastEl.dataset.kind = kind;
    toastEl.classList.add("ytdlx-show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toastEl && toastEl.classList.remove("ytdlx-show"), ms);
  }

  // ---------- メニュー ----------
  let menuEl = null;
  function closeMenu() {
    if (menuEl) { menuEl.remove(); menuEl = null; }
    document.removeEventListener("mousedown", onOutside, true);
    document.removeEventListener("keydown", onKey, true);
  }
  function onOutside(e) {
    if (menuEl && !menuEl.contains(e.target) && !(e.target.closest && e.target.closest(".ytdlx-btn"))) closeMenu();
  }
  function onKey(e) { if (e.key === "Escape") closeMenu(); }

  function openMenu(anchor) {
    if (menuEl) { closeMenu(); return; }
    const t = currentTarget();
    if (!t) { toast("動画が見つかりません", "error"); return; }

    menuEl = document.createElement("div");
    menuEl.className = "ytdlx-menu";
    const items = [
      { label: "動画でダウンロード", sub: "映像＋音声", mode: "video", url: t.url, playlist: false },
      { label: "音声でダウンロード", sub: "曲だけ", mode: "audio", url: t.url, playlist: false },
    ];
    if (t.playlistUrl) {
      items.push({ sep: true });
      items.push({ label: "プレイリストを全部（動画）", mode: "video", url: t.playlistUrl, playlist: true });
      items.push({ label: "プレイリストを全部（音声）", mode: "audio", url: t.playlistUrl, playlist: true });
    }
    const head = document.createElement("div");
    head.className = "ytdlx-menu-head";
    head.textContent = "YT Downloader";
    menuEl.appendChild(head);
    for (const it of items) {
      if (it.sep) {
        const s = document.createElement("div");
        s.className = "ytdlx-sep";
        menuEl.appendChild(s);
        continue;
      }
      const b = document.createElement("button");
      b.type = "button";
      b.className = "ytdlx-item";
      b.appendChild(makeIcon(it.mode === "audio" ? "audio" : "video", 1.5));
      const l = document.createElement("span");
      l.textContent = it.label;
      b.appendChild(l);
      if (it.sub) {
        const s = document.createElement("small");
        s.textContent = it.sub;
        b.appendChild(s);
      }
      b.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        closeMenu();
        send(it.url, it.mode, it.playlist);
      });
      menuEl.appendChild(b);
    }
    document.documentElement.appendChild(menuEl);

    // ボタンの上（入らなければ下）に出す
    const r = anchor.getBoundingClientRect();
    const mw = menuEl.offsetWidth;
    const mh = menuEl.offsetHeight;
    let left = Math.min(window.innerWidth - mw - 8, Math.max(8, r.left + r.width / 2 - mw / 2));
    let top = r.top - mh - 8;
    if (top < 8) top = Math.min(window.innerHeight - mh - 8, r.bottom + 8);
    menuEl.style.left = `${left}px`;
    menuEl.style.top = `${top}px`;

    setTimeout(() => {
      document.addEventListener("mousedown", onOutside, true);
      document.addEventListener("keydown", onKey, true);
    }, 0);
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
      e.preventDefault();
      e.stopPropagation();
      openMenu(b);
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
