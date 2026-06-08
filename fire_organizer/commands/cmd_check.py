import click

from ..storage import Storage
from ..utils import (
    find_duplicate_ids, find_missing_fields, validate_device_id,
    filter_by_area, filter_by_building
)


@click.command()
@click.option("--area", "-a", default="", help="按区域筛选")
@click.option("--building", "-b", default="", help="按楼栋筛选")
@click.option("--details/--summary", default=False, help="显示详细信息")
def check(area: str, building: str, details: bool):
    """校验设备编号重复、必填项缺失等数据质量问题。"""
    storage = Storage()
    if not storage.is_initialized():
        click.echo(click.style("错误：请先运行 init 初始化项目", fg="red"))
        return

    devices = storage.get_devices()
    total = len(devices)
    if total == 0:
        click.echo(click.style("尚未导入任何设备数据", fg="yellow"))
        return

    if area:
        devices = filter_by_area(devices, area)
        click.echo(f"筛选区域：{area}")
    if building:
        devices = filter_by_building(devices, building)
        click.echo(f"筛选楼栋：{building}")

    click.echo(click.style(f"=== 数据校验报告 ===", fg="cyan", bold=True))
    click.echo(f"抽检设备数：{len(devices)} / 总计：{total}")

    problem_count = 0

    dup_ids = find_duplicate_ids(devices)
    click.echo("")
    if dup_ids:
        problem_count += len(dup_ids)
        click.echo(click.style(f"[问题1] 编号重复：{len(dup_ids)} 个", fg="red", bold=True))
        if details:
            for did in dup_ids:
                dup_devices = [d for d in devices if d.device_id == did]
                locations = ", ".join(f"{d.building}-{d.location}" for d in dup_devices)
                click.echo(f"  • {did}: {locations}")
    else:
        click.echo(click.style(f"[通过1] 编号唯一性检查：无重复", fg="green"))

    missing_list = find_missing_fields(devices)
    click.echo("")
    if missing_list:
        problem_count += len(missing_list)
        click.echo(click.style(f"[问题2] 必填项缺失：{len(missing_list)} 条", fg="red", bold=True))
        if details:
            for dev_id, fields in missing_list:
                click.echo(f"  • {dev_id}: 缺少 {', '.join(fields)}")
    else:
        click.echo(click.style(f"[通过2] 必填项完整性检查：全部完整", fg="green"))

    invalid_ids = [d for d in devices if not validate_device_id(d.device_id)]
    click.echo("")
    if invalid_ids:
        problem_count += len(invalid_ids)
        click.echo(click.style(f"[问题3] 编号格式无效：{len(invalid_ids)} 条", fg="red", bold=True))
        if details:
            for d in invalid_ids:
                click.echo(f"  • {d.device_id} ({d.name})")
    else:
        click.echo(click.style(f"[通过3] 编号格式检查：全部有效", fg="green"))

    no_location = [d for d in devices if not d.building]
    click.echo("")
    if no_location:
        problem_count += len(no_location)
        click.echo(click.style(f"[问题4] 楼栋信息缺失：{len(no_location)} 条", fg="red", bold=True))
        if details:
            for d in no_location:
                click.echo(f"  • {d.device_id}: {d.name}")
    else:
        click.echo(click.style(f"[通过4] 楼栋信息检查：全部完整", fg="green"))

    click.echo("")
    click.echo(click.style("=" * 40, fg="cyan", bold=True))
    if problem_count == 0:
        click.echo(click.style(f"数据质量良好，未发现问题！", fg="green", bold=True))
    else:
        click.echo(click.style(f"共发现 {problem_count} 个问题，请及时修复。", fg="red", bold=True))
