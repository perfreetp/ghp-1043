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
SNAPSHOTS_DIR = "_snapshots"
ATTACHMENTS_DIR = "attachments"
EXPORTS_DIR = "exports"
REPORTS_DIR = "reports"
IMPORTS_DIR = "imports"


class Snapshot:
    """导入前快照，用于回滚和导入历史查询。"""

    STATUS_NORMAL = "正常"
    STATUS_ROLLED_BACK = "已回滚"

    def __init__(
        self,
        snapshot_id: str,
        created_at: str,
        operator: str,
        source_file: str,
        plan_ids_affected: List[str],
        copied_attachments: List[str],
        success_count: int = 0,
        skip_count: int = 0,
        warn_count: int = 0,
        diff_file_path: str = "",
        status: str = "正常",
        rollback_at: str = "",
        rollback_detail: Optional[Dict] = None,
    ):
        self.snapshot_id = snapshot_id
        self.created_at = created_at
        self.operator = operator
        self.source_file = source_file
        self.plan_ids_affected = plan_ids_affected
        self.copied_attachments = copied_attachments
        self.success_count = success_count
        self.skip_count = skip_count
        self.warn_count = warn_count
        self.diff_file_path = diff_file_path
        self.status = status
        self.rollback_at = rollback_at
        self.rollback_detail = rollback_detail or {}

    def to_dict(self) -> Dict:
        return {
            "snapshot_id": self.snapshot_id,
            "created_at": self.created_at,
            "operator": self.operator,
            "source_file": self.source_file,
            "plan_ids_affected": self.plan_ids_affected,
            "copied_attachments": self.copied_attachments,
            "success_count": self.success_count,
            "skip_count": self.skip_count,
            "warn_count": self.warn_count,
            "diff_file_path": self.diff_file_path,
            "status": self.status,
            "rollback_at": self.rollback_at,
            "rollback_detail": self.rollback_detail,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Snapshot":
        safe_data = {k: data.get(k, v) for k, v in {
            "snapshot_id": "",
            "created_at": "",
            "operator": "",
            "source_file": "",
            "plan_ids_affected": [],
            "copied_attachments": [],
            "success_count": 0,
            "skip_count": 0,
            "warn_count": 0,
            "diff_file_path": "",
            "status": "正常",
            "rollback_at": "",
            "rollback_detail": {},
        }.items()}
        safe_data.update({k: v for k, v in data.items() if k in safe_data})
        return cls(**safe_data)


class Storage:
    def __init__(self, project_path: str = "."):
        self.project_path = Path(project_path).resolve()
        self.data_dir = self.project_path / DATA_DIR
        self.snapshots_dir = self.data_dir / SNAPSHOTS_DIR
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

    def copy_attachment(self, src_path: str, subdir: str = "",
                        timestamp_override: Optional[str] = None) -> str:
        """复制附件到 attachments/{subdir}/，返回相对项目路径。
        传 timestamp_override 可指定固定前缀，保证 dry-run 和正式导入的文件名一致。
        """
        src = Path(src_path)
        if not src.exists():
            raise FileNotFoundError(f"文件不存在: {src_path}")
        target_dir = self.attachments_dir
        if subdir:
            target_dir = target_dir / subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        if timestamp_override:
            timestamp = str(timestamp_override)
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_name = f"{timestamp}_{src.name}"
        dst = target_dir / new_name
        shutil.copy2(src, dst)
        return str(dst.relative_to(self.project_path))

    def save_plan_snapshot(
        self, operator: str, source_file: str,
        original_plans: List, post_plans: List,
        affected_plan_ids: List[str],
        copied_attachments: List[str],
        success_count: int = 0, skip_count: int = 0, warn_count: int = 0,
        diff_file_path: str = "", diff_rows: Optional[List[Dict]] = None,
    ) -> Snapshot:
        """保存 plans 快照（导入前+导入后），用于回滚和导入历史查询。"""
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        snapshot_id = generate_id("SN")
        created_at = now_str()
        plans_backup_path = self.snapshots_dir / f"{snapshot_id}_plans.json"
        plans_post_path = self.snapshots_dir / f"{snapshot_id}_plans_post.json"
        diff_backup_path = self.snapshots_dir / f"{snapshot_id}_diff.json"
        self._write_json(plans_backup_path, [p.to_dict() for p in original_plans])
        self._write_json(plans_post_path, [p.to_dict() for p in post_plans])
        if diff_rows is not None:
            self._write_json(diff_backup_path, diff_rows)
        snapshot = Snapshot(
            snapshot_id=snapshot_id,
            created_at=created_at,
            operator=operator,
            source_file=source_file,
            plan_ids_affected=affected_plan_ids,
            copied_attachments=copied_attachments,
            success_count=success_count,
            skip_count=skip_count,
            warn_count=warn_count,
            diff_file_path=diff_file_path,
        )
        index_path = self.snapshots_dir / "index.json"
        index = self._read_json(index_path) or []
        index.append(snapshot.to_dict())
        self._write_json(index_path, index)
        return snapshot

    def list_plan_snapshots(self) -> List[Snapshot]:
        """列出所有导入快照。"""
        index_path = self.snapshots_dir / "index.json"
        if not index_path.exists():
            return []
        data = self._read_json(index_path) or []
        return [Snapshot.from_dict(d) for d in data]

    def get_snapshot_diff_rows(self, snapshot_id: str) -> Optional[List[Dict]]:
        """读取快照保存的差异清单。"""
        diff_path = self.snapshots_dir / f"{snapshot_id}_diff.json"
        if not diff_path.exists():
            return None
        return self._read_json(diff_path)

    def rollback_plan_snapshot(self, snapshot_id: str) -> Optional[Dict]:
        """按快照 ID 细粒度回滚：只恢复本次导入改过且之后未手工修改的计划。
        被跳过的计划仍然引用的照片文件保留不删除；快照记录不物理删除，只标记为已回滚。
        返回 dict: {snapshot, restored_count, skipped_manual_count, skipped_missing_count,
                    deleted_attach_count, retained_attach_count}
        """
        snapshots = self.list_plan_snapshots()
        target_idx = next((i for i, s in enumerate(snapshots) if s.snapshot_id == snapshot_id), None)
        if target_idx is None:
            return None
        target = snapshots[target_idx]

        orig_file = self.snapshots_dir / f"{snapshot_id}_plans.json"
        post_file = self.snapshots_dir / f"{snapshot_id}_plans_post.json"
        has_post = post_file.exists()

        # 1) 读取三种状态
        current_plans = self.get_plans()
        current_map = {p.plan_id: p for p in current_plans}
        orig_map = {}
        if orig_file.exists():
            orig_list = [PlanItem.from_dict(d) for d in self._read_json(orig_file)]
            orig_map = {p.plan_id: p for p in orig_list}
        post_map = {}
        if has_post:
            post_list = [PlanItem.from_dict(d) for d in self._read_json(post_file)]
            post_map = {p.plan_id: p for p in post_list}

        # 2) 差分判断：对每个 affected_plan_id，若 cur==post（之后未改）才恢复为 orig
        restored_count = 0
        skipped_manual_count = 0
        skipped_missing_count = 0
        skipped_pids = []
        for pid in target.plan_ids_affected:
            cur_p = current_map.get(pid)
            if cur_p is None:
                skipped_missing_count += 1
                skipped_pids.append(pid)
                continue
            post_p = post_map.get(pid) if has_post else None
            orig_p = orig_map.get(pid)
            fields_eq = True
            if post_p is not None:
                def _sig(p):
                    return (p.status, p.check_date, p.result, tuple(sorted(p.photo_paths or [])))
                if _sig(cur_p) != _sig(post_p):
                    fields_eq = False
            if fields_eq and orig_p is not None:
                cur_p.status = orig_p.status
                cur_p.check_date = orig_p.check_date
                cur_p.result = orig_p.result
                cur_p.photo_paths = list(orig_p.photo_paths or [])
                restored_count += 1
            elif not fields_eq:
                skipped_manual_count += 1
                skipped_pids.append(pid)
            else:
                skipped_missing_count += 1
                skipped_pids.append(pid)

        self.save_plans(current_plans)

        # 3) 清理附件：仅删除 copied_attachments 中未被「跳过计划」仍引用的
        #    收集所有跳过计划当前的 photo_paths（去重）
        retained_by_skipped = set()
        for pid in skipped_pids:
            p = current_map.get(pid)
            if p is None:
                continue
            for ph in (p.photo_paths or []):
                retained_by_skipped.add(str(ph).replace("/", "\\"))
                retained_by_skipped.add(str(ph).replace("\\", "/"))
                retained_by_skipped.add(str(ph))

        deleted_attach = 0
        retained_attach = 0
        for rel in target.copied_attachments:
            # 规范化：检查 rel 是否被跳过计划引用（用多种写法比对）
            rel_norm = str(rel).replace("/", "\\")
            is_referenced = False
            for ref in retained_by_skipped:
                if str(ref).replace("/", "\\") == rel_norm:
                    is_referenced = True
                    break
            p = self.project_path / rel
            if not p.exists():
                continue
            if is_referenced:
                retained_attach += 1
                continue
            try:
                p.unlink()
                deleted_attach += 1
            except Exception:
                pass

        # 4) 更新快照状态：不物理删除快照，仅标记 status=已回滚，写回滚元信息
        rollback_info = {
            "restored_count": restored_count,
            "skipped_manual_count": skipped_manual_count,
            "skipped_missing_count": skipped_missing_count,
            "deleted_attach_count": deleted_attach,
            "retained_attach_count": retained_attach,
            "rollback_operator": getattr(target, "operator", "system"),
        }
        target.status = Snapshot.STATUS_ROLLED_BACK
        target.rollback_at = now_str()
        target.rollback_detail = rollback_info
        # 同步到 index.json
        index_path = self.snapshots_dir / "index.json"
        index = self._read_json(index_path) or []
        if 0 <= target_idx < len(index):
            index[target_idx] = target.to_dict()
            self._write_json(index_path, index)

        return {
            "snapshot": target,
            "restored_count": restored_count,
            "skipped_manual_count": skipped_manual_count,
            "skipped_missing_count": skipped_missing_count,
            "deleted_attach_count": deleted_attach,
            "retained_attach_count": retained_attach,
        }
