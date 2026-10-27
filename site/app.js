'use strict';
const root=document.querySelector('[data-client]');const slug=root?.dataset.client;const $=id=>document.getElementById(id);
const fields=[['data_hora_local','Data/hora local'],['temp_media_c','Temperatura média (°C)'],['temp_min_c','Temp. mínima (°C)'],['temp_max_c','Temp. máxima (°C)'],['umidade_media_pct','Umidade média (%)'],['umidade_min_pct','Umidade mínima (%)'],['umidade_max_pct','Umidade máxima (%)'],['chuva_mm','Precipitação (mm)'],['vento_medio_kmh','Vento médio (km/h)'],['vento_max_kmh','Vento máximo (km/h)'],['rajada_kmh','Rajada (km/h)'],['direcao_vento_graus','Direção (°)'],['radiacao_solar_mjm2','Radiação solar (MJ/m²)'],['docCount','Amostras'],['offline','Situação']];
let manifest,client,records=[],page=0,map=null,mapLayer=null,charts=[],tab='dashboard',rawMode='daily',compareChart=null;const PAGESIZE=80;
const fmt=v=>v===null||v===undefined||v===''?'—':typeof v==='number'?v.toLocaleString('pt-BR',{maximumFractionDigits:2}):String(v).replace('T',' ').slice(0,25);
const fmtNum=(v,d=1)=>v===null||v===undefined?'—':v.toLocaleString('pt-BR',{maximumFractionDigits:d});
function status(s){$('status').textContent=s}function dateText(s){return s?.split('-').reverse().join('/')||'—'}
function months(a,b){let [y,m]=a.slice(0,7).split('-').map(Number),r=[];while(`${y}-${String(m).padStart(2,'0')}`<=b.slice(0,7)){r.push(`${y}-${String(m).padStart(2,'0')}`);if(++m===13){m=1;y++}}return r}
function range(){const a=$('dateFrom').value,b=$('dateTo').value;if(!a||!b||a>b)throw Error('Informe um período válido.');if(a<manifest.period_start||b>manifest.period_end)throw Error(`Período disponível: ${dateText(manifest.period_start)} a ${dateText(manifest.period_end)}.`);return[a,b]}
const monthCache=new Map();
async function monthRows(id,m){const key=`${slug}/${id}/${m}`;if(monthCache.has(key))return monthCache.get(key);const promise=(async()=>{const url=`data/${key}.json.gz`;let response=await fetch(url);if(response.status===404){response=await fetch(`data/${key}.json`);if(response.status===404)return [];if(!response.ok)throw Error(`HTTP ${response.status}: ${key}`);return (await response.json()).rows||[]}if(!response.ok)throw Error(`HTTP ${response.status}: ${key}`);if(!('DecompressionStream' in window))throw Error('Navegador sem suporte GZIP. Use Chrome, Edge ou Firefox atualizado.');const raw=await response.blob();const stream=raw.stream().pipeThrough(new DecompressionStream('gzip'));const body=await new Response(stream).text();return JSON.parse(body).rows||[]})();monthCache.set(key,promise);try{return await promise}catch(e){monthCache.delete(key);throw e}}
async function stationRows(id,a,b){const chunks=await Promise.all(months(a,b).map(m=>monthRows(id,m)));return chunks.flat().filter(x=>x.data_hora_local?.slice(0,10)>=a&&x.data_hora_local?.slice(0,10)<=b).sort((x,y)=>x.data_hora_local.localeCompare(y.data_hora_local))}
const valid=(v)=>typeof v==='number'&&Number.isFinite(v);
const isOffline=r=>!['temp_media_c','temp_min_c','temp_max_c','umidade_media_pct','umidade_min_pct','umidade_max_pct'].some(k=>valid(r[k]));
function aggregate(rows,key,how='sum'){const values=rows.map(r=>r[key]).filter(valid);if(!values.length)return null;if(how==='sum')return values.reduce((a,b)=>a+b,0);if(how==='max')return Math.max(...values);return values.reduce((a,b)=>a+b,0)/values.length}
function daily(rows){const groups=new Map();for(const r of rows){const d=r.data_hora_local?.slice(0,10);if(!d)continue;if(!groups.has(d))groups.set(d,[]);groups.get(d).push(r)}return [...groups].sort(([a],[b])=>a.localeCompare(b)).map(([day,list])=>{const good=list.filter(r=>!isOffline(r));return {day,chuva:aggregate(good,'chuva_mm'),temperatura:aggregate(good,'temp_media_c','avg'),umidade:aggregate(good,'umidade_media_pct','avg'),vento:aggregate(good,'vento_medio_kmh','avg'),rajada:aggregate(good,'rajada_kmh','max'),direcao:vectorMean(good),radiacao:aggregate(good,'radiacao_solar_mjm2'),horas:good.length,offline_horas:list.length-good.length}})}
function vectorMean(rows){const a=rows.map(r=>r.direcao_vento_graus).filter(valid);if(!a.length)return null;let x=0,y=0;for(const d of a){x+=Math.cos(d*Math.PI/180);y+=Math.sin(d*Math.PI/180)}if(Math.hypot(x,y)<1e-8)return null;return(Math.atan2(y,x)*180/Math.PI+360)%360}
function virtualStation(){
 const coords=client.estacoes.filter(s=>valid(s.latitude)&&valid(s.longitude));
 if(!coords.length)return null;
 return {id:'virtual',nome:'Fazenda inteira · estimativa',feid:'INTERPOLADO',latitude:coords.reduce((a,s)=>a+s.latitude,0)/coords.length,longitude:coords.reduce((a,s)=>a+s.longitude,0)/coords.length,virtual:true};
}
async function virtualRows(a,b){
 const stationList=client.estacoes.filter(s=>valid(s.latitude)&&valid(s.longitude));
 const groups=new Map();
 for(const st of stationList){const rr=await stationRows(st.id,a,b);for(const r of rr){if(isOffline(r))continue;const key=r.data_hora_local?.slice(0,19);if(!key)continue;if(!groups.has(key))groups.set(key,[]);groups.get(key).push({...r,latitude:st.latitude,longitude:st.longitude})}}
 const center=virtualStation();if(!center)return [];
 const keys=['chuva_mm','temp_media_c','temp_min_c','temp_max_c','umidade_media_pct','umidade_min_pct','umidade_max_pct','vento_medio_kmh','vento_max_kmh','rajada_kmh','radiacao_solar_mjm2'];
 return [...groups].sort(([a],[b])=>a.localeCompare(b)).map(([key,list])=>{
  const record={station_id:'virtual',data_hora_local:key,docCount:list.length};
  for(const k of keys)record[k]=estimateMetric(list,center.latitude,center.longitude,k);
  // Média circular ponderada para direções angulares.
  const directions=list.filter(r=>valid(r.direcao_vento_graus));let vx=0,vy=0,weight=0;
  for(const r of directions){const km=Math.max(.1,Math.hypot((r.latitude-center.latitude)*111,(r.longitude-center.longitude)*111*Math.cos(center.latitude*Math.PI/180)));const w=1/(km*km);vx+=w*Math.cos(r.direcao_vento_graus*Math.PI/180);vy+=w*Math.sin(r.direcao_vento_graus*Math.PI/180);weight+=w}
  record.direcao_vento_graus=weight&&Math.hypot(vx,vy)>1e-10?(Math.atan2(vy,vx)*180/Math.PI+360)%360:null;
  return record;
 });
}
function estimateMetric(list,lat,lng,key){let sum=0,weights=0;for(const s of list){if(!valid(s[key]))continue;const km=Math.hypot((lat-s.latitude)*111,(lng-s.longitude)*111*Math.cos(lat*Math.PI/180));if(km<.05)return s[key];const w=1/Math.max(km,.1)**2;sum+=w*s[key];weights+=w}return weights?sum/weights:null}
function compass(deg){if(!valid(deg))return '—';return ['N','NE','L','SE','S','SO','O','NO'][Math.round(deg/45)%8]}
function tableItems(){if(rawMode==='hourly')return records;return daily(records).map(r=>({data_hora_local:r.day,chuva_mm:r.chuva,temp_media_c:r.temperatura,umidade_media_pct:r.umidade,rajada_kmh:r.rajada,direcao_vento_graus:r.direcao,radiacao_solar_mjm2:r.radiacao,docCount:r.horas,offline:r.horas===0}))}
function drawTable(){const items=tableItems(),n=items.length,list=items.slice(page*PAGESIZE,(page+1)*PAGESIZE),fragment=document.createDocumentFragment();for(const r of list){const tr=document.createElement('tr');for(const [k] of fields){const td=document.createElement('td');td.textContent=k==='data_hora_local'?String(r[k]||'').replace('T',' ').slice(0,16):k==='offline'?(isOffline(r)?'Offline':'Com dados'):fmt(r[k]);tr.appendChild(td)}fragment.appendChild(tr)}$('tbody').replaceChildren(fragment);$('rowCount').textContent=`${n.toLocaleString('pt-BR')} registros ${rawMode==='daily'?'diários':'horários'}`;const max=Math.max(1,Math.ceil(n/PAGESIZE));$('pageInfo').textContent=`Página ${page+1} de ${max}`;$('prev').disabled=page===0;$('next').disabled=page>=max-1}
function paintCharts(){for(const c of charts)c.destroy();charts=[];if(typeof Chart==='undefined'){$('chartWarning').hidden=false;return}$('chartWarning').hidden=true;const d=daily(records),labels=d.map(x=>x.day.slice(8)+'/'+x.day.slice(5,7));const cfg=(id,type,label,key,color,unit)=>{const el=$(id);if(!el)return;const chart=new Chart(el,{type,data:{labels,datasets:[{label,data:d.map(x=>x[key]),borderColor:color,backgroundColor:type==='bar'?color+'bb':color+'20',borderWidth:2,tension:.28,fill:type==='line',pointRadius:d.length>70?0:2,maxBarThickness:36,spanGaps:false}]},options:{responsive:true,maintainAspectRatio:false,animation:false,interaction:{mode:'index',intersect:false},plugins:{legend:{display:false},tooltip:{callbacks:{label:c=>`${label}: ${c.raw===null?'sem dado':fmtNum(c.raw)} ${unit}`}}},scales:{x:{ticks:{maxTicksLimit:9}},y:{beginAtZero:type==='bar'}}}});charts.push(chart)};cfg('chartRain','bar','Chuva','chuva','#1573c7','mm');cfg('chartTemp','line','Temperatura','temperatura','#e57c43','°C');cfg('chartHumidity','line','Umidade','umidade','#15a18b','%');cfg('chartGust','line','Rajada máxima','rajada','#8a62ce','km/h');const petals=['N','NE','L','SE','S','SO','O','NO'].map((name,i)=>records.filter(r=>valid(r.direcao_vento_graus)&&Math.round(r.direcao_vento_graus/45)%8===i).length);$('windRose').textContent='Rosa dos ventos: frequência de registros por direção (8 setores).';charts.push(new Chart($('chartDirection'),{type:'polarArea',data:{labels:['N','NE','L','SE','S','SO','O','NO'],datasets:[{data:petals,backgroundColor:['#1270c1','#2c94d1','#64b0df','#95c5e9','#77a6d9','#648bd1','#476ab8','#244ca6']}]},options:{responsive:true,maintainAspectRatio:false,animation:false,plugins:{legend:{position:'bottom'}}}}));}
function paintCards(){const rain=aggregate(records,'chuva_mm'),temp=aggregate(records,'temp_media_c','avg'),humidity=aggregate(records,'umidade_media_pct','avg'),gust=aggregate(records,'rajada_kmh','max');$('rainKpi').textContent=fmtNum(rain)+' mm';$('tempKpi').textContent=fmtNum(temp)+' °C';$('humidityKpi').textContent=fmtNum(humidity)+' %';$('gustKpi').textContent=fmtNum(gust)+' km/h';$('directionKpi').textContent=compass(vectorMean(records));$('measurementNote').textContent=`${records.length.toLocaleString('pt-BR')} observações horárias · Dados ausentes não são considerados zero.`}
function tabSet(next){tab=next;for(const t of ['dashboard','map','raw','compare']){$('tab-'+t).hidden=t!==next;$('btn-'+t).classList.toggle('active',t===next);$('btn-'+t).setAttribute('aria-selected',String(t===next))}if(next==='map')setTimeout(()=>{ensureMap();map?.invalidateSize();paintMap().catch(e=>{$('mapInfo').textContent='Falha no mapa: '+e.message})},100)}
// V7: mapa coroplético por talhão; data independente do dashboard.
let bordersCache=null;
async function getBorders(){
 if(bordersCache!==null)return bordersCache;
 const r=await fetch(`maps/${slug}.geojson`,{cache:'no-store'});
 if(!r.ok){
  let details='';try{const d=await (await fetch('maps/status.json',{cache:'no-store'})).json();const x=d.clientes?.[slug];if(x)details=` Safra testada: ${x.attempts?.map(a=>`${a.season}: ${a.fields} talhões / ${a.polygons} bordas`).join('; ')||'sem diagnóstico'}.`;}catch(_e){}
  throw Error(`Bordas ainda não publicadas para ${client.nome} (HTTP ${r.status}).${details} Confira a etapa "Consultar bordaduras do grower" no Actions.`);
 }
 const geo=await r.json();
 bordersCache=(geo.features||[]).filter(f=>f.geometry&&['Polygon','MultiPolygon'].includes(f.geometry.type));
 if(!bordersCache.length)throw Error('GeoJSON sem talhões. Verifique grower_id, vínculo dos assets e fieldborder no GitHub Actions.');
 return bordersCache;
}
function ringsFor(feature){const g=feature.geometry;if(!g)return [];return g.type==='Polygon'?[g.coordinates]:g.type==='MultiPolygon'?g.coordinates:[]}
function pointInRing(lng,lat,ring){let inside=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){
 const xi=ring[i][0],yi=ring[i][1],xj=ring[j][0],yj=ring[j][1];
 if(((yi>lat)!==(yj>lat))&&(lng<(xj-xi)*(lat-yi)/(yj-yi)+xi))inside=!inside;
 }return inside;}
function insidePolygon(lon,lat,rings){return rings.length>0&&pointInRing(lon,lat,rings[0])&&!rings.slice(1).some(h=>pointInRing(lon,lat,h))}
function mapDates(){const a=$('mapDateFrom').value,b=$('mapDateTo').value;
 if(!a||!b||a>b)throw Error('Informe data inicial e final válidas para o mapa.');
 if(a<manifest.period_start||b>manifest.period_end)throw Error(`Histórico disponível de ${dateText(manifest.period_start)} até ${dateText(manifest.period_end)}.`);
 return[a,b];}
function ensureMap(){if(map)return;if(typeof L==='undefined'){$('mapInfo').textContent='Leaflet não carregou. Verifique sua conexão.';return;}
 map=L.map('rainMap',{scrollWheelZoom:false,zoomControl:true,attributionControl:false,preferCanvas:true,zoomSnap:.25});
 map.getContainer().style.background='#f5f8fb';
 mapLayer=L.layerGroup().addTo(map);
 const legend=L.control({position:'bottomright'});
 legend.onAdd=()=>{const el=L.DomUtil.create('div','rainfall-legend');el.innerHTML='<b>Chuva estimada por talhão (mm)</b><div class="rainfall-gradient"></div><div class="rainfall-ends"><span id="rainLegendMin">Menor</span><span id="rainLegendMax">Maior</span></div><small>Branco: menor acumulado<br>Azul: maior acumulado<br>Estimativa IDW · não é medição no talhão</small>';return el;};legend.addTo(map);
}
function estimate(stations,lat,lng){const values=stations.filter(s=>valid(s.rain));if(!values.length)return null;let up=0,down=0;
 for(const s of values){const dy=(lat-s.latitude)*111,dx=(lng-s.longitude)*111*Math.cos(lat*Math.PI/180),km=Math.hypot(dx,dy);
 if(km<.05)return s.rain;const w=1/Math.max(km,0.1)**2;up+=w*s.rain;down+=w;}return up/down;}
// Amostragem no INTERIOR do talhão, não apenas no centro da caixa delimitadora.
function rainForField(feature,stations){const estimates=[];
 for(const poly of ringsFor(feature)){
  if(!poly.length||!poly[0].length)continue;
  const outer=poly[0],lngs=outer.map(p=>p[0]),lats=outer.map(p=>p[1]);
  const west=Math.min(...lngs),east=Math.max(...lngs),south=Math.min(...lats),north=Math.max(...lats);
  // Quadrícula de amostragem adaptativa: 36 subáreas por parte do talhão.
  for(let i=0;i<6;i++)for(let j=0;j<6;j++){
   const lon=west+(east-west)*(i+.5)/6,lat=south+(north-south)*(j+.5)/6;
   if(insidePolygon(lon,lat,poly)){const value=estimate(stations,lat,lon);if(valid(value))estimates.push(value);}
  }
  // Talhões muito estreitos: fallback próximo ao vértice, em vez de declarar seca.
  if(!estimates.length){const v=outer[0];const val=estimate(stations,v[1],v[0]);if(valid(val))estimates.push(val);}
 }
 return estimates.length?estimates.reduce((a,b)=>a+b,0)/estimates.length:null;
}
function rainColor(value,min,max){if(!valid(value))return '#e5e7eb';
 if(max-min<.001)return max<=0?'#ffffff':'#9cc7ed';
 const t=Math.max(0,Math.min(1,(value-min)/(max-min)));
 const stops=[[255,255,255],[212,231,250],[113,174,235],[33,110,196],[7,54,143]];
 const k=Math.min(3,Math.floor(t*4)),f=t*4-k;
 return '#'+stops[k].map((x,i)=>Math.round(x+(stops[k+1][i]-x)*f).toString(16).padStart(2,'0')).join('');
}
async function paintMap(){
 ensureMap();if(!map)return;
 const [a,b]=mapDates();$('mapInfo').textContent=`Calculando chuva de ${dateText(a)} a ${dateText(b)} por talhão...`;
 $('refreshMap').disabled=true;
 try{
  // Requer bordas. Sem talhões, não renderiza mapa falso ou grade retangular.
  const features=await getBorders();
  const stations=[];
  for(const st of client.estacoes){if(!valid(st.latitude)||!valid(st.longitude))continue;
   const rr=await stationRows(st.id,a,b);
   const good=rr.filter(r=>!isOffline(r));
   const reading=good.filter(r=>valid(r.chuva_mm));
   stations.push({...st,rain:aggregate(reading,'chuva_mm'),observations:reading.length,offline:rr.length-good.length});
  }
  const measured=stations.filter(s=>valid(s.rain)&&s.observations>0);
  const estimates=features.map(f=>({feature:f,mm:measured.length?rainForField(f,measured):null}));
  for(const item of estimates){item.feature.properties=item.feature.properties||{};item.feature.properties._rainEstimate=item.mm;}
  const amounts=estimates.map(x=>x.mm).filter(valid);
  const min=amounts.length?Math.min(...amounts):0,max=amounts.length?Math.max(...amounts):0;
  mapLayer.clearLayers();
  const useColor=$('interpolate').checked;
  const featureLayer=L.geoJSON({type:'FeatureCollection',features}, {
   style:f=>{
    return {color:'#425d76',weight:1.3,opacity:.9,fill:true,fillOpacity:useColor&&amounts.length?.95:.13,fillColor:useColor?rainColor(f.properties?._rainEstimate,min,max):'#c4d4e2'};
   },
   onEachFeature:(f,layer)=>{
    const mm=f.properties?._rainEstimate;
    const name=String(f.properties?.name||'Talhão');
    const value=valid(mm)?`${fmtNum(mm,1)} mm`:'Sem estimativa';
    const tip=document.createElement('span');tip.textContent=`${name} · ${value}`;layer.bindTooltip(tip,{sticky:true});
    const popup=document.createElement('div');const title=document.createElement('strong');title.textContent=name;
    popup.append(title,document.createElement('br'),document.createTextNode(`Chuva estimada: ${value}`),document.createElement('br'),document.createTextNode(`Período: ${dateText(a)} a ${dateText(b)}`));
    layer.bindPopup(popup);
   }
  }).addTo(mapLayer);
  if(featureLayer.getBounds().isValid())map.fitBounds(featureLayer.getBounds().pad(.08),{animate:false});
  for(const st of stations){
   const marker=L.circleMarker([st.latitude,st.longitude],{radius:6,color:'#fff',weight:2,fillColor:valid(st.rain)?'#144d9b':'#aaa',fillOpacity:1}).addTo(mapLayer);
   const popup=document.createElement('div');const title=document.createElement('strong');title.textContent=st.nome;
   popup.append(title,document.createElement('br'),document.createTextNode(valid(st.rain)?`Chuva medida: ${fmtNum(st.rain)} mm`:'Chuva: sem medição'),document.createElement('br'),document.createTextNode(`${st.observations} horas válidas · ${st.offline} horas offline`));marker.bindPopup(popup);
  }
  if($('rainLegendMin'))$('rainLegendMin').textContent=amounts.length?`${fmtNum(min)} mm`:'S/ dados';
  if($('rainLegendMax'))$('rainLegendMax').textContent=amounts.length?`${fmtNum(max)} mm`:'S/ dados';
  $('mapInfo').textContent=`${features.length} polígonos de talhões · ${measured.length}/${stations.length} estações com chuva válida · ${dateText(a)} a ${dateText(b)}.`+(amounts.length?' Branco = menor chuva estimada, azul = maior chuva estimada.':' Não há leituras válidas de chuva nesse intervalo; talhões sem cor temática.');
 }catch(e){$('mapInfo').textContent='Mapa indisponível: '+e.message;console.warn('Mapa:',e.message);}
 finally{$('refreshMap').disabled=false;}
}
async function load(){status('Carregando dados horários...');$('load').disabled=true;try{const [a,b]=range();records=$('station').value==='virtual'?await virtualRows(a,b):await stationRows($('station').value,a,b);page=0;drawTable();paintCards();paintCharts();status(`Consulta concluída: ${records.length.toLocaleString('pt-BR')} registros.`);if(tab==='map')await paintMap()}catch(e){status('Erro: '+e.message);records=[];drawTable()}finally{$('load').disabled=false}}
function download(blob,name){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000)}
function compareWindow(year,begin,end){const parse=(txt)=>{const m=/^(\d{2})\/(\d{2})$/.exec(txt);if(!m)throw Error('Use datas no formato DD/MM');return [+m[1],+m[2]]};const [d1,m1]=parse(begin),[d2,m2]=parse(end);const a=`${year}-${String(m1).padStart(2,'0')}-${String(d1).padStart(2,'0')}`;let endYear=year;if(m2<m1||(m2===m1&&d2<d1))endYear++;const b=`${endYear}-${String(m2).padStart(2,'0')}-${String(d2).padStart(2,'0')}`;if(Number.isNaN(Date.parse(a))||Number.isNaN(Date.parse(b)))throw Error('Data do comparativo inválida');return[a,b]}
async function runCompare(){try{const begin=$('compareFrom').value.trim(),end=$('compareTo').value.trim(),ys=$('compareYears').value.trim();const years=(ys?ys.split(',').map(Number):Array.from({length:Math.min(10,Number(manifest.period_end.slice(0,4))-Number(manifest.period_start.slice(0,4))+1)},(_,i)=>Number(manifest.period_end.slice(0,4))-i)).filter(y=>Number.isInteger(y)&&y>=2010&&y<=2100).sort((a,b)=>a-b);const rows=[];for(const year of years){const[a,b]=compareWindow(year,begin,end);const start=a<manifest.period_start?manifest.period_start:a,last=b>manifest.period_end?manifest.period_end:b;const rr=start<=last?($('station').value==='virtual'?await virtualRows(start,last):await stationRows($('station').value,start,last)):[];rows.push({year,period:`${dateText(a)}–${dateText(b)}`,chuva_mm:aggregate(rr,'chuva_mm'),temp_media_c:aggregate(rr,'temp_media_c','avg'),umidade_media_pct:aggregate(rr,'umidade_media_pct','avg'),radiacao_solar_mjm2:aggregate(rr,'radiacao_solar_mjm2'),hours:rr.filter(r=>valid(r.temp_media_c)).length})}const body=$('compareBody');body.replaceChildren();for(const r of rows){const tr=document.createElement('tr');for(const k of ['year','period','chuva_mm','temp_media_c','umidade_media_pct','radiacao_solar_mjm2','hours']){const td=document.createElement('td');td.textContent=typeof r[k]==='number'?fmtNum(r[k]):r[k]??'—';tr.append(td)}body.append(tr)}$('compareInfo').textContent='Comparação da estação selecionada; totais para chuva/radiação e médias para temperatura/umidade. Ausências permanecem sem valor.';compareChart?.destroy();const metric=$('compareMetric').value;compareChart=new Chart($('chartCompare'),{type:'bar',data:{labels:rows.map(r=>String(r.year)),datasets:[{label:$('compareMetric').selectedOptions[0].text,data:rows.map(r=>r[metric]),backgroundColor:'#2171bc'}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}}}})}catch(e){$('compareInfo').textContent='Erro: '+e.message}}
// Sempre 1 XLSX horário consolidado por cliente, com uma aba auxiliar de coordenadas.
// Excel permite no máximo 1.048.576 linhas por aba; usamos partições conservadoras.
const CONSOLIDATED_COLUMNS=['Estação','ID estação','Data/hora local','Temperatura média (°C)','Temperatura mínima (°C)','Temperatura máxima (°C)','Umidade média (%)','Umidade mínima (%)','Umidade máxima (%)','Chuva (mm)','Vento médio (km/h)','Vento máximo (km/h)','Rajada (km/h)','Direção vento (°)','Radiação solar (MJ/m²)'];
function hourlyRow(st,r){return [st.nome,st.id,(r.data_hora_local||'').replace('T',' ').slice(0,16),r.temp_media_c,r.temp_min_c,r.temp_max_c,r.umidade_media_pct,r.umidade_min_pct,r.umidade_max_pct,r.chuva_mm,r.vento_medio_kmh,r.vento_max_kmh,r.rajada_kmh,r.direcao_vento_graus,r.radiacao_solar_mjm2]}
async function exportPeriodExcel(){
 const btn=$('periodExcel');btn.disabled=true;
 try{
  if(typeof XLSX==='undefined')throw Error('Biblioteca Excel indisponível. Verifique sua conexão à internet.');
  const [start,end]=range(), wb=XLSX.utils.book_new(), limit=100000;
  let sheetNumber=1,aoa=[CONSOLIDATED_COLUMNS],total=0;
  const flush=()=>{XLSX.utils.book_append_sheet(wb,XLSX.utils.aoa_to_sheet(aoa),`Horarios ${sheetNumber++}`);aoa=[CONSOLIDATED_COLUMNS]};
  for(const st of client.estacoes){
   const names=months(start,end);
   for(let i=0;i<names.length;i++){
    status(`Gerando Excel: ${st.nome} · ${i+1}/${names.length} meses...`);
    const rows=await monthRows(st.id,names[i]);
    for(const r of rows){
     const dt=r.data_hora_local?.slice(0,10);
     if(!dt||dt<start||dt>end||isOffline(r))continue;
     aoa.push(hourlyRow(st,r));total++;
     if(aoa.length>limit)flush();
    }
    // Atualiza a interface para que o navegador não pareça travado em períodos grandes.
    await new Promise(resolve=>setTimeout(resolve,0));
   }
  }
  if(aoa.length>1||sheetNumber===1)flush();
  XLSX.utils.book_append_sheet(wb,XLSX.utils.aoa_to_sheet([['Estação','ID estação','FEID','Latitude','Longitude','Cliente'],...client.estacoes.map(st=>[st.nome,st.id,st.feid,st.latitude,st.longitude,client.nome])]),'Coordenadas');
  status(`Compactando Excel do período: ${total.toLocaleString('pt-BR')} registros horários...`);
  await new Promise(resolve=>setTimeout(resolve,0));
  const buffer=XLSX.write(wb,{type:'array',bookType:'xlsx',compression:true});
  download(new Blob([buffer],{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}),`${slug}_horario_${start}_${end}.xlsx`);
  status(`Excel do período iniciado: ${total.toLocaleString('pt-BR')} horas válidas, todas as estações físicas.`);
 }catch(e){status('Erro ao preparar Excel do período: '+e.message);console.error(e)}
 finally{btn.disabled=false}
}
async function exportFullClient(){
 const btn=$('fullExcel');btn.disabled=true;
 try{
  status('Consultando Excel horário completo já preparado pelo GitHub Actions...');
  const url=`downloads/${slug}_historico_horario.xlsx`;
  const r=await fetch(url,{method:'HEAD',cache:'no-store'});
  if(!r.ok)throw Error('Histórico ainda não preparado. Execute a atualização no GitHub Actions.');
  const a=document.createElement('a');a.href=url;a.download=`${slug}_historico_horario.xlsx`;
  document.body.append(a);a.click();a.remove();
  status('Download iniciado: um Excel com todos os registros horários disponíveis e uma aba Coordenadas.');
 }catch(e){status('Erro no download do histórico: '+e.message)}finally{btn.disabled=false}
}
function stationOptions(){const selected=$('station').value||'virtual';const stations=[virtualStation(),...client.estacoes].filter(Boolean);$('station').replaceChildren();for(const s of stations){const o=document.createElement('option');o.value=s.id;o.textContent=`${s.nome} · ${s.feid}`;$('station').append(o)}$('station').value=stations.some(s=>String(s.id)===selected)?selected:String(stations[0]?.id||'')}
async function init(){if(!slug)return;try{const r=await fetch('manifest.json',{cache:'no-store'});if(!r.ok)throw Error('Dados ainda não publicados. Rode a automação.');manifest=await r.json();client=manifest.clientes.find(c=>c.slug===slug);if(!client)throw Error('Cliente não localizado');$('clientTitle').textContent=client.nome;$('stationCount').textContent=client.estacoes.length;$('dataUntil').textContent=dateText(manifest.period_end);$('dataSince').textContent=dateText(manifest.station_coverage?.[slug]?.[String(client.estacoes[0].id)]?.first || manifest.first_observation || manifest.period_start);$('lastUpdate').textContent=new Date(manifest.updated_at_utc).toLocaleString('pt-BR',{timeZone:'America/Cuiaba'});stationOptions();for(const key of ['dateFrom','dateTo']){$(key).min=manifest.period_start;$(key).max=manifest.period_end}const daysAgo=new Date(manifest.period_end+'T12:00:00Z');daysAgo.setUTCDate(daysAgo.getUTCDate()-29);$('compareYears').value=Array.from({length:Math.min(5,Number(manifest.period_end.slice(0,4))-Number(manifest.period_start.slice(0,4))+1)},(_,i)=>Number(manifest.period_end.slice(0,4))-i).reverse().join(',');$('dateFrom').value=daysAgo.toISOString().slice(0,10)<manifest.period_start?manifest.period_start:daysAgo.toISOString().slice(0,10);$('dateTo').value=manifest.period_end;const hr=document.createElement('tr');for(const [,label] of fields){const th=document.createElement('th');th.textContent=label;hr.append(th)}$('thead').append(hr);for(const t of ['dashboard','map','raw','compare'])$('btn-'+t).onclick=()=>tabSet(t);$('load').onclick=load;$('station').onchange=()=>load();$('periodExcel').onclick=exportPeriodExcel;$('fullExcel').onclick=exportFullClient;$('rawGranularity').onchange=()=>{rawMode=$('rawGranularity').value;page=0;drawTable()};$('runCompare').onclick=runCompare;$('prev').onclick=()=>{page--;drawTable()};$('next').onclick=()=>{page++;drawTable()};for(const key of ['mapDateFrom','mapDateTo']){$(key).min=manifest.period_start;$(key).max=manifest.period_end} $('mapDateFrom').value=$('dateFrom').value;$('mapDateTo').value=$('dateTo').value;$('applyMapDates').onclick=paintMap;$('refreshMap').onclick=paintMap;$('interpolate').onchange=paintMap;tabSet('dashboard');await load()}catch(e){status('Erro: '+e.message)}}init();
