"""Archive the public PDFs referenced by the collected disclosure catalogue."""
import concurrent.futures
import hashlib
import json
import sqlite3
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FOLDER = ROOT / '公告原件'
DB = ROOT / '高德红外_2023起.sqlite'


def download(record):
    code = record['art_code']
    if not code.startswith('AN') or not code[2:].isdigit():
        return code, None, None, 0, 'INVALID_ART_CODE'
    address = 'https://pdf.dfcfw.com/pdf/H2_' + code + '_1.pdf'
    path = FOLDER / (code + '.pdf')
    try:
        if path.exists():
            payload = path.read_bytes()
        else:
            with urllib.request.urlopen(address, timeout=20) as response:
                payload = response.read(20 * 1024 * 1024 + 1)
            if len(payload) > 20 * 1024 * 1024:
                raise ValueError('PDF_EXCEEDS_20MB_LIMIT')
            if not payload.startswith(b'%PDF-'):
                raise ValueError('NOT_A_PDF')
            path.write_bytes(payload)
        return code, address, hashlib.sha256(payload).hexdigest(), len(payload), None
    except Exception as exc:
        return code, address, None, 0, type(exc).__name__ + ': ' + str(exc)


def main():
    FOLDER.mkdir(exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute('''CREATE TABLE IF NOT EXISTS announcement_documents(
      art_code TEXT PRIMARY KEY,title TEXT,notice_date TEXT,url TEXT,retrieved_at TEXT,
      sha256 TEXT,bytes INTEGER,relative_path TEXT,error TEXT)''')
    records = {}
    for encoded, in c.execute("SELECT payload_json FROM current_source_records WHERE dataset LIKE 'announcements%'"):
        row = json.loads(encoded)
        records[row['art_code']] = row
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for code, address, digest, size, error in pool.map(download, records.values()):
            r = records[code]
            c.execute('INSERT OR REPLACE INTO announcement_documents VALUES (?,?,?,?,?,?,?,?,?)',
                      (code,r['title'],r.get('notice_date'),address,datetime.now(timezone.utc).isoformat(),
                       digest,size,'公告原件/'+code+'.pdf' if digest else None,error))
            done += 1
            if done % 30 == 0:
                c.commit(); print('PDF archived',done,'/',len(records),flush=True)
    c.commit()
    summary = dict(c.execute('SELECT CASE WHEN error IS NULL THEN "success" ELSE "failed" END,COUNT(*) FROM announcement_documents GROUP BY 1'))
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    c.close()


if __name__ == '__main__': main()
