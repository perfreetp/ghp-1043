import click
from pathlib import Path
from typing import Optional

from ..storage import Storage
from ..models import Issue, PlanItem, generate_id, today_str
from ..utils import (
    filter_by_area, filter_by_building, severity_order,
    parse_date
)


@click.group()
def issue():
    """隐患管理：登记、修改、查询、列出缺失照片。"""
    pass


@issue.command("list")
@click.option("--area", "-a", default="", help="按区域筛选")
@click.option("--building", "-b", default="", help="按楼栋筛选")
@click.option("--status", "-s", default="", help="按状态筛选：待整改/整改中/待复查/已关闭")
@click.option("--severity", "-v", default="", help="按严重程度：重大/严重/一般/轻微")
@click.option("--overdue/--all", default=False, help="仅显示逾期事项")
def issue_list(area: str, building: str, status: str, severity: str, overdue: bool):
    """列出隐患清单。"""
    storage = Storage()
    if not storage.is_initialized():
        click.echo(click.style("错误：请先运行 init 初始化项目", fg="red"))
        return

    issues = storage.get_issues()
    if not issues:
        click.echo(click.style("暂无隐患记录", fg="yellow"))
        return

    if area:
        issues = filter_by_area(issues, area)
    if building:
        issues = filter_by_building(issues, building)
    if status:
        issues = [i for i in issues if i.status == status]
    if severity:
        issues = [i for i in issues if i.severity == severity]
    if overdue:
        issues = [i for i in issues if i.is_overdue]

    if not issues:
        click.echo(click.style("没有符合条件的隐患记录", fg="yellow"))
        return

    issues.sort(key=lambda i: (severity_order(i.severity), i.deadline or "9999-99-99"))

    click.echo(click.style(f"{'='*100}", fg="cyan", bold=True))
    header = f"{'编号':<16}{'设备':<12}{'严重':<6}{'状态':<8}{'楼栋':<10}{'期限':<12}{'逾期':<6}描述"
    click.echo(click.style(header, fg="cyan", bold=True))
    click.echo(click.style(f"{'-'*100}", fg="cyan"))

    for i in issues:
        overdue_mark = click.style("是", fg="red") if i.is_overdue else "否"
        sev_color = {"重大": "red", "严重": "yellow", "一般": "cyan", "轻微": "green"}.get(i.severity, "white")
        sev = click.style(i.severity, fg=sev_color)
        st_color = {"待整改": "red", "整改中": "yellow", "待复查": "blue", "已关闭": "green"}.get(i.status, "white")
        st = click.style(i.status, fg=st_color)
        desc = i.description[:40] + ("..." if len(i.description) > 40 else "")
        click.echo(f"{i.issue_id:<16}{i.device_id:<12}{sev:<14}{st:<10}{i.building:<12}{i.deadline:<14}{overdue_mark:<8}{desc}")

    click.echo(click.style(f"{'-'*100}", fg="cyan"))
    click.echo(f"共 {len(issues)} 条隐患记录")


@issue.command("add")
@click.option("--plan-id", "-p", default="", help="关联的巡检计划编号")
@click.option("--device-id", "-d", required=True, help="设备编号")
@click.option("--description", "-D", required=True, help="隐患描述")
@click.option("--severity", "-v", default="一般", help="严重程度：重大/严重/一般/轻微",
              type=click.Choice(["重大", "严重", "一般", "轻微"]))
@click.option("--report-date", "-r", default=None, help="发现日期 (YYYY-MM-DD，默认今天)")
@click.option("--deadline", "-e", required=True, help="整改期限 (YYYY-MM-DD)")
@click.option("--reporter", "-R", default="system", help="登记人")
@click.option("--building", "-b", default="", help="楼栋（可从设备自动获取）")
@click.option("--area", "-a", default="", help="区域")
def issue_add(plan_id: str, device_id: str, description: str, severity: str,
              report_date: Optional[str], deadline: str, reporter: str,
              building: str, area: str):
    """登记一条新隐患。"""
    storage = Storage()
    if not storage.is_initialized():
        click.echo(click.style("错误：请先运行 init 初始化项目", fg="red"))
        return

    devices = storage.get_devices()
    dev = next((d for d in devices if d.device_id == device_id), None)
    if dev:
        building = building or dev.building
        area = area or dev.area
    elif not building:
        click.echo(click.style("警告：未找到该设备，请指定 --building 参数", fg="yellow"))

    if not parse_date(deadline):
        click.echo(click.style(f"错误：整改期限格式无效: {deadline}，请使用 YYYY-MM-DD", fg="red"))
        return

    new_issue = Issue(
        issue_id=generate_id("IS"),
        plan_id=plan_id,
        device_id=device_id,
        description=description,
        severity=severity,
        report_date=report_date or today_str(),
        deadline=deadline,
        reporter=reporter,
        building=building,
        area=area,
        status="待整改",
    )

    issues = storage.get_issues()
    issues.append(new_issue)
    storage.save_issues(issues)

    if plan_id:
        plans = storage.get_plans()
        for p in plans:
            if p.plan_id == plan_id:
                p.status = "有隐患"
        storage.save_plans(plans)

    click.echo(click.style(f"隐患登记成功！", fg="green", bold=True))
    click.echo(f"  隐患编号：{new_issue.issue_id}")
    click.echo(f"  设备编号：{device_id}")
    click.echo(f"  严重程度：{severity}")
    click.echo(f"  整改期限：{deadline}")
    if building:
        click.echo(f"  所属楼栋：{building}")
    click.echo(f"  隐患描述：{description}")

    storage.add_log(
        "issue_add", "issue", new_issue.issue_id,
        reporter,
        f"登记隐患[{severity}]: {device_id}, 期限{deadline}"
    )


@issue.command("update")
@click.argument("issue_id")
@click.option("--description", "-D", default=None, help="修改隐患描述")
@click.option("--severity", "-v", default=None, help="修改严重程度",
              type=click.Choice(["重大", "严重", "一般", "轻微"]))
@click.option("--deadline", "-e", default=None, help="修改整改期限 (YYYY-MM-DD)")
@click.option("--status", "-s", default=None, help="修改状态",
              type=click.Choice(["待整改", "整改中", "待复查", "已关闭"]))
@click.option("--rectification", "-c", default=None, help="整改措施说明")
@click.option("--operator", "-o", default="system", help="操作人")
def issue_update(issue_id: str, description: Optional[str], severity: Optional[str],
                 deadline: Optional[str], status: Optional[str],
                 rectification: Optional[str], operator: str):
    """修改隐患信息。"""
    storage = Storage()
    if not storage.is_initialized():
        click.echo(click.style("错误：请先运行 init 初始化项目", fg="red"))
        return

    issues = storage.get_issues()
    target = next((i for i in issues if i.issue_id == issue_id), None)
    if not target:
        click.echo(click.style(f"错误：未找到隐患编号 {issue_id}", fg="red"))
        return

    updated = []
    if description is not None:
        target.description = description
        updated.append("描述")
    if severity is not None:
        target.severity = severity
        updated.append("严重程度")
    if deadline is not None:
        if not parse_date(deadline):
            click.echo(click.style(f"错误：期限格式无效", fg="red"))
            return
        target.deadline = deadline
        updated.append("整改期限")
    if status is not None:
        target.status = status
        updated.append("状态")
    if rectification is not None:
        target.rectification = rectification
        updated.append("整改措施")

    if not updated:
        click.echo("未指定任何修改项")
        return

    storage.save_issues(issues)
    click.echo(click.style(f"已更新: {', '.join(updated)}", fg="green"))

    storage.add_log(
        "issue_update", "issue", issue_id,
        operator,
        f"修改隐患: {', '.join(updated)}"
    )


@issue.command("missing-photos")
@click.option("--area", "-a", default="", help="按区域筛选")
@click.option("--building", "-b", default="", help="按楼栋筛选")
def missing_photos(area: str, building: str):
    """列出缺少照片的计划和隐患。"""
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

    click.echo(click.style("=== 缺少照片的巡检计划 ===", fg="cyan", bold=True))
    missing_plan_photos = [
        p for p in plans
        if p.status in ("已完成", "有隐患") and not p.photo_paths
    ]
    if missing_plan_photos:
        for p in missing_plan_photos:
            click.echo(f"  {p.plan_id} | {p.device_id} | {p.building} | {p.floor} | {p.plan_date}")
        click.echo(f"共 {len(missing_plan_photos)} 条计划缺少照片")
    else:
        click.echo(click.style("  所有已完成计划均已上传照片", fg="green"))

    click.echo("")
    click.echo(click.style("=== 缺少整改前照片的隐患 ===", fg="cyan", bold=True))
    missing_before = [i for i in issues if not i.photo_before]
    if missing_before:
        for i in missing_before:
            click.echo(f"  {i.issue_id} | {i.device_id} | {i.severity} | {i.status}")
        click.echo(f"共 {len(missing_before)} 条隐患缺少整改前照片")
    else:
        click.echo(click.style("  所有隐患均已上传整改前照片", fg="green"))

    click.echo("")
    click.echo(click.style("=== 缺少整改后照片的隐患 ===", fg="cyan", bold=True))
    closed_issues = [i for i in issues if i.status == "已关闭"]
    missing_after = [i for i in closed_issues if not i.photo_after]
    if missing_after:
        for i in missing_after:
            click.echo(f"  {i.issue_id} | {i.device_id} | {i.close_date}")
        click.echo(f"共 {len(missing_after)} 条已关闭隐患缺少整改后照片")
    else:
        click.echo(click.style("  所有已关闭隐患均已上传整改后照片", fg="green"))


@issue.command("logs")
@click.option("--limit", "-n", default=50, help="显示最近N条")
def issue_logs(limit: int):
    """查看操作记录。"""
    storage = Storage()
    if not storage.is_initialized():
        click.echo(click.style("错误：请先运行 init 初始化项目", fg="red"))
        return

    logs = storage.get_logs()
    if not logs:
        click.echo(click.style("暂无操作记录", fg="yellow"))
        return

    logs = logs[-limit:]
    click.echo(click.style(f"{'时间':<20}{'操作':<12}{'类型':<10}{'对象ID':<18}{'操作人':<12}详情", fg="cyan", bold=True))
    click.echo("-" * 90)
    for log in logs:
        details = log.details[:50] + ("..." if len(log.details) > 50 else "")
        click.echo(f"{log.timestamp:<20}{log.action:<12}{log.target_type:<10}{log.target_id:<18}{log.operator:<12}{details}")
    click.echo("-" * 90)
    click.echo(f"显示最近 {len(logs)} 条记录")
