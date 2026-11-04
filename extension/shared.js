// YouTube 用・X 用のコンテンツスクリプトで共通に使う部品（アイコン、トースト、メニュー、送信）。
// 各サイトのスクリプトより先に読み込まれ、window.__ytdlx に置く。
(() => {
  if (window.__ytdlx) return;

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

  // ---------- 拡張機能の裏側（background.js）とのやり取り ----------
  function alive() {
    return !!(chrome.runtime && chrome.runtime.id);
  }
  function ask(message) {
    return new Promise((resolve) => {
      if (!alive()) { resolve({ ok: false, stale: true }); return; }
      try {
        chrome.runtime.sendMessage(message, (res) => {
          resolve(chrome.runtime.lastError || !res ? { ok: false, stale: true } : res);
        });
      } catch (_) {
        resolve({ ok: false, stale: true });
      }
    });
  }

  async function send(url, mode, playlist, items) {
    toast(mode === "audio" ? "音声のダウンロードを依頼中…" : "動画のダウンロードを依頼中…", "info", 1200);
    const res = await ask({ type: "download", url, mode, playlist, items: items || null });
    if (res.stale) {
      toast("拡張機能が更新されました。ページを再読み込みしてください。", "error");
    } else if (res.ok) {
      toast(mode === "audio" ? "音声のダウンロードを開始しました" : "動画のダウンロードを開始しました", "ok");
    } else {
      toast(res.offline ? "YT Downloader が起動していません。PC でアプリを起動してください。" : res.error, "error", 4500);
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
  // 項目の種類
  //   { label, sub, mode, url, playlist, items }  … 押すとダウンロード
  //   { row: "1 本目", actions: [{ mode, url, ... }, ...] } … 1 行に「動画」「音声」の小さなボタン
  //   { sep: true } / { note: "文字" }
  let menuEl = null;
  let menuAnchor = null;
  function closeMenu() {
    if (menuEl) { menuEl.remove(); menuEl = null; }
    menuAnchor = null;
    document.removeEventListener("mousedown", onOutside, true);
    document.removeEventListener("keydown", onKey, true);
    window.removeEventListener("scroll", onScroll, true);
  }
  function onOutside(e) {
    if (menuEl && !menuEl.contains(e.target) && !(e.target.closest && e.target.closest(".ytdlx-btn"))) closeMenu();
  }
  function onKey(e) { if (e.key === "Escape") closeMenu(); }
  let anchorTop = 0;
  function onScroll(e) {
    // X のタイムラインはスクロールで投稿が動く。少しのずれなら付いていき、大きく動いたら閉じる
    // （X はクリックやフォーカスでも小さくスクロールすることがある）
    if (!menuEl || !menuAnchor || menuEl.contains(e.target)) return;
    if (Math.abs(menuAnchor.getBoundingClientRect().top - anchorTop) > 24) closeMenu();
    else place();
  }

  function stopAll(e) { e.preventDefault(); e.stopPropagation(); }

  function actionButton(a, cls, children) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = cls;
    for (const c of children) b.appendChild(c);
    b.addEventListener("click", (e) => {
      stopAll(e);
      closeMenu();
      send(a.url, a.mode, a.playlist, a.items);
    });
    return b;
  }

  function fill(items) {
    if (!menuEl) return;
    menuEl.textContent = "";
    const head = document.createElement("div");
    head.className = "ytdlx-menu-head";
    head.textContent = "YT Downloader";
    menuEl.appendChild(head);
    for (const it of items) {
      if (it.sep) {
        const s = document.createElement("div");
        s.className = "ytdlx-sep";
        menuEl.appendChild(s);
      } else if (it.note !== undefined) {
        const n = document.createElement("div");
        n.className = `ytdlx-note${it.error ? " ytdlx-note-error" : ""}`;
        n.textContent = it.note;
        menuEl.appendChild(n);
      } else if (it.row) {
        const r = document.createElement("div");
        r.className = "ytdlx-row";
        const l = document.createElement("span");
        l.textContent = it.row;
        r.appendChild(l);
        for (const a of it.actions) {
          const t = document.createElement("span");
          t.textContent = a.mode === "audio" ? "音声" : "動画";
          const b = actionButton(a, "ytdlx-chip", [makeIcon(a.mode === "audio" ? "audio" : "video", 1.5), t]);
          b.title = `${it.row}を${a.mode === "audio" ? "音声" : "動画"}でダウンロード`;
          r.appendChild(b);
        }
        menuEl.appendChild(r);
      } else {
        const l = document.createElement("span");
        l.textContent = it.label;
        const kids = [makeIcon(it.mode === "audio" ? "audio" : "video", 1.5), l];
        if (it.sub) {
          const s = document.createElement("small");
          s.textContent = it.sub;
          kids.push(s);
        }
        menuEl.appendChild(actionButton(it, "ytdlx-item", kids));
      }
    }
    place();
  }

  // ボタンの上（入らなければ下）に出す
  function place() {
    if (!menuEl || !menuAnchor) return;
    const r = menuAnchor.getBoundingClientRect();
    const mw = menuEl.offsetWidth;
    const mh = menuEl.offsetHeight;
    const left = Math.min(window.innerWidth - mw - 8, Math.max(8, r.left + r.width / 2 - mw / 2));
    let top = r.top - mh - 8;
    if (top < 8) top = Math.min(window.innerHeight - mh - 8, r.bottom + 8);
    menuEl.style.left = `${left}px`;
    menuEl.style.top = `${top}px`;
  }

  // build は項目の配列か、配列を返す Promise。Promise の間は loading の文言を出しておく
  function openMenu(anchor, build, loading) {
    if (menuEl) {
      const same = menuAnchor === anchor;
      closeMenu();
      if (same) return;
    }
    menuEl = document.createElement("div");
    menuEl.className = "ytdlx-menu";
    menuEl.addEventListener("click", (e) => e.stopPropagation());
    menuAnchor = anchor;
    anchorTop = anchor.getBoundingClientRect().top;
    document.documentElement.appendChild(menuEl);
    const mine = menuEl;
    const result = build();
    if (result && typeof result.then === "function") {
      fill([{ note: loading || "確認中…" }]);
      result.then((items) => { if (menuEl === mine) fill(items); });
    } else {
      fill(result);
    }
    setTimeout(() => {
      document.addEventListener("mousedown", onOutside, true);
      document.addEventListener("keydown", onKey, true);
      window.addEventListener("scroll", onScroll, true);
    }, 0);
  }

  function menuOpenFor(anchor) { return !!menuEl && menuAnchor === anchor; }

  window.__ytdlx = { makeIcon, toast, send, ask, openMenu, closeMenu, menuOpenFor, stopAll };
})();
