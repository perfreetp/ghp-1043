import click
import os
import re
import shutil
from pathlib import Path
from datetime import date, datetime
from collections import defaultdict

try:
    import pandas as pd
except ImportError:
    pd = None

from ..storage import Storage
from ..models import today_str
from ..utils import (
    filter_by_area, filter_by_building,
    build_export_package_name
)


@click.group()
def export():
    """导出工具：批量重命名附件、导出交付包。"""
    pass


@export.command("rename")
@click.option("--pattern", "-p", default="{type}_{id}_{index}",
              help="命名模板：{type}(issue/plan) {id}(编号) {index}(序号) {date}(日期)")
@click.option("--type", "-t", default="all", help="重命名类型：all/issue/plan",
              type=click.Choice(["all", "issue", "plan"]))
@click.option("--area", "-a", default="", help="按区域筛选")
@click.option("--building", "-b", default="", help="按楼栋筛选")
@click.option("--dry-run", is_flag=True, help="试运行（不实际重命名）")
def export_rename(pattern: str, type: str, area: str, building: str, dry_run: bool):
    """批量重命名附件（照片、文档等）。"""
    storage = Storage()
    if not storage.is_initialized():
        click.echo(click.style("错误：请先运行 init 初始化项目", fg="red"))
        return

    plans = storage.get_plans()
    issues = storage.get_issues()

    if area:
        plans = filter_by_area(plans, area)
        issues = filter_by_area(issues, area)
    if building:
        plans = filter_by_building(plans, building)
        issues = filter_by_building(issues, building)

    attachments_dir = storage.attachments_dir
    renamed_count = 0
    errors = []

    if type in ("all", "plan"):
        for p in plans:
            photos = p.photo_paths
            for idx, photo_path in enumerate(photos, 1):
                full_path = storage.project_path / photo_path
                if not full_path.exists():
                    errors.append(f"文件不存在: {photo_path}")
                    continue
                ext = full_path.suffix
                new_name = pattern.format(
                    type="plan", id=p.plan_id, index=idx,
                    date=p.plan_date or p.check_date or today_str()
                ) + ext
                new_full = full_path.parent / new_name
                if new_full.exists():
                    errors.append(f"目标文件已存在，跳过: {new_name}")
                    continue
                if dry_run:
                    click.echo(f"  [试运行] {photo_path} -> {new_name}")
                else:
                    full_path.rename(new_full)
                    new_rel = str(new_full.relative_to(storage.project_path))
                    p.photo_paths[idx - 1] = new_rel
                    renamed_count += 1

        if not dry_run and renamed_count > 0:
            storage.save_plans(plans)

    if type in ("all", "issue"):
        issue_renamed = 0
        for i in issues:
            for group_name, photo_list in [("before", i.photo_before), ("after", i.photo_after)]:
                for idx, photo_path in enumerate(photo_list, 1):
                    full_path = storage.project_path / photo_path
                    if not full_path.exists():
                        errors.append(f"文件不存在: {photo_path}")
                        continue
                    ext = full_path.suffix
                    new_name = pattern.format(
                        type=f"issue-{group_name}", id=i.issue_id, index=idx,
                        date=i.report_date if group_name == "before" else (i.close_date or today_str())
                    ) + ext
                    new_full = full_path.parent / new_name
                    if new_full.exists():
                        errors.append(f"目标文件已存在，跳过: {new_name}")
                        continue
                    if dry_run:
                        click.echo(f"  [试运行] {photo_path} -> {new_name}")
                    else:
                        full_path.rename(new_full)
                        new_rel = str(new_full.relative_to(storage.project_path))
                        photo_list[idx - 1] = new_rel
                        issue_renamed += 1

        if not dry_run and issue_renamed > 0:
            storage.save_issues(issues)
            renamed_count += issue_renamed

    if dry_run:
        click.echo("")
        click.echo(click.style("[试运行模式] 以上为将执行的重命名操作", fg="yellow"))
    else:
        click.echo(click.style(f"重命名完成！", fg="green", bold=True))
        click.echo(f"  成功重命名：{renamed_count} 个文件")
    if errors:
        click.echo(f"  错误/跳过：{len(errors)} 个")
        if dry_run:
            for e in errors[:10]:
                click.echo(f"    - {e}")

    if not dry_run and renamed_count > 0:
        storage.add_log(
            "export_rename", "attachment", f"{renamed_count}个",
            "system",
            f"批量重命名附件{renamed_count}个"
        )


@export.command("package")
@click.option("--name", "-n", default=None, help="交付包名称")
@click.option("--area", "-a", default="", help="按区域筛选")
@click.option("--include-reports/--no-reports", default=True, help="包含报告文件")
@click.option("--include-attachments/--no-attachments", default=True, help="包含附件/照片")
@click.option("--format", "-f", default="dir", help="输出格式：dir(目录) 或 zip(压缩包)",
              type=click.Choice(["dir", "zip"]))
def export_package(name: str, area: str, include_reports: bool,
                   include_attachments: bool, format: str):
    """导出交付包（资料汇总）。"""
    storage = Storage()
    if not storage.is_initialized():
        click.echo(click.style("错误：请先运行 init 初始化项目", fg="red"))
        return

    config = storage.get_config()
    project_name = config.get("project_name", "消防资料")
    pkg_name = name or build_export_package_name(project_name, today_str())

    pkg_root = storage.exports_dir / pkg_name
    if pkg_root.exists():
        if not click.confirm(f"目录 {pkg_name} 已存在，是否覆盖？"):
            click.echo("已取消。")
            return
        shutil.rmtree(pkg_root)

    (pkg_root / "01_项目信息").mkdir(parents=True, exist_ok=True)
    (pkg_root / "02_设备清单").mkdir(parents=True, exist_ok=True)
    (pkg_root / "03_巡检计划").mkdir(parents=True, exist_ok=True)
    (pkg_root / "04_检查记录").mkdir(parents=True, exist_ok=True)
    (pkg_root / "05_隐患整改").mkdir(parents=True, exist_ok=True)
    (pkg_root / "06_月度报告").mkdir(parents=True, exist_ok=True)
    if include_attachments:
        (pkg_root / "07_附件照片").mkdir(parents=True, exist_ok=True)

    devices = storage.get_devices()
    plans = storage.get_plans()
    issues = storage.get_issues()
    logs = storage.get_logs()

    if area:
        devices = filter_by_area(devices, area)
        plans = filter_by_area(plans, area)
        issues = filter_by_area(issues, area)

    info_content = (
        f"项目名称: {project_name}\n"
        f"所属区域: {config.get('area', '')}\n"
        f"安全负责人: {config.get('manager', '')}\n"
        f"创建时间: {config.get('created_at', '')}\n"
        f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"统计信息:\n"
        f"  - 设备总数: {len(devices)}\n"
        f"  - 巡检计划: {len(plans)}\n"
        f"  - 隐患记录: {len(issues)} (已关闭: {len([i for i in issues if i.status == '已关闭'])})\n"
    )
    with open(pkg_root / "01_项目信息" / "项目说明.txt", "w", encoding="utf-8") as f:
        f.write(info_content)

    if pd is not None:
        dev_rows = [d.to_dict() for d in devices]
        if dev_rows:
            pd.DataFrame(dev_rows).to_excel(
                pkg_root / "02_设备清单" / "设备清单.xlsx",
                index=False, sheet_name="设备"
            )

        plan_rows = [p.to_dict() for p in plans]
        if plan_rows:
            pd.DataFrame(plan_rows).to_excel(
                pkg_root / "03_巡检计划" / "巡检计划汇总.xlsx",
                index=False, sheet_name="计划"
            )

        active_issues = [i for i in issues if i.status != "已关闭"]
        closed_issues = [i for i in issues if i.status == "已关闭"]
        all_issue_rows = [i.to_dict() for i in issues]
        if all_issue_rows:
            pd.DataFrame(all_issue_rows).to_excel(
                pkg_root / "05_隐患整改" / "整改台账_全部.xlsx",
                index=False, sheet_name="台账"
            )
        if active_issues:
            pd.DataFrame([i.to_dict() for i in active_issues]).to_excel(
                pkg_root / "05_隐患整改" / "整改台账_待处理.xlsx",
                index=False, sheet_name="待处理"
            )
        if closed_issues:
            pd.DataFrame([i.to_dict() for i in closed_issues]).to_excel(
                pkg_root / "05_隐患整改" / "整改台账_已关闭.xlsx",
                index=False, sheet_name="已关闭"
            )

    month_reports = sorted(storage.reports_dir.glob("*.xlsx"))
    if include_reports and month_reports:
        for rpt in month_reports:
            shutil.copy2(rpt, pkg_root / "06_月度报告" / rpt.name)

    if include_attachments:
        copied = 0
        for root, dirs, files in os.walk(storage.attachments_dir):
            for f in files:
                src = Path(root) / f
                rel = src.relative_to(storage.attachments_dir)
                dst = pkg_root / "07_附件照片" / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied += 1
        click.echo(f"  复制附件：{copied} 个")

    logs_dir = pkg_root / "01_项目信息"
    if pd is not None:
        pd.DataFrame([l.to_dict() for l in logs]).to_excel(
            logs_dir / "操作日志.xlsx", index=False, sheet_name="日志"
        )

    readme = pkg_root / "README.txt"
    with open(readme, "w", encoding="utf-8") as f:
        f.write(
            f"=== {project_name} 消防资料交付包 ===\n"
            f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"工具：fire-org (消防资料整理器)\n\n"
            f"目录说明：\n"
            f"  01_项目信息/     - 项目基本信息和操作日志\n"
            f"  02_设备清单/     - 设备明细（Excel）\n"
            f"  03_巡检计划/     - 巡检计划汇总\n"
            f"  04_检查记录/     - 检查相关数据\n"
            f"  05_隐患整改/     - 整改台账（全量/待处理/已关闭）\n"
            f"  06_月度报告/     - 历史月度报告\n"
            f"  07_附件照片/     - 原始照片和附件\n"
        )

    if format == "zip":
        zip_path = str(pkg_root)
        click.echo("正在打包...")
        shutil.make_archive(str(pkg_root), "zip", pkg_root)
        shutil.rmtree(pkg_root)
        final_path = f"{zip_path}.zip"
    else:
        final_path = str(pkg_root)

    click.echo(click.style(f"交付包导出成功！", fg="green", bold=True))
    click.echo(f"  位置：{final_path}")
    click.echo(f"  设备：{len(devices)} 台")
    click.echo(f"  计划：{len(plans)} 条")
    click.echo(f"  隐患：{len(issues)} 条")

    storage.add_log(
        "export_package", "export", pkg_name,
        "system",
        f"导出交付包: {pkg_name}"
    )
