; YT Downloader のインストーラー（Inno Setup 6）
; 使い方: ISCC /DAppVersion=1.0.0 installer\ytdownloader.iss
; 事前に build.bat（または同じ手順）で dist\YTDownloader を作っておく。

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "YT Downloader"
#define AppExe "YTDownloader.exe"

[Setup]
AppId={{8B30063A-D33C-4C53-8A39-52F48D22628E}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=pokobi
AppPublisherURL=https://github.com/pokobi/yt-downloader
AppSupportURL=https://github.com/pokobi/yt-downloader/issues
; 管理者権限なしで、ユーザーごとに入れる
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\YTDownloader
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
OutputDir=..\release
OutputBaseFilename=YTDownloader-Setup-{#AppVersion}
SetupIconFile=..\src\ytdl\assets\app.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; 起動中のアプリは、上書き・アンインストールの前に閉じる
CloseApplications=force
RestartApplications=no

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "デスクトップにショートカットを作る"; GroupDescription: "追加のショートカット:"; Flags: unchecked

[Files]
Source: "..\dist\YTDownloader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\拡張機能のフォルダ"; Filename: "{app}\extension"
Name: "{group}\{#AppName} をアンインストール"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{#AppName} を起動する"; Flags: nowait postinstall skipifsilent
Filename: "{app}\extension"; Description: "Chrome 拡張機能のフォルダを開く"; Flags: postinstall shellexec skipifsilent unchecked

[UninstallRun]
; 常駐しているアプリを止める（CloseApplications で閉じられなかった場合の保険）
Filename: "{sys}\taskkill.exe"; Parameters: "/IM {#AppExe} /F"; Flags: runhidden; RunOnceId: "StopApp"

[Registry]
; アプリが設定するログイン時の自動起動を、アンインストール時に消す
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "YTDownloader"; Flags: dontcreatekey uninsdeletevalue

[UninstallDelete]
; アプリが取得したツール（yt-dlp / FFmpeg / Deno）・キャッシュ・ログを消す。設定（%APPDATA%）は残す
Type: filesandordirs; Name: "{localappdata}\YTDownloader"
