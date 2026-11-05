#!/usr/bin/env python3
"""Monta um artefato de Pages enxuto SEM alterar site/data nem o Git.

Meses que contenham apenas registros offline (sem nenhuma temperatura e
nenhuma umidade) são mantidos no banco bruto, mas não são publicados.
Meses com ao menos uma leitura válida são copiados INTEGRALMENTE para o
site: nenhuma leitura, incluindo lacunas offline dentro desses meses, é alterada.

A saída temporária (site_publicacao) contém o site completo utilizável:
HTML, JS, CSS, GeoJSON, Excel e os meses consultáveis de meteorologia.
"""
import argparse
import gzip
import json
import logging
import shutil
from pathlib import Path

VALID_KEYS = (
    'temp_media_c', 'temp_min_c', 'temp_max_c',
    'umidade_media_pct', 'umidade_min_pct', 'umidade_max_pct',
)


def valid_reading(row):
    """Classifica um horário como válido conforme regra operacional definida."""
    return any(row.get(k) is not None for k in VALID_KEYS)


def load_month(path):
    if path.name.endswith('.json.gz'):
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            return json.load(stream).get('rows', [])
    return json.loads(path.read_text(encoding='utf-8')).get('rows', [])


def build(site: Path, output: Path):
    site = site.resolve()
    output = output.resolve()
    if site == output or site in output.parents:
        raise ValueError('Pasta de saída não pode estar dentro de site/')
    if not (site / 'manifest.json').is_file():
        raise FileNotFoundError('Faltando site/manifest.json; colete os dados antes de publicar')
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    for p in site.rglob('*'):
        if not p.is_file() or 'data' in p.relative_to(site).parts[:1]:
            continue
        target = output / p.relative_to(site)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)

    manifest = json.loads((site / 'manifest.json').read_text(encoding='utf-8'))
    months = {}
    counts = {}
    offline = {}
    available_dates = []
    kept = 0
    omitted = 0
    saved_bytes = 0
    for cli in manifest.get('clientes', []):
        slug = cli['slug']
        months[slug] = {}
        counts[slug] = {}
        offline[slug] = {}
        for st in cli.get('estacoes', []):
            sid = str(st['id'])
            station = site / 'data' / slug / sid
            good_dates = []
            valid_total = 0
            offline_total = 0
            available = []
            # A saída é mensal por compatibilidade com o site/app.js atual.
            candidates = sorted(station.glob('????-??.json.gz')) + sorted(station.glob('????-??.json'))
            # Se há .json.gz e .json do mesmo mês, o .gz tem prioridade.
            selected = {}
            for p in candidates:
                key = p.name[:7]
                if key not in selected or p.suffix == '.gz':
                    selected[key] = p
            for month, p in sorted(selected.items()):
                rows = load_month(p)
                valid = [r for r in rows if valid_reading(r)]
                offline_total += len(rows) - len(valid)
                if not valid:
                    omitted += 1
                    saved_bytes += p.stat().st_size
                    continue
                # Mantém o formato e TODAS as observações do mês consultável.
                target = output / 'data' / slug / sid / p.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, target)
                available.append(month)
                kept += 1
                valid_total += len(valid)
                good_dates.extend([r['data_hora_local'][:10] for r in valid if r.get('data_hora_local')])
            months[slug][sid] = available
            counts[slug][sid] = valid_total
            offline[slug][sid] = offline_total
            cov = manifest.setdefault('station_coverage', {}).setdefault(slug, {}).setdefault(sid, {})
            cov['rows'] = valid_total
            if good_dates:
                cov['first'] = min(good_dates)
                cov['last'] = max(good_dates)
                available_dates.extend([cov['first'], cov['last']])
            else:
                cov['first'] = None
                cov['last'] = None
    manifest['counts'] = counts
    manifest['available_months'] = months
    manifest['offline_rows_in_storage'] = offline
    if available_dates:
        manifest['first_observation'] = manifest['period_start'] = min(available_dates)
    (output / 'manifest.json').write_text(
        json.dumps(manifest, ensure_ascii=False, separators=(',', ':')), encoding='utf-8'
    )
    stats = {
        'published_months': kept, 'omitted_offline_months': omitted,
        'raw_files_bytes_omitted': saved_bytes,
        'published_files': sum(p.is_file() for p in output.rglob('*')),
        'published_total_bytes': sum(p.stat().st_size for p in output.rglob('*') if p.is_file()),
        'valid_rows_per_station': counts,
    }
    (output / 'publication-stats.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding='utf-8')
    logging.info('Pages: %s meses publicados; %s meses inteiramente offline omitidos', kept, omitted)
    logging.info('Pages: %s arquivos; %.1f MB no total (antes de compactar o artefato)',
                 stats['published_files'], stats['published_total_bytes'] / 1_000_000)
    logging.info('Pages: %.1f MB de arquivos brutos vazios deixaram de ser publicados', saved_bytes / 1_000_000)
    return stats


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    parser = argparse.ArgumentParser()
    parser.add_argument('--site', default='site')
    parser.add_argument('--out', default='site_publicacao')
    args = parser.parse_args()
    build(Path(args.site), Path(args.out))

if __name__ == '__main__':
    main()
