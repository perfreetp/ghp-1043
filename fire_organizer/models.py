import os
import json
import uuid
from datetime import datetime, date
from typing import List, Dict, Optional, Any


class Device:
    def __init__(
        self,
        device_id: str,
        name: str,
        location: str,
        building: str,
        floor: str,
        device_type: str,
        area: str = "",
        last_check_date: Optional[str] = None,
        status: str = "正常",
        notes: str = "",
    ):
        self.device_id = device_id
        self.name = name
        self.location = location
        self.building = building
        self.floor = floor
        self.device_type = device_type
        self.area = area
        self.last_check_date = last_check_date
        self.status = status
        self.notes = notes

    def to_dict(self) -> Dict:
        return {
            "device_id": self.device_id,
            "name": self.name,
            "location": self.location,
            "building": self.building,
            "floor": self.floor,
            "device_type": self.device_type,
            "area": self.area,
            "last_check_date": self.last_check_date,
            "status": self.status,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Device":
        return cls(**data)


class PlanItem:
    def __init__(
        self,
        plan_id: str,
        device_id: str,
        building: str,
        floor: str,
        plan_date: str,
        inspector: str = "",
        area: str = "",
        status: str = "待执行",
        check_date: Optional[str] = None,
        result: str = "",
        photo_paths: List[str] = None,
    ):
        self.plan_id = plan_id
        self.device_id = device_id
        self.building = building
        self.floor = floor
        self.plan_date = plan_date
        self.inspector = inspector
        self.area = area
        self.status = status
        self.check_date = check_date
        self.result = result
        self.photo_paths = photo_paths or []

    def to_dict(self) -> Dict:
        return {
            "plan_id": self.plan_id,
            "device_id": self.device_id,
            "building": self.building,
            "floor": self.floor,
            "plan_date": self.plan_date,
            "inspector": self.inspector,
            "area": self.area,
            "status": self.status,
            "check_date": self.check_date,
            "result": self.result,
            "photo_paths": self.photo_paths,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "PlanItem":
        return cls(**data)


class Issue:
    def __init__(
        self,
        issue_id: str,
        plan_id: str,
        device_id: str,
        description: str,
        severity: str,
        report_date: str,
        deadline: str,
        reporter: str,
        building: str = "",
        floor: str = "",
        area: str = "",
        status: str = "待整改",
        rectification: str = "",
        reviewer: str = "",
        close_date: Optional[str] = None,
        photo_before: List[str] = None,
        photo_after: List[str] = None,
    ):
        self.issue_id = issue_id
        self.plan_id = plan_id
        self.device_id = device_id
        self.description = description
        self.severity = severity
        self.report_date = report_date
        self.deadline = deadline
        self.reporter = reporter
        self.building = building
        self.floor = floor
        self.area = area
        self.status = status
        self.rectification = rectification
        self.reviewer = reviewer
        self.close_date = close_date
        self.photo_before = photo_before or []
        self.photo_after = photo_after or []

    @property
    def is_overdue(self) -> bool:
        if self.status == "已关闭" or not self.deadline:
            return False
        try:
            deadline_date = datetime.strptime(self.deadline, "%Y-%m-%d").date()
            return date.today() > deadline_date
        except (ValueError, TypeError):
            return False

    def to_dict(self) -> Dict:
        return {
            "issue_id": self.issue_id,
            "plan_id": self.plan_id,
            "device_id": self.device_id,
            "description": self.description,
            "severity": self.severity,
            "report_date": self.report_date,
            "deadline": self.deadline,
            "reporter": self.reporter,
            "building": self.building,
            "floor": self.floor,
            "area": self.area,
            "status": self.status,
            "rectification": self.rectification,
            "reviewer": self.reviewer,
            "close_date": self.close_date,
            "photo_before": self.photo_before,
            "photo_after": self.photo_after,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Issue":
        return cls(**data)


class OperationLog:
    def __init__(
        self,
        log_id: str,
        action: str,
        target_type: str,
        target_id: str,
        operator: str,
        timestamp: str,
        details: str = "",
    ):
        self.log_id = log_id
        self.action = action
        self.target_type = target_type
        self.target_id = target_id
        self.operator = operator
        self.timestamp = timestamp
        self.details = details

    def to_dict(self) -> Dict:
        return {
            "log_id": self.log_id,
            "action": self.action,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "operator": self.operator,
            "timestamp": self.timestamp,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "OperationLog":
        return cls(**data)


def generate_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12].upper()}"


def today_str() -> str:
    return date.today().strftime("%Y-%m-%d")


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
