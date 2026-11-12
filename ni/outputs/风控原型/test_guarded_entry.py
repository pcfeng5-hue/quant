import unittest
from risk_demo import RiskBook


class GuardedEntryTests(unittest.TestCase):
    def setUp(self):
        self.b = RiskBook()

    def tearDown(self):
        self.b.close()

    def test_fresh_quote_and_valuation_accept(self):
        r = self.b.submit_with_valuation('a', 'A', 100, 2000, {'A': (2000, 100)}, 100)
        self.assertEqual(r['decision'], 'ACCEPTED')
        self.assertEqual(r['valuation']['nav'], 5000000)

    def test_missing_target_quote_blocks_empty_account(self):
        r = self.b.submit_with_valuation('a', 'A', 100, 2000, {}, 100)
        self.assertEqual(r['decision'], 'QUOTE_UNAVAILABLE')
        self.assertEqual(self.b._reserved(), 0)

    def test_stale_target_quote_blocks(self):
        r = self.b.submit_with_valuation('a', 'A', 100, 2000, {'A': (2000, 39)}, 100)
        self.assertEqual(r['decision'], 'QUOTE_UNAVAILABLE')

    def test_unvalued_existing_position_blocks_new_stock(self):
        self.b.submit('a', 'A', 100, 2000)
        self.b.fill('f', 'a', 100, 2000)
        r = self.b.submit_with_valuation('b', 'B', 100, 2000, {'B': (2000, 100)}, 100)
        self.assertEqual(r['decision'], 'VALUATION_UNAVAILABLE')
        self.assertEqual(self.b._reserved(), 0)

    def test_unobserved_loss_blocks_before_new_order(self):
        for symbol in 'ABCDEF':
            self.b.submit(symbol, symbol, 100, 2000)
            self.b.fill('fill'+symbol, symbol, 100, 2000)
        quotes = {s: (333, 100) for s in 'ABCDEF'}
        quotes['G'] = (1000, 100)
        r = self.b.submit_with_valuation('new', 'G', 100, 1000, quotes, 100)
        self.assertEqual(r['decision'], 'PAUSED')
        self.assertEqual(r['valuation']['trading_pnl'], -1000200)
        self.assertEqual(self.b._reserved(), 0)

    def test_exception_rolls_back_whole_transaction(self):
        original = self.b.submit
        def failing(*args, **kwargs):
            result = original(*args, **kwargs)
            self.assertEqual(result, 'ACCEPTED')
            raise RuntimeError('Injected failure after reservation')
        self.b.submit = failing
        with self.assertRaises(RuntimeError):
            self.b.submit_with_valuation('a', 'A', 100, 2000, {'A': (2000, 100)}, 100)
        self.assertEqual(self.b._reserved(), 0)
        self.assertFalse(self.b.db.in_transaction)


if __name__ == '__main__':
    unittest.main(verbosity=2)
