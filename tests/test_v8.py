import sys
import json
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import buscar_talhoes as b


def example_polygon(x=-55.7, y=-12.5):
    return {'type':'Polygon','coordinates':[[[x,y],[x+0.01,y],[x+0.01,y+0.01],[x,y]]]}

class FakeResponse:
    def __init__(self, val): self.val=val
    def raise_for_status(self): pass
    def json(self): return self.val

class FakeSession:
    def __init__(self, direct=True, season=1087):self.calls=[];self.direct=direct;self.season=season
    def get(self,url,params,timeout):
        self.calls.append((url,params.copy()))
        if '/asset/field/' in url:
            if not self.direct: return FakeResponse({'results':[]})
            return FakeResponse({'results':[{'id':123,'category':'Field','label':'T1','season_id':self.season}]})
        if '/asset/' in url:
            return FakeResponse({'results':[{'id':22,'parent':92088,'category':'Farm'}, {'id':123,'parent':22,'category':'Field','label':'T1'}]})
        if '/fieldborder/' in url:
            if params.get('seasonID') == self.season:
                return FakeResponse([{'shapeData':json.dumps({'type':'FeatureCollection','features':[{'type':'Feature','geometry':example_polygon()}]})}])
            return FakeResponse([])
        raise AssertionError(url)

class TestV8(unittest.TestCase):
    def test_shape_data_and_featurecollection(self):
        result=b.collect_polygons({'results':[{'shapeData':json.dumps({'type':'FeatureCollection','features':[{'type':'Feature','geometry':example_polygon()}]})}]})
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['type'],'Polygon')
    def test_season_and_assetid_in_query(self):
        sess=FakeSession()
        geo,meta=b.build_client(sess,{'slug':'tessaro','grower_id':92088})
        self.assertEqual(meta['season_id'],1087)
        self.assertEqual(meta['polygons'],1)
        border_calls=[params for url,params in sess.calls if '/fieldborder/' in url]
        self.assertEqual(border_calls,[{'assetID':123,'seasonID':1087,'format':'json'}])
    def test_tree_fallback(self):
        sess=FakeSession(direct=False)
        geo,meta=b.build_client(sess,{'slug':'tessaro','grower_id':92088})
        self.assertEqual(meta['polygons'],1)
        self.assertEqual(meta['method'],'asset_tree_season')
    def test_does_not_mix_other_growers(self):
        assets=[{'id':22,'parent':92088,'category':'Farm'},{'id':23,'parent':2222,'category':'Farm'},{'id':11,'parent':22,'category':'Field'},{'id':12,'parent':23,'category':'Field'}]
        f=b.fields_for_grower(assets,92088)
        self.assertEqual([x['id'] for x in f],[11])
    def test_multipolygon(self):
        p={'type':'MultiPolygon','coordinates':[example_polygon()['coordinates']]}
        self.assertEqual(len(b.collect_polygons(p)),1)
    def test_virtual_first(self):
        js=(Path(__file__).resolve().parents[1]/'site'/'app.js').read_text(encoding='utf-8')
        self.assertIn('const selected=$(\'station\').value||\'virtual\'',js)
        self.assertIn('[virtualStation(),...client.estacoes]',js)
        self.assertNotIn('L.tileLayer(',js)

if __name__ == '__main__': unittest.main()
