"""Gera ZIPs estáticos com dois Excel consolidados por cliente.
Não persiste os XLSX no Git: apenas no artefato Pages publicado.
"""
import gzip
import json
import logging
import zipfile
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from openpyxl import Workbook

from offline_utils import is_offline

ROOT=Path(__file__).resolve().parent
SITE=ROOT/'site'
HEAD=['Estação','ID estação','Data/hora local','Temperatura média (°C)','Temperatura mínima (°C)','Temperatura máxima (°C)','Umidade média (%)','Umidade mínima (%)','Umidade máxima (%)','Chuva (mm)','Vento médio (km/h)','Vento máximo (km/h)','Rajada (km/h)','Direção vento (°)','Radiação solar (MJ/m²)']
KEYS=['temp_media_c','temp_min_c','temp_max_c','umidade_media_pct','umidade_min_pct','umidade_max_pct','chuva_mm','vento_medio_kmh','vento_max_kmh','rajada_kmh','direcao_vento_graus','radiacao_solar_mjm2']
LIMIT=1_000_000

def records(root):
    for path in sorted(root.glob('????-??.json*')):
        try:
            if path.suffix=='.gz':
                with gzip.open(path,'rt',encoding='utf-8') as h:
                    for row in json.load(h)['rows']:
                        if not is_offline(row):
                            yield row
            elif not path.with_suffix(path.suffix+'.gz').exists():
                with path.open(encoding='utf-8') as h:
                    for row in json.load(h)['rows']:
                        if not is_offline(row):
                            yield row
        except (OSError,ValueError,KeyError) as e:
            raise RuntimeError(f'Falha lendo {path} ({type(e).__name__})') from e

def workbook(client, daily, target):
    wb=Workbook(write_only=True)
    num=1; ws=wb.create_sheet(('Diarios' if daily else 'Horarios')+' '+str(num));ws.append(HEAD)
    total=0
    def next_row(row):
        nonlocal ws,num,total
        if total and total%LIMIT==0:
            num+=1;ws=wb.create_sheet(('Diarios' if daily else 'Horarios')+' '+str(num));ws.append(HEAD)
        ws.append(row);total+=1
    for st in client['estacoes']:
        entries=records(SITE/'data'/client['slug']/str(st['id']))
        if not daily:
            for r in entries:
                t=str(r.get('data_hora_local','')).replace('T',' ')[:16]
                next_row([st['nome'],st['id'],t]+[r.get(k) for k in KEYS])
        else:
            # Iteração mensal em ordem cronológica: cada dia só fica na memória até trocar a data.
            last=None; bucket=[]
            def finish(items,date):
                if not items:return
                def vals(key):return [v for r in items if isinstance((v:=r.get(key)),(float,int)) and not isinstance(v,bool)]
                def mean(key):
                    v=vals(key);return sum(v)/len(v) if v else None
                def total_sum(key):
                    v=vals(key);return sum(v) if v else None
                def maxval(key):
                    v=vals(key);return max(v) if v else None
                from math import sin,cos,atan2,pi,hypot
                angles=vals('direcao_vento_graus')
                u=sum(sin(a*pi/180) for a in angles);v=sum(cos(a*pi/180) for a in angles)
                dr=(atan2(u,v)*180/pi)%360 if angles and hypot(u,v)>1e-9 else None
                next_row([st['nome'],st['id'],date,mean('temp_media_c'),maxval('temp_min_c') if False else (min(vals('temp_min_c')) if vals('temp_min_c') else None),maxval('temp_max_c'),mean('umidade_media_pct'),min(vals('umidade_min_pct')) if vals('umidade_min_pct') else None,maxval('umidade_max_pct'),total_sum('chuva_mm'),mean('vento_medio_kmh'),maxval('vento_max_kmh'),maxval('rajada_kmh'),dr,total_sum('radiacao_solar_mjm2')])
            for r in entries:
                day=str(r.get('data_hora_local',''))[:10]
                if not day:continue
                if last is not None and day!=last:
                    finish(bucket,last);bucket=[]
                bucket.append(r);last=day
            if last is not None:finish(bucket,last)
    coords=wb.create_sheet('Coordenadas')
    coords.append(['Estação','ID estação','FEID','Latitude','Longitude','Cliente'])
    for st in client['estacoes']:
        coords.append([st['nome'],st['id'],st.get('feid'),st.get('latitude'),st.get('longitude'),client['nome']])
    target.parent.mkdir(parents=True,exist_ok=True)
    wb.save(target)
    return total

def main():
    cfg=json.loads((ROOT/'clientes.json').read_text(encoding='utf-8'))
    for client in cfg['clientes']:
        folder=SITE/'downloads';folder.mkdir(exist_ok=True)
        path=folder/(client['slug']+'_historico_completo.zip')
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            hourly=Path(tmp)/'dados_horarios.xlsx';daily=Path(tmp)/'dados_diarios.xlsx'
            nh=workbook(client,False,hourly)
            nd=workbook(client,True,daily)
            with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as z:
                z.write(hourly,arcname='dados_horarios.xlsx');z.write(daily,arcname='dados_diarios.xlsx')
        logging.info('%s ZIP pronto: %s horas, %s dias, %.2f MB',client['slug'],nh,nd,path.stat().st_size/1048576)

if __name__=='__main__':
    logging.basicConfig(level=logging.INFO)
    main()
