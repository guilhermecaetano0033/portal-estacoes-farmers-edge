"""Busca talhões de cada grower via /asset e /fieldborder, salva GeoJSON para Pages.

Nunca publica assets de outros growers. Não publica resposta bruta nem token.
Não substitui mapa válido por conjunto de geometria vazio.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict, deque
from pathlib import Path

from atualizar import SITE, auth_session

ROOT = Path(__file__).resolve().parent
SEASONS = (1087, 1088, 1084, 1083)
URL = 'https://admin.farmcommand.com'


def oid(value):
    if isinstance(value, dict):
        value = value.get('id')
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def unpack_assets(payload):
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ('results', 'data', 'assets'):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []


def parent_id(item):
    for key in ('parent', 'parent_id', 'parentID', 'parentId'):
        val = oid(item.get(key))
        if val is not None:
            return val
    return None


def category(item):
    val = item.get('category', item.get('type', ''))
    if isinstance(val, dict):
        val = val.get('name', val.get('label', ''))
    return str(val or '').casefold().strip()


def fields_for_grower(assets, grower_id):
    """Garante vinculação à árvore do grower mesmo com vários níveis de Farm."""
    children = defaultdict(list)
    unique = {}
    for item in assets:
        aid = oid(item.get('id'))
        if aid is None:
            continue
        unique[aid] = item
    for item in unique.values():
        children[parent_id(item)].append(item)
    seen = {grower_id}
    queue = deque([grower_id])
    found = {}
    while queue:
        current = queue.popleft()
        for item in children.get(current, []):
            aid = oid(item.get('id'))
            if aid is None or aid in seen:
                continue
            seen.add(aid)
            queue.append(aid)
            if category(item) in ('field', 'talhao', 'talhão'):
                found[aid] = item
    # APIs com lista achatada podem fornecer grower_id diretamente no talhão.
    for aid, item in unique.items():
        direct = oid(item.get('grower_id', item.get('growerID', item.get('grower'))))
        if direct == grower_id and category(item) in ('field', 'talhao', 'talhão'):
            found[aid] = item
    return list(found.values())


def geometries(payload):
    """Lê shapeData GeoJSON, incluindo múltiplos registros e FeatureCollection."""
    if isinstance(payload, dict):
        payload = payload.get('results', payload.get('data', [payload]))
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return
    for record in payload:
        if not isinstance(record, dict):
            continue
        shape = record.get('shapeData', record.get('geometry', record))
        if isinstance(shape, str):
            try:
                shape = json.loads(shape)
            except (ValueError, TypeError):
                continue
        if not isinstance(shape, dict):
            continue
        typ = shape.get('type')
        if typ == 'FeatureCollection':
            feats = shape.get('features', [])
        elif typ == 'Feature':
            feats = [shape]
        else:
            feats = [{'geometry': shape}]
        for feature in feats:
            geom = feature.get('geometry') if isinstance(feature, dict) else None
            if not isinstance(geom, dict) or geom.get('type') not in ('Polygon', 'MultiPolygon'):
                continue
            try:
                polygon = geom['coordinates']
                first = polygon[0][0] if geom['type'] == 'Polygon' else polygon[0][0][0]
                lon, lat = float(first[0]), float(first[1])
                if not (-75 < lon < -35 and -35 < lat < 10):
                    logging.warning('Borda ignorada: coordenadas fora da região (ordem lon/lat?)')
                    continue
            except (ValueError, IndexError, TypeError, KeyError):
                continue
            yield geom


def fetch_geometries(session, config):
    all_assets = {}
    for season in SEASONS:
        try:
            response = session.get(URL + '/asset/', params={'season': season}, timeout=90)
            response.raise_for_status()
            items = unpack_assets(response.json())
            logging.info('Safra %s: %s assets', season, len(items))
            for item in items:
                aid = oid(item.get('id'))
                if aid is not None:
                    all_assets.setdefault(aid, item)
        except Exception as exc:
            logging.warning('Assets da safra %s indisponíveis: %s', season, type(exc).__name__)
    if not all_assets:
        raise RuntimeError('Nenhum asset foi retornado; dados geográficos anteriores preservados.')
    out = {}
    for c in config['clientes']:
        grower = oid(c.get('grower_id'))
        slug = c['slug']
        fields = fields_for_grower(list(all_assets.values()), grower)
        features = []
        errors = 0
        for field in fields:
            fid = oid(field.get('id'))
            try:
                r = session.get(URL + '/fieldborder/', params={'assetID': fid, 'format': 'json'}, timeout=75)
                r.raise_for_status()
                for geom in geometries(r.json()):
                    features.append({
                        'type': 'Feature',
                        'properties': {'field_id': fid, 'name': str(field.get('label') or field.get('name') or f'Talhão {fid}')},
                        'geometry': geom,
                    })
            except Exception as exc:
                errors += 1
                logging.warning('%s: fieldborder %s indisponível (%s)', slug, fid, type(exc).__name__)
        out[slug] = {'type': 'FeatureCollection', 'features': features}
        logging.info('%s grower=%s: %s talhões identificados, %s geometrias, %s falhas', slug, grower, len(fields), len(features), errors)
        if not fields:
            logging.warning('%s: grower %s sem talhões nas safras consultadas: verificar vínculo dos assets', slug, grower)
    return out


def main():
    cfg = json.loads((ROOT / 'clientes.json').read_text(encoding='utf-8'))
    session = auth_session()
    result = fetch_geometries(session, cfg)
    folder = SITE / 'maps'
    folder.mkdir(parents=True, exist_ok=True)
    for slug, geojson in result.items():
        target = folder / f'{slug}.geojson'
        if not geojson['features']:
            logging.warning('%s: GeoJSON vazio; mantendo arquivo anterior se existir.', slug)
            continue
        temporary = target.with_suffix('.geojson.tmp')
        temporary.write_text(json.dumps(geojson, separators=(',', ':'), ensure_ascii=False), encoding='utf-8')
        temporary.replace(target)
        logging.info('Mapa %s atualizado: %s polígonos', slug, len(geojson['features']))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    main()
