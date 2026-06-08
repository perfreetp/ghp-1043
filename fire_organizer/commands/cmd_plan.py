import click
import copy
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
    get_all_buildings, parse_date
)


PLAN_RESULT_COLUMNS = {
    "plan_id": ["计划编号", "plan_id", "巡检编号"],
    "device_id": ["设备编号", "device_id"],
    "status": ["状态", "status"],
    "result": ["检查结果", "结果", "result"],
    "check_date": ["检查日期", "check_date", "实际检查日期"],
    "notes": ["备注", "notes", "说明"],
    "photo_paths": ["照片路径", "照片", "photo_paths", "图片路径"],
}


def _map_plan_columns(df_columns):
    mapping = {}
    for target, candidates in PLAN_RESULT_COLUMNS.items():
        for col in df_columns:
            if col in candidates:
                mapping[col] = target
                break
    return mapping


def _parse_photo_paths(raw_val):
    if raw_val is None:
        return []
    if isinstance(raw_val, float) and pd.isna(raw_val):
        return []
    s = str(raw_val).strip()
    if not s:
        return []
    for sep in ["\n", ";", "；", "|", ","]:
        if sep in s:
            return [p.strip() for p in s.split(sep) if p.strip()]
    return [s]


def _infer_status(raw_status, raw_result):
    """根据巡检表中填写的状态/结果，推断统一的计划状态"""
    s_val = str(raw_status or "").strip()
    r_val = str(raw_result or "").strip()
    combined = (s_val + r_val)
    keywords_issue = ["隐患", "异常", "不合格", "有问题", "待整改", "坏", "损坏", "失效", "不足"]
    keywords_done = ["已完成", "已检查", "完成", "正常", "合格", "通过", "检查", "ok", "OK"]
    for kw in keywords_issue:
        if kw in combined:
            return "有隐患"
    for kw in keywords_done:
        if kw in combined:
            return "已完成"
    if r_val or s_val in ["已完成", "已检查", "有隐患"]:
        return "已完成"
    return "待执行"


def _collect_changes(storage, df, copy_photos):
    """核心：解析每一行，返回 changes（成功）和 skipped（跳过/警告）。"""
    plans = storage.get_plans()
    plans_work = [copy.deepcopy(p) for p in plans]
    plan_map = {p.plan_id: p for p in plans_work}

    changes_list = []
    skipped = defaultdict(list)
    copied_attachments = []
    diff_rows = []

    for idx, row in df.iterrows():
        row_no = idx + 2
        raw_plan_id = row.get("plan_id", "")
        plan_id = ""
        if raw_plan_id is not None and not (isinstance(raw_plan_id, float) and pd.isna(raw_plan_id)):
            plan_id = str(raw_plan_id).strip()

        if not plan_id:
            skipped["缺少计划编号"].append(f"第{row_no}行")
            diff_rows.append({
                "行号": row_no, "计划编号": "", "设备编号": "",
                "类别": "跳过", "原因": "缺少计划编号", "变更内容": ""
            })
            continue

        target = plan_map.get(plan_id)
        if target is None:
            skipped["计划编号不存在"].append(f"第{row_no}行 {plan_id}")
            diff_rows.append({
                "行号": row_no, "计划编号": plan_id, "设备编号": "",
                "类别": "跳过", "原因": "计划编号不存在", "变更内容": ""
            })
            continue

        device_id_raw = row.get("device_id", "") if "device_id" in df.columns else None
        device_id = ""
        if device_id_raw is not None and not (isinstance(device_id_raw, float) and pd.isna(device_id_raw)):
            device_id = str(device_id_raw).strip()
        if device_id and device_id != target.device_id:
            skipped["设备编号与计划不匹配"].append(
                f"第{row_no}行 {plan_id}: 表中={device_id} 计划中={target.device_id}"
            )
            diff_rows.append({
                "行号": row_no, "计划编号": plan_id, "设备编号": device_id or target.device_id,
                "类别": "跳过", "原因": "设备编号与计划不匹配", "变更内容": ""
            })
            continue

        old_status = target.status
        old_check_date = target.check_date or ""
        old_result = target.result or ""
        old_photo_count = len(target.photo_paths)

        if "check_date" in df.columns:
            raw_cd = row.get("check_date")
            if raw_cd is not None and not (isinstance(raw_cd, float) and pd.isna(raw_cd)):
                cd_val = parse_date(str(raw_cd).strip()[:10])
                if cd_val is None:
                    skipped["检查日期格式错误"].append(f"第{row_no}行 {plan_id}: {raw_cd}")
                    diff_rows.append({
                        "行号": row_no, "计划编号": plan_id, "设备编号": target.device_id,
                        "类别": "跳过", "原因": "检查日期格式错误",
                        "变更内容": f"原始值={raw_cd}"
                    })
                    continue
                target.check_date = cd_val.strftime("%Y-%m-%d")

        raw_status = row.get("status") if "status" in df.columns else None
        raw_result = row.get("result") if "result" in df.columns else None
        inferred = _infer_status(raw_status, raw_result)
        if inferred != "待执行":
            target.status = inferred

        if raw_result is not None and not (isinstance(raw_result, float) and pd.isna(raw_result)):
            target.result = str(raw_result).strip()

        if "notes" in df.columns:
            raw_notes = row.get("notes")
            if raw_notes is not None and not (isinstance(raw_notes, float) and pd.isna(raw_notes)):
                notes_str = str(raw_notes).strip()
                if notes_str:
                    if target.result:
                        target.result = f"{target.result}；{notes_str}"
                    else:
                        target.result = notes_str

        new_photos_to_list = []
        warn_messages = []
        if "photo_paths" in df.columns:
            raw_photos = row.get("photo_paths")
            photo_list = _parse_photo_paths(raw_photos)
            for p in photo_list:
                p_path = Path(p)
                if copy_photos and p_path.exists() and p_path.is_file():
                    try:
                        subdir = plan_id
                        rel = storage.copy_attachment(str(p_path), subdir)
                        new_photos_to_list.append(rel)
                        copied_attachments.append(rel)
                    except Exception as e:
                        skipped["照片复制失败"].append(f"第{row_no}行 {plan_id}: {p} ({e})")
                        warn_messages.append(f"照片{p}复制失败")
                else:
                    new_photos_to_list.append(p)
                    if copy_photos and not p_path.exists():
                        skipped["照片路径不存在(未复制)"].append(f"第{row_no}行 {plan_id}: {p}")
                        warn_messages.append(f"照片{p}不存在(未复制)")
            if new_photos_to_list:
                target.photo_paths = list(set(target.photo_paths + new_photos_to_list))

        new_status = target.status
        new_check_date = target.check_date or ""
        new_result = target.result or ""
        new_photo_count = len(target.photo_paths)

        change_desc_parts = []
        if old_status != new_status:
            change_desc_parts.append(f"状态: {old_status}→{new_status}")
        if old_check_date != new_check_date:
            change_desc_parts.append(f"检查日期: {old_check_date or '(空)'}→{new_check_date}")
        if old_result != new_result:
            change_desc_parts.append(f"结果: {old_result or '(空)'}→{new_result}")
        if old_photo_count != new_photo_count:
            change_desc_parts.append(f"照片数: {old_photo_count}→{new_photo_count}")
        if not change_desc_parts:
            change_desc_parts.append("(无变更)")
        change_desc = " | ".join(change_desc_parts)

        changes_list.append({
            "row_no": row_no,
            "plan_id": plan_id,
            "device_id": target.device_id,
            "building": target.building,
            "old_status": old_status,
            "new_status": new_status,
            "old_check_date": old_check_date,
            "new_check_date": new_check_date,
            "photos_added": len(new_photos_to_list),
            "warnings": warn_messages,
            "desc": change_desc,
        })
        diff_rows.append({
            "行号": row_no,
            "计划编号": plan_id,
            "设备编号": target.device_id,
            "楼栋": target.building,
            "类别": "成功",
            "原因": "; ".join(warn_messages) if warn_messages else "正常",
            "变更内容": change_desc,
        })
    return plans_work, changes_list, skipped, copied_attachments, diff_rows


@click.group(invoke_without_command=True)
@click.option("--date", "-d", default=None, help="计划日期 (YYYY-MM-DD，默认今天)")
@click.option("--building", "-b", default="", help="指定楼栋（不指定则按全部楼栋分组）")
@click.option("--area", "-a", default="", help="按区域筛选")
@click.option("--inspector", "-i", default="", help="责任人/巡检人")
@click.option("--export-excel/--no-export", default=False, help="同时导出 Excel 巡检表")
@click.pass_context
def plan(ctx, date, building, area, inspector, export_excel):
    """巡检计划管理：生成计划 / 导入检查结果 / 回滚。

    不带子命令时默认为 plan generate（生成巡检计划）。
    """
    if ctx.invoked_subcommand is None:
        ctx.invoke(plan_generate, date=date, building=building, area=area,
                   inspector=inspector, export_excel=export_excel)


@plan.command("generate")
@click.option("--date", "-d", default=None, help="计划日期 (YYYY-MM-DD，默认今天)")
@click.option("--building", "-b", default="", help="指定楼栋（不指定则按全部楼栋分组）")
@click.option("--area", "-a", default="", help="按区域筛选")
@click.option("--inspector", "-i", default="", help="责任人/巡检人")
@click.option("--export-excel/--no-export", default=False, help="同时导出 Excel 巡检表")
def plan_generate(date, building, area, inspector, export_excel):
    """按楼栋生成巡检计划（原 plan 命令）。"""
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
                    "检查结果": p.result or "",
                    "检查日期": p.check_date or "",
                    "照片路径": "",
                    "备注": "",
                })
            df = pd.DataFrame(rows)
            filename = build_plan_filename(b, plan_date)
            export_path = storage.exports_dir / filename
            df.to_excel(export_path, index=False, sheet_name="巡检表")
            click.echo(f"  已导出: {export_path}")


@plan.command("import")
@click.argument("filepath", type=click.Path(exists=True))
@click.option("--sheet", "-s", default="0", help="Excel 工作表序号或名称")
@click.option("--operator", "-o", default="system", help="操作人")
@click.option("--copy-photos/--no-copy", default=True, help="自动复制照片到 attachments 目录")
@click.option("--dry-run", is_flag=True, help="预览模式：只解析不落库")
@click.option("--export-diff", is_flag=True, help="导出导入差异清单 Excel")
def plan_import(filepath, sheet, operator, copy_photos, dry_run, export_diff):
    """导入填好的巡检表，回写计划状态/结果/检查日期/照片。

    FILEPATH: 填好的巡检表（.xlsx/.xls）路径
    """
    if pd is None:
        click.echo(click.style("错误：未安装 pandas，请运行: pip install pandas openpyxl", fg="red"))
        return

    storage = Storage()
    if not storage.is_initialized():
        click.echo(click.style("错误：请先运行 init 初始化项目", fg="red"))
        return

    fp = Path(filepath)
    try:
        sheet_arg = int(sheet) if str(sheet).isdigit() else sheet
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

    col_map = _map_plan_columns(df.columns.tolist())
    if "plan_id" not in col_map.values():
        click.echo(click.style("错误：文件缺少【计划编号】列，无法定位计划", fg="red"))
        click.echo(f"当前列名：{list(df.columns)}")
        return
    df = df.rename(columns=col_map)

    original_plans = storage.get_plans()
    plans_work, changes_list, skipped, copied_attachments, diff_rows = _collect_changes(
        storage, df, copy_photos if not dry_run else False
    )

    banner = "[预览模式] 导入巡检结果" if dry_run else "巡检结果导入完成！"
    click.echo(click.style(f"{banner}", fg="green" if not dry_run else "cyan", bold=True))
    click.echo(f"  读取行数：{len(df)}")
    click.echo(f"  成功更新：{len(changes_list)} 条")

    if changes_list:
        click.echo("")
        click.echo(click.style("【成功明细（状态变更）】", fg="green", bold=True))
        click.echo(click.style(
            f"{'行号':<8}{'计划编号':<18}{'设备':<14}{'楼栋':<10}{'状态变化':<26}检查日期变化  {'照片':<10}",
            fg="cyan"
        ))
        click.echo("-" * 130)
        for c in changes_list:
            st_change = f"{c['old_status']}→{c['new_status']}"
            cd_change = f"{c['old_check_date'] or '(空)'}→{c['new_check_date'] or '(空)'}"
            warn_msg = "; ".join(c["warnings"][:2]) if c["warnings"] else ""
            if warn_msg:
                warn_str = click.style(f" ⚠ " + warn_msg, fg="yellow")
            else:
                warn_str = ""
            click.echo(
                f"{c['row_no']:<8}{c['plan_id']:<18}{c['device_id']:<14}{c['building']:<10}"
                f"{st_change:<28}{cd_change:<20}新增{c['photos_added']}张{warn_str}"
            )
            if len(c["warnings"]):
                for w in c["warnings"]:
                    click.echo(f"        警告: {w}")

    if skipped:
        click.echo("")
        click.echo(click.style(
            f"  跳过/警告：{sum(len(v) for v in skipped.values())} 条",
            fg="yellow", bold=True
        ))
        for reason, details in skipped.items():
            click.echo(click.style(f"    - {reason}: {len(details)} 条", fg="yellow"))
            for d in details[:5]:
                click.echo(f"        · {d}")
            if len(details) > 5:
                    click.echo(f"        · ... 还有 {len(details) - 5} 条省略")

    snapshot = None
    if not dry_run and changes_list:
        affected_ids = [c["plan_id"] for c in changes_list]
        snapshot = storage.save_plan_snapshot(
            operator=operator,
            source_file=fp.name,
            original_plans=original_plans,
            affected_plan_ids=affected_ids,
            copied_attachments=copied_attachments,
        )
        storage.save_plans(plans_work)
        click.echo("")
        click.echo(click.style(
            f"已创建回滚快照：{snapshot.snapshot_id}（可使用 plan rollback {snapshot.snapshot_id} 撤回）",
            fg="yellow"
        ))
        storage.add_log(
            "plan_import", "plan", f"{len(changes_list)}条",
            operator,
            f"导入巡检结果: {fp.name}, 成功{len(changes_list)}条, 跳过{sum(len(v) for v in skipped.values())}条, 快照{snapshot.snapshot_id}"
        )
    elif dry_run:
        click.echo("")
        click.echo(click.style(
            "【预览模式，未写入任何变更。确认无误后去掉 --dry-run 正式导入。",
            fg="yellow", bold=True
        ))

    if export_diff and pd is not None and diff_rows:
        diff_path = storage.exports_dir / f"导入差异_{fp.stem}_{today_str()}.xlsx"
        pd.DataFrame(diff_rows).to_excel(diff_path, index=False, sheet_name="差异清单")
        click.echo("")
        click.echo(click.style(f"差异清单已导出：{diff_path}", fg="green"))


@plan.command("snapshots")
def plan_snapshots():
    """列出可回滚的导入快照。"""
    storage = Storage()
    if not storage.is_initialized():
        click.echo(click.style("错误：请先运行 init 初始化项目", fg="red"))
        return

    snaps = storage.list_plan_snapshots()
    if not snaps:
        click.echo(click.style("暂无导入快照", fg="yellow"))
        return

    click.echo(click.style(
        f"{'快照ID':<18}{'创建时间':<22}{'操作人':<12}{'来源文件':<32}{'影响计划数':<12}{'复制附件数'}",
        fg="cyan", bold=True
    ))
    click.echo("-" * 110)
    for s in reversed(snaps):
        click.echo(
            f"{s.snapshot_id:<18}{s.created_at:<22}{s.operator:<12}"
            f"{s.source_file:<34}{len(s.plan_ids_affected):<14}{len(s.copied_attachments)}"
        )


@plan.command("rollback")
@click.argument("snapshot_id", required=False, default=None)
@click.option("--last", "-l", is_flag=True, help="回滚最近一次导入")
@click.option("--operator", "-o", default="system", help="操作人")
def plan_rollback(snapshot_id, last, operator):
    """按快照 ID 回滚一次 plan import 导入操作。"""
    storage = Storage()
    if not storage.is_initialized():
        click.echo(click.style("错误：请先运行 init 初始化项目", fg="red"))
        return

    snaps = storage.list_plan_snapshots()
    if not snaps:
        click.echo(click.style("暂无可回滚快照", fg="yellow"))
        return

    if last:
        target_id = snaps[-1].snapshot_id
    else:
        target_id = snapshot_id
        if not target_id:
            click.echo(click.style("请指定快照 ID 或使用 --last", fg="red"))
            return

    click.echo(click.style(f"准备回滚快照：{target_id}", fg="yellow", bold=True))
    if not click.confirm("确认回滚？此操作将恢复计划状态，并删除本次导入复制的附件照片。"):
        click.echo("已取消。")
        return

    result = storage.rollback_plan_snapshot(target_id)
    if result is None:
        click.echo(click.style(f"错误：快照 {target_id} 不存在", fg="red"))
        return

    click.echo(click.style(f"回滚成功！", fg="green", bold=True))
    click.echo(f"  恢复时间：{result.created_at}")
    click.echo(f"  影响计划：{len(result.plan_ids_affected)} 条")
    attach_info = ", ".join(result.copied_attachments[:5])
    click.echo(f"  清理附件：{attach_info}")

    storage.add_log(
        "plan_rollback", "snapshot", target_id,
        operator,
        f"回滚导入快照: {target_id}, 恢复{len(result.plan_ids_affected)}条计划"
    )
