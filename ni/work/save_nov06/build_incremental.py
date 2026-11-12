"""Save the frozen 11/06 offline first-receipt release above the 11/05 delta."""

import argparse
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile


WORK = Path(__file__).resolve().parent.parent
NOV05_SCRIPT = WORK / 'save_nov05/build_incremental.py'
NOV05_SCRIPT_SHA = 'dfa399aa438d1c9b03bc74456ec247476ab265827acef60d83b7b7a1ada6b560'
ARCHIVES = Path('/Users/puchun/Documents/Codex/项目归档/ni')
NOV05_RESULT = ARCHIVES / '20261105_输入台账与验证设计增量保存/增量归档核验.json'
NOV05_ARCHIVE_SHA = '816e198b952f0588ebd8678e35f24d3423cad88e8f203aacb36d9630617202e5'
NOV05_MANIFEST_SHA = 'c133d9ea92dbdf12d6f653bae23a4cc5622c20c71963653e1df410527e64880c'
DEFAULT_DEST = ARCHIVES / '20261106_首收版本离线工具增量保存'


def load_nov05_helpers():
    # Suppress import bytecode so the frozen source inventory stays stable.
    from importlib.util import module_from_spec, spec_from_file_location

    if hashlib.sha256(NOV05_SCRIPT.read_bytes()).hexdigest() != NOV05_SCRIPT_SHA:
        raise RuntimeError('The verified 11/05 helper script has changed')
    spec = spec_from_file_location('verified_nov05_archive', NOV05_SCRIPT)
    if spec is None or spec.loader is None:
        raise ImportError(NOV05_SCRIPT)
    module = module_from_spec(spec)
    old_setting = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = old_setting
    return module


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources-frozen', action='store_true', required=True)
    parser.add_argument('--entry', required=True, help='Final report, relative to the project')
    parser.add_argument('--state', required=True, help='Final state JSON, relative to the project')
    parser.add_argument('--release-audit', required=True, help='Final passing audit JSON, relative to the project')
    parser.add_argument('--new-metadata-db', action='append', required=True,
                        help='New synthetic metadata SQLite, relative to the project. Repeatable.')
    parser.add_argument('--destination', type=Path, default=DEFAULT_DEST)
    return parser.parse_args()


def fingerprints(rows):
    keyed = {row['archive_path']: (row['bytes'], row['sha256'], row['mtime_ns']) for row in rows}
    if len(keyed) != len(rows):
        raise RuntimeError('Duplicate paths in archive inventory')
    return keyed


def verify_embedded_manifest(helpers, archive, member, expected_sha):
    with zipfile.ZipFile(archive) as package, package.open(member) as stream:
        if helpers.sha_stream(stream) != expected_sha:
            raise RuntimeError(f'Embedded manifest mismatch for {archive}')


def load_predecessor(helpers):
    full = helpers.read_json(helpers.BASE_RESULT)
    prior = helpers.read_json(NOV05_RESULT)
    if not (full.get('full_snapshot') and full.get('every_source_file_verified') and
            full.get('every_archived_file_and_metadata_verified') and
            full.get('sha256') == helpers.EXPECTED_BASE_SHA):
        raise RuntimeError('Missing verified 11/04 full base')
    if not (prior.get('all_scope_delta') and prior.get('every_delta_member_and_metadata_verified') and
            prior.get('source_content_and_inventory_stable') and
            prior.get('base_plus_delta_inventory_reconstruction_verified') and
            prior.get('sha256') == NOV05_ARCHIVE_SHA):
        raise RuntimeError('Missing verified 11/05 predecessor delta')

    full_archive = Path(full['archive'])
    full_manifest_sha = helpers.sha(helpers.BASE_MANIFEST)
    full_dependency = prior['base_dependency']
    if not (str(full_archive) == full_dependency['archive'] and
            full_archive.stat().st_size == full['zip_bytes'] == full_dependency['zip_bytes'] and
            full['sha256'] == full_dependency['sha256'] and
            full_manifest_sha == full_dependency['manifest_sha256'] and
            helpers.sha(helpers.BASE_RESULT) == full_dependency['prior_verified_result_sha256']):
        raise RuntimeError('11/05 predecessor is bound to a different 11/04 base')
    verify_embedded_manifest(helpers, full_archive, 'metadata/文件清单与SHA256.json', full_manifest_sha)

    prior_archive = Path(prior['archive'])
    prior_manifest_path = Path(prior['manifest'])
    if not (prior_archive.stat().st_size == prior['zip_bytes'] and
            helpers.sha(prior_archive) == NOV05_ARCHIVE_SHA and
            helpers.sha(prior_manifest_path) == prior['manifest_sha256'] == NOV05_MANIFEST_SHA):
        raise RuntimeError('11/05 predecessor archive or manifest has changed')
    verify_embedded_manifest(helpers, prior_archive, 'metadata/增量文件清单与SHA256.json', NOV05_MANIFEST_SHA)

    full_manifest = helpers.read_json(helpers.BASE_MANIFEST)
    prior_manifest = helpers.read_json(prior_manifest_path)
    if full_manifest['source_exclusions'] or prior_manifest['source_exclusions']:
        raise RuntimeError('Source scope differs from the full project and visualizations')
    combined = fingerprints(full_manifest['files'])
    for name in prior_manifest['removed_since_base']:
        del combined[name]
    combined.update(fingerprints(prior_manifest['delta_files']))
    if combined != fingerprints(prior_manifest['files']):
        raise RuntimeError('11/04 full base and 11/05 delta inventories do not match the verified predecessor')

    dependencies = [
        dict(date='2026-11-04', kind='full', archive=str(full_archive),
             sha256=full['sha256'], verified_result=str(helpers.BASE_RESULT),
             manifest_sha256=full_manifest_sha, full_sha_rehashed_this_run=False),
        dict(date='2026-11-05', kind='delta', archive=str(prior_archive),
             sha256=NOV05_ARCHIVE_SHA, verified_result=str(NOV05_RESULT),
             manifest_sha256=NOV05_MANIFEST_SHA, full_sha_rehashed_this_run=True),
    ]
    return prior_manifest, dependencies


def main():
    args = parse_args()
    helpers = load_nov05_helpers()
    dest = args.destination.resolve()
    if any(dest.is_relative_to(root) for root in (helpers.PROJECT, helpers.VISUAL)):
        raise ValueError('Archive destination must be outside the source trees')
    if dest.exists():
        raise FileExistsError(f'Preserve the existing archive directory {dest}')

    helpers.project_file(args.entry)
    state = helpers.read_json(helpers.project_file(args.state))
    audit = helpers.read_json(helpers.project_file(args.release_audit))
    if not (audit.get('all_checks_passed') is True and
            isinstance(audit.get('total'), int) and audit['total'] > 0 and
            audit.get('passed') == audit['total']):
        raise RuntimeError('Final delivery audit has not passed')

    predecessor, dependencies = load_predecessor(helpers)
    previous = fingerprints(predecessor['files'])
    rows, directories = helpers.inventory()
    for row in rows:
        row['sha256'] = helpers.sha(row['source'])
    current = fingerprints(rows)
    added = sorted(current.keys() - previous.keys())
    removed = sorted(previous.keys() - current.keys())
    shared = current.keys() & previous.keys()
    changed = sorted(name for name in shared if current[name][:2] != previous[name][:2])
    changed_paths = set(changed)
    metadata_changed = sorted(name for name in shared - changed_paths if current[name][2] != previous[name][2])
    selected = set(added + changed)
    delta_rows = [row for row in rows if row['archive_path'] in selected]
    added_dirs = sorted(set(directories) - set(predecessor['directories']))
    removed_dirs = sorted(set(predecessor['directories']) - set(directories))
    reconstructed = {name: previous[name] for name in shared}
    reconstructed.update(fingerprints(delta_rows))
    for name in metadata_changed:
        reconstructed[name] = (*previous[name][:2], current[name][2])
    if reconstructed != current:
        raise RuntimeError('The three-layer archive chain does not reconstruct the current inventory')

    db_members = []
    for relative in args.new_metadata_db:
        path = helpers.project_file(relative)
        member = 'project/' + path.relative_to(helpers.PROJECT).as_posix()
        if member not in added or member in db_members:
            raise ValueError(f'Expected a distinct new metadata SQLite member, got {member}')
        if any(Path(str(path) + suffix).exists() for suffix in ('-journal', '-wal', '-shm')):
            raise RuntimeError(f'Close all database writers before archiving {path}')
        db_members.append(member)

    dest.mkdir(parents=True, exist_ok=False)
    archive = dest / '首收版本离线工具_全项目增量_20261106.zip'
    partial = archive.with_suffix('.zip.partial')
    manifest_path = dest / '增量文件清单与SHA256.json'
    manifest = dict(
        client_date='2026-11-06', timezone='America/Toronto',
        created_at_utc=datetime.now(timezone.utc).isoformat(), full_snapshot=False,
        source_exclusions=[], source_file_count=len(rows), files=rows, directories=directories,
        delta_files=delta_rows, added=added, content_changed=changed,
        metadata_only_changed=metadata_changed, removed_since_predecessor=removed,
        added_directories=added_dirs, removed_directories=removed_dirs,
        restoration_order=dependencies, incremental_comparison_date='2026-11-05',
        reused_archive_helpers=dict(path=str(NOV05_SCRIPT.relative_to(helpers.PROJECT)), sha256=NOV05_SCRIPT_SHA),
        new_metadata_database_members=db_members, current_entry=args.entry,
        current_continuation_state=args.state, current_release_audit=args.release_audit,
        continuation_state=state, release_audit=audit,
        automation_policy=dict(nightly_automation_deleted=True, restore_schedule=False,
                               archived_automation_material_is_historical_evidence=True),
    )
    helpers.write_json(manifest_path, manifest)
    guide = dest / '保存与恢复说明.md'
    guide.write_text(f'''# 首收版本离线工具增量保存

2026年11月6日，多伦多。归档范围包括全部项目普通文件和指定可视化目录。这个包包含相对11月5日已核验快照新增和内容变更的文件。删除项和仅修改时间变化的项目记在清单中。

1. 在新目录核验并解压11月4日全量包 `{dependencies[0]['archive']}`，SHA-256为 `{dependencies[0]['sha256']}`。
2. 核验并叠加11月5日增量包 `{dependencies[1]['archive']}`，SHA-256为 `{dependencies[1]['sha256']}`。
3. 核验本增量的SHA-256和归档核验结果。按 `removed_since_predecessor` 和 `removed_directories` 把已移除的旧路径从恢复副本移到隔离位置，再叠加 `project/`、`visualizations/`。`metadata/` 可按日期分开保留。
4. 对照最新清单 `files` 核对完整文件集合的大小和SHA-256。ZIP的时间精度有限，需要纳秒时间时按清单恢复。报告位于 `project/{args.entry}`，续作状态位于 `project/{args.state}`，交付核验位于 `project/{args.release_audit}`。

夜间自动任务已取消。恢复范围为研究资料，归档内的自动任务记录仅作为历史证据。请把恢复后的配置保留在独立目录，后续研究由用户手动启动。

归档复用11月4日全量核验，重新验证11月5日小增量的SHA-256及两层清单。当前包逐成员核验。指定的新合成元数据数据库会还原到临时目录并进行只读 `quick_check`。旧数据库的核验结果见各自归档。
''', encoding='utf-8')

    metadata = {
        'metadata/增量文件清单与SHA256.json': manifest_path,
        'metadata/保存与恢复说明.md': guide,
        'metadata/build_incremental.py': Path(__file__).resolve(),
    }
    metadata_hashes = {name: helpers.sha(path) for name, path in metadata.items()}
    with zipfile.ZipFile(partial, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as package:
        for name in added_dirs:
            package.writestr(name, b'')
        for row in delta_rows:
            package.write(row['source'], row['archive_path'])
        for name, path in metadata.items():
            package.write(path, name)

    restored_databases = []
    with zipfile.ZipFile(partial) as package:
        names = package.namelist()
        expected = selected | set(added_dirs) | metadata.keys()
        if set(names) != expected or len(names) != len(expected):
            raise RuntimeError('Unexpected archive members or duplicate paths')
        for name in added_dirs:
            item = package.getinfo(name)
            if not item.is_dir() or item.file_size != 0:
                raise RuntimeError(f'Invalid archived directory {name}')
        for name, value in {**{row['archive_path']: row['sha256'] for row in delta_rows}, **metadata_hashes}.items():
            with package.open(name) as stream:
                if helpers.sha_stream(stream) != value:
                    raise RuntimeError(f'Archived member hash differs for {name}')
        with tempfile.TemporaryDirectory(prefix='first_receipt_nov06_restore_') as temporary:
            for index, member in enumerate(db_members):
                target = Path(temporary) / f'{index}.sqlite'
                with package.open(member) as source, target.open('wb') as output:
                    shutil.copyfileobj(source, output)
                helpers.inspect_new_metadata_database(target)
                restored_databases.append(dict(path=member, result='ok'))

    after, after_directories = helpers.inventory()
    original_shape = [{key: value for key, value in row.items() if key != 'sha256'} for row in rows]
    if after != original_shape or after_directories != directories:
        raise RuntimeError('Source inventory changed while archiving')
    for row in rows:
        if helpers.sha(row['source']) != row['sha256']:
            raise RuntimeError(f"Source content changed while archiving {row['source']}")
    for name, path in metadata.items():
        if helpers.sha(path) != metadata_hashes[name]:
            raise RuntimeError(f'Metadata changed while archiving {path}')

    archive_sha = helpers.sha(partial)
    partial.replace(archive)
    result = dict(
        archive=str(archive), sha256=archive_sha, zip_bytes=archive.stat().st_size,
        full_snapshot=False, all_scope_delta=True, source_file_count=len(rows),
        delta_file_count=len(delta_rows), added_count=len(added), changed_count=len(changed),
        metadata_only_changed_count=len(metadata_changed),
        removed_count=len(removed), restoration_order=dependencies,
        manifest=str(manifest_path), manifest_sha256=helpers.sha(manifest_path),
        every_delta_member_and_metadata_verified=True, source_content_and_inventory_stable=True,
        chain_inventory_reconstruction_verified=True, restored_new_metadata_databases=restored_databases,
        old_database_checks_repeated=False, automation_restored_or_created=False,
        parent_latest_pointer_modified=False, completed_at_utc=datetime.now(timezone.utc).isoformat(),
    )
    helpers.write_json(dest / '增量归档核验.json', result)
    (dest / '增量归档包SHA256.txt').write_text(f'{archive_sha}  {archive.name}\n', encoding='utf-8')
    print(f'Archived {len(delta_rows)} changed files, restored {len(db_members)} new metadata SQLite. SHA-256 {archive_sha}', flush=True)


if __name__ == '__main__':
    main()
