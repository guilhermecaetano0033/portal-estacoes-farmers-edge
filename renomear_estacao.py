"""Executado somente pelo proprietário via workflow_dispatch do GitHub Actions."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def rename(slug, sid, name):
    name = ' '.join(name.split())
    if not 1 <= len(name) <= 90:
        raise ValueError('Nome deve ter entre 1 e 90 caracteres')
    path = ROOT / 'clientes.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    for client in data['clientes']:
        if client['slug'] != slug:
            continue
        for station in client['estacoes']:
            if station['id'] == int(sid):
                station['nome'] = name
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
                print(f'Estação {sid} do cliente {slug} renomeada com sucesso.')
                return
    raise ValueError('A estação informada não pertence ao cliente informado.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--client', required=True, choices=['tessaro', 'fenix'])
    parser.add_argument('--station', required=True, type=int)
    parser.add_argument('--name', required=True)
    args = parser.parse_args()
    rename(args.client, args.station, args.name)
