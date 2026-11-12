"""Offline buy-risk simulator. Integer cents; no broker/network integration."""
import sqlite3


class RiskBook:
    def __init__(self, path=':memory:'):
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS state (
            id INTEGER PRIMARY KEY CHECK(id=1), account_cash INTEGER,
            strategy_cash INTEGER, paused INTEGER DEFAULT 0);
        INSERT OR IGNORE INTO state VALUES(1,5000000,5000000,0);
        CREATE TABLE IF NOT EXISTS holds(reason TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS positions (
            symbol TEXT, owner TEXT, qty INTEGER, cost INTEGER,
            PRIMARY KEY(symbol,owner));
        CREATE TABLE IF NOT EXISTS orders (
            intent TEXT PRIMARY KEY, symbol TEXT, qty INTEGER,
            price INTEGER, remaining INTEGER, status TEXT);
        CREATE TABLE IF NOT EXISTS fills (
            execution_id TEXT PRIMARY KEY, intent TEXT, qty INTEGER, price INTEGER);
        CREATE TABLE IF NOT EXISTS cashflows(event_id TEXT PRIMARY KEY, amount INTEGER);
        CREATE TABLE IF NOT EXISTS expenses(event_id TEXT PRIMARY KEY, amount INTEGER);
        CREATE TABLE IF NOT EXISTS sells(execution_id TEXT PRIMARY KEY, symbol TEXT,
            qty INTEGER, price INTEGER, fee INTEGER, released_cost INTEGER);
        ''')
        for table, column in [('orders', 'fee_reserve'), ('fills', 'fee')]:
            if column not in [r['name'] for r in self.db.execute('PRAGMA table_info('+table+')')]:
                self.db.execute('ALTER TABLE '+table+' ADD COLUMN '+column+' INTEGER NOT NULL DEFAULT 0')

    def _reserved(self):
        return self.db.execute('SELECT COALESCE(SUM(remaining*price+fee_reserve),0) FROM orders WHERE remaining>0').fetchone()[0]

    def submit(self, intent, symbol, qty, price, signal=True, fee_budget=0):
        """Test-only limits: first 2500, stock 5000, portfolio 30000 yuan.
        Costs substitute for market valuation in this deliberately limited demo.
        Fees are supplied mock amounts, not a broker tariff calculator.
        No liquidity, ST/calendar checks or real-world execution path yet.
        """
        if type(qty) is not int or type(price) is not int or qty <= 0 or price <= 0 or type(fee_budget) is not int or fee_budget < 0:
            return 'INVALID_ORDER'
        owns_transaction = not self.db.in_transaction
        if owns_transaction:
            self.db.execute('BEGIN IMMEDIATE')
        try:
            s = self.db.execute('SELECT * FROM state').fetchone()
            if self.db.execute('SELECT 1 FROM orders WHERE intent=?', (intent,)).fetchone():
                result = 'DUPLICATE_INTENT'
            elif s['paused'] or self.db.execute('SELECT 1 FROM holds').fetchone():
                result = 'PAUSED'
            elif not signal:
                result = 'INCOMPLETE_SIGNAL'
            elif self.db.execute("SELECT 1 FROM positions WHERE symbol=? AND owner='manual' AND qty>0", (symbol,)).fetchone():
                result = 'OWNERSHIP_CONFLICT'
            else:
                stock_cost = self.db.execute("SELECT COALESCE(SUM(cost),0) FROM positions WHERE symbol=? AND owner='strategy'", (symbol,)).fetchone()[0]
                stock_reserve = self.db.execute('SELECT COALESCE(SUM(remaining*price+fee_reserve),0) FROM orders WHERE symbol=? AND remaining>0', (symbol,)).fetchone()[0]
                total_cost = self.db.execute("SELECT COALESCE(SUM(cost),0) FROM positions WHERE owner='strategy'").fetchone()[0]
                reserved = self._reserved()
                amount = qty * price + fee_budget
                if stock_cost + stock_reserve + amount > 250000:
                    result = 'ENTRY_BUDGET'  # shared first-entry budget; no scale-in
                elif total_cost + reserved + amount > 3000000:
                    result = 'PORTFOLIO_LIMIT'
                elif amount + reserved > s['strategy_cash']:
                    result = 'STRATEGY_CASH'
                elif amount + reserved > s['account_cash']:
                    result = 'ACCOUNT_CASH'
                else:
                    self.db.execute('INSERT INTO orders(intent,symbol,qty,price,remaining,status,fee_reserve) VALUES(?,?,?,?,?,?,?)',
                                    (intent, symbol, qty, price, qty, 'OPEN', fee_budget))
                    result = 'ACCEPTED'
            if owns_transaction:
                self.db.execute('COMMIT')
            return result
        except BaseException:
            if owns_transaction:
                self.db.execute('ROLLBACK')
            raise

    def request_cancel(self, intent):
        # Request alone never releases reservation.
        self.db.execute("UPDATE orders SET status='CANCEL_PENDING' WHERE intent=? AND remaining>0", (intent,))

    def fill(self, execution_id, intent, qty, price, fee=0):
        if type(qty) is not int or type(price) is not int or qty <= 0 or price <= 0 or type(fee) is not int or fee < 0:
            raise ValueError('Invalid simulated fill')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            old = self.db.execute('SELECT * FROM fills WHERE execution_id=?', (execution_id,)).fetchone()
            if old:
                if (old['intent'], old['qty'], old['price'], old['fee']) != (intent, qty, price, fee):
                    raise ValueError('Conflicting execution record')
                self.db.execute('COMMIT')
                return 'DUPLICATE_FILL'
            o = self.db.execute('SELECT * FROM orders WHERE intent=?', (intent,)).fetchone()
            if not o or qty > o['remaining'] or price > o['price']:
                raise ValueError('Fill needs reconciliation; cannot apply automatically')
            amount = qty * price + fee
            self.db.execute('INSERT INTO fills(execution_id,intent,qty,price,fee) VALUES(?,?,?,?,?)', (execution_id, intent, qty, price, fee))
            self.db.execute('UPDATE state SET account_cash=account_cash-?, strategy_cash=strategy_cash-?', (amount, amount))
            self.db.execute('''INSERT INTO positions VALUES(?,?,?,?)
                ON CONFLICT(symbol,owner) DO UPDATE SET qty=qty+excluded.qty,cost=cost+excluded.cost''',
                (o['symbol'], 'strategy', qty, amount))
            left = o['remaining'] - qty
            self.db.execute('UPDATE orders SET remaining=?,status=?,fee_reserve=? WHERE intent=?',
                            (left, 'FILLED' if left == 0 else o['status'], max(0, o['fee_reserve']-fee) if left else 0, intent))
            if fee > o['fee_reserve']:
                self.db.execute("INSERT OR IGNORE INTO holds VALUES('FEE_BUDGET_EXCEEDED')")
            s = self.db.execute('SELECT * FROM state').fetchone()
            if min(s['account_cash'], s['strategy_cash']) < self._reserved():
                self.db.execute("INSERT OR IGNORE INTO holds VALUES('CASH_DEFICIT')")
            self.db.execute('COMMIT')
            return 'APPLIED'
        except BaseException:
            self.db.execute('ROLLBACK')
            self.db.execute("INSERT OR IGNORE INTO holds VALUES('FILL_RECONCILIATION')")
            raise

    def reconcile_cancel(self, intent, confirmed_total_filled):
        """Called only with a final broker snapshot after all fills are imported.
        A bare cancellation callback is deliberately insufficient.
        """
        self.db.execute('BEGIN IMMEDIATE')
        try:
            o = self.db.execute('SELECT * FROM orders WHERE intent=?', (intent,)).fetchone()
            actual = self.db.execute('SELECT COALESCE(SUM(qty),0) FROM fills WHERE intent=?', (intent,)).fetchone()[0]
            if not o or o['status'] not in ('CANCEL_PENDING', 'FILLED') or actual != confirmed_total_filled:
                self.db.execute("INSERT OR IGNORE INTO holds VALUES('CANCEL_RECONCILIATION')")
                result = 'RECONCILIATION_REQUIRED'
            else:
                self.db.execute("UPDATE orders SET remaining=0,status='CLOSED' WHERE intent=?", (intent,))
                result = 'CLOSED'
            self.db.execute('COMMIT')
            return result
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def manual_buy(self, symbol, qty, price):
        """Inject a confirmed external purchase; debit actual account, not strategy."""
        if type(qty) is not int or type(price) is not int or min(qty, price) <= 0:
            raise ValueError('Invalid manual event')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            self.db.execute('UPDATE state SET account_cash=account_cash-?', (qty*price,))
            self.db.execute('''INSERT INTO positions VALUES(?,?,?,?)
                ON CONFLICT(symbol,owner) DO UPDATE SET qty=qty+excluded.qty,cost=cost+excluded.cost''',
                (symbol, 'manual', qty, qty*price))
            overlap = self.db.execute("SELECT 1 FROM positions WHERE symbol=? AND owner='strategy' UNION SELECT 1 FROM orders WHERE symbol=? AND remaining>0", (symbol, symbol)).fetchone()
            cash = self.db.execute('SELECT account_cash FROM state').fetchone()[0]
            if overlap:
                self.db.execute("INSERT OR IGNORE INTO holds VALUES('OWNERSHIP_CONFLICT')")
            if cash < self._reserved():
                self.db.execute("INSERT OR IGNORE INTO holds VALUES('ACCOUNT_CASH_DEFICIT')")
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def observe_strategy_pnl(self, pnl_cents):
        """Legacy test hook; normal valuation uses value_portfolio()."""
        if type(pnl_cents) is not int:
            raise ValueError('P&L must be integer cents')
        if pnl_cents <= -1000000:
            self.db.execute('UPDATE state SET paused=1')

    def cashflow(self, event_id, amount):
        """Simulation of an external deposit/withdrawal allocated to strategy."""
        if type(amount) is not int or amount == 0:
            raise ValueError('Nonzero integer cents required')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            old = self.db.execute('SELECT amount FROM cashflows WHERE event_id=?', (event_id,)).fetchone()
            if old:
                if old['amount'] != amount:
                    raise ValueError('Conflicting cashflow')
                self.db.execute('COMMIT')
                return 'DUPLICATE'
            s = self.db.execute('SELECT * FROM state').fetchone()
            if amount < 0 and min(s['account_cash'], s['strategy_cash']) + amount < self._reserved():
                raise ValueError('Withdrawal would consume reserved/unavailable cash')
            self.db.execute('INSERT INTO cashflows VALUES(?,?)', (event_id, amount))
            self.db.execute('UPDATE state SET account_cash=account_cash+?,strategy_cash=strategy_cash+?', (amount, amount))
            self.db.execute('COMMIT')
            return 'APPLIED'
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def operating_expense(self, event_id, amount):
        """External project expense; paid OUTSIDE the trading account."""
        if type(amount) is not int or amount <= 0:
            raise ValueError('Positive integer cents required')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            old = self.db.execute('SELECT amount FROM expenses WHERE event_id=?', (event_id,)).fetchone()
            if old and old['amount'] != amount:
                raise ValueError('Conflicting expense')
            self.db.execute('INSERT OR IGNORE INTO expenses VALUES(?,?)', (event_id, amount))
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def record_sell(self, execution_id, symbol, qty, price, fee=0):
        """Book an already-confirmed simulated sell, NOT a sell-order gateway.
        Cost basis uses integer average cost, final sale consumes remainder.
        T+1 availability and broker confirmations are not implemented here.
        """
        if any(type(x) is not int for x in (qty, price, fee)) or min(qty, price) <= 0 or fee < 0 or fee > qty*price:
            raise ValueError('Invalid sell')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            old = self.db.execute('SELECT * FROM sells WHERE execution_id=?', (execution_id,)).fetchone()
            if old:
                if (old['symbol'], old['qty'], old['price'], old['fee']) != (symbol, qty, price, fee):
                    raise ValueError('Conflicting sell')
                self.db.execute('COMMIT')
                return 'DUPLICATE'
            p = self.db.execute("SELECT * FROM positions WHERE symbol=? AND owner='strategy'", (symbol,)).fetchone()
            if not p or qty > p['qty']:
                raise ValueError('Sell exceeds attributed position')
            cost = p['cost'] if qty == p['qty'] else p['cost'] * qty // p['qty']
            net = qty*price-fee
            self.db.execute('INSERT INTO sells VALUES(?,?,?,?,?,?)', (execution_id, symbol, qty, price, fee, cost))
            self.db.execute("UPDATE positions SET qty=qty-?,cost=cost-? WHERE symbol=? AND owner='strategy'", (qty, cost, symbol))
            self.db.execute('UPDATE state SET account_cash=account_cash+?,strategy_cash=strategy_cash+?', (net, net))
            self.db.execute('COMMIT')
            return 'APPLIED'
        except BaseException:
            self.db.execute('ROLLBACK')
            self.db.execute("INSERT OR IGNORE INTO holds VALUES('SELL_RECONCILIATION')")
            raise

    def value_portfolio(self, quotes, now, max_age=60):
        """Quotes: {symbol: (integer price cents, integer epoch seconds)}.
        Explicit now/max_age make synthetic tests deterministic; no live feed.
        Unknown/stale quotes latch a hold rather than assume zero or cost value.
        """
        if type(now) is not int or type(max_age) is not int or max_age < 0:
            raise ValueError('Invalid quote time policy')
        owns_transaction = not self.db.in_transaction
        if owns_transaction:
            self.db.execute('BEGIN IMMEDIATE')
        try:
            positions = self.db.execute("SELECT * FROM positions WHERE owner='strategy' AND qty>0").fetchall()
            market_value = cost = 0
            bad = []
            for p in positions:
                q = quotes.get(p['symbol'])
                if not isinstance(q, (tuple, list)) or len(q) != 2 or any(type(x) is not int for x in q) or q[0] <= 0 or not 0 <= now-q[1] <= max_age:
                    bad.append(p['symbol'])
                else:
                    market_value += p['qty']*q[0]
                    cost += p['cost']
            if bad:
                self.db.execute("INSERT OR IGNORE INTO holds VALUES('VALUATION_UNAVAILABLE')")
                if owns_transaction:
                    self.db.execute('COMMIT')
                return {'status': 'UNAVAILABLE', 'symbols': bad}
            cash = self.db.execute('SELECT strategy_cash FROM state').fetchone()[0]
            flows = self.db.execute('SELECT COALESCE(SUM(amount),0) FROM cashflows').fetchone()[0]
            expenses = self.db.execute('SELECT COALESCE(SUM(amount),0) FROM expenses').fetchone()[0]
            realized = self.db.execute('SELECT COALESCE(SUM(qty*price-fee-released_cost),0) FROM sells').fetchone()[0]
            nav = cash + market_value
            pnl = nav - 5000000 - flows
            if pnl <= -1000000:
                self.db.execute('UPDATE state SET paused=1')
            result = {'status': 'VALUED', 'nav': nav, 'net_cashflows': flows,
                      'realized_pnl': realized, 'unrealized_pnl': market_value-cost,
                      'trading_pnl': pnl, 'operating_expenses': expenses,
                      'project_pnl': pnl-expenses,
                      'loss_paused': bool(self.db.execute('SELECT paused FROM state').fetchone()[0]),
                      'holds': [r[0] for r in self.db.execute('SELECT reason FROM holds ORDER BY reason')]}
            if owns_transaction:
                self.db.execute('COMMIT')
            return result
        except BaseException:
            if owns_transaction:
                self.db.execute('ROLLBACK')
            raise

    def submit_with_valuation(self, intent, symbol, qty, price, quotes, now,
                              signal=True, fee_budget=0, max_age=60):
        """Offline guarded entry: valuation and reservation share one transaction.
        Caller supplies mock quotes; this does not fetch or authenticate live prices.
        Legacy submit() remains a low-level synthetic-test interface.
        """
        if not isinstance(quotes, dict) or type(now) is not int or type(max_age) is not int or max_age < 0:
            raise ValueError('Invalid valuation input')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            target = quotes.get(symbol)
            valid_target = (isinstance(target, (tuple, list)) and len(target) == 2
                            and all(type(x) is int for x in target)
                            and target[0] > 0 and 0 <= now-target[1] <= max_age)
            valuation = self.value_portfolio(quotes, now, max_age)
            if not valid_target:
                self.db.execute("INSERT OR IGNORE INTO holds VALUES('ORDER_QUOTE_UNAVAILABLE')")
                result = 'QUOTE_UNAVAILABLE'
            elif valuation['status'] != 'VALUED':
                result = 'VALUATION_UNAVAILABLE'
            else:
                result = self.submit(intent, symbol, qty, price, signal, fee_budget)
            self.db.execute('COMMIT')
            return {'decision': result, 'valuation': valuation}
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def close(self):
        self.db.close()
