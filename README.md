# Portal Agrometeorológico V8 — Correção das bordas

**Correção principal:** o código anterior não havia chegado ao repositório publicado: `buscar_talhoes.py` estava ausente. Esta versão consulta as bordas com os mesmos parâmetros do código de telemetria que funciona:

1. `GET /asset/field/?rootAsset=<grower_id>&season=<season_id>`.
2. Alternativa, se a consulta direta não retornar fields utilizáveis: `GET /asset/?season=<season_id>` e seleção pela árvore do grower.
3. `GET /fieldborder/?assetID=<field_id>&seasonID=<season_id>&format=json`.
4. Salva `site/maps/<cliente>.geojson` quando há polígonos; salva sempre o diagnóstico em `site/maps/status.json`. Não mistura polígonos de safras diferentes.

Safras tentadas por ordem: **1087, 1084, 1083, 1088**. Se a safra atual não retornar geometrias, o script tenta a anterior. O número de talhões encontrados é mostrado nos logs. O resultado efetivo depende dos IDs e da autorização da API.

**Na página:** `Fazenda inteira · estimativa · INTERPOLADO` passa a ser a primeira opção e vem selecionada inicialmente. O mapa de chuva V7 já desenha os polígonos sem tiles OpenStreetMap: branco para menor chuva estimada, azul para maior. As versões antigas no navegador não possuem essa lógica; confirme **Portal V8** no rodapé.

**Importante:** não exclua a pasta `site/data`, `site/manifest.json`, `.git` nem os GeoJSON anteriores. Copie os arquivos desta pasta sobre o projeto conectado ao GitHub. Não copie nenhum arquivo com tokens/senhas. Faça `git add` apenas de código e de mapas explicitamente revisados; **não use `git add -A`**.

### Arquivos a enviar

```powershell
git status
git add atualizar.py buscar_talhoes.py gerar_downloads.py offline_utils.py requirements.txt
git add site/app.js site/style.css site/tessaro.html site/fenix.html
git add .github/workflows/publicar.yml
git add README.md
git commit -m "Portal V8 bordas por safra e fazenda interpolada padrao"
git pull --rebase origin main
git push origin main
```

Se `git pull --rebase` falhar por alterações pendentes, conflitos ou `rebase` em andamento, não force o push; guarde ou integre as alterações antes de continuar. Como o GitHub Actions também cria commits de dados, há risco de divergência. **Nunca faça `git push --force` ou `git reset --hard`.**

### Verificação no GitHub Actions

Abra a última execução > **Consultar bordaduras do grower**. Veja mensagens por cliente e safra, por exemplo `Tessaro: safra 1087 => X talhões, Y polígonos`. No navegador abra `https://guilhermecaetano0033.github.io/portal-estacoes-farmers-edge/maps/status.json` (ou ajuste com o endereço do seu repositório) e procure o status do cliente. A publicação pode ocorrer após o job terminar.

**Nenhuma chamada real à API com credenciais foi realizada nos testes locais.** Uma saída vazia na API deve ser tratada como diagnóstico, não como mapa concluído.
