import click
from datetime import date

from .storage import Storage
from .commands import (
    init, import_cmd, check, plan, issue, close, report, export, photo
)


BANNER = """
╔══════════════════════════════════════════════════════════════╗
║              🔥 消防资料整理器 Fire-Organizer               ║
║          消防检查资料批量维护工具 v1.0.0                     ║
╚══════════════════════════════════════════════════════════════╝
"""


@click.group(
    help=BANNER + """
消防资料整理器 - 为安全员设计的本地批量消防检查资料维护工具。

\b
支持的命令：
  init      初始化项目目录结构
  import    导入设备清单 (Excel/CSV)
  check     校验编号重复和必填项完整性
  plan      巡检计划（生成/导入/回滚/历史查询）
  issue     隐患管理（登记/修改/查询/列缺照片/操作日志）
  close     关闭已复查通过的隐患
  report    报告管理（月度汇总/整改台账/检查报告/逾期筛选/月度检查包）
  export    导出工具（批量重命名附件/导出交付包）
  photo     照片管理（缺失/重复/未引用校验 + 丢失照片重关联）

\b
常用示例：
  fire-org init -n "A厂区消防项目" -a "华东区" -m "张工"
  fire-org import devices.xlsx --append
  fire-org plan -d 2026-06-10 -i "李工" -b "1号楼"
  fire-org plan import 巡检表.xlsx --dry-run --export-diff
  fire-org plan imports
  fire-org plan rollback --last
  fire-org photo audit -v
  fire-org report package -y 2026 -m 6 -a 华东区 --zip
  fire-org issue add -d FH-001 -D "灭火器压力不足" -v 一般 -e 2026-06-20
  fire-org check --details
  fire-org report summary -y 2026 -m 6
  fire-org report ledger -y 2026 -m 6 --export
  fire-org export package -f zip
""",
    cls=click.Group,
    context_settings={"help_option_names": ["-h", "--help"]}
)
@click.version_option(version="1.0.0", prog_name="fire-org")
def cli():
    """消防资料整理器 CLI 主入口。"""
    pass


cli.add_command(init, name="init")
cli.add_command(import_cmd, name="import")
cli.add_command(check, name="check")
cli.add_command(plan, name="plan")
cli.add_command(issue, name="issue")
cli.add_command(close, name="close")
cli.add_command(report, name="report")
cli.add_command(export, name="export")
cli.add_command(photo, name="photo")


@cli.command(name="status")
def cmd_status():
    """查看当前项目状态概览。"""
    storage = Storage()
    if not storage.is_initialized():
        click.echo(click.style("未初始化项目，请先运行: fire-org init", fg="yellow"))
        return

    config = storage.get_config()
    devices = storage.get_devices()
    plans = storage.get_plans()
    issues = storage.get_issues()
    logs = storage.get_logs()

    click.echo(click.style(BANNER, fg="cyan"))
    click.echo(click.style("【项目信息】", fg="yellow", bold=True))
    click.echo(f"  项目名称：{config.get('project_name', '-')}")
    click.echo(f"  所属区域：{config.get('area', '-')}")
    click.echo(f"  安全负责人：{config.get('manager', '-')}")
    click.echo(f"  创建时间：{config.get('created_at', '-')}")
    click.echo(f"  项目路径：{storage.project_path}")

    click.echo("")
    click.echo(click.style("【数据概览】", fg="yellow", bold=True))
    click.echo(f"  设备总数：{len(devices)} 台")
    if devices:
        buildings = sorted(set(d.building for d in devices if d.building))
        types = sorted(set(d.device_type for d in devices if d.device_type))
        click.echo(f"  覆盖楼栋：{len(buildings)} 个 ({', '.join(buildings[:5])}{'...' if len(buildings) > 5 else ''})")
        click.echo(f"  设备类型：{len(types)} 种 ({', '.join(types[:5])}{'...' if len(types) > 5 else ''})")

    click.echo(f"  巡检计划：{len(plans)} 条")
    if plans:
        today = date.today().strftime("%Y-%m-%d")
        pending = len([p for p in plans if p.status == "待执行"])
        done = len([p for p in plans if p.status in ("已完成", "有隐患")])
        with_issue = len([p for p in plans if p.status == "有隐患"])
        click.echo(f"    - 待执行：{pending}")
        click.echo(f"    - 已完成：{done}")
        click.echo(f"    - 有隐患：{with_issue}")

    click.echo(f"  隐患记录：{len(issues)} 条")
    if issues:
        active = [i for i in issues if i.status != "已关闭"]
        closed = len(issues) - len(active)
        overdue = [i for i in active if i.is_overdue]
        click.echo(f"    - 未关闭：{len(active)}")
        click.echo(f"    - 已关闭：{closed}")
        if overdue:
            click.echo(click.style(f"    - 已逾期：{len(overdue)} 条 ⚠️", fg="red"))
        else:
            click.echo(click.style(f"    - 已逾期：0", fg="green"))

    click.echo(f"  操作日志：{len(logs)} 条")

    attachments_dir = storage.attachments_dir
    if attachments_dir.exists():
        photo_count = sum(1 for _ in attachments_dir.rglob("*") if _.is_file())
        click.echo(f"  附件文件：{photo_count} 个")


def main():
    cli()


if __name__ == "__main__":
    main()
