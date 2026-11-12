"""Synthetic boundary tests; these are not supplier observations or production data."""
import importlib.util
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('chip_validator',ROOT/'outputs/高德红外数据库/validate_chip_export.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class ChipValidationTests(unittest.TestCase):
    def setUp(self):
        self.metadata=dict(interface='cyq_chips',symbol='002414.SZ',
            evidence_type='provider_cost_distribution_estimate',source_url='https://example.invalid/synthetic',
            retrieved_at='2026-10-13T12:00:00+00:00',requested_start='2023-01-03',requested_end='2023-01-04',
            percent_unit='percentage_points',price_unit='CNY_per_share')
        self.payload=dict(code=0,data=dict(fields=['ts_code','trade_date','price','percent'],items=[
            ['002414.SZ','20230103',10,40],['002414.SZ','20230103',11,60],
            ['002414.SZ','20230104',10,100]]))
        self.expected={'2023-01-03','2023-01-04'}

    def audit(self):return module.validate(self.payload,self.metadata,self.expected)
    def kinds(self):return {x['kind'] for x in self.audit()['issues']}
    def test_structurally_valid_is_not_historical_approval(self):
        r=self.audit();self.assertTrue(r['structural_checks_passed']);self.assertFalse(r['historical_input_eligible']);self.assertFalse(r['chip_price_alignment_ready'])
    def test_basis_declaration_never_certifies_alignment(self):
        self.metadata.update(price_basis='unadjusted',price_basis_evidence='synthetic test evidence')
        r=self.audit();self.assertTrue(r['price_basis_declared']);self.assertFalse(r['chip_price_alignment_ready']);self.assertFalse(r['historical_input_eligible'])
    def test_duplicate_bins_are_rejected(self):
        self.payload['data']['items'].append(self.payload['data']['items'][0]);self.assertIn('row',self.kinds())
    def test_fraction_scaled_percent_is_rejected(self):
        for r in self.payload['data']['items']:r[3]/=100
        self.assertIn('distribution_sum',self.kinds())
    def test_missing_date_is_reported(self):
        self.payload['data']['items'].pop();self.assertEqual(self.audit()['missing_dates'],['2023-01-04'])
    def test_nonfinite_is_rejected(self):
        self.payload['data']['items'][0][2]='NaN';self.assertIn('row',self.kinds())
    def test_wrong_stock_is_rejected(self):
        self.payload['data']['items'][0][0]='600000.SH';self.assertIn('row',self.kinds())
    def test_closed_or_outside_date_is_rejected(self):
        self.payload['data']['items'][0][1]='20230101';self.assertIn('row',self.kinds())
    def test_failed_permission_is_not_empty_history(self):
        self.payload={'code':2002,'data':None};self.assertIn('response',self.kinds());self.assertFalse(self.audit()['structural_checks_passed'])
    def test_request_at_row_cap_is_flagged(self):
        self.payload['data']['items']=[self.payload['data']['items'][0]]*6000;self.assertIn('possible_truncation',self.kinds())
    def test_unknown_adjustment_vintage_blocks_alignment(self):
        self.metadata.update(price_basis='qfq',price_basis_evidence='synthetic test evidence');self.assertFalse(self.audit()['chip_price_alignment_ready'])
    def test_missing_unit_is_not_guessed(self):
        self.metadata.pop('percent_unit');self.assertIn('percent_unit',self.kinds())
    def test_partial_response_fields_are_rejected(self):
        self.payload['data']['fields']=['ts_code']*4;self.assertIn('response',self.kinds())
    def test_quantile_order_failure_is_rejected(self):
        self.metadata['interface']='cyq_perf'
        fields=['ts_code','trade_date','his_low','his_high','cost_5pct','cost_15pct','cost_50pct','cost_85pct','cost_95pct','weight_avg','winner_rate']
        self.payload['data']=dict(fields=fields,items=[['002414.SZ','20230103',5,20,10,9,12,13,14,12,50]])
        self.assertIn('row',self.kinds())
    def test_beyond_baseline_not_declared_complete(self):
        self.metadata['requested_end']='2027-12-31';self.assertIn('outside_baseline_coverage',self.kinds())
    def test_no_baseline_cannot_pass(self):
        r=module.validate(self.payload,self.metadata,set());self.assertFalse(r['structural_checks_passed'])


if __name__=='__main__':unittest.main()
