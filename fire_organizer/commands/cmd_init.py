import click

from ..storage import Storage


@click.command()
@click.option("--name", "-n", required=True, help="项目名称")
@click.option("--area", "-a", default="", help="区域名称")
@click.option("--manager", "-m", default="", help="安全负责人")
@click.option("--path", "-p", default=".", help="项目路径（默认为当前目录）")
def init(name: str, area: str, manager: str, path: str):
    """初始化消防资料项目，建立目录结构。"""
    storage = Storage(path)
    if storage.is_initialized():
        click.echo(click.style(f"错误：项目目录已存在，请勿重复初始化", fg="red"))
        return

    success = storage.initialize_project(name, area, manager)
    if success:
        click.echo(click.style(f"项目初始化成功！", fg="green", bold=True))
        click.echo(f"  项目名称：{name}")
        if area:
            click.echo(f"  所属区域：{area}")
        if manager:
            click.echo(f"  安全负责人：{manager}")
        click.echo(f"  项目路径：{storage.project_path}")
        click.echo("")
        click.echo("已创建目录结构：")
        click.echo("  .fire_data/       数据存储（设备、计划、隐患、日志）")
        click.echo("  attachments/      附件目录（照片、文档）")
        click.echo("  exports/          导出文件目录")
        click.echo("  reports/          检查报告目录")
        click.echo("  imports/          待导入文件目录")
        click.echo("")
        click.echo("提示：使用 fire-org --help 查看所有命令")
    else:
        click.echo(click.style("初始化失败，请检查目录权限", fg="red"))
