"""アプリケーション設定を一度だけ読み込む．"""
import json
from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"
with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
    config = json.load(config_file)


__all__ = ["CONFIG_PATH", "config"]
