import os
import json
import shutil
from typing import List, Dict, Optional, Any
from pathlib import Path
from datetime import datetime

from .models import (
    Device, PlanItem, Issue, OperationLog,
    generate_id, now_str, today_str
)


DATA_DIR = ".fire_data"
DEVICES_FILE = "devices.json"
PLANS_FILE = "plans.json"
ISSUES_FILE = "issues.json"
LOGS_FILE = "logs.json"
CONFIG_FILE = "config.json"
ATTACHMENTS_DIR = "attachments"
EXPORTS_DIR = "exports"
REPORTS_DIR = "reports"
IMPORTS_DIR = "imports"


class Storage:
    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path).resolve()
        self.data_dir = self.project_path / DATA_DIR
        self.attachments_dir = self.project_path / ATTACHMENTS_DIR
        self.exports_dir = self.project_path / EXPORTS_DIR
        self.reports_dir = self.project_path / REPORTS_DIR
        self.imports_dir = self.project_path / IMPORTS_DIR

    def is_initialized(self) -> bool:
        return self.data_dir.exists()

    def initialize_project(self, project_name: str, area: str = "", manager: str = "") -> bool:
        if self.is_initialized():
            return False
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.attachments_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.imports_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(self.data_dir / DEVICES_FILE, [])
        self._write_json(self.data_dir / PLANS_FILE, [])
        self._write_json(self.data_dir / ISSUES_FILE, [])
        self._write_json(self.data_dir / LOGS_FILE, [])
        config = {
            "project_name": project_name,
            "area": area,
            "manager": manager,
            "created_at": now_str(),
        }
        self._write_json(self.data_dir / CONFIG_FILE, config)
        self.add_log("init", "project", project_name, manager or "system",
                     f"初始化项目: {project_name}")
        return True

    def get_config(self) -> Dict:
        config_file = self.data_dir / CONFIG_FILE
        if not config_file.exists():
            return {}
        return self._read_json(config_file)

    def get_devices(self) -> List[Device]:
        data = self._read_json(self.data_dir / DEVICES_FILE)
        return [Device.from_dict(d) for d in data]

    def save_devices(self, devices: List[Device]) -> None:
        self._write_json(self.data_dir / DEVICES_FILE, [d.to_dict() for d in devices])

    def get_plans(self) -> List[PlanItem]:
        data = self._read_json(self.data_dir / PLANS_FILE)
        return [PlanItem.from_dict(d) for d in data]

    def save_plans(self, plans: List[PlanItem]) -> None:
        self._write_json(self.data_dir / PLANS_FILE, [p.to_dict() for p in plans])

    def get_issues(self) -> List[Issue]:
        data = self._read_json(self.data_dir / ISSUES_FILE)
        return [Issue.from_dict(d) for d in data]

    def save_issues(self, issues: List[Issue]) -> None:
        self._write_json(self.data_dir / ISSUES_FILE, [i.to_dict() for i in issues])

    def get_logs(self) -> List[OperationLog]:
        data = self._read_json(self.data_dir / LOGS_FILE)
        return [OperationLog.from_dict(d) for d in data]

    def add_log(
        self, action: str, target_type: str, target_id: str,
        operator: str, details: str = ""
    ) -> OperationLog:
        logs = self.get_logs()
        log = OperationLog(
            log_id=generate_id("LOG"),
            action=action,
            target_type=target_type,
            target_id=target_id,
            operator=operator,
            timestamp=now_str(),
            details=details,
        )
        logs.append(log)
        self._write_json(self.data_dir / LOGS_FILE, [l.to_dict() for l in logs])
        return log

    def _read_json(self, path: Path) -> Any:
        if not path.exists():
            return []
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_json(self, path: Path, data: Any) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def copy_attachment(self, src_path: str, subdir: str = "") -> str:
        src = Path(src_path)
        if not src.exists():
            raise FileNotFoundError(f"文件不存在: {src_path}")
        target_dir = self.attachments_dir
        if subdir:
            target_dir = target_dir / subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_name = f"{timestamp}_{src.name}"
        dst = target_dir / new_name
        shutil.copy2(src, dst)
        return str(dst.relative_to(self.project_path))
