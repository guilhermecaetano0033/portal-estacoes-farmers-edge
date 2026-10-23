"""Publica somente observações horárias das estações autorizadas em clientes.json.
Credenciais exclusivamente por variáveis de ambiente / GitHub Actions Secrets.
"""
import argparse
import calendar
import json
import logging
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
SITE = ROOT / 'site'
API = 'https://admin.farmcommand.com'
TZ_NOTE = 'Horário local conforme retornado pela estação/FarmCommand'
START_DEFAULT = '2026-09-01'
FIELDS = {
    'avg_temp_c': 'temp_media_c', 'min_temp_c': 'temp_min_c', 'max_temp_c': 'temp_max_c',
    'avg_relative_humidity': 'umidade_media_pct',
    'min_relative_humidity': 'umidade_min_pct', 'max_relative_humidity': 'umidade_max_pct',
    'total_precip_mm': 'chuva_mm', 'avg_windspeed_kph': 'vento_medio_kmh',
    'max_windspeed_kph': 'vento_max_kmh',
}


def numeric(raw):
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        x = float(raw)
        return x if abs(x) != float('inf') and x == x else None
    except (TypeError, ValueError):
        return None


def nested_metric(raw, key, selector='avg'):
    value = raw.get(key)
    return numeric(value.get(selector)) if isinstance(value, dict) else numeric(value)


def normalize(raw, station_id):
    """Não transforma valor ausente em zero; preserva horário local e UTC."""
    local = raw.get('local_time') or raw.get('date')
    if not local:
        return None
    row = {'station_id': station_id, 'data_hora_local': str(local),
           'data_hora_utc': raw.get('utc_time'), 'docCount': raw.get('docCount')}
    for source, target in FIELDS.items():
        row[target] = numeric(raw.get(source))
    if row['chuva_mm'] is None:
        row['chuva_mm'] = nested_metric(raw, 'rainfall_mm', 'sum')
    for target, source in [('temp_media_c', 'temperature_c'),
                           ('umidade_media_pct', 'relative_humidity_pct'),
                           ('vento_medio_kmh', 'wind_speed_kph')]:
        if row[target] is None:
            row[target] = nested_metric(raw, source)
    row['rajada_kmh'] = nested_metric(raw, 'wind_gust_kph', 'max')
    row['direcao_vento_graus'] = nested_metric(raw, 'wind_direction_deg', 'avg')
    return row


def month_range(start, end):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        first = date(y, m, 1)
        last = date(y, m, calendar.monthrange(y, m)[1])
        yield max(first, start), min(last, end)
        m += 1
        if m > 12:
            y, m = y + 1, 1


def auth_session():
    token = os.environ.get('FARM_TOKEN', '').strip()
    user = os.environ.get('FARM_USER', '').strip()
    password = os.environ.get('FARM_PASS', '').strip()
    s = requests.Session()
    s.headers.update({'Accept': 'application/json', 'User-Agent': 'WeatherDataPortal/1.0'})
    if token:
        # FARM_TOKEN deve conter apenas o valor; FARM_TOKEN_SCHEME normalmente 'Token' ou 'Bearer'.
        scheme = os.environ.get('FARM_TOKEN_SCHEME', '').strip() or 'Token'
        if scheme not in ('Token', 'Bearer'):
            raise ValueError('FARM_TOKEN_SCHEME inválido (Token ou Bearer).')
        s.headers['Authorization'] = f'{scheme} {token}'
    elif user and password:
        # Fluxo de login compatível com o script legado fornecido.
        login = API + '/login/'
        r = s.get(login, timeout=40)
        r.raise_for_status()
        csrf = s.cookies.get('csrftoken')
        if not csrf:
            raise RuntimeError('FarmCommand não retornou CSRF; configure FARM_TOKEN ou ajuste o login.')
        r = s.post(login, data={'username': user, 'password': password,
                                'csrfmiddlewaretoken': csrf},
                   headers={'Referer': login}, timeout=40)
        r.raise_for_status()
        if '/login/' in r.url:
            raise RuntimeError('Falha no login FarmCommand.')
        s.headers.update({'Referer': API + '/', 'X-CSRFToken': s.cookies.get('csrftoken', csrf)})
    else:
        raise RuntimeError('Configure FARM_TOKEN ou FARM_USER e FARM_PASS em GitHub Secrets.')
    return s


def fetch(s, station_id, start, end):
    url = f'{API}/weather/{station_id}/historical-summary-hourly/'
    params = {'startDate': f'{start.isoformat()}T00:00:00',
              'endDate': f'{end.isoformat()}T23:59:59'}
    for attempt in range(5):
        try:
            r = s.get(url, params=params, timeout=90)
            if r.status_code in (429, 500, 502, 503, 504):
                if attempt < 4:
                    time.sleep(min(4 * 2 ** attempt, 40))
                    continue
            r.raise_for_status()
            result = r.json()
            if not isinstance(result, dict) or not isinstance(result.get('results'), list):
                raise RuntimeError(f'Resposta inesperada da estação {station_id}')
            if result.get('errors'):
                raise RuntimeError(f'API retornou erro para estação {station_id}: {result["errors"]}')
            return result['results']
        except (requests.RequestException, ValueError):
            if attempt == 4:
                raise
            time.sleep(min(4 * 2 ** attempt, 40))
    raise RuntimeError('Falha nas tentativas de coleta')


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    temp.replace(path)


def collect(config, start, end, refresh_days):
    s = auth_session()
    errors = []
    counts = {}
    today = date.today()
    for client in config['clientes']:
        slug = client['slug']
        counts[slug] = {}
        for station in client['estacoes']:
            sid = int(station['id'])
            saved = 0
            for a, b in month_range(start, end):
                out = SITE / 'data' / slug / str(sid) / f'{a:%Y-%m}.json'
                # Meses históricos prontos não precisam ser consultados novamente.
                if out.exists() and b < today - timedelta(days=refresh_days):
                    try:
                        saved += len(json.loads(out.read_text(encoding='utf-8'))['rows'])
                        continue
                    except (ValueError, KeyError):
                        logging.warning('Arquivo inválido; refazendo %s', out)
                logging.info('%s / %s: %s..%s', slug, sid, a, b)
                try:
                    records = fetch(s, sid, a, b)
                    rows = [normalize(r, sid) for r in records]
                    rows = [r for r in rows if r is not None and a.isoformat() <= r['data_hora_local'][:10] <= b.isoformat()]
                    # Em meses parciais, preserve o restante do mês previamente coletado.
                    if out.exists():
                        try:
                            old = json.loads(out.read_text(encoding='utf-8')).get('rows', [])
                            rows += [r for r in old if not (a.isoformat() <= r['data_hora_local'][:10] <= b.isoformat())]
                        except (ValueError, KeyError):
                            pass
                    rows = list({r['data_hora_local']: r for r in rows}.values())
                    rows.sort(key=lambda r: r['data_hora_local'])
                    write_json(out, {'station_id': sid, 'month': f'{a:%Y-%m}', 'rows': rows})
                    saved += len(rows)
                except Exception as exc:
                    errors.append(f'{slug}/{sid}/{a:%Y-%m}: {type(exc).__name__}: {exc}')
            counts[slug][str(sid)] = saved
    if errors:
        for err in errors:
            logging.error('%s', err)
        raise RuntimeError(f'{len(errors)} consultas falharam; deploy bloqueado para evitar atualização parcial.')
    write_json(SITE / 'manifest.json', {
        'updated_at_utc': datetime.now(timezone.utc).isoformat(),
        'period_start': start.isoformat(), 'period_end': end.isoformat(),
        'timezone_note': TZ_NOTE,
        'clientes': [{k: c[k] for k in ('slug', 'nome', 'estacoes')} for c in config['clientes']],
        'counts': counts,
    })


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--from', dest='start', default=os.environ.get('BACKFILL_START', START_DEFAULT))
    ap.add_argument('--to', dest='end', default=None)
    ap.add_argument('--refresh-days', type=int, default=5)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else date.today() - timedelta(days=1)
    if end < start:
        raise ValueError('Período inválido.')
    cfg = json.loads((ROOT / 'clientes.json').read_text(encoding='utf-8'))
    collect(cfg, start, end, args.refresh_days)
    logging.info('Exportação concluída até %s', end)


if __name__ == '__main__':
    main()
