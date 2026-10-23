import unittest
from datetime import date
from atualizar import normalize, month_range

class ExportTests(unittest.TestCase):
    def test_missing_is_not_zero(self):
        row = normalize({'local_time':'2026-09-29T00:00:00-04:00', 'total_precip_mm':None,
                         'rainfall_mm':{'sum':None},'temperature_c':{'avg':None},'docCount':0}, 81263)
        self.assertIsNone(row['chuva_mm'])
        self.assertIsNone(row['temp_media_c'])
        self.assertEqual(row['docCount'], 0)
    def test_fallback(self):
        row = normalize({'local_time':'2026-09-29T01:00:00-04:00','rainfall_mm':{'sum':2.5},
                         'temperature_c':{'avg':23.4}},81263)
        self.assertEqual(row['chuva_mm'],2.5)
        self.assertEqual(row['temp_media_c'],23.4)
    def test_months(self):
        self.assertEqual(list(month_range(date(2026,9,29),date(2026,10,3))),[(date(2026,9,29),date(2026,9,30)),(date(2026,10,1),date(2026,10,3))])
if __name__=='__main__': unittest.main()
