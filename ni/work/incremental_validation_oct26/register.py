"""Freeze source/contract/code fingerprints before candidate evaluation."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
WORK=Path(__file__).resolve().parent
OUT=ROOT/'outputs/量价增量验证_20261026'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def enc(x):return json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)
def main():
    receipt=WORK/'registration_receipt.json'
    if receipt.exists():raise FileExistsError('Registration already exists; never silently rewrite it')
    cfg=json.loads((WORK/'contract.json').read_text())
    previous=json.loads((ROOT/'outputs/初始化与验证推进_20261026/本轮状态与续作断点.json').read_text())
    protected=previous['protected_source_sha256']
    for path,value in protected.items():
        if sha(ROOT/path)!=value:raise ValueError('Prior source differs: '+path)
    for path in ['work/forecast_validation_oct26/run_validation.py','work/forecast_validation_oct26/contract.json','work/forecast_validation_oct26/registration_receipt.json','outputs/初始化与验证推进_20261026/时间验证/开发期滚动验证.sqlite','work/chip_initialization_oct26/build_initialization_v2.py','outputs/初始化与验证推进_20261026/筹码初始化/初始化改进v2.sqlite']:
        protected[path]=sha(ROOT/path)
    for path in ['逐日概率与实际结果_仅开发期.csv','量价增量开发验证.sqlite']:
        if (OUT/path).exists():raise ValueError('Candidate result already exists')
    record=dict(experiment_id=cfg['experiment_id'],registered_at_utc=datetime.now(timezone.utc).isoformat(),contract_sha256=sha(WORK/'contract.json'),producer_code_sha256=sha(WORK/'run_incremental.py'),protected_source_sha256=protected,
      before_this_candidate_results=True,source_databases_hashed_not_queried_by_registration=True,previous_development_exploration_disclosed=True,not_an_external_independent_preregistration=True)
    receipt.write_text(enc(record))
    log=dict(status='cumulative_research_choices_not_independent_tests',registered_at_utc=record['registered_at_utc'],entries=[
      dict(id='002414_daily_engineering_20261025_v1',kind='descriptive_signal_definitions',variants=12,source='work/baseline_oct25/engineering_contract.json',status='reported_all_not_ranked'),
      dict(id='002414_development_walkforward_20261026_v1',kind='registered_models',variants=2,source='work/forecast_validation_oct26/contract.json',status='MA_increment_not_supported_negative_result_retained'),
      dict(id=cfg['experiment_id'],kind='one_new_hierarchical_model',variants=1,repeated_comparators=2,source='work/incremental_validation_oct26/contract.json',status='registered_before_candidate_results')],cumulative_variants=15,folds_subsets_cells_and_repeated_comparators_not_counted_as_new_models=True,not_a_multiple_testing_correction=True)
    (WORK/'cumulative_experiment_registration.json').write_text(enc(log))
    print(enc({'registered':str(receipt),'source_count':len(protected),'contract_sha256':record['contract_sha256'],'producer_code_sha256':record['producer_code_sha256']}))
if __name__=='__main__':main()
