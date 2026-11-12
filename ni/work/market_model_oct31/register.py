"""Freeze one market-state candidate before reading its development outcomes."""
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
    if receipt.exists():raise FileExistsError('Never overwrite an experiment registration')
    cfg=json.loads((WORK/'contract.json').read_text())
    previous=json.loads((ROOT/'outputs/市场环境输入准备_20261031/本轮状态与续作断点.json').read_text())
    protected=previous['protected_source_sha256']
    for p,h in protected.items():
        if sha(ROOT/p)!=h:raise ValueError('Previously protected source changed: '+p)
    added=['work/market_context_oct31/build_context.py','work/market_context_oct31/contract.json','work/market_context_oct31/registration_receipt.json','outputs/市场环境输入准备_20261031/市场环境工程输入.sqlite','work/market_context_independent_oct31/市场特征独立复核.json','work/market_model_input_oct31/选定市场输入核查.json','work/market_model_input_oct31/audit_selected_input.py','outputs/市场环境输入准备_20261031/累计研究与特征准备台账.json']
    for p in added:protected[p]=sha(ROOT/p)
    if (ROOT/'outputs/市场环境候选验证_20261031/市场状态候选开发验证.sqlite').exists():raise FileExistsError('Candidate output already exists')
    rec=dict(experiment_id=cfg['experiment_id'],registered_at_utc=datetime.now(timezone.utc).isoformat(),contract_sha256=sha(WORK/'contract.json'),producer_code_sha256=sha(WORK/'run_market_model.py'),protected_source_sha256=protected,before_this_candidate_results=True,previous_development_exploration_disclosed=True,not_an_external_timestamped_registration=True,hashing_source_databases_does_not_query_target_values=True)
    receipt.write_text(enc(rec))
    previous_log=json.loads((ROOT/'outputs/市场环境输入准备_20261031/累计研究与特征准备台账.json').read_text())
    ledger=dict(previous_research_and_preparation_log=previous_log,previous_registered_variants=15,new_registered_model_variants=1,repeated_comparator_not_new_variant=1,cumulative_registered_variants=16,new_experiment=dict(id=cfg['experiment_id'],selected_feature_id=cfg['feature_id'],status='registered_before_candidate_outcomes',source='work/market_model_oct31/contract.json'),other_prepared_features_scored=False,old_negative_results_retained=True)
    (WORK/'cumulative_registration.json').write_text(enc(ledger))
    print(enc({'registered':str(receipt),'sources':len(protected),'contract_sha256':rec['contract_sha256'],'producer_code_sha256':rec['producer_code_sha256']}))
if __name__=='__main__':main()
