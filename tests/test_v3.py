import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('atualizar', ROOT / 'atualizar.py')
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)

class V3Tests(unittest.TestCase):
    def test_solar_radiation(self):
        r=a.normalize({'local_time':'2026-10-24T11:00:00-04:00','sumSolarRadiation':1.23},81263)
        self.assertEqual(r['radiacao_solar_mjm2'],1.23)
    def test_missing_is_not_zero(self):
        r=a.normalize({'local_time':'2026-10-24T11:00:00-04:00'},81263)
        self.assertIsNone(r['chuva_mm'])
        self.assertIsNone(r['radiacao_solar_mjm2'])
    def test_gzip_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'2026-10.json.gz'
            obj={'rows':[{'data_hora_local':'2026-10-24T11:00:00-04:00','radiacao_solar_mjm2':2.0}]}
            a.write_gzip_json(p,obj)
            self.assertEqual(a.read_rows(p),obj['rows'])
            self.assertTrue(p.read_bytes().startswith(b'\x1f\x8b'))

if __name__=='__main__': unittest.main()
