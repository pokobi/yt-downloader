# PyInstaller の設定（build.bat から使う）
# フォルダ型（onedir）にしている：起動が速く、ウイルス対策ソフトの誤検知も少ないため。

a = Analysis(
    ["run.pyw"],
    pathex=["src"],
    datas=[("src/ytdl/assets", "ytdl/assets")],
    hiddenimports=[],
    excludes=["tkinter", "unittest", "pydoc", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtOpenGL",
              "PySide6.QtPdf", "PySide6.QtDBus"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="YTDownloader",
    console=False,
    icon="src/ytdl/assets/app.ico",
    version=None,
    upx=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    upx=False,
    name="YTDownloader",
)
