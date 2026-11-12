"""Save the frozen project/visualization delta against the verified 2026-11-04 base.

Preparation alone performs no archive operation. The coordinator must freeze all
writers, finalize the delivery audit and then call this script explicitly.
No original/market/outcome database is queried. Only explicitly named NEW
metadata databases are restored from this delta and checked read-only.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import tempfile
import zipfile

PROJECT = Path('/Users/puchun/Documents/Codex/2026-10-07/ni')
VISUAL = Path('/Users/puchun/.codex/visualizations/2026/10/07/01a117ad-aa9c-7e12-a194-47edf9f62817')
BASE_DIR = Path('/Users/puchun/Documents/Codex/项目归档/ni/20261104_路线决策完整保存')
BASE_MANIFEST = BASE_DIR / '文件清单与SHA256.json'
BASE_RESULT = BASE_DIR / '归档校验结果.json'
EXPECTED_BASE_SHA = '823651f58e75447658d220f3367be075408b2945e8800f8a67029283eacef716'
DEFAULT_DEST = Path('/Users/puchun/Documents/Codex/项目归档/ni/20261105_输入台账与验证设计增量保存')


def sha_stream(stream):
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1048576), b''):
        digest.update(block)
    return digest.hexdigest()


def sha(path):
    with Path(path).open('rb') as stream:
        return sha_stream(stream)


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    path = Path(path)
    tmp = path.with_name(path.name + '.pending')
    if tmp.exists():
        raise FileExistsError(tmp)
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    tmp.replace(path)


def project_file(relative):
    relative = Path(relative)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Expected project-relative path: ' + str(relative))
    path = PROJECT / relative
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def inventory():
    rows, directories = [], []
    for prefix, root in [('project', PROJECT), ('visualizations', VISUAL)]:
        if not root.is_dir():
            raise NotADirectoryError(root)
        directories.append(prefix + '/')
        for folder, children, names in os.walk(root, followlinks=False):
            children.sort()
            for name in children:
                path = Path(folder) / name
                if not stat.S_ISDIR(path.lstat().st_mode):
                    raise RuntimeError('Non-directory entry; do not follow links: ' + str(path))
                directories.append(prefix + '/' + path.relative_to(root).as_posix() + '/')
            for name in sorted(names):
                path = Path(folder) / name
                value = path.lstat()
                if not stat.S_ISREG(value.st_mode):
                    raise RuntimeError('Non-regular file; do not follow links: ' + str(path))
                rows.append(dict(source=str(path), archive_path=prefix + '/' + path.relative_to(root).as_posix(),
                                 bytes=value.st_size, mtime_ns=value.st_mtime_ns))
    return sorted(rows, key=lambda row: row['archive_path']), sorted(directories)


def inspect_new_metadata_database(path):
    """The path has to come from --new-metadata-db, never from DB discovery."""
    with Path(path).open('rb') as stream:
        if stream.read(16) != b'SQLite format 3\x00':
            raise ValueError('Not SQLite: ' + str(path))
    with sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro&immutable=1', uri=True) as connection:
        connection.execute('PRAGMA query_only=ON')
        if connection.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise RuntimeError('Restored metadata SQLite quick_check failed: ' + str(path))


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources-frozen', action='store_true', required=True,
                        help='Coordinator confirms all project/visualization writers are stopped')
    parser.add_argument('--entry', required=True, help='Final project-relative delivery report')
    parser.add_argument('--state', required=True, help='Final project-relative continuation state')
    parser.add_argument('--release-audit', required=True, help='Final project-relative audit JSON')
    parser.add_argument('--new-metadata-db', action='append', required=True,
                        help='Only NEW metadata SQLite, project-relative; can be repeated')
    parser.add_argument('--destination', type=Path, default=DEFAULT_DEST)
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.sources_frozen:
        raise RuntimeError('Freeze the source writers before creating an archive')
    dest = args.destination.resolve()
    if dest == PROJECT or PROJECT in dest.parents or dest == VISUAL or VISUAL in dest.parents:
        raise ValueError('Archive must be outside the scanned source trees')
    dest.mkdir(parents=True, exist_ok=True)
    archive = dest / '输入台账与买入等待验证设计_全项目增量_20261105.zip'
    partial = archive.with_name(archive.name + '.partial')
    result_path = dest / '增量归档核验.json'
    for path in [archive, partial, result_path, dest / '增量文件清单与SHA256.json']:
        if path.exists():
            raise FileExistsError('Preserve prior package, choose a new destination: ' + str(path))
    entry = project_file(args.entry)
    state = project_file(args.state)
    release_audit_path = project_file(args.release_audit)
    release_audit = read_json(release_audit_path)
    if not (release_audit.get('all_checks_passed') is True and
            release_audit.get('passed') == release_audit.get('total') and
            isinstance(release_audit.get('total'), int) and release_audit['total'] > 0):
        raise RuntimeError('Final delivery audit is not complete and passed')
    new_db_paths = [project_file(relative) for relative in args.new_metadata_db]
    if len(set(new_db_paths)) != len(new_db_paths):
        raise ValueError('Duplicate new metadata database argument')

    base_result = read_json(BASE_RESULT)
    if not (base_result.get('sha256') == EXPECTED_BASE_SHA and
            base_result.get('full_snapshot') is True and
            base_result.get('every_source_file_verified') is True and
            base_result.get('every_archived_file_and_metadata_verified') is True):
        raise RuntimeError('Verified base result does not match the declared dependency')
    base_archive = Path(base_result['archive'])
    if not base_archive.is_file() or base_archive.stat().st_size != base_result['zip_bytes']:
        raise RuntimeError('Base archive is missing or size changed')
    base_manifest_sha = sha(BASE_MANIFEST)
    with zipfile.ZipFile(base_archive) as saved_base:
        with saved_base.open('metadata/文件清单与SHA256.json') as stream:
            if sha_stream(stream) != base_manifest_sha:
                raise RuntimeError('Base manifest copy differs from archived manifest')
    base = read_json(BASE_MANIFEST)
    old = {row['archive_path']: row for row in base['files']}
    if len(old) != len(base['files']) or base.get('source_exclusions') != []:
        raise RuntimeError('Base manifest has duplicates or a different declared scope')

    print('Hash frozen full project scope; discover only added/changed content', flush=True)
    rows, directories = inventory()
    for row in rows:
        row['sha256'] = sha(row['source'])
    current = {row['archive_path']: row for row in rows}
    added = sorted(set(current) - set(old))
    removed = sorted(set(old) - set(current))
    content_changed = sorted(path for path in set(current) & set(old)
                             if (current[path]['sha256'], current[path]['bytes']) !=
                                (old[path]['sha256'], old[path]['bytes']))
    metadata_changed = sorted(path for path in (set(current) & set(old)) - set(content_changed)
                              if current[path]['mtime_ns'] != old[path]['mtime_ns'])
    selected = sorted(set(added) | set(content_changed) | set(metadata_changed))
    selected_rows = [current[path] for path in selected]
    unchanged = sorted(set(current) - set(selected))
    for path in new_db_paths:
        member = 'project/' + path.relative_to(PROJECT).as_posix()
        if member not in set(added) or member not in selected:
            raise RuntimeError('Only newly added metadata databases may be quick-checked: ' + member)
    reconstruction = {path: (row['sha256'], row['bytes']) for path, row in old.items()
                      if path not in set(removed)}
    reconstruction.update({path: (current[path]['sha256'], current[path]['bytes']) for path in selected})
    if reconstruction != {path: (row['sha256'], row['bytes']) for path, row in current.items()}:
        raise RuntimeError('Base plus delta cannot reconstruct the current content inventory')

    manifest = dict(created_at_utc=datetime.now(timezone.utc).isoformat(), client_date='2026-11-05',
        timezone='America/Toronto', archive_kind='all_scope_content_and_metadata_delta', full_snapshot=False,
        scope='Same complete project and designated visualization scope as the base; no source exclusions',
        source_exclusions=[], source_file_count=len(rows), source_total_bytes=sum(row['bytes'] for row in rows),
        directories=directories, files=rows, delta_files=selected_rows,
        added=added, content_changed=content_changed, metadata_only_changed=metadata_changed,
        removed_since_base=removed, removed_source_files_deleted_by_this_script=False,
        unchanged_files_in_base=unchanged, delta_file_count=len(selected_rows),
        delta_bytes=sum(row['bytes'] for row in selected_rows),
        added_directories=sorted(set(directories)-set(base['directories'])),
        removed_directories=sorted(set(base['directories'])-set(directories)),
        base_dependency=dict(archive=str(base_archive), sha256=EXPECTED_BASE_SHA,
            zip_bytes=base_result['zip_bytes'], manifest=str(BASE_MANIFEST), manifest_sha256=base_manifest_sha,
            prior_verified_result=str(BASE_RESULT), prior_verified_result_sha256=sha(BASE_RESULT),
            base_archive_full_sha_rehashed_this_run=False,
            prior_35_database_checks_repeated=False,
            note='Prior verified base result reused; the manifest copy inside its ZIP is rechecked. This run does not freshly prove every base member.'),
        restoration_requires_only_declared_base_and_this_delta=True,
        intermediate_nov04_partial_capsule_required=False,
        current_entry=args.entry, current_continuation_state=args.state,
        current_release_audit=args.release_audit,
        continuation_state=read_json(state), release_audit=release_audit,
        new_metadata_database_members=['project/' + path.relative_to(PROJECT).as_posix() for path in new_db_paths],
        automation_policy=dict(nightly_automation_deleted=True, restore_schedule=False,
            restore_config_to_active_application=False,
            any_archived_automation_material_is_inert_evidence_only=True),
        archive_operations=dict(new_market_queries=False,new_real_labels=False,new_models=False,
            target_database_queries=False,old_database_quick_checks=False,parent_latest_pointer_modified=False),
        limitations='Content inventory and saved local files only; not missing external market data, unsaved browser state or complete platform chat. Engineering checks are not forecast validation.')
    manifest_path = dest / '增量文件清单与SHA256.json'
    write_json(manifest_path, manifest)
    guide_path = dest / '保存与恢复说明.md'
    guide_path.write_text(f'''# 输入台账与验证设计：全范围增量保存

2026年11月5日，多伦多。先保留11月4日已核验全量包，再叠加本增量；本包不是独立全量包。与全量基座相比，扫描相同的全部项目普通文件和指定外部可视化，新增、内容变更及仅修改时间变化的文件均写入。本次不排除源文件，不重复打包未变历史文件；11月4日中间小包不构成本次恢复依赖。

基座：`{base_archive}`，已核验SHA-256为`{EXPECTED_BASE_SHA}`。本次复用其既有验证结果，并核对包内原清单与外部原清单一致；不重新读取全部基座成员，也不重做35个旧数据库检查。若基座从非可信位置找回或发生变动，恢复前另核其SHA。本包逐成员重新核验，指定的新元数据数据库从增量恢复到临时目录做只读quick_check。

## 恢复

1. 在新的空目录操作；不要覆盖原项目或任何旧库。先核基座文件SHA，再解压基座的`project/`与`visualizations/`。
2. 核本增量旁的SHA和`增量归档核验.json`，逐条核增量文件清单后，将本包`project/`和`visualizations/`叠加到该新目录。`metadata/`单独保留以追溯本次保存。
3. 清单的`removed_since_base`仅记录冻结时已不在源目录的文件。本脚本不会删除源文件。要重建精确当前文件集合，应把新恢复副本中这些旧路径移动到隔离目录，不永久删除任何旧成果。按`directories`重建当前空目录；旧空目录可留在隔离副本。
4. 用清单`files`核对最终完整文件集合的SHA和大小。`mtime_ns`记录源元数据；ZIP本身不保证纳秒时间恢复，必要时在恢复副本另按清单设置，不改原件。当前报告是`project/{args.entry}`，续作断点为`project/{args.state}`，交付核验为`project/{args.release_audit}`。

## 自动任务已取消

恢复仅还原研究资料。无论基座或增量中是否保存过自动任务文本、调度截图或配置副本，均只作历史证据，不将其复制到Codex活动自动化目录，不激活、不重建、不修改定时任务。后续研究须等用户手动发出继续指令。

## 回退和范围

回退时重新在另一空目录只解压11月4日基座，或保留本次新恢复副本作比对；不要覆盖原项目或删除旧包。所有旧全量/中间保存保留原位。本增量归档仅说明冻结时本地内容可恢复，不表示输入历史可得性已认证、模型有效、预测已开始、资金使用已授权或任何数据缺口已消失。2025/2026结果隔离及用户风险口径以本轮状态为准。

归档结果和包SHA保存在包旁，避免自引用。脚本不改项目进度、项目续作指针或父级最新归档指针；发布由主线程在核验后完成。之后若更改项目文件，应另有带日期的增量或下次完整保存，不能把后写内容声称已入本包。
''')
    script = Path(__file__).resolve()
    metadata = [(manifest_path,'metadata/增量文件清单与SHA256.json'),
                (guide_path,'metadata/保存与恢复说明.md'),
                (script,'metadata/build_incremental.py'),
                (BASE_RESULT,'metadata/基座既有归档核验.json')]
    metadata_hashes = {name: sha(path) for path, name in metadata}
    print(f'Create delta: {len(selected_rows)} files ({len(added)} new, {len(content_changed)} changed, {len(metadata_changed)} metadata-only)',flush=True)
    with zipfile.ZipFile(partial, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as saved:
        for name in directories:
            saved.writestr(name,b'')
        for row in selected_rows:
            saved.write(row['source'],row['archive_path'])
        for path, name in metadata:
            saved.write(path,name)
    print('Verify delta members and restore only named new metadata SQLite',flush=True)
    restored_db_checks = []
    with zipfile.ZipFile(partial) as saved:
        names = saved.namelist()
        expected = directories + selected + [name for _,name in metadata]
        if len(names) != len(set(names)) or len(names) != len(expected) or set(names) != set(expected):
            raise RuntimeError('Archive member list mismatch or duplicate')
        for name in directories:
            if not saved.getinfo(name).is_dir() or saved.getinfo(name).file_size != 0:
                raise RuntimeError('Directory metadata mismatch: ' + name)
        for row in selected_rows:
            if saved.getinfo(row['archive_path']).file_size != row['bytes']:
                raise RuntimeError('Archived size mismatch: ' + row['archive_path'])
            with saved.open(row['archive_path']) as stream:
                if sha_stream(stream) != row['sha256']:
                    raise RuntimeError('Archived SHA mismatch: ' + row['archive_path'])
        for name, value in metadata_hashes.items():
            with saved.open(name) as stream:
                if sha_stream(stream) != value:
                    raise RuntimeError('Metadata SHA mismatch: ' + name)
        with tempfile.TemporaryDirectory(prefix='input_ledger_nov05_metadata_restore_') as temporary:
            for index, member in enumerate(manifest['new_metadata_database_members']):
                target = Path(temporary) / f'{index}.sqlite'
                with saved.open(member) as source, target.open('wb') as destination:
                    shutil.copyfileobj(source,destination)
                inspect_new_metadata_database(target)
                restored_db_checks.append(dict(path=member,result='ok'))
    print('Recheck full source fingerprints and archive metadata stability',flush=True)
    after, after_directories = inventory()
    original_shape = [{key:row[key] for key in ['source','archive_path','bytes','mtime_ns']} for row in rows]
    if original_shape != after or directories != after_directories:
        raise RuntimeError('Source inventory changed during archive')
    for row in rows:
        if sha(row['source']) != row['sha256']:
            raise RuntimeError('Source content changed during archive: ' + row['source'])
    for path, name in metadata:
        if sha(path) != metadata_hashes[name]:
            raise RuntimeError('Metadata changed during archive: ' + name)
    archive_sha = sha(partial)
    partial.replace(archive)
    result = dict(archive=str(archive),sha256=archive_sha,zip_bytes=archive.stat().st_size,
        full_snapshot=False,all_scope_delta=True,source_file_count=len(rows),
        delta_file_count=len(selected_rows),added_count=len(added),content_changed_count=len(content_changed),
        metadata_only_changed_count=len(metadata_changed),removed_count=len(removed),
        every_delta_member_and_metadata_verified=True,all_current_source_hashes_verified=True,
        source_content_and_inventory_stable=True,base_plus_delta_inventory_reconstruction_verified=True,
        restored_new_metadata_databases=restored_db_checks,old_35_database_checks_repeated=False,
        base_dependency=manifest['base_dependency'],base_archive_full_sha_rehashed_this_run=False,
        automation_restored_or_created=False,parent_latest_pointer_modified=False,
        no_original_or_outcome_database_queries=True,
        manifest=str(manifest_path),manifest_sha256=sha(manifest_path),
        completed_at_utc=datetime.now(timezone.utc).isoformat())
    write_json(result_path,result)
    (dest/'增量归档包SHA256.txt').write_text(archive_sha+'  '+archive.name+'\n')
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
