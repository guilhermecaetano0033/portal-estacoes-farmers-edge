# Portal Agrometeorológico V7 — Tessaro e Fazenda Fênix

Dashboard responsivo alimentado por histórico horário do FarmCommand. Credenciais exclusivamente no GitHub Actions Secrets. O site GitHub Pages é **público**; a publicação das bordas dos talhões e dos dados de chuva depende de autorização para compartilhar essas informações.

## Melhorias V7

### Mapa de chuva por talhão
- **Período próprio** (data inicial e final) dentro da aba Mapa de chuva, independente dos filtros do Dashboard.
- Identifica os talhões do `grower_id` via `/asset/?season=...` e recupera as geometrias por `/fieldborder/?assetID={id}&format=json`. Aceita Polygon, MultiPolygon e FeatureCollection; não consulta talhões de outros growers.
- Calcula a chuva acumulada **medida por estação** no período, descartando horas classificadas como offline. Em cada talhão faz uma amostragem de pontos internos e estima a precipitação via IDW (inverso do quadrado da distância).
- **Pinta o polígono inteiro do talhão**. Branco indica menor chuva estimada entre os talhões, azul mais escuro indica maior. A legenda informa os extremos em milímetros. Se todos tiverem chuva zero, todos ficam brancos. Áreas sem leitura válida ficam neutras, não falsas áreas secas.
- Ao tocar/clicar no talhão, abre o nome e a estimativa em mm. As estações físicas são marcadas com acumulados reais e cobertura (horas válidas e offline).
- Não carrega blocos do OpenStreetMap, evitando os quadrados incompletos mostrados antes. Usa geometria agrícola sobre fundo neutro.
- **Importante:** IDW é estimativa e não medição em cada talhão. Para mapas comparáveis, use períodos com cobertura adequada da rede. Mapas não são perícia meteorológica.

### Offline e Excel
- Registro horário é **offline** quando nenhum campo de temperatura (média/mínima/máxima) **e** nenhum campo de umidade (média/mínima/máxima) possui valor numérico válido. Zero medido não equivale a dado ausente.
- As novas linhas guardam `offline: true/false`; dados de anos anteriores são avaliados pela mesma regra na leitura, sem precisar refazer toda a coleta.
- O portal mostra a situação na tabela horária. **Excel horário e diário** (ZIP completo pré-gerado no GitHub Actions, Excel individual e Excel consolidado por período), bem como CSV, **omitem essas horas offline**. Agregação diária utiliza somente horários válidos.
- Registros offline permanecem armazenados no JSON histórico para auditoria; não são transformados em chuva zero. É uma regra de qualidade baseada em medições, não diagnóstico definitivo da conectividade da estação.

## Instalando na pasta já conectada ao GitHub

1. Faça um backup da pasta atual. Copie o conteúdo deste projeto sobre os arquivos de código existentes.
2. **Não apague** `.git/`, `site/data/`, `site/manifest.json` ou eventuais `site/maps/*.geojson` que já foram coletados. Não use `git add -A` sobre o banco histórico ao atualizar a interface.
3. Confirme com `git status` que **não existe rebase/conflito em andamento**. Se houver, resolva isso antes.
4. Adicione SOMENTE os arquivos do código:

```powershell
git add atualizar.py buscar_talhoes.py gerar_downloads.py offline_utils.py
git add site/app.js site/style.css site/tessaro.html site/fenix.html
git add .github/workflows/publicar.yml README.md tests/test_v7.py
git commit -m "Portal V7 mapa de chuva por talhao e filtro offline"
git pull --rebase origin main
git push origin main
```

Se `git pull --rebase` gerar `CONFLICT`, **pare** e resolva antes de dar `push`. Não use `git push --force` nem remova dados históricos. O commit de dados automático do GitHub Actions pode modificar `site/data/` e `site/manifest.json` entre duas atualizações.

## Diagnóstico quando o mapa não mostra talhões

Abra **Actions → Atualizar estações e publicar portal → Consultar bordaduras do grower**. O log agora informa, por grower, quantos assets foram retornados nas safras consultadas, quantos talhões foram identificados e quantas geometrias reais vieram do `fieldborder`.

Growers configurados no `clientes.json`:
- Tessaro: `92088`.
- Fazenda Fênix: `4583088`.

Se aparecer `0 talhões` ou `0 geometrias`, a API não forneceu limites suficientes para desenhar o mapa. Confira IDs, estrutura de parent dos assets, `season` e permissão da conta FarmCommand. O programa **não inventa** bordas de talhões nem substitui um GeoJSON existente por um arquivo vazio.

## Testes

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
node --check site/app.js
```

Há testes para o critério de offline, filtragem de registros antigos no Excel, consulta hierárquica por grower, geometrias GeoJSON e dados ausentes.

**Limite de validação:** estes testes são locais e usam amostras sintéticas. Precisamos conferir as bordas retornadas pela API real e a interface publicada após o primeiro workflow da V7.
