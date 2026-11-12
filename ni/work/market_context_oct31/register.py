"""Register feature formulas and code before computing this preparation output."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
WORK=Path(__file__).resolve().parent
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def enc(x):return json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)
def main():
    receipt=WORK/'registration_receipt.json'
    if receipt.exists():raise FileExistsError('Never overwrite a frozen registration')
    cfg=json.loads((WORK/'contract.json').read_text())
    previous=json.loads((ROOT/'outputs/量价增量验证_20261026/本轮状态与续作断点.json').read_text())
    protected=previous['protected_source_sha256']
    for p,h in protected.items():
        if sha(ROOT/p)!=h:raise ValueError('Previous protected source changed: '+p)
    for p in ['work/market_industry_oct22/market_rows_unique.json','work/market_industry_oct22/manifest.json','work/market_industry_oct22/input_admission.json','work/market_industry_oct22/summary.json']:
        protected[p]=sha(ROOT/p)
    if (ROOT/'outputs/市场环境输入准备_20261031/市场环境工程输入.sqlite').exists():raise FileExistsError('Preparation output already exists')
    rec=dict(preparation_id=cfg['preparation_id'],registered_at_utc=datetime.now(timezone.utc).isoformat(),contract_sha256=sha(WORK/'contract.json'),producer_code_sha256=sha(WORK/'build_context.py'),protected_source_sha256=protected,source_file_hashing_does_not_query_outcome_values=True,before_this_feature_preparation_output=True,prior_development_exploration_disclosed=True,not_external_timestamped_registration=True,new_scored_or_model_variants=0,previous_research_variants=15,candidate_feature_definitions=15,auxiliary_feature_definitions=1)
    receipt.write_text(enc(rec));print(enc({'registered':str(receipt),'protected_sources':len(protected),'contract_sha256':rec['contract_sha256'],'producer_code_sha256':rec['producer_code_sha256']}))
if __name__=='__main__':main()
