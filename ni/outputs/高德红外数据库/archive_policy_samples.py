"""Archive a declared, non-exhaustive official policy/news sample; no sentiment tags."""
import concurrent.futures
import hashlib
import json
import sqlite3
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SAMPLES = [
 dict(document_id='mofcom_2023_27',title='关于对无人机相关物项实施出口管制的公告',
      url='https://www.mofcom.gov.cn/zfxxgk/gkml/art/2023/art_e525a76205ac47da9a4dd82613e5f9d4.html',
      publisher='商务部等',publication_display='2023-07-31',issue_date='2023-07-31',effective_date='2023-09-01',
      tags=['红外成像','出口管制','无人机'],note='页面元数据生效日期写2023-07-31，正文第八条实施日期2023-09-01；保留冲突，采用正文日期作为标注，不认证当前效力。'),
 dict(document_id='mofcom_2024_31',title='关于优化调整无人机出口管制措施的公告',
      url='https://www.mofcom.gov.cn/zwgk/zcfb/art/2024/art_db6e21907d69404fb473ddb0b248d3d7.html',
      publisher='商务部等',publication_display='2024-07-31 16:00',issue_date='2024-07-31',effective_date='2024-09-01',
      tags=['红外成像','出口管制','无人机'],note='页面显示精确至分钟的时间，但未取得历史首次上线档案；正文明确废止2023年第27/28号。'),
 dict(document_id='state_council_792',title='中华人民共和国两用物项出口管制条例',
      url='https://exportcontrol.mofcom.gov.cn/article/zcfg/gnzcfg/gzjgfxwj/202410/1057.html',
      publisher='国务院，商务部网站发布',publication_display=None,issue_date='2024-09-30',effective_date='2024-12-01',
      tags=['两用物项','出口管制'],note='发文日期不是首次公开时间；该页未提供可核实的首次发布时间。'),
 dict(document_id='mofcom_2024_51',title='关于发布中华人民共和国两用物项出口管制清单的公告',
      url='https://app.www.gov.cn/govdata/gov/202411/19/521898/article.html',
      publisher='商务部等，中国政府网转载',publication_display='2024-11-19',issue_date='2024-11-15',effective_date='2024-12-01',
      tags=['两用物项','出口管制'],note='发文日11/15、政府网转载日11/19、生效日12/1分开；附件清单未在本脚本逐项解析。'),
 dict(document_id='most_2023_57',title='关于公布中国禁止出口限制出口技术目录的公告',
      url='https://www.most.gov.cn/tztg/202312/t20231221_189244.html',
      publisher='商务部、科技部',publication_display='2023-12-21',issue_date=None,effective_date=None,
      tags=['技术出口','目录'],note='仅归档网页；发文、生效日期未逐条认证，不从URL猜测。'),
 dict(document_id='mofcom_uav_explanation_2024',title='无人机出口管制调整公开解读',
      url='https://exportcontrol.mofcom.gov.cn/article/zjsj/202408/1025.html',
      publisher='商务部出口管制信息网',publication_display=None,issue_date=None,effective_date=None,
      tags=['红外成像','政策解读'],note='作为公开政策解读原文样本；URL月份不当作首发时间，无交易方向标签。'),
 dict(document_id='mofcom_license_guide_2025',title='两用物项出口许可申请填报指南',
      url='https://exportcontrol.mofcom.gov.cn/article/cjwt/202504/1135.html',
      publisher='商务部安全与管制局',publication_display='2025-03-28 17:00',issue_date=None,effective_date=None,
      tags=['两用物项','许可指南'],note='搜索可见正文而直接读取可能只返回外壳；按实际响应检验正文是否取得。'),
]


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'): self.skip+=1
        if tag in ('p','div','br','tr','h1','h2','h3','li'): self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style') and self.skip: self.skip-=1
    def handle_data(self,data):
        if not self.skip: self.parts.append(data)


def fetch(sample):
    s=dict(sample);s['retrieved_at']=datetime.now(timezone.utc).isoformat()
    try:
        req=urllib.request.Request(s['url'],headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req,timeout=20) as r:
            raw=r.read(5*1024*1024+1)
            charset=r.headers.get_content_charset() or 'utf-8'
        if len(raw)>5*1024*1024: raise ValueError('size cap exceeded')
        digest=hashlib.sha256(raw).hexdigest()
        rel='政策原文/'+s['document_id']+'_'+digest[:16]+'.html'
        (ROOT/rel).write_bytes(raw)
        parser=TextParser();parser.feed(raw.decode(charset,errors='replace'))
        content='\n'.join(line.strip() for line in ''.join(parser.parts).splitlines() if line.strip())
        # No search snippets or empty dynamic shells may be marked as body archives.
        expected='出口' if s['document_id']=='most_2023_57' else '两用物项' if s['document_id'] in ('state_council_792','mofcom_2024_51','mofcom_license_guide_2025') else '无人'
        if expected not in content or len(content)<200: raise ValueError('body content not obtained')
        s.update(sha256=digest,relative_path=rel,text=content,status='public_page_body_archived_first_public_time_unverified',error=None)
    except Exception as exc:
        s.update(status='not_acquired',error=type(exc).__name__+': '+str(exc))
    return s


def main():
    (ROOT/'政策原文').mkdir(exist_ok=True)
    c=sqlite3.connect(ROOT/'高德红外_2023起.sqlite')
    c.execute('''CREATE TABLE IF NOT EXISTS public_document_samples(
       document_id TEXT,source_sha256 TEXT,url TEXT,title TEXT,reference_date TEXT,
       publication_display TEXT,issue_date TEXT,effective_date TEXT,retrieved_at TEXT,
       relative_path TEXT,text TEXT,status TEXT,metadata_json TEXT,
       PRIMARY KEY(document_id,source_sha256))''')
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for s in pool.map(fetch,SAMPLES):
            results.append(s)
            if not s['error']:
                c.execute('INSERT OR IGNORE INTO public_document_samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                 (s['document_id'],s['sha256'],s['url'],s['title'],(s['publication_display'] or s['issue_date'] or '')[:10],
                  s['publication_display'],s['issue_date'],s['effective_date'],s['retrieved_at'],s['relative_path'],s['text'],
                  s['status'],json.dumps({k:v for k,v in s.items() if k!='text'},ensure_ascii=False)))
            print(s['document_id'],s['status'],s['error'],flush=True)
    c.commit();c.close()
    (ROOT/'政策样本采集记录.json').write_text(json.dumps([{k:v for k,v in s.items() if k!='text'} for s in results],ensure_ascii=False,indent=2))


if __name__=='__main__':main()
