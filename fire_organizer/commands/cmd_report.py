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
def report_summary(year, month, area, building):
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
    plans_checked_this_month = [
        p for p in plans
        if p.check_date and is_in_month(p.check_date, year, month)
        and p.status in ("已完成", "有隐患")
    ]
    month_issues = [i for i in issues if is_in_month(i.report_date, year, month)]
    month_closed = [i for i in issues if i.close_date and is_in_month(i.close_date, year, month)]

    if area:
        month_plans = filter_by_area(month_plans, area)
        plans_checked_this_month = filter_by_area(plans_checked_this_month, area)
        month_issues = filter_by_area(month_issues, area)
        month_closed = filter_by_area(month_closed, area)
    if building:
        month_plans = filter_by_building(month_plans, building)
        plans_checked_this_month = filter_by_building(plans_checked_this_month, building)
        month_issues = filter_by_building(month_issues, building)
        month_closed = filter_by_building(month_closed, building)

    devices_dict = {d.device_id: d for d in devices}

    click.echo(click.style(f"{'='*60}", fg="cyan", bold=True))
    click.echo(click.style(f"  月度任务汇总 - {year}年{month:02d}月", fg="cyan", bold=True))
    click.echo(click.style(f"{'='*60}", fg="cyan", bold=True))

    click.echo("")
    click.echo(click.style("【巡检计划统计】", fg="yellow", bold=True))
    total_p = len(month_plans)
    done_plan = len([p for p in month_plans if p.status in ("已完成", "有隐患")])
    done_actual = len(plans_checked_this_month)
    pending_p = len([p for p in month_plans if p.status == "待执行"])
    issue_p = len([p for p in month_plans if p.status == "有隐患"])
    issue_actual = len([p for p in plans_checked_this_month if p.status == "有隐患"])
    rate_p = (done_plan / total_p * 100) if total_p > 0 else 0
    click.echo(f"  本月计划总数：{total_p} 项")
    click.echo(f"  计划内已完成(按计划日期)：{done_plan} 项 ({rate_p:.1f}%)")
    click.echo(click.style(f"  本月实际完成(按检查日期)：{done_actual} 项", fg="cyan", bold=True))
    click.echo(f"  待执行：  {pending_p} 项")
    click.echo(f"  计划中发现隐患：{issue_p} 项")
    if issue_actual != issue_p:
        click.echo(f"  本月实际发现隐患：{issue_actual} 项")

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
        dev_floor_map = {}
        for dv in storage.get_devices():
            dev_floor_map[dv.device_id] = dv.floor
        for i in filtered:
            real_floor = i.floor
            if not real_floor:
                real_floor = dev_floor_map.get(i.device_id, "")
            rows.append({
                "隐患编号": i.issue_id,
                "设备编号": i.device_id,
                "严重程度": i.severity,
                "状态": i.status,
                "是否逾期": "是" if i.is_overdue else "否",
                "楼栋": i.building,
                "楼层": real_floor,
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
@click.option("--date", "-d", default=None, help="计划日期筛选 (YYYY-MM-DD)")
@click.option("--check-date", "-c", default=None, help="实际检查日期筛选 (YYYY-MM-DD)")
@click.option("--building", "-b", default="", help="按楼栋筛选")
@click.option("--area", "-a", default="", help="按区域筛选")
@click.option("--export", "-e", is_flag=True, help="导出为 Excel")
def report_inspection(date, check_date, building, area, export):
    """输出检查报告（按计划日期或实际检查日期筛选）。"""
    storage = Storage()
    if not storage.is_initialized():
        click.echo(click.style("错误：请先运行 init 初始化项目", fg="red"))
        return

    plans = storage.get_plans()
    devices = storage.get_devices()
    issues = storage.get_issues()

    if date:
        day_plans = [p for p in plans if p.plan_date == date]
        date_label = f"计划日期={date}"
    elif check_date:
        day_plans = [p for p in plans if p.check_date == check_date]
        date_label = f"检查日期={check_date}"
    else:
        d = today_str()
        day_plans = [p for p in plans if p.plan_date == d or p.check_date == d]
        date_label = f"计划/检查日期={d}"

    if area:
        day_plans = filter_by_area(day_plans, area)
    if building:
        day_plans = filter_by_building(day_plans, building)

    if not day_plans:
        click.echo(click.style(f"该条件下无记录：{date_label}", fg="yellow"))
        return

    dev_dict = {d.device_id: d for d in devices}
    plan_issue_map = defaultdict(list)
    for i in issues:
        if i.plan_id:
            plan_issue_map[i.plan_id].append(i)

    click.echo(click.style(f"{'='*100}", fg="cyan", bold=True))
    click.echo(click.style(f"  检查报告 - {date_label}", fg="cyan", bold=True))
    click.echo(click.style(f"{'='*100}", fg="cyan", bold=True))

    total = len(day_plans)
    done = len([p for p in day_plans if p.status != "待执行"])
    has_issue = len([p for p in day_plans if p.status == "有隐患"])
    missing_photos = len([p for p in day_plans if p.status != "待执行" and not p.photo_paths])
    overdue_checked = [p for p in day_plans if p.check_date and p.plan_date and p.check_date > p.plan_date]

    click.echo("")
    click.echo(f"  涉及计划：{total}")
    click.echo(f"  已检查：{done} 项 ({done/total*100:.1f}%)")
    click.echo(f"  正常：{done - has_issue} 项")
    click.echo(f"  异常/隐患：{has_issue} 项")
    if missing_photos:
        click.echo(click.style(f"  缺照片：{missing_photos} 项", fg="red"))
    if overdue_checked:
        click.echo(click.style(f"  延期检查：{len(overdue_checked)} 项", fg="yellow"))

    click.echo("")
    click.echo(click.style("【详细记录】", fg="yellow", bold=True))
    for p in sorted(day_plans, key=lambda x: (x.building, x.floor)):
        dev = dev_dict.get(p.device_id)
        st_c = {"待执行": "white", "已完成": "green", "有隐患": "red"}.get(p.status, "white")
        p_issues = plan_issue_map.get(p.plan_id, [])
        issue_info = f" [隐患{len(p_issues)}条]" if p_issues else ""
        plan_cd = f"  计划={p.plan_date}"
        actual_cd = f" 实际={p.check_date or '(未检查)'}"
        date_diff = click.style(" [延期]", fg="yellow") if (
            p.check_date and p.plan_date and p.check_date > p.plan_date
        ) else ""
        click.echo(
            f"  {click.style(p.status, fg=st_c):<10} | "
            f"{p.building:<10} {p.floor:<6} | "
            f"{p.device_id:<14} {dev.name if dev else '':<10} | "
            f"巡检人:{p.inspector or '-':<8}"
            f"{plan_cd} {actual_cd}"
            f"{date_diff}"
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


@report.command("package")
@click.option("--year", "-y", type=int, default=None, help="年份（默认今年）")
@click.option("--month", "-m", type=int, default=None, help="月份（默认本月）")
@click.option("--area", "-a", default="", help="按区域筛选")
@click.option("--building", "-b", default="", help="按楼栋筛选")
@click.option("--zip/--no-zip", default=False, help="打包为 zip 压缩包")
def report_package(year, month, area, building, zip):
    """月度检查包：一次生成汇总+每日检查报告+台账+缺照片+附件索引。"""
    storage = Storage()
    if not storage.is_initialized():
        click.echo(click.style("错误：请先运行 init 初始化项目", fg="red"))
        return
    if pd is None:
        click.echo(click.style("错误：未安装 pandas，请运行 pip install pandas openpyxl", fg="red"))
        return

    today = date.today()
    year = year or today.year
    month = month or today.month
    if not (1 <= month <= 12):
        click.echo(click.style("错误：月份必须在 1-12 之间", fg="red"))
        return

    # 准备基础数据
    plans = storage.get_plans()
    issues = storage.get_issues()
    devices = storage.get_devices()
    dev_dict = {d.device_id: d for d in devices}
    dev_floor_map = {d.device_id: d.floor for d in devices}

    # 按条件筛选
    def _filter(objs):
        r = objs
        if area:
            r = filter_by_area(r, area)
        if building:
            r = filter_by_building(r, building)
        return r

    month_plan_all = [p for p in plans if is_in_month(p.plan_date, year, month)]
    month_plans = _filter(month_plan_all)
    plans_checked_this_month = _filter([
        p for p in plans
        if p.check_date and is_in_month(p.check_date, year, month)
        and p.status in ("已完成", "有隐患")
    ])
    month_issues = _filter([i for i in issues if is_in_month(i.report_date, year, month)])
    month_closed = _filter([i for i in issues if i.close_date and is_in_month(i.close_date, year, month)])

    # 检查包目标目录
    area_suffix = f"_{area}" if area else ""
    bld_suffix = f"_{building}" if building else ""
    pkg_dirname = f"月度检查包_{year}年{month:02d}月{area_suffix}{bld_suffix}"
    pkg_dir = storage.reports_dir / pkg_dirname
    pkg_dir.mkdir(parents=True, exist_ok=True)

    # ========== Sheet 1: 月度汇总 ==========
    total_p = len(month_plans)
    done_plan = len([p for p in month_plans if p.status in ("已完成", "有隐患")])
    done_actual = len(plans_checked_this_month)
    pending_p = total_p - done_plan
    issue_p = len([p for p in month_plans if p.status == "有隐患"])
    issue_actual = len([p for p in plans_checked_this_month if p.status == "有隐患"])
    overdue_plans = _filter([
        p for p in plans if p.check_date and p.plan_date and p.check_date > p.plan_date
        and is_in_month(p.check_date, year, month)
    ])

    summary_rows = [
        {"项目": "月份", "数值": f"{year}年{month:02d}月"},
        {"项目": "区域", "数值": area or "（全部）"},
        {"项目": "楼栋", "数值": building or "（全部）"},
        {"项目": "生成时间", "数值": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        {"项目": "", "数值": ""},
        {"项目": "本月计划总数", "数值": total_p},
        {"项目": "计划内已完成（按计划日期）", "数值": done_plan},
        {"项目": "本月实际完成（按检查日期）", "数值": done_actual},
        {"项目": "待执行", "数值": pending_p},
        {"项目": "计划中发现隐患", "数值": issue_p},
        {"项目": "本月实际发现隐患", "数值": issue_actual},
        {"项目": "延期完成的计划（跨月/补检）", "数值": len(overdue_plans)},
        {"项目": "", "数值": ""},
        {"项目": "隐患：本月新增", "数值": len(month_issues)},
        {"项目": "隐患：本月关闭", "数值": len(month_closed)},
    ]

    # ========== Sheet 2: 每日检查报告（每日一个数据块） ==========
    # 收集该月所有出现计划/检查的日期
    date_set = set()
    for p in month_plans:
        date_set.add(("plan", p.plan_date))
        if p.check_date:
            date_set.add(("check", p.check_date))
    for p in plans_checked_this_month:
        date_set.add(("check", p.check_date))
        if p.plan_date:
            date_set.add(("plan", p.plan_date))
    # 去重日期后排序
    day_dates = sorted(set(d for _, d in date_set))

    inspection_rows = []
    for d in day_dates:
        by_plan = [p for p in month_plans if p.plan_date == d]
        by_check = [p for p in (month_plans + plans_checked_this_month) if p.check_date == d]
        if not by_plan and not by_check:
            continue
        day_total = len(set(p.plan_id for p in (by_plan + by_check)))
        day_done = len(set(p.plan_id for p in (by_plan + by_check) if p.status != "待执行"))
        day_issue = len(set(p.plan_id for p in (by_plan + by_check) if p.status == "有隐患"))
        inspection_rows.append({
            "日期类型": f"--- {d} ---", "计划编号": "", "设备编号": "", "设备名称": "",
            "楼栋": "", "楼层": "", "状态": f"涉及{day_total}项/已检查{day_done}项/隐患{day_issue}项",
            "计划日期": "", "实际检查日期": "", "延期标记": "", "巡检人": "", "检查结果": "", "照片数": ""
        })
        day_pids = set()
        for p in by_plan + by_check:
            if p.plan_id in day_pids:
                continue
            day_pids.add(p.plan_id)
            dev = dev_dict.get(p.device_id)
            overdue_tag = "是" if (p.check_date and p.plan_date and p.check_date > p.plan_date) else ""
            inspection_rows.append({
                "日期类型": "", "计划编号": p.plan_id, "设备编号": p.device_id,
                "设备名称": dev.name if dev else "",
                "楼栋": p.building, "楼层": p.floor,
                "状态": p.status,
                "计划日期": p.plan_date or "",
                "实际检查日期": p.check_date or "",
                "延期标记": overdue_tag,
                "巡检人": p.inspector or "",
                "检查结果": p.result or "",
                "照片数": len(p.photo_paths or []),
            })

    # ========== Sheet 3: 整改台账 ==========
    ledger_rows = []
    all_month_issues = month_issues  # 新增的
    # 再加上：该月关闭（不管之前哪个月新增）但状态是已关闭的也纳入
    for i in _filter(issues):
        if is_in_month(i.report_date, year, month) or (i.close_date and is_in_month(i.close_date, year, month)):
            if any(ir["隐患编号"] == i.issue_id for ir in ledger_rows):
                continue
            real_floor = i.floor
            if not real_floor:
                real_floor = dev_floor_map.get(i.device_id, "")
            ledger_rows.append({
                "隐患编号": i.issue_id,
                "设备编号": i.device_id,
                "严重程度": i.severity,
                "状态": i.status,
                "是否逾期": "是" if i.is_overdue else "否",
                "楼栋": i.building,
                "楼层": real_floor,
                "区域": i.area,
                "发现日期": i.report_date,
                "整改期限": i.deadline,
                "登记人": i.reporter,
                "隐患描述": i.description,
                "整改措施": i.rectification,
                "复查人": i.reviewer,
                "关闭日期": i.close_date or "",
            })

    # ========== Sheet 4: 缺照片清单 ==========
    missing_rows = []
    for p in (month_plans + plans_checked_this_month):
        if p.status != "待执行" and not p.photo_paths:
            dev = dev_dict.get(p.device_id)
            missing_rows.append({
                "来源类型": "计划",
                "编号": p.plan_id,
                "关联设备": p.device_id,
                "设备名称": dev.name if dev else "",
                "楼栋/楼层": f"{p.building} {p.floor}",
                "计划日期": p.plan_date or "",
                "实际检查日期": p.check_date or "",
                "当前状态": p.status,
                "缺失字段": "photo_paths",
                "备注": p.result or "",
            })
    for i in _filter(issues):
        if i.status == "待整改" and not i.photo_before:
            real_floor = i.floor or dev_floor_map.get(i.device_id, "")
            missing_rows.append({
                "来源类型": "隐患(整改前)",
                "编号": i.issue_id,
                "关联设备": i.device_id,
                "设备名称": dev_dict.get(i.device_id).name if dev_dict.get(i.device_id) else "",
                "楼栋/楼层": f"{i.building} {real_floor}",
                "计划日期": "", "实际检查日期": i.report_date,
                "当前状态": i.status,
                "缺失字段": "photo_before",
                "备注": i.description,
            })
        if i.status == "已关闭" and not i.photo_after:
            real_floor = i.floor or dev_floor_map.get(i.device_id, "")
            missing_rows.append({
                "来源类型": "隐患(整改后)",
                "编号": i.issue_id,
                "关联设备": i.device_id,
                "设备名称": dev_dict.get(i.device_id).name if dev_dict.get(i.device_id) else "",
                "楼栋/楼层": f"{i.building} {real_floor}",
                "计划日期": "", "实际检查日期": i.close_date or "",
                "当前状态": i.status,
                "缺失字段": "photo_after",
                "备注": i.rectification or "",
            })

    # ========== Sheet 5: 附件目录说明（计划照片 + 隐患照片映射） ==========
    attach_rows = []
    for p in (month_plans + plans_checked_this_month):
        if not p.photo_paths:
            continue
        dev = dev_dict.get(p.device_id)
        for idx, ph in enumerate(p.photo_paths, 1):
            abs_p = storage.project_path / ph
            size = abs_p.stat().st_size if abs_p.exists() else -1
            overdue_tag = "是" if (p.check_date and p.plan_date and p.check_date > p.plan_date) else ""
            attach_rows.append({
                "关联类型": "巡检计划",
                "关联编号": p.plan_id,
                "关联设备": p.device_id,
                "设备名称": dev.name if dev else "",
                "计划日期": p.plan_date or "",
                "实际检查日期": p.check_date or "",
                "延期完成": overdue_tag,
                "计划状态": p.status,
                "照片序号": f"{idx}/{len(p.photo_paths)}",
                "附件相对路径": ph,
                "文件大小(字节)": size if size >= 0 else "(文件不存在)",
            })
    for i in _filter(issues):
        if not (i.photo_before or i.photo_after):
            continue
        dev = dev_dict.get(i.device_id)
        real_floor = i.floor or dev_floor_map.get(i.device_id, "")
        for idx, ph in enumerate(i.photo_before, 1):
            abs_p = storage.project_path / ph
            size = abs_p.stat().st_size if abs_p.exists() else -1
            attach_rows.append({
                "关联类型": "隐患(整改前)",
                "关联编号": i.issue_id,
                "关联设备": i.device_id,
                "设备名称": dev.name if dev else "",
                "计划日期": "",
                "实际检查日期": i.report_date,
                "延期完成": "",
                "计划状态": i.status,
                "照片序号": f"前{idx}/{len(i.photo_before)}",
                "附件相对路径": ph,
                "文件大小(字节)": size if size >= 0 else "(文件不存在)",
            })
        for idx, ph in enumerate(i.photo_after, 1):
            abs_p = storage.project_path / ph
            size = abs_p.stat().st_size if abs_p.exists() else -1
            attach_rows.append({
                "关联类型": "隐患(整改后)",
                "关联编号": i.issue_id,
                "关联设备": i.device_id,
                "设备名称": dev.name if dev else "",
                "计划日期": "",
                "实际检查日期": i.close_date or "",
                "延期完成": "",
                "计划状态": i.status,
                "照片序号": f"后{idx}/{len(i.photo_after)}",
                "附件相对路径": ph,
                "文件大小(字节)": size if size >= 0 else "(文件不存在)",
            })

    # ========== Sheet 6: 延期完成计划清单 ==========
    overdue_rows = []
    for p in _filter(plans):
        if p.check_date and p.plan_date and p.check_date > p.plan_date:
            try:
                from datetime import datetime as _dt
                d1 = _dt.strptime(p.plan_date, "%Y-%m-%d").date()
                d2 = _dt.strptime(p.check_date, "%Y-%m-%d").date()
                days = (d2 - d1).days
            except:
                days = "?"
            dev = dev_dict.get(p.device_id)
            overdue_rows.append({
                "计划编号": p.plan_id,
                "设备编号": p.device_id,
                "设备名称": dev.name if dev else "",
                "楼栋": p.building,
                "楼层": p.floor,
                "计划日期": p.plan_date,
                "实际检查日期": p.check_date,
                "延期天数": days,
                "巡检人": p.inspector or "",
                "状态": p.status,
                "检查结果": (p.result or "")[:80],
            })

    # ========== 如果 --zip：先复制附件建立「原路径→包内路径」映射 ==========
    rel_to_pkg_path = {}
    if zip:
        import shutil as _shutil
        attach_dst_dir = pkg_dir / "附件照片"
        copied_rel = set()
        for r in attach_rows:
            rel = r["附件相对路径"]
            if rel in copied_rel:
                continue
            src = storage.project_path / rel
            if src.exists():
                dst = attach_dst_dir / Path(rel).name
                i = 1
                orig_stem, orig_suffix = Path(rel).stem, Path(rel).suffix
                while dst.exists():
                    dst = attach_dst_dir / f"{orig_stem}_{i}{orig_suffix}"
                    i += 1
                dst.parent.mkdir(parents=True, exist_ok=True)
                _shutil.copy2(src, dst)
                copied_rel.add(rel)
                pkg_in_path = f"附件照片/{dst.name}"
                rel_to_pkg_path[rel] = pkg_in_path

    # ========== 回填 attach_rows 包内路径列 ==========
    for r in attach_rows:
        r["包内路径"] = rel_to_pkg_path.get(r["附件相对路径"], "")

    # ========== 写入 Excel ==========
    pkg_file = pkg_dir / f"月度检查包_{year}年{month:02d}月{area_suffix}{bld_suffix}.xlsx"
    with pd.ExcelWriter(pkg_file, engine="openpyxl") as writer:
        pd.DataFrame(summary_rows).to_excel(writer, index=False, sheet_name="月度汇总")
        pd.DataFrame(inspection_rows).to_excel(writer, index=False, sheet_name="每日检查报告")
        pd.DataFrame(ledger_rows).to_excel(writer, index=False, sheet_name="整改台账")
        pd.DataFrame(missing_rows).to_excel(writer, index=False, sheet_name="缺照片清单")
        pd.DataFrame(attach_rows).to_excel(writer, index=False, sheet_name="附件目录说明")
        pd.DataFrame(overdue_rows).to_excel(writer, index=False, sheet_name="延期完成计划")

    # ========== zip 打包 ==========
    zip_path_out = ""
    if zip:
        import shutil as _shutil2
        zip_base = str(pkg_dir)
        zip_path_out = _shutil2.make_archive(zip_base, "zip", root_dir=pkg_dir.parent, base_dir=pkg_dir.name)
        click.echo(click.style(f"已生成 zip 包：{zip_path_out}", fg="green", bold=True))

    click.echo(click.style("=" * 80, fg="cyan", bold=True))
    click.echo(click.style(f"  月度检查包生成完成 - {year}年{month:02d}月{area_suffix}{bld_suffix}", fg="cyan", bold=True))
    click.echo(click.style("=" * 80, fg="cyan", bold=True))
    click.echo(f"  目录：{pkg_dir}")
    click.echo(f"  主文件：{pkg_file}")
    click.echo("")
    click.echo(f"  包含 Sheet：")
    click.echo(f"    - 月度汇总 ({len(summary_rows)} 项指标)")
    click.echo(f"    - 每日检查报告 ({len(day_dates)} 天, {len([r for r in inspection_rows if r['日期类型']==''])} 条记录)")
    click.echo(f"    - 整改台账 ({len(ledger_rows)} 条)")
    click.echo(f"    - 缺照片清单 ({len(missing_rows)} 项)")
    click.echo(f"    - 附件目录说明 ({len(attach_rows)} 条照片映射)")
    click.echo(f"    - 延期完成计划 ({len(overdue_rows)} 条)")
    if zip:
        click.echo(f"    - 附件照片 ({len(copied_rel)} 个文件已复制)")

