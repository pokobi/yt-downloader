// X（旧 Twitter）の、動画が入った投稿の操作列（返信・リポスト・いいね…）にダウンロードボタンを差し込む。
// X の画面はクラス名が頻繁に変わるため、手がかりは「article」「role=group」「/status/数字 へのリンク」「video 要素」だけにする。
(() => {
  if (window.__ytdlxXInjected) return;
  window.__ytdlxXInjected = true;

  const { makeIcon, ask, openMenu, closeMenu, menuOpenFor, stopAll } = window.__ytdlx;
  const STATUS_RE = /^\/([A-Za-z0-9_]{1,30})\/status\/(\d{5,25})(?:\/|$)/;

  // 投稿の URL（ページの URL ではなく、その投稿自身の URL）
  // 引用された投稿は内側の article になっている。内側のリンクと、引用カード全体を包む
  // 文字のないリンクは除き、日時を表示しているリンク（投稿自身へのリンク）を使う
  function postUrl(article) {
    const own = [...article.querySelectorAll('a[href*="/status/"]')].filter((a) => a.closest("article") === article);
    const pick = own.find((a) => a.textContent.trim()) || own[0];
    const m = pick && (pick.getAttribute("href") || "").match(STATUS_RE);
    if (m) return `https://x.com/${m[1]}/status/${m[2]}`;
    // 投稿の詳細ページでは、自分自身へのリンクがないことがある
    const here = own.length ? null : location.pathname.match(STATUS_RE);
    return here ? `https://x.com/${here[1]}/status/${here[2]}` : null;
  }

  // ---------- メニュー ----------
  const probeCache = new Map();  // 投稿の URL → 動画の本数など（同じ投稿を何度も問い合わせない）

  async function probe(url) {
    const hit = probeCache.get(url);
    if (hit && Date.now() - hit.at < 10 * 60 * 1000) return hit.res;
    const res = await ask({ type: "probe", url });
    if (res.ok) probeCache.set(url, { at: Date.now(), res });
    return res;
  }

  async function menuItems(url) {
    const res = await probe(url);
    if (res.stale) return [{ note: "拡張機能が更新されました。ページを再読み込みしてください。", error: true }];
    if (!res.ok && res.offline) return [{ note: "YT Downloader が起動していません。PC でアプリを起動してください。", error: true }];
    const n = res.ok ? res.count : 1;  // 本数を確かめられないときは、投稿の動画をまとめて取る
    if (n <= 1) {
      const items = [
        { label: "動画でダウンロード", sub: "映像＋音声", mode: "video", url, playlist: false },
        { label: "音声でダウンロード", sub: "音だけ", mode: "audio", url, playlist: false },
      ];
      // 確認に失敗しても、ダウンロード自体は試せるようにしておく
      if (!res.ok && res.error) items.unshift({ note: res.error, error: true }, { sep: true });
      return items;
    }
    const both = (extra) => [{ mode: "video", url, ...extra }, { mode: "audio", url, ...extra }];
    const items = [{ row: `全部（${n} 本）`, actions: both({ playlist: true }) }, { sep: true }];
    for (let i = 1; i <= n; i++) items.push({ row: `${i} 本目`, actions: both({ playlist: true, items: i }) });
    return items;
  }

  // ---------- ボタン ----------
  // 見た目は X の操作ボタンと揃える（ホバー時の丸い背景は X 自身のクラスを借りる）
  function makeButton(url) {
    const wrap = document.createElement("div");
    wrap.className = "ytdlx-xwrap";
    const b = document.createElement("button");
    b.type = "button";
    b.className = "ytdlx-btn ytdlx-x group x-engagement-button transition-colors hover:text-brand text-secondary";
    b.title = "YT Downloader でダウンロード";
    b.setAttribute("aria-label", "YT Downloader でダウンロード");
    b.dataset.url = url;
    const pill = document.createElement("span");
    pill.className = "ytdlx-xpill x-engagement-pill h-9 px-2.5 before:bg-brand/10";
    pill.appendChild(makeIcon("download", 1.75));
    b.appendChild(pill);
    for (const ev of ["mousedown", "mouseup", "pointerdown", "dblclick"]) b.addEventListener(ev, (e) => e.stopPropagation());
    b.addEventListener("click", (e) => {
      stopAll(e);
      openMenu(b, () => menuItems(b.dataset.url), "動画の本数を確認中…");
    });
    wrap.appendChild(b);
    return wrap;
  }

  // 投稿自身の操作列（返信・リポスト・いいね…）。動画の再生位置バーも role=group なので除く。
  // 引用された投稿（内側の article）には操作列がない
  function actionRow(article) {
    const own = [...article.querySelectorAll('[role="group"]')].filter((g) => g.closest("article") === article);
    return own.find((g) => g.querySelector("[data-engagement-action]"))
      || own.filter((g) => !g.querySelector('[role="slider"], video')).pop()
      || null;
  }

  function ensure() {
    for (const article of document.querySelectorAll("article")) {
      const group = actionRow(article);
      if (!group) continue;
      const have = group.querySelector(":scope > .ytdlx-xwrap");
      const url = article.querySelector("video") ? postUrl(article) : null;
      if (!url) {
        if (have) have.remove();
        continue;
      }
      if (have) {
        // X は表示中の要素を別の投稿に使い回すことがあるので、URL を毎回合わせる
        const btn = have.querySelector(".ytdlx-btn");
        if (btn.dataset.url !== url) {
          btn.dataset.url = url;
          if (menuOpenFor(btn)) closeMenu();
        }
        continue;
      }
      // ブックマーク・共有のまとまり（いちばん右）の手前に置く
      group.insertBefore(makeButton(url), group.lastElementChild);
    }
  }

  // ---------- 見張り ----------
  let scheduled = false;
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    setTimeout(() => { scheduled = false; ensure(); }, 300);
  }
  let lastHref = location.href;
  new MutationObserver(() => {
    if (location.href !== lastHref) { lastHref = location.href; closeMenu(); }
    schedule();
  }).observe(document.documentElement, { childList: true, subtree: true });
  setInterval(ensure, 3000);
  ensure();
})();
