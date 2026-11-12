"""Offline, append-only first-receipt evidence for the BW17 close field."""
import argparse
import hashlib
import json
import re
import sqlite3
from contextlib import closing, contextmanager
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo('Asia/Shanghai')
SYMBOL = '002414.SZ'
FIELD = 'raw_close'
UNIT = 'CNY/share'
ACTION_BLOCKERS = ['HISTORICAL_MAPPING_AND_VERSION_UNBOUND', 'CALENDAR_AND_STOCK_STATUS_UNBOUND',
                   'TRADING_RULES_UNBOUND', 'RIGHTS_AND_FEES_UNBOUND', 'EXECUTION_MODEL_UNBOUND']
MAX_RAW_BYTES = 4 * 1024 * 1024
MAX_METADATA_BYTES = 32 * 1024
IDENTIFIER = re.compile(r'[A-Za-z0-9_.:-]{1,128}\Z')
META_REQUIRED = {'provider', 'symbol', 'field', 'date', 'version', 'supersedes', 'observation_at',
                 'unit', 'adjustment', 'native_field', 'adapter_version'}
META_OPTIONAL = {'source_event_at', 'publication', 'expected_sha256'}

SCHEMA = '''
CREATE TABLE profile(singleton INTEGER PRIMARY KEY CHECK(singleton=1), body TEXT NOT NULL, sha256 TEXT NOT NULL);
CREATE TABLE raw_objects(sha256 TEXT PRIMARY KEY, body BLOB NOT NULL);
CREATE TABLE attempts(
  id INTEGER PRIMARY KEY, provider TEXT, observation_date TEXT, version TEXT,
  request_started_at TEXT NOT NULL, received_at TEXT NOT NULL, checked_at TEXT NOT NULL,
  raw_sha256 TEXT REFERENCES raw_objects(sha256), manifest TEXT, fingerprint TEXT,
  status TEXT NOT NULL, reason TEXT, quarantine TEXT,
  CHECK(request_started_at <= received_at AND received_at <= checked_at),
  CHECK(status IN ('ACCEPTED','DUPLICATE','REJECTED'))
);
CREATE TABLE versions(
  provider TEXT NOT NULL, observation_date TEXT NOT NULL, version TEXT NOT NULL, supersedes TEXT,
  accepted_attempt_id INTEGER UNIQUE NOT NULL REFERENCES attempts(id),
  first_received_at TEXT NOT NULL, value TEXT NOT NULL, fingerprint TEXT NOT NULL,
  PRIMARY KEY(provider,observation_date,version),
  FOREIGN KEY(provider,observation_date,supersedes) REFERENCES versions(provider,observation_date,version)
);
CREATE INDEX attempts_timeline ON attempts(provider,observation_date,checked_at,id);
CREATE INDEX attempts_fingerprint ON attempts(provider,observation_date,version,fingerprint);
'''


class Refusal(ValueError):
    """A stable rejection code suitable for the audit trail."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def utc_stamp(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise Refusal('MISSING_TIMEZONE')
    return value.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def parse_stamp(value):
    try:
        if not isinstance(value, str) or 'T' not in value:
            raise ValueError()
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise Refusal('INVALID_TIMESTAMP') from exc
    utc_stamp(parsed)
    return parsed


def parse_date(value):
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError()
    except (TypeError, ValueError) as exc:
        raise Refusal('INVALID_OBSERVATION_DATE') from exc
    return parsed


def cutoff_for(value):
    return utc_stamp(datetime.combine(parse_date(value), time(18), SHANGHAI))


def json_bytes(data, *, decimal_numbers=False):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Refusal('DUPLICATE_JSON_KEY')
            result[key] = value
        return result

    def reject_constant(_):
        raise Refusal('NONFINITE_JSON_NUMBER')

    kwargs = {'parse_float': Decimal, 'parse_int': Decimal} if decimal_numbers else {}
    try:
        return json.loads(data.decode('utf-8'), object_pairs_hook=unique_object,
                          parse_constant=reject_constant, **kwargs)
    except (UnicodeError, json.JSONDecodeError, InvalidOperation, RecursionError) as exc:
        raise Refusal('INVALID_JSON') from exc


def decimal_value(value):
    if not isinstance(value, (str, int, Decimal)) or isinstance(value, bool):
        raise Refusal('INVALID_DECIMAL')
    if isinstance(value, str) and len(value) > 64:
        raise Refusal('INVALID_DECIMAL')
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise Refusal('INVALID_DECIMAL') from exc
    if not number.is_finite() or not -12 <= number.as_tuple().exponent <= 9 or abs(number) > 10**9:
        raise Refusal('INVALID_DECIMAL')
    return number


def json_pointer(document, pointer):
    for token in pointer.split('/')[1:]:
        part = token.replace('~1', '/').replace('~0', '~')
        if isinstance(document, dict) and part in document:
            document = document[part]
        elif isinstance(document, list) and re.fullmatch(r'0|[1-9][0-9]{0,8}', part) and int(part) < len(document):
            document = document[int(part)]
        else:
            raise Refusal('MISSING_NATIVE_FIELD')
    return document


def valid_identifier(value):
    return isinstance(value, str) and IDENTIFIER.fullmatch(value) is not None


def validate_profile(profile):
    if not isinstance(profile, dict) or set(profile) != {'profile_id', 'mode', 'tolerance', 'sources'}:
        raise Refusal('INVALID_PROFILE')
    if not valid_identifier(profile['profile_id']) or profile['mode'] not in ('synthetic', 'offline_unverified'):
        raise Refusal('INVALID_PROFILE')
    if not isinstance(profile['tolerance'], str) or decimal_value(profile['tolerance']) < 0:
        raise Refusal('INVALID_TOLERANCE')
    sources = profile['sources']
    if not isinstance(sources, dict) or set(sources) != {'primary', 'comparison'}:
        raise Refusal('TWO_DECLARED_SOURCES_REQUIRED')
    for source in sources.values():
        if not isinstance(source, dict) or set(source) != {
                'provider', 'source_url', 'price_pointer', 'symbol_pointer', 'date_pointer', 'adapter_version'}:
            raise Refusal('INVALID_SOURCE_PROFILE')
        if not all(valid_identifier(source[key]) for key in ('provider', 'adapter_version')):
            raise Refusal('INVALID_SOURCE_PROFILE')
        if not isinstance(source['source_url'], str):
            raise Refusal('INVALID_SOURCE_URL')
        url = urlsplit(source['source_url'])
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise Refusal('INVALID_SOURCE_URL')
        if profile['mode'] == 'synthetic' and not url.hostname.endswith('.invalid'):
            raise Refusal('SYNTHETIC_SOURCE_REQUIRES_INVALID_DOMAIN')
        for key in ('price_pointer', 'symbol_pointer', 'date_pointer'):
            pointer = source[key]
            if not isinstance(pointer, str) or not pointer.startswith('/') or len(pointer) > 128 or re.search(r'~(?![01])', pointer):
                raise Refusal('INVALID_JSON_POINTER')
    if sources['primary']['provider'] == sources['comparison']['provider']:
        raise Refusal('SOURCES_MUST_BE_DISTINCT')


def connect(path, *, readonly=False):
    path = Path(path).resolve()
    mode = 'ro' if readonly else 'rw'
    db = sqlite3.connect(f'{path.as_uri()}?mode={mode}', uri=True, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    if readonly:
        db.execute('PRAGMA query_only=ON')
    return db


def init_db(path, profile):
    validate_profile(profile)
    path = Path(path)
    body = canonical(profile)
    # Build the new schema and profile in one SQLite transaction.
    with path.open('xb'):
        pass
    try:
        with closing(connect(path)) as db:
            db.executescript('BEGIN IMMEDIATE;\n' + SCHEMA)
            db.execute('INSERT INTO profile VALUES(1,?,?)', (body, sha256(body.encode())))
            for table in ('profile', 'raw_objects', 'attempts', 'versions'):
                for operation in ('UPDATE', 'DELETE'):
                    db.execute(f"CREATE TRIGGER {table}_no_{operation.lower()} BEFORE {operation} ON {table} "
                               "BEGIN SELECT RAISE(ABORT,'append-only ledger'); END")
            db.commit()
    except Exception:
        path.unlink()
        raise


def load_profile(db):
    stored = db.execute('SELECT body,sha256 FROM profile WHERE singleton=1').fetchone()
    if stored is None or sha256(stored['body'].encode()) != stored['sha256']:
        raise Refusal('PROFILE_INTEGRITY_ERROR')
    profile = json.loads(stored['body'])
    validate_profile(profile)
    return profile, stored['sha256']


@contextmanager
def transaction(db, *, write=False):
    db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
    try:
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise


def bounded_read(path, limit):
    with Path(path).open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise Refusal('INPUT_TOO_LARGE')
    return data


def metadata_identity(manifest, profile):
    if not isinstance(manifest, dict) or set(manifest) - (META_REQUIRED | META_OPTIONAL):
        raise Refusal('INVALID_MANIFEST_FIELDS')
    if manifest.get('symbol') != SYMBOL or manifest.get('field') != FIELD:
        raise Refusal('WRONG_SYMBOL_OR_FIELD')
    providers = {source['provider'] for source in profile['sources'].values()}
    provider = manifest.get('provider')
    if not isinstance(provider, str) or provider not in providers:
        raise Refusal('UNKNOWN_PROVIDER')
    parse_date(manifest.get('date'))
    if not valid_identifier(manifest.get('version')):
        raise Refusal('MISSING_OR_INVALID_VERSION')
    return provider, manifest['date'], manifest['version']


def validate_capture(manifest, profile, raw, received, digest):
    if not META_REQUIRED <= manifest.keys():
        raise Refusal('MISSING_MANIFEST_FIELDS')
    previous = manifest['supersedes']
    if previous is not None and not valid_identifier(previous):
        raise Refusal('INVALID_PREDECESSOR')
    if previous == manifest['version']:
        raise Refusal('SELF_SUPERSESSION')
    source = next(source for source in profile['sources'].values() if source['provider'] == manifest['provider'])
    if manifest['native_field'] != source['price_pointer'] or manifest['adapter_version'] != source['adapter_version']:
        raise Refusal('UNBOUND_FIELD_MAPPING')
    if manifest['unit'] != UNIT or manifest['adjustment'] != 'unadjusted':
        raise Refusal('UNKNOWN_UNIT_OR_ADJUSTMENT')
    observed = parse_stamp(manifest['observation_at'])
    if observed.astimezone(SHANGHAI).date().isoformat() != manifest['date']:
        raise Refusal('OBSERVATION_DATE_MISMATCH')
    if utc_stamp(observed) > received:
        raise Refusal('OBSERVATION_AFTER_RECEIPT')
    if manifest.get('source_event_at') is not None and utc_stamp(parse_stamp(manifest['source_event_at'])) > received:
        raise Refusal('EVENT_AFTER_RECEIPT')
    publication = manifest.get('publication')
    if publication is not None:
        if not isinstance(publication, dict) or set(publication) != {'precision', 'value'}:
            raise Refusal('INVALID_PUBLICATION_EVIDENCE')
        if publication['precision'] == 'date':
            parse_date(publication['value'])
        elif publication['precision'] == 'instant':
            if utc_stamp(parse_stamp(publication['value'])) > received:
                raise Refusal('PUBLICATION_AFTER_RECEIPT')
        else:
            raise Refusal('INVALID_PUBLICATION_PRECISION')
    if 'expected_sha256' in manifest and manifest['expected_sha256'] != digest:
        raise Refusal('RAW_SHA256_MISMATCH')
    document = json_bytes(raw, decimal_numbers=True)
    if json_pointer(document, source['symbol_pointer']) != SYMBOL:
        raise Refusal('RAW_SYMBOL_MISMATCH')
    if json_pointer(document, source['date_pointer']) != manifest['date']:
        raise Refusal('RAW_DATE_MISMATCH')
    value = decimal_value(json_pointer(document, source['price_pointer']))
    if value <= 0:
        raise Refusal('NONPOSITIVE_CLOSE')
    return format(value, 'f')


def check_lineage(db, key, previous, fingerprint):
    provider, day, version = key
    identity = db.execute('SELECT fingerprint FROM versions WHERE provider=? AND observation_date=? AND version=?', key).fetchone()
    if identity is not None:
        if identity['fingerprint'] == fingerprint:
            return 'DUPLICATE', None, None
        return 'REJECTED', 'VERSION_CONTENT_CONFLICT', 'HARD'
    same_unresolved = db.execute('''SELECT 1 FROM attempts WHERE provider=? AND observation_date=? AND version=?
        AND quarantine='GAP' AND fingerprint<>? LIMIT 1''', (*key, fingerprint)).fetchone()
    if same_unresolved:
        return 'REJECTED', 'VERSION_CONTENT_CONFLICT', 'HARD'
    hard = db.execute("SELECT 1 FROM attempts WHERE provider=? AND observation_date=? AND quarantine='HARD' LIMIT 1", (provider, day)).fetchone()
    if hard:
        return 'REJECTED', 'UNRESOLVED_VERSION_CONFLICT', 'HARD'
    head = db.execute('''SELECT version FROM versions WHERE provider=? AND observation_date=?
        ORDER BY accepted_attempt_id DESC LIMIT 1''', (provider, day)).fetchone()
    if previous is not None and db.execute('SELECT 1 FROM versions WHERE provider=? AND observation_date=? AND version=?', (provider, day, previous)).fetchone() is None:
        return 'REJECTED', 'PREDECESSOR_UNAVAILABLE', 'GAP'
    if previous != (head['version'] if head else None):
        return 'REJECTED', 'VERSION_BRANCH_CONFLICT', 'HARD'
    return 'ACCEPTED', None, None


def ingest(path, manifest_path, raw_path, *, synthetic_clock=None):
    """Read local bytes once. Timestamp the read and its validation inside the writer transaction."""
    with closing(connect(path)) as db, transaction(db, write=True):
        profile, profile_sha = load_profile(db)
        if synthetic_clock is not None and profile['mode'] != 'synthetic':
            raise Refusal('CLOCK_INJECTION_REQUIRES_SYNTHETIC_PROFILE')
        clock = synthetic_clock or (lambda: datetime.now(timezone.utc))
        started = utc_stamp(clock())
        last = db.execute('SELECT checked_at FROM attempts ORDER BY id DESC LIMIT 1').fetchone()
        if last and started < last['checked_at']:
            raise Refusal('LOCAL_CLOCK_REGRESSION')
        raw = manifest = None
        key = (None, None, None)
        refusal = None
        try:
            # Read bytes before parsing, so the receipt stamp represents arrival, not validation.
            raw = bounded_read(raw_path, MAX_RAW_BYTES)
            meta_bytes = bounded_read(manifest_path, MAX_METADATA_BYTES)
        except OSError:
            refusal = 'LOCAL_INPUT_UNREADABLE'
        except Refusal as exc:
            refusal = str(exc)
        received = utc_stamp(clock())
        digest = sha256(raw) if raw is not None else None
        fingerprint = value = reason = quarantine = None
        status = 'REJECTED'
        if refusal is None:
            try:
                manifest = json_bytes(meta_bytes)
                key = metadata_identity(manifest, profile)
                value = validate_capture(manifest, profile, raw, received, digest)
                # External expected hashes validate the transfer, rather than define a vendor version.
                identity = {key: item for key, item in manifest.items() if key != 'expected_sha256'}
                fingerprint = sha256(canonical([profile_sha, identity, digest]).encode())
                status, reason, quarantine = check_lineage(db, key, manifest['supersedes'], fingerprint)
            except Refusal as exc:
                reason = str(exc)
                quarantine = 'LATEST' if key[0] is not None else None
        else:
            reason = refusal
        checked = utc_stamp(clock())
        if not started <= received <= checked:
            raise Refusal('LOCAL_CLOCK_REGRESSION')
        if raw is not None:
            db.execute('INSERT INTO raw_objects VALUES(?,?) ON CONFLICT(sha256) DO NOTHING', (digest, raw))
        attempt_id = db.execute('''INSERT INTO attempts(provider,observation_date,version,request_started_at,received_at,
            checked_at,raw_sha256,manifest,fingerprint,status,reason,quarantine) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
            (*key, started, received, checked, digest, canonical(manifest) if key[0] is not None else None,
             fingerprint, status, reason, quarantine)).lastrowid
        first_received = None
        if status == 'ACCEPTED':
            first_received = db.execute('''SELECT min(received_at) FROM attempts WHERE provider=? AND observation_date=?
                AND version=? AND fingerprint=?''', (*key, fingerprint)).fetchone()[0]
            db.execute('INSERT INTO versions VALUES(?,?,?,?,?,?,?,?)', (*key, manifest['supersedes'], attempt_id,
                                                                     first_received, value, fingerprint))
        elif status == 'DUPLICATE':
            first_received = db.execute('SELECT first_received_at FROM versions WHERE provider=? AND observation_date=? AND version=?', key).fetchone()[0]
    return {'attempt_id': attempt_id, 'status': status, 'reason': reason, 'mode': profile['mode'],
            'raw_sha256': digest, 'immutable_raw_path': f'sqlite:raw_objects/{digest}' if digest else None,
            'request_started_at_utc': started, 'response_end_utc': received,
            'first_project_received_at_utc': first_received, 'validation_checked_at_utc': checked,
            'after_observation_day_cutoff': checked > cutoff_for(key[1]) if key[1] else None}


def version_at(db, provider, observation_date, cutoff):
    key = (provider, observation_date, cutoff)
    hard = db.execute('''SELECT reason FROM attempts WHERE provider=? AND observation_date=? AND checked_at<=?
        AND quarantine='HARD' ORDER BY id LIMIT 1''', key).fetchone()
    if hard:
        return None, hard['reason']
    gap = db.execute('''SELECT 1 FROM attempts p WHERE p.provider=? AND p.observation_date=? AND p.checked_at<=?
        AND p.quarantine='GAP' AND NOT EXISTS(
            SELECT 1 FROM versions v JOIN attempts a ON a.id=v.accepted_attempt_id
            WHERE v.provider=p.provider AND v.observation_date=p.observation_date AND v.version=p.version
            AND v.fingerprint=p.fingerprint AND a.checked_at<=?) LIMIT 1''', (*key, cutoff)).fetchone()
    if gap:
        return None, 'PREDECESSOR_UNAVAILABLE'
    row = db.execute('''SELECT v.version,v.supersedes,v.first_received_at,v.value,a.id,a.checked_at,a.raw_sha256,a.manifest,r.body
        FROM versions v JOIN attempts a ON a.id=v.accepted_attempt_id JOIN raw_objects r ON r.sha256=a.raw_sha256
        WHERE v.provider=? AND v.observation_date=? AND a.checked_at<=? ORDER BY a.id DESC LIMIT 1''', key).fetchone()
    invalid = db.execute('''SELECT id,reason FROM attempts WHERE provider=? AND observation_date=? AND checked_at<=?
        AND quarantine='LATEST' ORDER BY id DESC LIMIT 1''', key).fetchone()
    if invalid and (row is None or invalid['id'] > row['id']):
        return None, invalid['reason']
    if row is None:
        return None, 'MISSING_BY_CUTOFF'
    if sha256(row['body']) != row['raw_sha256']:
        return None, 'RAW_INTEGRITY_ERROR'
    return {'version': row['version'], 'supersedes': row['supersedes'], 'value': row['value'], 'unit': UNIT,
            'first_project_received_at_utc': row['first_received_at'], 'eligible_for_declared_decision_at': row['checked_at'],
            'raw_sha256': row['raw_sha256'], 'immutable_raw_path': f"sqlite:raw_objects/{row['raw_sha256']}"}, None


def evaluate(path, observation_date, *, decision_date=None, as_of=None):
    observed = parse_date(observation_date)
    decision_date = decision_date or observation_date
    if parse_date(decision_date) < observed:
        raise Refusal('DECISION_PRECEDES_OBSERVATION_DATE')
    declared_cutoff = cutoff_for(decision_date)
    cutoff = utc_stamp(parse_stamp(as_of)) if as_of is not None else declared_cutoff
    if cutoff > declared_cutoff:
        raise Refusal('CUTOFF_AFTER_DECLARED_WINDOW')
    with closing(connect(path, readonly=True)) as db, transaction(db):
        profile, profile_sha = load_profile(db)
        if profile['mode'] != 'synthetic' and cutoff > utc_stamp(datetime.now(timezone.utc)):
            raise Refusal('CUTOFF_NOT_REACHED')
        sources, reasons = {}, []
        for role, source in profile['sources'].items():
            version, reason = version_at(db, source['provider'], observation_date, cutoff)
            sources[role] = {'provider': source['provider'], 'source_url': source['source_url'],
                             'evidence': version, 'reason': reason}
            if reason:
                reasons.append(f'{role}:{reason}')
        if not reasons:
            left = Decimal(sources['primary']['evidence']['value'])
            right = Decimal(sources['comparison']['evidence']['value'])
            if abs(left - right) > Decimal(profile['tolerance']):
                reasons.append('CROSS_SOURCE_CONFLICT')
    return {'symbol': SYMBOL, 'field': FIELD, 'mode': profile['mode'], 'profile_sha256': profile_sha,
            'observation_date': observation_date, 'decision_date': decision_date, 'cutoff_utc': cutoff,
            'declared_cutoff_utc': declared_cutoff, 'price_evidence_status': 'REJECTED' if reasons else 'OFFLINE_MATCH',
            'sources': sources, 'rejection_reasons': reasons, 'tolerance_CNY_per_share': profile['tolerance'],
            'eligible_close': None if reasons else sources['primary']['evidence']['value'],
            'BW17_action_eligible': False, 'action_blockers': ACTION_BLOCKERS}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init', help='Create an empty offline evidence ledger')
    init.add_argument('database')
    init.add_argument('profile')
    capture = commands.add_parser('ingest', help='Record a local raw response and its manifest')
    capture.add_argument('database')
    capture.add_argument('manifest')
    capture.add_argument('raw')
    inspect = commands.add_parser('evaluate', help='Resolve evidence available by a declared cutoff')
    inspect.add_argument('database')
    inspect.add_argument('observation_date')
    inspect.add_argument('--decision-date')
    inspect.add_argument('--as-of')
    args = parser.parse_args()
    try:
        if args.command == 'init':
            init_db(args.database, json_bytes(bounded_read(args.profile, MAX_METADATA_BYTES)))
            result = {'status': 'INITIALIZED', 'database': args.database}
        elif args.command == 'ingest':
            result = ingest(args.database, args.manifest, args.raw)
        else:
            result = evaluate(args.database, args.observation_date, decision_date=args.decision_date, as_of=args.as_of)
    except (Refusal, OSError, sqlite3.Error) as exc:
        print(canonical({'status': 'ERROR', 'reason': str(exc)}))
        return 1
    print(canonical(result))
    return 2 if result.get('status') == 'REJECTED' or result.get('price_evidence_status') == 'REJECTED' else 0


if __name__ == '__main__':
    raise SystemExit(main())
