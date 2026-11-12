import sqlite3,json,pathlib,hashlib
import pypdfium2 as pdfium
base=pathlib.Path('outputs/高德红外数据库');out=pathlib.Path('work/round4_capital_status');c=sqlite3.connect(base/'高德红外_2023起.sqlite');c.row_factory=sqlite3.Row
selected={'AN202304191585591293':[77,78], 'AN202312281615153661':[1,2], 'AN202412301641472101':[1,2], 'AN202512301811330148':[1,2], 'AN202304191585591299':[1,2,3], 'AN202306281591781833':[1,2], 'AN202306121590866740':[1,2,3], 'AN202308301596833817':[43,44], 'AN202404151630235965':[79,80,81], 'AN202408261639461683':[38,39], 'AN202504241661802959':[71,72], 'AN202508251734295811':[36,37], 'AN202604141821191363':[69,70], 'AN202608250006749021':[32,33], 'AN202504241661802971':[1,2], 'AN202604141821191382':[1,2], 'AN202305161586693421':[1,2,3,4]}
manifest=[]
for art,pages in selected.items():
 d=dict(c.execute('select * from announcement_documents where art_code=?',(art,)).fetchone());fp=base/d['relative_path'];assert hashlib.sha256(fp.read_bytes()).hexdigest()==d['sha256'];pdf=pdfium.PdfDocument(fp)
 for pn in pages:
  if pn>len(pdf):continue
  page=pdf[pn-1];bitmap=page.render(scale=1.35);image=bitmap.to_pil();ip=out/f'{art}_p{pn}.png';image.save(ip);bitmap.close();page.close()
  row=c.execute('select text from announcement_pages where art_code=? and page_number=? and source_sha256=?',(art,pn,d['sha256'])).fetchone()
  manifest.append({'art_code':art,'page_number':pn,'source_sha256':d['sha256'],'pdf_path':str(fp.resolve()),'image_path':str(ip.resolve()),'text':row[0],'notice_date':d['notice_date'],'url':d['url'],'title':d['title']})
 pdf.close()
json.dump(manifest,open(out/'review_page_manifest.json','w'),ensure_ascii=False,indent=2)
print(len(manifest))
