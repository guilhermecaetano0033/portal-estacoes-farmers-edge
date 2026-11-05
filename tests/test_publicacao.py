import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from preparar_publicacao import build


def write_month(root, slug, station, month, rows):
    p = root / 'data' / slug / str(station) / (month + '.json.gz')
    p.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(p, 'wt', encoding='utf-8') as h:
        json.dump({'rows': rows}, h)
    return p


def test_build_does_not_lose_good_hours_or_modify_source():
    with TemporaryDirectory() as td:
        site, out = Path(td) / 'site', Path(td) / 'publicacao'
        site.mkdir()
        (site / 'index.html').write_text('<h1>Clima</h1>')
        (site / 'maps').mkdir()
        (site / 'maps' / 'tessaro.geojson').write_text('{"type":"FeatureCollection","features":[]}')
        (site / 'downloads').mkdir()
        (site / 'downloads' / 'tessaro_historico_horario.xlsx').write_bytes(b'fake-xlsx')
        (site / 'manifest.json').write_text(json.dumps({
            'period_start': '2010-01-01', 'first_observation':'2010-01-01', 'period_end': '2026-11-04',
            'clientes': [{'slug': 'tessaro', 'estacoes': [{'id': 39266}]}]}))
        empty = write_month(site, 'tessaro', 39266, '2010-01', [
            {'data_hora_local': '2010-01-01T00:00:00-04:00', 'temp_media_c': None, 'umidade_media_pct': None}
        ])
        good = write_month(site, 'tessaro', 39266, '2017-01', [
            {'data_hora_local': '2017-01-02T00:00:00-04:00', 'temp_media_c': 25, 'umidade_media_pct': None},
            {'data_hora_local': '2017-01-02T01:00:00-04:00', 'temp_media_c': None, 'umidade_media_pct': None},
        ])
        before_good, before_empty = good.read_bytes(), empty.read_bytes()
        st = build(site, out)
        assert st['published_months'] == 1 and st['omitted_offline_months'] == 1
        assert not (out / 'data/tessaro/39266/2010-01.json.gz').exists()
        assert (out / 'data/tessaro/39266/2017-01.json.gz').read_bytes() == before_good
        assert good.read_bytes() == before_good and empty.read_bytes() == before_empty
        assert (out / 'downloads/tessaro_historico_horario.xlsx').exists()
        assert (out / 'maps/tessaro.geojson').exists()
        m = json.loads((out / 'manifest.json').read_text())
        assert m['counts']['tessaro']['39266'] == 1
        assert m['period_start'] == '2017-01-02'
        assert m['available_months']['tessaro']['39266'] == ['2017-01']
