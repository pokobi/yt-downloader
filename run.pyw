"""開発版の起動スクリプト（黒い画面を出さずに起動）。exe 版のエントリーポイントも兼ねる。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from ytdl.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
