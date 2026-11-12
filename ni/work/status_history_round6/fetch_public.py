import urllib.request, urllib.parse, pathlib, hashlib, datetime, json, sys

OUT = pathlib.Path(__file__).resolve().parent
def fetch(name, url, params=None, method='GET', data=None):
    params = params or {}
    actual_url = url + ('?' + urllib.parse.urlencode(params) if params else '')
    meta = {'name':name, 'url':url, 'method':method,'parameters':params,
            'retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        request = urllib.request.Request(actual_url, data=data, method=method,
            headers={'User-Agent':'Mozilla/5.0', 'Referer':'https://www.szse.cn/'})
        with urllib.request.urlopen(request, timeout=25) as response:
            raw = response.read()
            sha = hashlib.sha256(raw).hexdigest()
            content_type = response.headers.get('Content-Type','')
            ext = '.json' if 'json' in content_type or raw[:1] in (b'{', b'[') else '.html'
            path = OUT / (name + '_' + sha[:16] + ext)
            path.write_bytes(raw)
            meta.update(status_code=response.status, sha256=sha,
                        content_type=content_type,raw_path=str(path),bytes=len(raw))
    except Exception as error:
        meta['error'] = repr(error)
    manifest = OUT / 'requests.json'
    rows = json.loads(manifest.read_text()) if manifest.exists() else []
    rows.append(meta)
    manifest.write_text(json.dumps(rows,ensure_ascii=False,indent=2))
    print(json.dumps(meta,ensure_ascii=False), flush=True)
    return meta

if __name__ == '__main__':
    if len(sys.argv) == 3:
        fetch(sys.argv[1],sys.argv[2])
    else:
        fetch('szse_month_index','https://www.szse.cn/market/periodical/month/index.html')
        fetch('szse_temp_index','https://www.szse.cn/disclosure/notice/temp/index.html')
        fetch('szse_month_sample','https://docs.static.szse.cn/www/market/periodical/month/W020250905347571947097.html')
