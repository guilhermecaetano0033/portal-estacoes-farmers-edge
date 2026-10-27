"""Consulta bordas reais do FarmCommand por grower e safra.

Adaptado do fluxo /asset/field/?rootAsset=&season= +
/fieldborder/?assetID=&seasonID= usado pelo dashboard de telemetria.
Sem credenciais na publicação. Mantém um GeoJSON válido quando a API falha.
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from atualizar import SITE, auth_session

ROOT = Path(__file__).resolve().parent
BASE = 'https://admin.farmcommand.com'
# 1087 = safra 1 2026/27; o fallback só entra se essa safra não trouxer bordas.
SEASONS = (1087, 1084, 1083, 1088)
MAX_FIELDS = 500


def oid(value):
    if isinstance(value, dict):
        value = value.get('id')
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def unpack_assets(data):
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for k in ('results', 'data', 'assets', 'items'):
            if isinstance(data.get(k), list):
                return [x for x in data[k] if isinstance(x, dict)]
        if 'id' in data:
            return [data]
    return []


def parent_id(asset):
    for k in ('parent', 'parent_id', 'parentID', 'parentId'):
        v = oid(asset.get(k))
        if v is not None:
            return v
    return None


def category(asset):
    v = asset.get('category', asset.get('type', ''))
    if isinstance(v, dict):
        v = v.get('name', v.get('label', ''))
    return str(v or '').casefold().strip()


def season_of(asset):
    for key in ('seasonID', 'season_id', 'seasonId', 'season'):
        if key in asset:
            return oid(asset[key])
    return None


def fields_for_grower(assets, grower_id):
    """Fallback seguro: caminha pela árvore do grower, nunca pela árvore toda."""
    by_id = {oid(a.get('id')): a for a in assets if oid(a.get('id')) is not None}
    children = defaultdict(list)
    for a in by_id.values():
        children[parent_id(a)].append(a)
    q = deque([grower_id])
    visited = {grower_id}
    found = {}
    while q:
        for a in children.get(q.popleft(), []):
            aid = oid(a.get('id'))
            if aid in visited or aid is None:
                continue
            visited.add(aid)
            q.append(aid)
            if category(a) in ('field', 'talhão', 'talhao'):
                found[aid] = a
    for aid, a in by_id.items():
        if category(a) in ('field', 'talhao', 'talhão'):
            if any(oid(a.get(k)) == grower_id for k in ('grower', 'grower_id', 'growerID')):
                found[aid] = a
    return list(found.values())


def collect_polygons(payload):
    """Suporta shapeData serializado, GeoJSON, GeometryCollection e wrappers."""
    result = []
    def visit(value):
        if isinstance(value, str):
            try: visit(json.loads(value))
            except (ValueError, TypeError): pass
            return
        if isinstance(value, list):
            for part in value: visit(part)
            return
        if not isinstance(value, dict): return
        kind = str(value.get('type', '')).casefold()
        if kind == 'featurecollection':
            visit(value.get('features', [])); return
        if kind == 'feature':
            visit(value.get('geometry')); return
        if kind == 'geometrycollection':
            visit(value.get('geometries', [])); return
        if kind in ('polygon', 'multipolygon'):
            coords = value.get('coordinates')
            try:
                p = coords[0][0] if kind == 'polygon' else coords[0][0][0]
                lon,lat = float(p[0]), float(p[1])
                if not (-75 <= lon <= -30 and -35 <= lat <= 10): return
            except (IndexError, TypeError, ValueError): return
            result.append({'type': 'Polygon' if kind == 'polygon' else 'MultiPolygon', 'coordinates': coords})
            return
        for key in ('results','data','shapeData','geometry','geom','shape','border','fieldborder'):
            if key in value: visit(value[key])
    visit(payload)
    return result


def geometries(payload):
    """Compatibilidade com testes da implementação anterior."""
    yield from collect_polygons(payload)

def api_get(session, path, params, timeout=30, retries=2):
    last = None
    for attempt in range(retries):
        try:
            r = session.get(BASE+path, params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            last = exc
            if attempt < retries-1: time.sleep(1+attempt)
    raise RuntimeError(type(last).__name__) from None


def fields_in_season(session, grower, season):
    """Mesmo endpoint do código que já recupera as bordas no FarmCommand."""
    try:
        raw = api_get(session,'/asset/field/', {'rootAsset':grower,'season':season}, timeout=75)
        fields = [f for f in unpack_assets(raw) if oid(f.get('id')) is not None]
        tagged = [f for f in fields if season_of(f) == season]
        # Se houver etiquetas de safra, usamos só as linhas correspondentes.
        if tagged: fields = tagged
        else: fields = [f for f in fields if season_of(f) in (None, season)]
        if 0 < len(fields) <= MAX_FIELDS:
            logging.info('Grower %s / safra %s: %s talhões via asset/field rootAsset', grower, season, len(fields))
            return fields, 'asset_field_rootAsset+season'
        if len(fields) > MAX_FIELDS:
            logging.warning('Grower %s / safra %s: consulta direta retornou %s talhões; verificando árvore', grower, season, len(fields))
    except Exception as exc:
        logging.warning('Grower %s / safra %s: asset/field falhou (%s)',grower,season,type(exc).__name__)
    try:
        raw = api_get(session,'/asset/',{'season':season},timeout=100)
        assets = unpack_assets(raw)
        found = fields_for_grower(assets,grower)
        logging.info('Grower %s / safra %s: %s talhões via árvore de assets (%s assets)',grower,season,len(found),len(assets))
        return found, 'asset_tree_season'
    except Exception as exc:
        logging.warning('Grower %s / safra %s: árvore falhou (%s)',grower,season,type(exc).__name__)
        return [], 'unavailable'


def border_for_field(session, field, season):
    fid = oid(field.get('id'))
    if fid is None or fid <= 0: return fid, [], 'invalid-id'
    # O Season ID é essencial; sem ele o FarmCommand pode responder com a borda errada.
    try:
        raw = api_get(session,'/fieldborder/',{'assetID':fid,'seasonID':season,'format':'json'},timeout=14,retries=2)
        shapes = collect_polygons(raw)
        return fid, shapes, 'ok' if shapes else 'no-geometry'
    except Exception as exc:
        return fid, [], type(exc).__name__


def build_client(session, customer):
    slug = customer['slug']
    grower = oid(customer.get('grower_id'))
    if not grower: raise ValueError(f'{slug}: grower_id inválido')
    total_checked = 0
    summary = []
    for season in SEASONS:
        fields, source = fields_in_season(session, grower, season)
        total_checked += len(fields)
        if not fields:
            summary.append({'season':season,'fields':0,'polygons':0,'source':source})
            continue
        features = []
        errors = defaultdict(int)
        # Um request por campo, em paralelo limitado, como no código de telemetria.
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = {pool.submit(border_for_field, session, f, season): f for f in fields}
            for job in as_completed(jobs):
                field = jobs[job]
                fid = oid(field.get('id'))
                try: _, geometries, result = job.result()
                except Exception as exc:
                    geometries, result = [], type(exc).__name__
                if not geometries: errors[result] += 1
                for geom in geometries:
                    features.append({
                        'type':'Feature',
                        'properties':{'field_id':fid,'name':str(field.get('label') or field.get('name') or f'Talhão {fid}'),'season_id':season},
                        'geometry':geom,
                    })
        logging.info('%s: safra %s => %s talhões, %s polígonos, falhas/sem borda %s',slug,season,len(fields),len(features),dict(errors))
        summary.append({'season':season,'fields':len(fields),'polygons':len(features),'source':source,'misses':dict(errors)})
        if features:
            # NÃO mistura bordas de várias safras; isso causava sobreposições incorretas.
            return {'type':'FeatureCollection','features':features}, {'grower_id':grower,'season_id':season,'polygons':len(features),'fields':len(fields),'method':source,'attempts':summary,'status':'ok'}
    return None, {'grower_id':grower,'season_id':None,'polygons':0,'fields':total_checked,'attempts':summary,'status':'no-geometries'}


def main():
    cfg = json.loads((ROOT/'clientes.json').read_text(encoding='utf-8'))
    session = auth_session()
    folder = SITE/'maps'
    folder.mkdir(parents=True, exist_ok=True)
    status = {'version':8, 'updated_at_utc':datetime.now(timezone.utc).isoformat(timespec='seconds'),'clientes':{}}
    for c in cfg['clientes']:
        slug = c['slug']
        try: geo, diag = build_client(session, c)
        except Exception as exc:
            logging.error('%s: erro na coleta de bordas (%s)',slug,type(exc).__name__)
            geo, diag = None, {'status':'error','error_type':type(exc).__name__,'polygons':0}
        status['clientes'][slug] = diag
        path = folder/f'{slug}.geojson'
        if geo and geo['features']:
            temp = path.with_suffix('.geojson.tmp')
            temp.write_text(json.dumps(geo,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
            temp.replace(path)
        else:
            logging.warning('%s: 0 polígonos obtidos; mapa anterior preservado, quando existir',slug)
    (folder/'status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
    logging.info('Diagnóstico publicado em site/maps/status.json')

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
    main()
