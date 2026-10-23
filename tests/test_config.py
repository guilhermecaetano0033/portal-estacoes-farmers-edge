import json
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class ConfigTests(unittest.TestCase):
    def test_station_lists(self):
        cfg=json.loads((ROOT/'clientes.json').read_text(encoding='utf-8'))
        self.assertEqual([(x['slug'],len(x['estacoes'])) for x in cfg['clientes']],[('tessaro',8),('fenix',10)])
        ids=[s['id'] for c in cfg['clientes'] for s in c['estacoes']]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertIn(81263,ids)
        self.assertNotIn('contatos',(ROOT/'clientes.json').read_text())
if __name__=='__main__':unittest.main()
