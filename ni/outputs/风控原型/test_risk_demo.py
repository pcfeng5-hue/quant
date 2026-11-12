import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from risk_demo import RiskBook


class RiskTests(unittest.TestCase):
    def setUp(self):
        self.book = RiskBook()

    def tearDown(self):
        self.book.close()

    def test_missing_signal(self):
        self.assertEqual(self.book.submit('a', 'A', 100, 2000, False), 'INCOMPLETE_SIGNAL')

    def test_large_order(self):
        self.assertEqual(self.book.submit('a', 'A', 1000, 2000), 'ENTRY_BUDGET')

    def test_split_orders(self):
        self.assertEqual(self.book.submit('a', 'A', 100, 2000), 'ACCEPTED')
        self.assertEqual(self.book.submit('b', 'A', 100, 2000), 'ENTRY_BUDGET')

    def test_duplicate_intent(self):
        self.book.submit('a', 'A', 100, 2000)
        self.assertEqual(self.book.submit('a', 'A', 100, 2000), 'DUPLICATE_INTENT')

    def test_cancel_request_keeps_reservation(self):
        self.book.submit('a', 'A', 100, 2000)
        self.book.request_cancel('a')
        self.assertEqual(self.book._reserved(), 200000)
        self.assertEqual(self.book.submit('b', 'A', 100, 2000), 'ENTRY_BUDGET')

    def test_partial_fill_and_final_cancel(self):
        self.book.submit('a', 'A', 100, 2000)
        self.book.fill('f1', 'a', 40, 1900)
        self.assertEqual(self.book._reserved(), 120000)
        self.book.request_cancel('a')
        self.assertEqual(self.book.reconcile_cancel('a', 40), 'CLOSED')
        self.assertEqual(self.book._reserved(), 0)
        self.assertEqual(self.book.db.execute('SELECT strategy_cash FROM state').fetchone()[0], 4924000)

    def test_missing_fill_prevents_cancel_release(self):
        self.book.submit('a', 'A', 100, 2000)
        self.book.request_cancel('a')
        self.assertEqual(self.book.reconcile_cancel('a', 40), 'RECONCILIATION_REQUIRED')
        self.assertEqual(self.book._reserved(), 200000)

    def test_duplicate_fill(self):
        self.book.submit('a', 'A', 100, 2000)
        self.book.fill('f1', 'a', 40, 1900)
        self.assertEqual(self.book.fill('f1', 'a', 40, 1900), 'DUPLICATE_FILL')
        self.assertEqual(self.book.db.execute("SELECT qty FROM positions WHERE owner='strategy'").fetchone()[0], 40)

    def test_manual_same_stock_blocks_strategy(self):
        self.book.manual_buy('A', 100, 2000)
        self.assertEqual(self.book.submit('a', 'A', 100, 2000), 'OWNERSHIP_CONFLICT')

    def test_manual_trade_does_not_debit_strategy(self):
        self.book.manual_buy('B', 100, 2000)
        s = self.book.db.execute('SELECT * FROM state').fetchone()
        self.assertEqual(s['strategy_cash'], 5000000)
        self.assertEqual(s['account_cash'], 4800000)

    def test_real_cash_overrides_virtual_allocation(self):
        self.book.manual_buy('B', 2450, 2000)
        self.assertEqual(self.book.submit('a', 'A', 100, 2000), 'ACCOUNT_CASH')

    def test_manual_overlap_after_strategy_order(self):
        self.book.submit('a', 'A', 100, 2000)
        self.book.manual_buy('A', 100, 2000)
        self.assertEqual(self.book.submit('b', 'B', 100, 2000), 'PAUSED')

    def test_loss_latched_after_restart(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / 'book.db')
            first = RiskBook(path)
            first.observe_strategy_pnl(-999999)
            self.assertEqual(first.submit('before', 'A', 100, 2000), 'ACCEPTED')
            first.observe_strategy_pnl(-1000000)
            first.close()
            second = RiskBook(path)
            second.observe_strategy_pnl(0)
            self.assertEqual(second.submit('after', 'B', 100, 2000), 'PAUSED')
            second.close()

    def test_concurrent_reservation(self):
        with tempfile.TemporaryDirectory() as d:
            path = str(Path(d) / 'book.db')
            RiskBook(path).close()
            def attempt(intent):
                b = RiskBook(path)
                try:
                    return b.submit(intent, 'A', 100, 2000)
                finally:
                    b.close()
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(attempt, ['a', 'b']))
            self.assertEqual(sorted(results), ['ACCEPTED', 'ENTRY_BUDGET'])

    def test_no_signals_no_orders(self):
        for i in range(30):
            self.book.submit(str(i), 'A', 100, 2000, False)
        self.assertEqual(self.book.db.execute('SELECT COUNT(*) FROM orders').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
