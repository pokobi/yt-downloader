# YT Downloader

Windows の通知領域に常駐する、yt-dlp ベースの動画・音声ダウンローダー。
Chrome の拡張機能と連携し、YouTube / YouTube Music の再生画面からダウンロードできる。

## 機能

- 通知領域への常駐、Windows ログイン時の自動起動（設定で切り替え）
- YouTube のプレーヤー操作バーと YouTube Music の再生バーにダウンロードボタンを追加
  - 動画 / 音声を選択。プレイリスト再生中はプレイリスト全体も選択可（自動生成のミックスは対象外）
  - ツールバーのポップアップと右クリックメニューから、YouTube 以外のサイトにも対応
- アプリ画面での URL 入力（複数可）、ドラッグ＆ドロップ
- yt-dlp・FFmpeg・Deno の自動更新（起動時と 1 日 1 回）
  - 新しい版があるときだけ取得し、SHA-256 を照合してから入れ替える
  - 更新に失敗した場合は既存の版で動作を続ける
- 同時ダウンロード、キャンセル、再試行、完了通知
- メタデータ・サムネイルの埋め込み、SponsorBlock による区間の削除

## 構成

| パス | 内容 |
|---|---|
| `src/ytdl/` | アプリ本体（Python / PySide6） |
| `src/ytdl/tools.py` | yt-dlp・FFmpeg・Deno の取得と更新 |
| `src/ytdl/jobs.py` | ダウンロードのキュー。yt-dlp は別プロセスで実行 |
| `src/ytdl/server.py` | 拡張機能からの依頼を受けるローカル HTTP サーバー |
| `src/ytdl/ui/` | 画面 |
| `extension/` | ブラウザ拡張機能（Manifest V3） |
| `tools/make_icons.py` | アイコンの生成（Pillow が必要） |

## ビルド

Windows 10 / 11、Python 3.10 以降。

```bat
build.bat
```

`dist\YTDownloader\YTDownloader.exe` が生成され、同じフォルダに `extension` がコピーされる。
ビルドせずに起動する場合は `run_dev.bat`。

## 拡張機能の導入

1. Chrome で `chrome://extensions` を開く
2. 右上の「デベロッパー モード」をオンにする
3. 「パッケージ化されていない拡張機能を読み込む」で `extension` フォルダを選ぶ

拡張機能 ID は manifest の `key` により `hmllfgdnihfkggcipeklgjpdmblhhkfk` に固定されている。

## 通信

アプリは `127.0.0.1:47863` で待ち受ける。ダウンロード依頼は Origin が
`chrome-extension://hmllfgdnihfkggcipeklgjpdmblhhkfk` のものだけを受け付けるため、Web ページからは依頼できない。

## データの保存場所

| 内容 | 場所 |
|---|---|
| 設定 | `%APPDATA%\YTDownloader\settings.json` |
| yt-dlp / FFmpeg / Deno | `%LOCALAPPDATA%\YTDownloader\bin` |
| ログ | `%LOCALAPPDATA%\YTDownloader\logs` |

## 注意

個人での利用を想定している。

ほとんどのコーディングは生成AIです。
