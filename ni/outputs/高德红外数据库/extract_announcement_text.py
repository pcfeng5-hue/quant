"""Extract page text for search; not financial or event interpretation."""
import json
import sqlite3
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent


def main():
    c = sqlite3.connect(ROOT / '高德红外_2023起.sqlite')
    c.executescript('''
      CREATE TABLE IF NOT EXISTS announcement_pages(art_code TEXT,page_number INTEGER,
        source_sha256 TEXT,extractor TEXT,text TEXT,status TEXT,error TEXT,
        PRIMARY KEY(art_code,page_number,source_sha256));
    ''')
    rows = list(c.execute('SELECT art_code,relative_path,sha256 FROM announcement_documents WHERE error IS NULL'))
    pages = 0
    for code, relative, digest in rows:
        if c.execute('SELECT 1 FROM announcement_pages WHERE art_code=? AND source_sha256=?',(code,digest)).fetchone():
            continue
        try:
            reader = PdfReader(ROOT / relative)
            for index, page in enumerate(reader.pages):
                try:
                    text = page.extract_text() or ''
                    status, error = ('extracted_unverified', None) if text.strip() else ('needs_ocr', None)
                except Exception as exc:
                    text, status, error = '', 'failed', str(exc)
                c.execute('INSERT OR IGNORE INTO announcement_pages VALUES (?,?,?,?,?,?,?)',
                          (code,index+1,digest,'pypdf',text,status,error))
                pages += 1
        except Exception as exc:
            c.execute('INSERT OR IGNORE INTO announcement_pages VALUES (?,?,?,?,?,?,?)',
                      (code,0,digest,'pypdf','','failed',str(exc)))
        c.commit()
    print(json.dumps({'documents':len(rows),'new_pages':pages,'page_status':dict(c.execute('SELECT status,COUNT(*) FROM announcement_pages GROUP BY status'))},ensure_ascii=False))
    c.close()


if __name__ == '__main__': main()
