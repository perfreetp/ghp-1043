import click
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    pd = None

from ..storage import Storage
from ..models import Device, today_str
from ..utils import validate_device_id


COLUMN_MAPPING = {
    "device_id": ["设备编号", "编号", "device_id", "id", "设备ID"],
    "name": ["设备名称", "名称", "name", "设备名"],
    "location": ["安装位置", "位置", "location", "安装地点"],
    "building": ["楼栋", "所属楼栋", "building", "楼栋号"],
    "floor": ["楼层", "floor", "楼层号"],
    "device_type": ["设备类型", "类型", "device_type", "种类"],
    "area": ["区域", "所属区域", "area", "管辖区域"],
    "notes": ["备注", "说明", "notes", "备注信息"],
}


def _map_columns(df_columns):
    mapping = {}
    for target, candidates in COLUMN_MAPPING.items():
        for col in df_columns:
            if col in candidates:
                mapping[col] = target
                break
    return mapping


def _safe_str(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    return str(val).strip()


def _parse_sheet_arg(sheet: str):
    """将 --sheet 参数解析为 int 序号或 str 名称。"""
    if sheet is None:
        return 0
    s = str(sheet).strip()
    if s.isdigit():
        try:
            return int(s)
        except ValueError:
            return s
    return s


@click.command()
@click.argument("filepath", type=click.Path(exists=True))
@click.option("--sheet", "-s", default="0", help="Excel 工作表序号（0/1）或名称")
@click.option("--area", "-a", default="", help="指定区域（覆盖文件中的区域）")
@click.option("--operator", "-o", default="system", help="操作人")
@click.option("--append/--replace", default=True, help="追加模式（默认追加，--replace 覆盖）")
def import_cmd(filepath: str, sheet: str, area: str, operator: str, append: bool):
    """导入设备清单（支持 Excel/CSV 格式）。

    FILEPATH: 设备清单文件路径
    """
    if pd is None:
        click.echo(click.style("错误：未安装 pandas，请运行: pip install pandas openpyxl", fg="red"))
        return

    storage = Storage()
    if not storage.is_initialized():
        click.echo(click.style("错误：请先运行 init 初始化项目", fg="red"))
        return

    fp = Path(filepath)
    sheet_arg = _parse_sheet_arg(sheet)
    try:
        if fp.suffix.lower() in (".xlsx", ".xls"):
            df = pd.read_excel(fp, sheet_name=sheet_arg)
        elif fp.suffix.lower() == ".csv":
            df = pd.read_csv(fp)
        else:
            click.echo(click.style("错误：仅支持 .xlsx/.xls/.csv 格式", fg="red"))
            return
    except Exception as e:
        click.echo(click.style(f"读取文件失败: {e}", fg="red"))
        return

    col_map = _map_columns(df.columns.tolist())
    if "device_id" not in col_map.values() or "name" not in col_map.values():
        click.echo(click.style("错误：文件缺少必要列（设备编号/设备名称）", fg="red"))
        click.echo(f"当前列名：{list(df.columns)}")
        return

    df = df.rename(columns=col_map)

    new_devices = []
    skipped = 0
    for _, row in df.iterrows():
        device_id = _safe_str(row.get("device_id"))
        if not validate_device_id(device_id):
            skipped += 1
            continue

        device = Device(
            device_id=device_id,
            name=_safe_str(row.get("name")),
            location=_safe_str(row.get("location")),
            building=_safe_str(row.get("building")),
            floor=_safe_str(row.get("floor")),
            device_type=_safe_str(row.get("device_type")),
            area=area or _safe_str(row.get("area")),
            notes=_safe_str(row.get("notes")),
        )
        new_devices.append(device)

    if not new_devices:
        click.echo(click.style("未找到有效设备数据", fg="yellow"))
        return

    existing = storage.get_devices()
    if append:
        existing_ids = {d.device_id for d in existing}
        to_add = [d for d in new_devices if d.device_id not in existing_ids]
        duplicates = len(new_devices) - len(to_add)
        all_devices = existing + to_add
    else:
        all_devices = new_devices
        to_add = new_devices
        duplicates = 0

    storage.save_devices(all_devices)

    buildings = sorted(set(d.building for d in all_devices if d.building))
    device_types = sorted(set(d.device_type for d in all_devices if d.device_type))

    click.echo(click.style(f"导入成功！", fg="green", bold=True))
    click.echo(f"  读取数据：{len(new_devices)} 条")
    click.echo(f"  新增设备：{len(to_add)} 条")
    if skipped:
        click.echo(f"  跳过无效编号：{skipped} 条")
    if append and duplicates:
        click.echo(f"  跳过已存在：{duplicates} 条")
    click.echo(f"  当前总计：{len(all_devices)} 台设备")
    if buildings:
        click.echo(f"  覆盖楼栋：{', '.join(buildings)}")
    if device_types:
        click.echo(f"  设备类型：{', '.join(device_types)}")

    storage.add_log(
        "import", "device", f"{len(to_add)}",
        operator,
        f"导入设备清单: {fp.name}, 新增{len(to_add)}台, 跳过{skipped + duplicates}条"
    )
