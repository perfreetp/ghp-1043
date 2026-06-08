import click
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
    filter_by_area, filter_by_building, is_in_month,
    get_month_range, severity_order, status_order,
    build_report_filename
)


@click.group()
def report():
    """报告管理：月度汇总、整改台账、检查报告、逾期筛选。"""
    pass


@report.command("summary")
@click.option("--year", "-y", type=int, default=None, help="年份（默认今年）")
@click.option("--month", "-m", type=int, default=None, help="月份（默认本月）")
@click.option("--area", "-a", default="", help="按区域筛选")
@click.option("--building", "-b", default="", help="按楼栋筛选")
def report_summary(year: int, month: int, area: str, building: str):
    """按月份汇总任务完成情况。"""
    storage = Storage()
    if not storage.is_initialized():
        click.echo(click.style("错误：请先运行 init 初始化项目", fg="red"))
        return

    today = date.today()
    year = year or today.year
    month = month or today.month
    if not (1 <= month <= 12):
        click.echo(click.style("错误：月份必须在 1-12 之间", fg="red"))
        return

    plans = storage.get_plans()
    issues = storage.get_issues()
    devices = storage.get_devices()

    month_plans = [p for p in plans if is_in_month(p.plan_date, year, month)]
    month_issues = [i for i in issues if is_in_month(i.report_date, year, month)]
    month_closed = [i for i in issues if i.close_date and is_in_month(i.close_date, year, month)]

    if area:
        month_plans = filter_by_area(month_plans, area)
        month_issues = filter_by_area(month_issues, area)
        month_closed = filter_by_area(month_closed, area)
    if building:
        month_plans = filter_by_building(month_plans, building)
        month_issues = filter_by_building(month_issues, building)
        month_closed = filter_by_building(month_closed, building)

    devices_dict = {d.device_id: d for d in devices}

    click.echo(click.style(f"{'='*60}", fg="cyan", bold=True))
    click.echo(click.style(f"  月度任务汇总 - {year}年{month:02d}月", fg="cyan", bold=True))
    click.echo(click.style(f"{'='*60}", fg="cyan", bold=True))

    click.echo("")
    click.echo(click.style("【巡检计划统计】", fg="yellow", bold=True))
    total_p = len(month_plans)
    done_p = len([p for p in month_plans if p.status in ("已完成", "有隐患")])
    pending_p = len([p for p in month_plans if p.status == "待执行"])
    issue_p = len([p for p in month_plans if p.status == "有隐患"])
    rate_p = (done_p / total_p * 100) if total_p > 0 else 0
    click.echo(f"  计划总数：{total_p} 项")
    click.echo(f"  已完成：  {done_p} 项 ({rate_p:.1f}%)")
    click.echo(f"  待执行：  {pending_p} 项")
    click.echo(f"  发现隐患：{issue_p} 项")

    inspectors = defaultdict(lambda: {"total": 0, "done": 0})
    for p in month_plans:
        key = p.inspector or "(未指定)"
        inspectors[key]["total"] += 1
        if p.status in ("已完成", "有隐患"):
            inspectors[key]["done"] += 1
    if inspectors:
        click.echo("")
        click.echo("  各巡检人完成情况：")
        for name, st in sorted(inspectors.items()):
            r = st["done"] / st["total"] * 100 if st["total"] else 0
            click.echo(f"    • {name:<10} {st['done']}/{st['total']}  ({r:.1f}%)")

    buildings_p = defaultdict(lambda: {"total": 0, "done": 0})
    for p in month_plans:
        key = p.building or "(未分配)"
        buildings_p[key]["total"] += 1
        if p.status in ("已完成", "有隐患"):
            buildings_p[key]["done"] += 1
    if buildings_p:
        click.echo("")
        click.echo("  各楼栋完成情况：")
        for name, st in sorted(buildings_p.items()):
            r = st["done"] / st["total"] * 100 if st["total"] else 0
            click.echo(f"    • {name:<12} {st['done']}/{st['total']}  ({r:.1f}%)")

    click.echo("")
    click.echo(click.style("【隐患管理统计】", fg="yellow", bold=True))
    click.echo(f"  本月新增：{len(month_issues)} 条")
    click.echo(f"  本月关闭：{len(month_closed)} 条")

    sev_count = defaultdict(int)
    for i in month_issues:
        sev_count[i.severity] += 1
    click.echo("  严重程度分布：")
    for sev in ["重大", "严重", "一般", "轻微"]:
        n = sev_count.get(sev, 0)
        if n:
            color = {"重大": "red", "严重": "yellow", "一般": "cyan", "轻微": "green"}[sev]
            click.echo(click.style(f"    • {sev}: {n} 条", fg=color))

    active_issues = [i for i in issues if i.status != "已关闭"]
    if area:
        active_issues = filter_by_area(active_issues, area)
    if building:
        active_issues = filter_by_building(active_issues, building)
    overdue = [i for i in active_issues if i.is_overdue]

    click.echo("")
    click.echo(click.style("【当前状态】", fg="yellow", bold=True))
    click.echo(f"  未关闭隐患：{len(active_issues)} 条")
    if overdue:
        click.echo(click.style(f"  其中逾期：  {len(overdue)} 条", fg="red", bold=True))
    else:
        click.echo(click.style(f"  其中逾期：  0 条", fg="green"))

    storage.add_log(
        "report_summary", "report", f"{year}-{month:02d}",
        "system",
        f"生成月度汇总报告: {year}年{month:02d}月"
    )


@report.command("ledger")
@click.option("--year", "-y", type=int, default=None, help="年份（默认今年）")
@click.option("--month", "-m", type=int, default=None, help="月份（默认本月）")
@click.option("--area", "-a", default="", help="按区域筛选")
@click.option("--status", "-s", default="", help="按状态筛选")
@click.option("--export", "-e", is_flag=True, help="导出为 Excel")
def report_ledger(year: int, month: int, area: str, status: str, export: bool):
    """生成整改台账。"""
    storage = Storage()
    if not storage.is_initialized():
        click.echo(click.style("错误：请先运行 init 初始化项目", fg="red"))
        return

    today = date.today()
    year = year or today.year
    month = month or today.month

    issues = storage.get_issues()
    if not issues:
        click.echo(click.style("暂无隐患记录", fg="yellow"))
        return

    filtered = [i for i in issues if is_in_month(i.report_date, year, month)]
    if not filtered:
        click.echo(click.style(f"{year}年{month:02d}月无隐患记录", fg="yellow"))
        return

    if area:
        filtered = filter_by_area(filtered, area)
    if status:
        filtered = [i for i in filtered if i.status == status]

    filtered.sort(key=lambda i: (severity_order(i.severity), status_order(i.status), i.deadline or "9999"))

    click.echo(click.style(f"{'='*120}", fg="cyan", bold=True))
    click.echo(click.style(f"  整改台账 - {year}年{month:02d}月  (共 {len(filtered)} 条)", fg="cyan", bold=True))
    click.echo(click.style(f"{'='*120}", fg="cyan", bold=True))
    hdr = f"{'编号':<16}{'设备':<12}{'严重':<8}{'状态':<10}{'楼栋':<12}{'发现日':<12}{'期限':<12}{'登记人':<10}描述"
    click.echo(click.style(hdr, fg="cyan"))
    click.echo("-" * 120)

    for i in filtered:
        desc = i.description[:30] + ("..." if len(i.description) > 30 else "")
        sev_c = {"重大": "red", "严重": "yellow", "一般": "cyan", "轻微": "green"}.get(i.severity, "white")
        st_c = {"待整改": "red", "整改中": "yellow", "待复查": "blue", "已关闭": "green"}.get(i.status, "white")
        ovd = click.style("[逾期]", fg="red", bold=True) if i.is_overdue else ""
        click.echo(
            f"{i.issue_id:<16}{i.device_id:<12}"
            f"{click.style(i.severity, fg=sev_c):<14}"
            f"{click.style(i.status, fg=st_c):<12}"
            f"{i.building:<14}{i.report_date:<14}{i.deadline:<14}"
            f"{i.reporter:<12}{desc} {ovd}"
        )

    click.echo("-" * 120)

    if export and pd is not None:
        rows = []
        for i in filtered:
            rows.append({
                "隐患编号": i.issue_id,
                "设备编号": i.device_id,
                "严重程度": i.severity,
                "状态": i.status,
                "是否逾期": "是" if i.is_overdue else "否",
                "楼栋": i.building,
                "楼层": i.floor,
                "区域": i.area,
                "发现日期": i.report_date,
                "整改期限": i.deadline,
                "登记人": i.reporter,
                "隐患描述": i.description,
                "整改措施": i.rectification,
                "复查人": i.reviewer,
                "关闭日期": i.close_date or "",
            })
        df = pd.DataFrame(rows)
        filename = f"整改台账_{year}年{month:02d}月.xlsx"
        path = storage.reports_dir / filename
        df.to_excel(path, index=False, sheet_name="整改台账")
        click.echo(click.style(f"已导出：{path}", fg="green"))


@report.command("inspection")
@click.option("--date", "-d", default=None, help="检查日期 (YYYY-MM-DD，默认今天)")
@click.option("--building", "-b", default="", help="按楼栋筛选")
@click.option("--area", "-a", default="", help="按区域筛选")
@click.option("--export", "-e", is_flag=True, help="导出为 Excel")
def report_inspection(date: str, building: str, area: str, export: bool):
    """输出检查报告。"""
    storage = Storage()
    if not storage.is_initialized():
        click.echo(click.style("错误：请先运行 init 初始化项目", fg="red"))
        return

    check_date = date or today_str()
    plans = storage.get_plans()
    devices = storage.get_devices()
    issues = storage.get_issues()

    day_plans = [p for p in plans if p.plan_date == check_date]
    if area:
        day_plans = filter_by_area(day_plans, area)
    if building:
        day_plans = filter_by_building(day_plans, building)

    if not day_plans:
        click.echo(click.style(f"该日期无巡检计划：{check_date}", fg="yellow"))
        return

    dev_dict = {d.device_id: d for d in devices}
    plan_issue_map = defaultdict(list)
    for i in issues:
        if i.plan_id:
            plan_issue_map[i.plan_id].append(i)

    click.echo(click.style(f"{'='*100}", fg="cyan", bold=True))
    click.echo(click.style(f"  检查报告 - {check_date}", fg="cyan", bold=True))
    click.echo(click.style(f"{'='*100}", fg="cyan", bold=True))

    total = len(day_plans)
    done = len([p for p in day_plans if p.status != "待执行"])
    has_issue = len([p for p in day_plans if p.status == "有隐患"])
    missing_photos = len([p for p in day_plans if p.status != "待执行" and not p.photo_paths])

    click.echo("")
    click.echo(f"  计划总数：{total}")
    click.echo(f"  已检查：{done} 项 ({done/total*100:.1f}%)")
    click.echo(f"  正常：{done - has_issue} 项")
    click.echo(f"  异常/隐患：{has_issue} 项")
    if missing_photos:
        click.echo(click.style(f"  缺照片：{missing_photos} 项", fg="red"))

    click.echo("")
    click.echo(click.style("【详细记录】", fg="yellow", bold=True))
    for p in sorted(day_plans, key=lambda x: (x.building, x.floor)):
        dev = dev_dict.get(p.device_id)
        st_c = {"待执行": "white", "已完成": "green", "有隐患": "red"}.get(p.status, "white")
        p_issues = plan_issue_map.get(p.plan_id, [])
        issue_info = f" [隐患{len(p_issues)}条]" if p_issues else ""
        click.echo(
            f"  {click.style(p.status, fg=st_c):<10} | "
            f"{p.building:<10} {p.floor:<6} | "
            f"{p.device_id:<14} {dev.name if dev else '':<10} | "
            f"巡检人:{p.inspector or '-':<10}"
            f"{issue_info}"
        )
        for iss in p_issues:
            click.echo(f"         -> {iss.severity}: {iss.description[:50]}")

    if export and pd is not None:
        rows = []
        for p in sorted(day_plans, key=lambda x: (x.building, x.floor)):
            dev = dev_dict.get(p.device_id)
            p_issues = plan_issue_map.get(p.plan_id, [])
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
                "检查日期": p.check_date or "",
                "检查结果": p.result,
                "隐患数量": len(p_issues),
                "隐患描述": " / ".join(f"[{i.severity}]{i.description}" for i in p_issues),
                "照片数量": len(p.photo_paths),
            })
        df = pd.DataFrame(rows)
        filename = f"检查报告_{check_date}.xlsx"
        path = storage.reports_dir / filename
        df.to_excel(path, index=False, sheet_name="检查记录")
        click.echo("")
        click.echo(click.style(f"已导出：{path}", fg="green"))


@report.command("overdue")
@click.option("--area", "-a", default="", help="按区域筛选")
@click.option("--building", "-b", default="", help="按楼栋筛选")
@click.option("--severity", "-v", default="", help="按严重程度筛选")
@click.option("--export", "-e", is_flag=True, help="导出为 Excel")
def report_overdue(area: str, building: str, severity: str, export: bool):
    """筛选并列出逾期未整改事项。"""
    storage = Storage()
    if not storage.is_initialized():
        click.echo(click.style("错误：请先运行 init 初始化项目", fg="red"))
        return

    issues = storage.get_issues()
    overdue = [i for i in issues if i.is_overdue]

    if area:
        overdue = filter_by_area(overdue, area)
    if building:
        overdue = filter_by_building(overdue, building)
    if severity:
        overdue = [i for i in overdue if i.severity == severity]

    if not overdue:
        click.echo(click.style("没有逾期事项，做得好！", fg="green"))
        return

    overdue.sort(key=lambda i: (severity_order(i.severity), i.deadline))

    click.echo(click.style(f"{'='*120}", fg="red", bold=True))
    click.echo(click.style(f"  逾期事项清单 (共 {len(overdue)} 条)", fg="red", bold=True))
    click.echo(click.style(f"{'='*120}", fg="red", bold=True))

    today = date.today()
    hdr = f"{'编号':<16}{'设备':<12}{'严重':<8}{'楼栋':<12}{'发现日':<12}{'期限':<12}{'逾期天数':<10}{'登记人':<10}描述"
    click.echo(click.style(hdr, fg="yellow"))
    click.echo("-" * 120)

    for i in overdue:
        try:
            dl = datetime.strptime(i.deadline, "%Y-%m-%d").date()
            days = (today - dl).days
        except:
            days = "?"
        desc = i.description[:30] + ("..." if len(i.description) > 30 else "")
        sev_c = {"重大": "red", "严重": "yellow", "一般": "cyan", "轻微": "green"}.get(i.severity, "white")
        click.echo(
            f"{i.issue_id:<16}{i.device_id:<12}"
            f"{click.style(i.severity, fg=sev_c):<14}"
            f"{i.building:<14}{i.report_date:<14}{i.deadline:<14}"
            f"{click.style(str(days) + '天', fg='red'):<12}"
            f"{i.reporter:<12}{desc}"
        )

    click.echo("-" * 120)

    sev_summary = defaultdict(int)
    for i in overdue:
        sev_summary[i.severity] += 1
    click.echo("")
    click.echo("逾期按严重程度统计：")
    for sev in ["重大", "严重", "一般", "轻微"]:
        n = sev_summary.get(sev, 0)
        if n:
            click.echo(f"  {sev}: {n} 条")

    if export and pd is not None:
        rows = []
        for i in overdue:
            try:
                dl = datetime.strptime(i.deadline, "%Y-%m-%d").date()
                days = (today - dl).days
            except:
                days = None
            rows.append({
                "隐患编号": i.issue_id,
                "设备编号": i.device_id,
                "严重程度": i.severity,
                "楼栋": i.building,
                "发现日期": i.report_date,
                "整改期限": i.deadline,
                "逾期天数": days,
                "登记人": i.reporter,
                "隐患描述": i.description,
                "整改措施": i.rectification,
                "当前状态": i.status,
            })
        df = pd.DataFrame(rows)
        filename = f"逾期事项_{today_str()}.xlsx"
        path = storage.reports_dir / filename
        df.to_excel(path, index=False, sheet_name="逾期清单")
        click.echo("")
        click.echo(click.style(f"已导出：{path}", fg="green"))
