import click
from pathlib import Path
from collections import defaultdict

try:
    import pandas as pd
except ImportError:
    pd = None

from ..storage import Storage
from ..models import PlanItem, generate_id, today_str
from ..utils import (
    filter_by_area, filter_by_building, build_plan_filename,
    get_all_buildings
)


@click.command()
@click.option("--date", "-d", default=None, help="计划日期 (YYYY-MM-DD，默认今天)")
@click.option("--building", "-b", default="", help="指定楼栋（不指定则按全部楼栋分组）")
@click.option("--area", "-a", default="", help="按区域筛选")
@click.option("--inspector", "-i", default="", help="责任人/巡检人")
@click.option("--export-excel/--no-export", default=False, help="同时导出 Excel 巡检表")
def plan(date: str, building: str, area: str, inspector: str, export_excel: bool):
    """按楼栋生成巡检计划。"""
    storage = Storage()
    if not storage.is_initialized():
        click.echo(click.style("错误：请先运行 init 初始化项目", fg="red"))
        return

    devices = storage.get_devices()
    if not devices:
        click.echo(click.style("错误：尚未导入设备数据，请先 import 设备清单", fg="red"))
        return

    plan_date = date or today_str()
    filtered = devices
    if area:
        filtered = filter_by_area(filtered, area)
        click.echo(f"筛选区域：{area}")

    if building:
        filtered = filter_by_building(filtered, building)
        building_map = {building: filtered}
    else:
        building_map = defaultdict(list)
        for d in filtered:
            b = d.building or "未分配楼栋"
            building_map[b].append(d)

    existing_plans = storage.get_plans()
    existing_keys = {(p.building, p.device_id, p.plan_date) for p in existing_plans}

    new_plans = []
    summary = defaultdict(int)

    for b, devs in sorted(building_map.items()):
        for d in devs:
            key = (b, d.device_id, plan_date)
            if key in existing_keys:
                continue
            plan_item = PlanItem(
                plan_id=generate_id("PL"),
                device_id=d.device_id,
                building=b,
                floor=d.floor,
                plan_date=plan_date,
                inspector=inspector,
                area=d.area,
                status="待执行",
            )
            new_plans.append(plan_item)
            summary[b] += 1

    if not new_plans:
        click.echo(click.style("该日期计划已存在，未生成新计划。", fg="yellow"))
    else:
        all_plans = existing_plans + new_plans
        storage.save_plans(all_plans)

        click.echo(click.style(f"巡检计划生成成功！", fg="green", bold=True))
        click.echo(f"  计划日期：{plan_date}")
        if inspector:
            click.echo(f"  巡检人：{inspector}")
        click.echo(f"  生成计划：{len(new_plans)} 条")
        click.echo(f"  覆盖楼栋：{len(summary)} 个")
        for b, n in sorted(summary.items()):
            click.echo(f"    • {b}: {n} 项")

        storage.add_log(
            "plan", "plan", f"{len(new_plans)}",
            inspector or "system",
            f"生成巡检计划: {plan_date}, 共{len(new_plans)}条, 覆盖{len(summary)}个楼栋"
        )

    if export_excel and pd is not None:
        plans_to_export = [
            p for p in (existing_plans + new_plans)
            if p.plan_date == plan_date and (not building or p.building == building)
        ]
        if not plans_to_export:
            click.echo(click.style("无计划数据可导出。", fg="yellow"))
            return

        devices_dict = {d.device_id: d for d in devices}

        export_buildings = sorted(set(p.building for p in plans_to_export))
        for b in export_buildings:
            b_plans = [p for p in plans_to_export if p.building == b]
            rows = []
            for p in b_plans:
                dev = devices_dict.get(p.device_id)
                rows.append({
                    "计划编号": p.plan_id,
                    "设备编号": p.device_id,
                    "设备名称": dev.name if dev else "",
                    "楼栋": p.building,
                    "楼层": p.floor,
                    "位置": dev.location if dev else "",
                    "设备类型": dev.device_type if dev else "",
                    "计划日期": p.plan_date,
                    "巡检人": p.inspector,
                    "状态": p.status,
                    "检查结果": "",
                    "检查日期": "",
                    "备注": "",
                })
            df = pd.DataFrame(rows)
            filename = build_plan_filename(b, plan_date)
            export_path = storage.exports_dir / filename
            df.to_excel(export_path, index=False, sheet_name="巡检表")
            click.echo(f"  已导出: {export_path}")
