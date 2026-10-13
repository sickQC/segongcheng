"""在 backend 工作目录用项目虚拟环境执行。"""

from pathlib import Path

import yaml
from app.main import app

path = Path(__file__).resolve().parents[1] / "docs" / "api.yaml"
path.write_text(
    yaml.safe_dump(app.openapi(), allow_unicode=True, sort_keys=False), encoding="utf-8"
)
print(path)
