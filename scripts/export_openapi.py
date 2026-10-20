"""导出 OpenAPI 契约到 docs/api.yaml。

用法（项目虚拟环境）：
    python scripts/export_openapi.py

脚本会把 backend/ 加入模块搜索路径，因此在仓库根目录或 backend/ 下执行都可以，
不依赖当前工作目录。
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import yaml

from app.main import app

path = ROOT / "docs" / "api.yaml"
path.write_text(
    yaml.safe_dump(app.openapi(), allow_unicode=True, sort_keys=False), encoding="utf-8"
)
print(path)
