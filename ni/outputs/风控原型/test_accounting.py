import tempfile
import unittest
from pathlib import Path
from risk_demo import RiskBook


class AccountingTests(unittest.TestCase):
    def setUp(self):
        self.b = RiskBook()

    def tearDown(self):
        self.b.close()

    def buy(self, symbol='A', fee=500):
        self.assertEqual(self.b.submit(symbol, symbol, 100, 2000, fee_budget=fee), 'ACCEPTED')
        self.b.fill('buy'+symbol, symbol, 100, 2000, fee)

    def test_initial_cash(self):
        v = self.b.value_portfolio({}, 100)
        self.assertEqual((v['nav'], v['trading_pnl']), (5000000, 0))

    def test_buy_fee_and_mark_to_market(self):
        self.buy()
        v = self.b.value_portfolio({'A': (2100, 100)}, 100)
        self.assertEqual(v['nav'], 5009500)
        self.assertEqual(v['trading_pnl'], 9500)
        self.assertEqual(v['unrealized_pnl'], 9500)

    def test_partial_sell_fee_cost_and_remaining_position(self):
        self.buy()
        self.b.record_sell('s1', 'A', 40, 2200, 200)
        v = self.b.value_portfolio({'A': (2100, 100)}, 100)
        self.assertEqual(v['realized_pnl'], 7600)
        self.assertEqual(v['unrealized_pnl'], 5700)
        self.assertEqual(v['trading_pnl'], 13300)
        self.b.record_sell('s2', 'A', 60, 2100, 300)
        v = self.b.value_portfolio({}, 101)
        self.assertEqual((v['trading_pnl'], v['realized_pnl'], v['unrealized_pnl']), (13000, 13000, 0))

    def test_deposit_not_profit_and_withdrawal_not_loss(self):
        self.b.cashflow('deposit', 1000000)
        self.b.cashflow('withdraw', -400000)
        v = self.b.value_portfolio({}, 100)
        self.assertEqual((v['nav'], v['trading_pnl'], v['net_cashflows']), (5600000, 0, 600000))
        self.assertEqual(self.b.cashflow('deposit', 1000000), 'DUPLICATE')

    def test_withdrawal_cannot_spend_reserved_cash(self):
        self.b.submit('a', 'A', 100, 2000, fee_budget=500)
        with self.assertRaises(ValueError):
            self.b.cashflow('bad', -4900000)
        self.assertEqual(self.b.value_portfolio({}, 100)['net_cashflows'], 0)

    def test_separate_operating_expense(self):
        self.b.operating_expense('data', 20000)
        self.b.operating_expense('data', 20000)
        v = self.b.value_portfolio({}, 100)
        self.assertEqual((v['nav'], v['trading_pnl'], v['project_pnl']), (5000000, 0, -20000))

    def test_missing_quote_blocks_buys(self):
        self.buy()
        self.assertEqual(self.b.value_portfolio({}, 100)['status'], 'UNAVAILABLE')
        self.assertEqual(self.b.submit('b', 'B', 100, 1000), 'PAUSED')

    def test_stale_and_future_quotes(self):
        self.buy()
        for stamp in (39, 101):
            self.assertEqual(self.b.value_portfolio({'A': (2000, stamp)}, 100, max_age=60)['status'], 'UNAVAILABLE')

    def test_reserved_cash_not_deducted_twice_from_nav(self):
        self.b.submit('a', 'A', 100, 2000, fee_budget=500)
        self.assertEqual(self.b._reserved(), 200500)
        self.assertEqual(self.b.value_portfolio({}, 100)['nav'], 5000000)

    def test_fee_overrun_books_fact_then_pauses(self):
        self.b.submit('a', 'A', 100, 2000, fee_budget=100)
        self.b.fill('f', 'a', 100, 2000, fee=500)
        v = self.b.value_portfolio({'A': (2000, 100)}, 100)
        self.assertEqual(v['trading_pnl'], -500)
        self.assertIn('FEE_BUDGET_EXCEEDED', v['holds'])

    def test_duplicate_sell_and_oversell(self):
        self.buy()
        self.b.record_sell('s1', 'A', 40, 2200, 200)
        self.assertEqual(self.b.record_sell('s1', 'A', 40, 2200, 200), 'DUPLICATE')
        with self.assertRaises(ValueError):
            self.b.record_sell('s2', 'A', 61, 2200, 200)
        self.assertEqual(self.b.db.execute("SELECT qty FROM positions WHERE owner='strategy'").fetchone()[0], 60)

    def test_floating_loss_triggers_latch_and_deposit_cannot_reset(self):
        with tempfile.TemporaryDirectory() as d:
            self.b.close()
            path = str(Path(d) / 'ledger.db')
            self.b = RiskBook(path)
            for symbol in 'ABCDEF':
                self.buy(symbol, fee=0)
            quotes = {symbol: (333, 100) for symbol in 'ABCDEF'}
            v = self.b.value_portfolio(quotes, 100)
            self.assertEqual(v['trading_pnl'], -1000200)
            self.assertTrue(v['loss_paused'])
            self.b.cashflow('new_money', 1000000)
            self.assertEqual(self.b.value_portfolio(quotes, 100)['trading_pnl'], -1000200)
            self.b.close()
            self.b = RiskBook(path)
            self.assertEqual(self.b.submit('new', 'G', 100, 1000), 'PAUSED')


if __name__ == '__main__':
    unittest.main(verbosity=2)
