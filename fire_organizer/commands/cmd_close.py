import click
from typing import Optional

from ..storage import Storage
from ..models import today_str
from ..utils import filter_by_building, filter_by_area


@click.command()
@click.argument("issue_ids", nargs=-1, required=False)
@click.option("--all", "-a", "close_all", is_flag=True, help="关闭所有待复查的隐患")
@click.option("--building", "-b", default="", help="按楼栋筛选待复查隐患")
@click.option("--area", "-r", default="", help="按区域筛选待复查隐患")
@click.option("--reviewer", "-R", default="system", help="复查人")
@click.option("--close-date", "-d", default=None, help="关闭日期 (YYYY-MM-DD，默认今天)")
@click.option("--rectification", "-c", default="", help="整改说明")
@click.option("--dry-run", is_flag=True, help="仅列出将关闭的隐患，不实际执行")
def close(issue_ids, close_all: bool, building: str, area: str,
          reviewer: str, close_date: Optional[str], rectification: str,
          dry_run: bool):
    """关闭已复查通过的隐患（状态变为"已关闭"）。"""
    storage = Storage()
    if not storage.is_initialized():
        click.echo(click.style("错误：请先运行 init 初始化项目", fg="red"))
        return

    issues = storage.get_issues()
    if not issues:
        click.echo(click.style("暂无隐患记录", fg="yellow"))
        return

    to_close = []

    if issue_ids:
        for iid in issue_ids:
            target = next((i for i in issues if i.issue_id == iid), None)
            if not target:
                click.echo(click.style(f"警告：未找到隐患 {iid}", fg="yellow"))
                continue
            if target.status == "已关闭":
                click.echo(click.style(f"跳过：{iid} 已处于关闭状态", fg="yellow"))
                continue
            to_close.append(target)
    elif close_all:
        candidates = [i for i in issues if i.status != "已关闭"]
        if building:
            candidates = filter_by_building(candidates, building)
        if area:
            candidates = filter_by_area(candidates, area)
        to_close = candidates
    else:
        pending = [i for i in issues if i.status == "待复查"]
        if building:
            pending = filter_by_building(pending, building)
        if area:
            pending = filter_by_area(pending, area)
        to_close = pending

    if not to_close:
        click.echo(click.style("没有需要关闭的隐患", fg="yellow"))
        return

    c_date = close_date or today_str()

    click.echo(click.style(f"以下 {len(to_close)} 条隐患将被关闭：", fg="yellow", bold=True))
    click.echo(click.style(f"{'编号':<16}{'设备':<12}{'严重':<8}{'楼栋':<12}{'状态':<10}描述", fg="cyan"))
    for i in to_close:
        desc = i.description[:30] + ("..." if len(i.description) > 30 else "")
        click.echo(f"{i.issue_id:<16}{i.device_id:<12}{i.severity:<10}{i.building:<14}{i.status:<12}{desc}")

    if dry_run:
        click.echo("")
        click.echo(click.style("[试运行模式] 未执行实际关闭操作", fg="yellow"))
        return

    if not click.confirm(f"\n确认由 [{reviewer}] 关闭以上 {len(to_close)} 条隐患？"):
        click.echo("已取消操作。")
        return

    closed = 0
    for i in to_close:
        i.status = "已关闭"
        i.close_date = c_date
        i.reviewer = reviewer
        if rectification:
            i.rectification = (i.rectification + "\n" if i.rectification else "") + rectification
        closed += 1

    storage.save_issues(issues)

    click.echo(click.style(f"成功关闭 {closed} 条隐患！", fg="green", bold=True))
    click.echo(f"  复查人：{reviewer}")
    click.echo(f"  关闭日期：{c_date}")

    storage.add_log(
        "close", "issue", f"{closed}条",
        reviewer,
        f"批量关闭隐患{closed}条"
    )
