import os
import re
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import List, Tuple, Optional, Dict
from collections import Counter


from .models import Device, PlanItem, Issue, OperationLog, today_str


def validate_device_id(device_id: str) -> bool:
    if not device_id:
        return False
    pattern = r'^[A-Za-z0-9\-_]+$'
    return bool(re.match(pattern, device_id))


def find_duplicate_ids(devices: List[Device]) -> List[str]:
    ids = [d.device_id for d in devices]
    counter = Counter(ids)
    return [id_ for id_, count in counter.items() if count > 1]


def find_missing_fields(devices: List[Device]) -> List[Tuple[str, List[str]]]:
    required = ["device_id", "name", "location", "building", "device_type"]
    results = []
    for d in devices:
        missing = []
        d_dict = d.to_dict()
        for field in required:
            if not d_dict.get(field):
                missing.append(field)
        if missing:
            results.append((d.device_id or "(无编号)", missing))
    return results


def parse_date(date_str: str) -> Optional[date]:
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def format_date(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def get_month_range(year: int, month: int) -> Tuple[date, date]:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end


def is_in_month(date_str: str, year: int, month: int) -> bool:
    d = parse_date(date_str)
    if not d:
        return False
    return d.year == year and d.month == month


def build_plan_filename(building: str, plan_date: str) -> str:
    safe_name = re.sub(r'[^\w\-]', '_', building)
    return f"巡检计划_{safe_name}_{plan_date}.xlsx"


def build_report_filename(area: str, year: int, month: int) -> str:
    safe_name = re.sub(r'[^\w\-]', '_', area or "全部区域")
    return f"月度报告_{safe_name}_{year}年{month:02d}月.xlsx"


def build_export_package_name(project_name: str, export_date: str) -> str:
    safe_name = re.sub(r'[^\w\-]', '_', project_name)
    return f"交付包_{safe_name}_{export_date}"


def filter_by_area(items: List, area: str) -> List:
    if not area:
        return items
    return [i for i in items if getattr(i, "area", "") == area]


def filter_by_building(items: List, building: str) -> List:
    if not building:
        return items
    return [i for i in items if getattr(i, "building", "") == building]


def get_all_areas(devices: List[Device]) -> List[str]:
    areas = sorted(set(d.area for d in devices if d.area))
    return areas


def get_all_buildings(devices: List[Device]) -> List[str]:
    buildings = sorted(set(d.building for d in devices if d.building))
    return buildings


def get_all_inspectors(plans: List[PlanItem]) -> List[str]:
    inspectors = sorted(set(p.inspector for p in plans if p.inspector))
    return inspectors


def severity_order(severity: str) -> int:
    order = {"重大": 0, "严重": 1, "一般": 2, "轻微": 3}
    return order.get(severity, 99)


def status_order(status: str) -> int:
    order = {"待整改": 0, "整改中": 1, "待复查": 2, "已关闭": 3}
    return order.get(status, 99)
