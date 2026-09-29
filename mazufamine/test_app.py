import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from app import Ledger, Monitor, fetch

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.ledger = Ledger(self.path/'ledger.db')
    def csv(self, rows):
        p=self.path/'events.csv'
        p.write_text('id,occurred_at,kind,eur\n'+rows)
        return p
    def test_net_and_idempotency(self):
        p=self.csv('a,2026-09-29T12:00:00Z,sale_net,10.20\nb,2026-09-29T12:00:00Z,electricity,2.10\nc,2026-09-29T12:00:00Z,fee_extra,0.10\n')
        self.assertEqual(self.ledger.import_csv(p),3)
        self.assertEqual(self.ledger.import_csv(p),0)
        self.assertEqual(self.ledger.summary()['net_eur'],'8.00')
    def test_conflicting_duplicate_rolls_back(self):
        self.ledger.import_csv(self.csv('a,2026-09-29T12:00:00Z,sale_net,10\n'))
        with self.assertRaises(ValueError):
            self.ledger.import_csv(self.csv('b,2026-09-29T12:00:00Z,sale_net,5\na,2026-09-29T12:00:00Z,sale_net,20\n'))
        self.assertEqual(self.ledger.summary()['events'],1)
    def test_missing_is_not_zero(self):
        self.assertIsNone(self.ledger.summary()['net_eur'])
    def test_nan_rejected(self):
        with self.assertRaises(ValueError):
            self.ledger.import_csv(self.csv('a,2026-09-29T12:00:00Z,sale_net,NaN\n'))
    def test_stale_keeps_last_data(self):
        m=Monitor([{'name':'rig','url':'http://127.0.0.1:4000'}],self.ledger)
        with patch('app.fetch',return_value={'sample':1}):m.poll()
        with patch('app.fetch',side_effect=TimeoutError):m.poll()
        e=m.snapshot()['rigs']['rig']['balances']
        self.assertTrue(e['stale'])
        self.assertEqual(e['data'],{'sample':1})
    def test_write_endpoint_rejected(self):
        with self.assertRaises(ValueError):fetch('http://localhost:4000','setdevices')

if __name__=='__main__':unittest.main()
