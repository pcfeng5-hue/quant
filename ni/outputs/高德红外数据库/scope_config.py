"""Read validated dataset scope without changing preserved historical snapshots."""
import json


def read_scope(connection):
    result=dict(start='2023-01-01',end='2026-10-13',
        reconciliation_version='supplement-audit-v1',
        index_sources={'上证指数':'index_1.000001','深证成指':'index_0.399001'})
    if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='database_settings'").fetchone():
        settings=dict(connection.execute('SELECT key,value FROM database_settings'))
        for key in ('start','end','reconciliation_version'):
            if key in settings:result[key]=settings[key]
        if 'index_sources' in settings:result['index_sources']=json.loads(settings['index_sources'])
    return result
