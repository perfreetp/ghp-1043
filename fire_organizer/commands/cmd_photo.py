import click
from pathlib import Path
from collections import defaultdict

from ..storage import Storage


@click.group()
def photo():
    """照片管理：校验缺失/重复/未引用，重关联丢失的照片。"""
    pass


def _collect_all_photo_refs(storage):
    """返回 (plan_photos, issue_photos, all_refs)。
    plan_photos: {plan_id: [rel_path]}
    issue_photos: {issue_id: {before:[], after:[]}}
    all_refs: [(ref, source_type, source_id, field)]
    """
    plans = storage.get_plans()
    issues = storage.get_issues()
    plan_photos = {}
    issue_photos = {}
    all_refs = []
    for p in plans:
        refs = list(p.photo_paths or [])
        plan_photos[p.plan_id] = refs
        for r in refs:
            all_refs.append((r, "plan", p.plan_id, "photo_paths"))
    for i in issues:
        before = list(i.photo_before or [])
        after = list(i.photo_after or [])
        issue_photos[i.issue_id] = {"before": before, "after": after}
        for r in before:
            all_refs.append((r, "issue", i.issue_id, "photo_before"))
        for r in after:
            all_refs.append((r, "issue", i.issue_id, "photo_after"))
    return plan_photos, issue_photos, all_refs


def _scan_attachment_files(storage):
    """扫描 attachments 目录返回 {相对路径: 绝对Path}。"""
    result = {}
    if not storage.attachments_dir.exists():
        return result
    for f in storage.attachments_dir.rglob("*"):
        if f.is_file():
            try:
                rel = str(f.relative_to(storage.project_path))
                result[rel] = f
            except Exception:
                pass
    return result


@photo.command("audit")
@click.option("--area", "-a", default="", help="按区域筛选")
@click.option("--details", "-v", is_flag=True, help="显示每条缺失的详情")
def photo_audit(area, details):
    """校验照片路径：缺失、重复引用、附件未引用。"""
    storage = Storage()
    if not storage.is_initialized():
        click.echo(click.style("错误：请先运行 init 初始化项目", fg="red"))
        return

    from ..utils import filter_by_area
    plans = storage.get_plans()
    if area:
        plans = filter_by_area(plans, area)

    plan_photos, issue_photos, all_refs = _collect_all_photo_refs(storage)

    # 1) 缺失：引用的路径不存在
    missing = []
    for ref, stype, sid, field in all_refs:
        abs_p = storage.project_path / ref
        if not abs_p.exists() or not abs_p.is_file():
            missing.append((ref, stype, sid, field))

    # 2) 重复引用：同一相对路径被多处引用
    ref_count = defaultdict(list)
    for ref, stype, sid, field in all_refs:
        ref_count[ref].append((stype, sid, field))
    duplicates = {r: occs for r, occs in ref_count.items() if len(occs) > 1}

    # 3) 附件未被引用
    attachments_map = _scan_attachment_files(storage)
    referenced_paths = set(r for r, *_ in all_refs)
    unreferenced = [rel for rel in attachments_map.keys() if rel not in referenced_paths]

    click.echo(click.style("=" * 100, fg="cyan", bold=True))
    click.echo(click.style("  照片路径审计", fg="cyan", bold=True))
    click.echo(click.style("=" * 100, fg="cyan", bold=True))
    click.echo(f"  引用总数：{len(all_refs)} 条")
    click.echo(f"  附件目录文件：{len(attachments_map)} 个")

    click.echo("")
    click.echo(click.style(f"【缺失照片】 {len(missing)} 处", fg="red", bold=True))
    if missing:
        if details:
            for ref, stype, sid, field in missing:
                label = {"plan": "计划", "issue": "隐患"}.get(stype, stype)
                click.echo(f"  · {label} {sid}.{field}: {ref}")
        else:
            by_src = defaultdict(list)
            for ref, stype, sid, field in missing:
                by_src[(stype, sid)].append((ref, field))
            for (stype, sid), items in sorted(by_src.items()):
                label = {"plan": "计划", "issue": "隐患"}.get(stype, stype)
                ref_str = ", ".join(f"{r}({f})" for r, f in items[:3])
                extra = f" ... +{len(items)-3}" if len(items) > 3 else ""
                click.echo(f"  · {label} {sid}: {ref_str}{extra}")
    else:
        click.echo(click.style("  ✓ 所有引用的照片都存在", fg="green"))

    click.echo("")
    click.echo(click.style(f"【重复引用】 {len(duplicates)} 处", fg="yellow", bold=True))
    if duplicates:
        for ref, occs in list(duplicates.items())[:10]:
            occ_str = ", ".join(f"{st}-{sid}.{f}" for st, sid, f in occs)
            click.echo(f"  · {ref}: 被 {occ_str} 共用")
        if len(duplicates) > 10:
            click.echo(f"  · ... 还有 {len(duplicates)-10} 条省略")
    else:
        click.echo(click.style("  ✓ 无重复引用", fg="green"))

    click.echo("")
    click.echo(click.style(f"【未引用的附件】 {len(unreferenced)} 个", fg="yellow", bold=True))
    if unreferenced:
        for rel in sorted(unreferenced)[:20]:
            size = (storage.project_path / rel).stat().st_size
            click.echo(f"  · {rel} ({size}B)")
        if len(unreferenced) > 20:
            click.echo(f"  · ... 还有 {len(unreferenced)-20} 个省略")
    else:
        click.echo(click.style("  ✓ 附件均被引用", fg="green"))


@photo.command("relink")
@click.option("--search-dir", "-d", default="imports", help="搜索照片的根目录（默认 imports/）")
@click.option("--copy/--use-raw", default=True, help="找到后复制到 attachments (默认) 或保留原路径")
@click.option("--dry-run", is_flag=True, help="预览不落地")
@click.option("--details", "-v", is_flag=True, help="显示每条细节")
def photo_relink(search_dir, copy, dry_run, details):
    """扫描缺失照片并在指定目录下寻找同名文件重新关联。"""
    storage = Storage()
    if not storage.is_initialized():
        click.echo(click.style("错误：请先运行 init 初始化项目", fg="red"))
        return

    search_root = Path(search_dir)
    if not search_root.exists():
        click.echo(click.style(f"错误：搜索目录不存在: {search_dir}", fg="red"))
        return

    # 收集当前缺失的引用，按文件名建索引候选
    plan_photos, issue_photos, all_refs = _collect_all_photo_refs(storage)
    missing_refs = []
    for ref, stype, sid, field in all_refs:
        abs_p = storage.project_path / ref
        if not abs_p.exists() or not abs_p.is_file():
            missing_refs.append((ref, stype, sid, field))

    if not missing_refs:
        click.echo(click.style("没有缺失的照片引用，无需重关联。", fg="green"))
        return

    # 在 search_root 下建立文件名→候选绝对路径的索引
    name_index = defaultdict(list)
    for f in search_root.rglob("*"):
        if f.is_file():
            name_index[f.name].append(f)

    # 处理每条缺失引用
    plans = storage.get_plans()
    plan_map = {p.plan_id: p for p in plans}
    issues = storage.get_issues()
    issue_map = {i.issue_id: i for i in issues}

    fixed = 0
    not_found = 0
    multi_match = 0
    plan_touched = set()
    issue_touched = set()

    click.echo(click.style(f"缺失引用共 {len(missing_refs)} 处，开始扫描 {search_root}...", fg="cyan"))
    for ref, stype, sid, field in missing_refs:
        src_p = Path(ref)
        fname = src_p.name
        candidates = name_index.get(fname, [])
        if not candidates:
            not_found += 1
            if details:
                click.echo(click.style(f"  ✗ 未找到同名文件: {ref} ({stype} {sid})", fg="red"))
            continue
        if len(candidates) > 1:
            multi_match += 1
            if details:
                click.echo(click.style(f"  ⚠ 找到 {len(candidates)} 个同名，取第一个: {candidates[0]}", fg="yellow"))
        chosen = candidates[0]

        # 确定新路径
        subdir = sid
        if copy:
            if dry_run:
                from datetime import datetime
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                target_dir = storage.attachments_dir / subdir if subdir else storage.attachments_dir
                new_rel = str((target_dir / f"{ts}_{chosen.name}").relative_to(storage.project_path))
            else:
                try:
                    new_rel = storage.copy_attachment(str(chosen), subdir)
                except Exception as e:
                    click.echo(click.style(f"  ✗ 复制失败: {chosen} → {e}", fg="red"))
                    not_found += 1
                    continue
        else:
            # 保留原路径（相对项目路径）
            try:
                new_rel = str(chosen.resolve().relative_to(storage.project_path.resolve()))
            except Exception:
                new_rel = str(chosen.resolve())

        # 更新对象引用
        old_ref = ref
        if stype == "plan":
            p = plan_map.get(sid)
            if p:
                new_paths = [(new_rel if r == old_ref else r) for r in (p.photo_paths or [])]
                if not dry_run:
                    p.photo_paths = new_paths
                    plan_touched.add(sid)
                fixed += 1
                if details:
                    click.echo(click.style(f"  ✓ 计划 {sid}: {old_ref} → {new_rel}", fg="green"))
        else:
            i = issue_map.get(sid)
            if i:
                if field == "photo_before":
                    lst = list(i.photo_before or [])
                    new_paths = [(new_rel if r == old_ref else r) for r in lst]
                    if not dry_run:
                        i.photo_before = new_paths
                        issue_touched.add(sid)
                elif field == "photo_after":
                    lst = list(i.photo_after or [])
                    new_paths = [(new_rel if r == old_ref else r) for r in lst]
                    if not dry_run:
                        i.photo_after = new_paths
                        issue_touched.add(sid)
                fixed += 1
                if details:
                    click.echo(click.style(f"  ✓ 隐患 {sid}.{field}: {old_ref} → {new_rel}", fg="green"))

    # 落库
    if not dry_run:
        if plan_touched:
            storage.save_plans(plans)
        if issue_touched:
            storage.save_issues(issues)

    click.echo("")
    click.echo(click.style("【重关联结果】", fg="yellow", bold=True))
    if dry_run:
        click.echo(click.style("  [预览模式，未写入]", fg="cyan"))
    click.echo(click.style(f"  ✓ 成功处理：{fixed}", fg="green"))
    if multi_match:
        click.echo(click.style(f"  ⚠ 多候选取第一个：{multi_match}", fg="yellow"))
    click.echo(click.style(f"  ✗ 未找到：{not_found}", fg="red"))
