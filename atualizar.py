"""Publica somente observações horárias das estações autorizadas em clientes.json.
Credenciais exclusivamente por variáveis de ambiente / GitHub Actions Secrets.
"""
import argparse
import calendar
import gzip
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
START_DEFAULT = '2010-01-01'  # limite de busca retrospectiva; se houver registros anteriores, amplie
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
    row['rajada_kmh'] = numeric(raw.get('maxWindGust'))
    if row['rajada_kmh'] is None:
        row['rajada_kmh'] = nested_metric(raw, 'wind_gust_kph', 'max')
    row['radiacao_solar_mjm2'] = numeric(raw.get('sumSolarRadiation'))
    row['direcao_vento_graus'] = numeric(raw.get('diravgWindDirection'))
    if row['direcao_vento_graus'] is None:
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


class FarmTokenSession(requests.Session):
    """Anexa token apenas em chamadas HTTPS ao host admin.farmcommand.com."""
    def __init__(self, token):
        super().__init__()
        self._farm_token = token
        self.headers.update({'Accept': 'application/json', 'User-Agent': 'WeatherDataPortal/1.1'})

    def request(self, method, url, **kwargs):
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.scheme != 'https' or parsed.hostname != 'admin.farmcommand.com':
            raise RuntimeError('Destino não autorizado para a sessão meteorológica')
        params = dict(kwargs.pop('params', {}) or {})
        params['token'] = self._farm_token
        # requests.Session.get() ja define allow_redirects=True; removemos a opcao
        # antes de fixa-la em False para impedir vazamento do token em redirects.
        kwargs.pop('allow_redirects', None)
        response = super().request(method, url, params=params, allow_redirects=False, **kwargs)
        if 300 <= response.status_code < 400:
            raise RuntimeError('A API retornou redirecionamento inesperado; nenhuma URL de login foi seguida')
        return response


def auth_session():
    """Obtém token temporário via POST /token-login/ com os Secrets FARM_USER/PASS.
    Também aceita FARM_TOKEN já emitido, se fornecido por meio seguro.
    """
    token = os.environ.get('FARM_TOKEN', '').strip()
    if not token:
        user = os.environ.get('FARM_USER', '').strip()
        password = os.environ.get('FARM_PASS', '').strip()
        if not user or not password:
            raise RuntimeError('Configure FARM_USER e FARM_PASS nos GitHub Actions Secrets.')
        response = requests.post(
            API + '/token-login/',
            json={'username': user, 'password': password},
            headers={'Accept': 'application/json'}, timeout=30, allow_redirects=False)
        if response.status_code != 200:
            raise RuntimeError(f'Falha no token-login do FarmCommand: HTTP {response.status_code}')
        try:
            token = response.json().get('token')
        except ValueError as exc:
            raise RuntimeError('Resposta do token-login não é JSON') from exc
        if not isinstance(token, str) or not token.strip():
            raise RuntimeError('token-login não retornou um token válido')
        logging.info('Token do FarmCommand obtido com sucesso (valor oculto)')
    return FarmTokenSession(token)


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
                raise RuntimeError(f'API retornou erros para estação {station_id} (detalhes ocultos)')
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


def read_rows(path):
    if path.exists():
        if path.suffix == '.gz':
            with gzip.open(path, 'rt', encoding='utf-8') as fh:
                return json.load(fh).get('rows', [])
        return json.loads(path.read_text(encoding='utf-8')).get('rows', [])
    return []


def write_gzip_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('wb') as fh:
        with gzip.GzipFile(filename='', mode='wb', fileobj=fh, compresslevel=9, mtime=0) as gz:
            gz.write(json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8'))
    temp.replace(path)


def collect(config, start, end, refresh_days):
    s = auth_session()
    errors = []
    counts = {}
    today = date.today()
    earliest = None
    for client in config['clientes']:
        slug = client['slug']
        counts[slug] = {}
        for station in client['estacoes']:
            sid = int(station['id'])
            saved = 0
            for a, b in month_range(start, end):
                out = SITE / 'data' / slug / str(sid) / f'{a:%Y-%m}.json.gz'
                legacy = out.with_suffix('')
                # Meses históricos prontos não precisam ser consultados novamente.
                if (out.exists() or legacy.exists()) and b < today - timedelta(days=refresh_days):
                    try:
                        existing_rows = read_rows(out if out.exists() else legacy)
                        if legacy.exists() and not out.exists():
                            write_gzip_json(out, {'station_id': sid, 'month': f'{a:%Y-%m}', 'rows': existing_rows})
                            legacy.unlink()
                        if existing_rows and 'radiacao_solar_mjm2' not in existing_rows[0]:
                            logging.info('Arquivo antigo sem radiacao solar; atualizando %s', out)
                        else:
                            saved += len(existing_rows)
                            if existing_rows:
                                first = existing_rows[0]['data_hora_local'][:10]
                                earliest = min(earliest, first) if earliest else first
                            continue
                    except (ValueError, KeyError):
                        logging.warning('Arquivo inválido; refazendo %s', out)
                logging.info('%s / %s: %s..%s', slug, sid, a, b)
                try:
                    records = fetch(s, sid, a, b)
                    rows = [normalize(r, sid) for r in records]
                    rows = [r for r in rows if r is not None and a.isoformat() <= r['data_hora_local'][:10] <= b.isoformat()]
                    # Em meses parciais, preserve o restante do mês previamente coletado.
                    if out.exists() or legacy.exists():
                        try:
                            old = read_rows(out if out.exists() else legacy)
                            rows += [r for r in old if not (a.isoformat() <= r['data_hora_local'][:10] <= b.isoformat())]
                        except (ValueError, KeyError):
                            pass
                    rows = list({r['data_hora_local']: r for r in rows}.values())
                    rows.sort(key=lambda r: r['data_hora_local'])
                    write_gzip_json(out, {'station_id': sid, 'month': f'{a:%Y-%m}', 'rows': rows})
                    if legacy.exists():
                        legacy.unlink()
                    saved += len(rows)
                    if rows:
                        first = rows[0]['data_hora_local'][:10]
                        earliest = min(earliest, first) if earliest else first
                except Exception as exc:
                    errors.append(f'{slug}/{sid}/{a:%Y-%m}: {type(exc).__name__}: falha na consulta (detalhe omitido para proteger o token)')
            counts[slug][str(sid)] = saved
    if errors:
        for err in errors:
            logging.error('%s', err)
        raise RuntimeError(f'{len(errors)} consultas falharam; deploy bloqueado para evitar atualização parcial.')
    write_json(SITE / 'manifest.json', {
        'updated_at_utc': datetime.now(timezone.utc).isoformat(),
        'period_start': start.isoformat(), 'first_observation': earliest, 'period_end': end.isoformat(),
        'timezone_note': TZ_NOTE,
        'clientes': [{k: c[k] for k in ('slug', 'nome', 'estacoes')} for c in config['clientes']],
        'storage': 'gzip-monthly-v3', 'counts': counts,
    })


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--from', dest='start', default=os.environ.get('BACKFILL_START', START_DEFAULT))
    ap.add_argument('--to', dest='end', default=None)
    ap.add_argument('--refresh-days', type=int, default=5)
    ap.add_argument('--backfill-months', type=int, default=int(os.environ.get('BACKFILL_MONTHS', '12')), help='Meses de histórico retroativo por execução (0 = todo período)')
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else date.today() - timedelta(days=1)
    if end < start:
        raise ValueError('Período inválido.')
    cfg = json.loads((ROOT / 'clientes.json').read_text(encoding='utf-8'))
    # Retomada histórica, mês a mês. Em cada execução amplia a janela em N meses.
    # Dados de execuções anteriores devem ser persistidos pelo workflow via commit.
    latest_existing = []
    for c in cfg['clientes']:
        for st in c['estacoes']:
            files = sorted((SITE / 'data' / c['slug'] / str(st['id'])).glob('????-??.json*'))
            if files:
                latest_existing.append(date.fromisoformat(files[0].name[:7] + '-01'))
    if args.backfill_months > 0:
        anchor = min(latest_existing) if latest_existing else end.replace(day=1)
        year = anchor.year
        month = anchor.month - args.backfill_months + (1 if latest_existing else 0)
        while month <= 0:
            month += 12
            year -= 1
        start = max(start, date(year, month, 1))
        logging.info('Janela retrospectiva desta execução: %s até %s', start, end)
    collect(cfg, start, end, args.refresh_days)
    logging.info('Exportação concluída até %s', end)


if __name__ == '__main__':
    main()
