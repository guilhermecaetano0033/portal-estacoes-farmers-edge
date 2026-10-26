# Portal agrometeorológico v2 — Tessaro e Fazenda Fênix

Portal estático responsivo, alimentado pela API horária do FarmCommand por meio de `POST /token-login/` no GitHub Actions. **Não coloque senha, token, cookies, nem arquivos legados com credenciais no repositório.**

## Novidades

- Abas **Dashboard**, **Mapa de Chuva** e **Dados Brutos** em cada portal.
- Gráficos de precipitação diária, temperatura média diária, umidade diária, rajadas máximas e direção média do vento. O gráfico de direção usa graus e os indicadores usam média vetorial.
- Mapa com estações nas coordenadas dos JSONs. Chuva acumulada por estação e opção de **interpolação indicativa IDW** (não constitui medição por talhão e não utiliza bordaduras). A interpolação é somente uma aproximação local; não utilizar para perícia.
- Seleção de estação e período, tabela horária paginada, exportação CSV individual, ZIP individual ou ZIP com todas as estações do cliente. A geração de ZIP acontece no navegador; períodos muito longos podem exigir memória considerável no celular.
- Campos ausentes (`null`) continuam ausentes; não são convertidos em zero. A direção média do vento e a rajada são extraídas também dos campos planos da API (`diravgWindDirection` e `maxWindGust`).
- Layout responsivo para smartphone e desktop. Os gráficos usam Chart.js, o mapa Leaflet/OpenStreetMap (conexão à internet necessária).

## Instalação (no mesmo repositório)

Substitua **todo o conteúdo do projeto**, exceto o diretório oculto `.git/`. Não é necessário refazer `git init`, criar outro repositório ou configurar novamente os Secrets.

```powershell
git add -A
git commit -m "Novo portal dashboards mapas e historico"
git push origin main
```

Depois confira `Actions` e a publicação do GitHub Pages. Os endereços permanecem:

- `https://guilhermecaetano0033.github.io/portal-estacoes-farmers-edge/tessaro.html`
- `https://guilhermecaetano0033.github.io/portal-estacoes-farmers-edge/fenix.html`

## Histórico desde as primeiras observações

O histórico anterior à versão inicial **não aparece automaticamente de uma só vez**. O workflow busca inicialmente os **12 meses mais recentes** e, em cada execução, amplia retrospectivamente mais **12 meses**, sem baixar novamente os meses já gravados. Assim, a coleta não precisa executar todos os anos em uma única ação. Pode rodar manualmente repetidas vezes em Actions para acelerar o preenchimento retroativo. `BACKFILL_START=2010-01-01` é um **limite de busca configurável**, não uma data de instalação detectada. Se existirem dados antes de 2010, diminua o limite. O início real depende do que a API retornar. Os dados são armazenados em `site/data` **e commitados ao repositório** pelo workflow antes da publicação; o armazenamento é persistente entre execuções. O repositório é público: **todos os JSONs publicados também são públicos**.

`BACKFILL_MONTHS` (no YAML) ajusta quantos meses anteriores tenta acrescentar a cada execução. Muitas estações/anos poderão esbarrar em limites da API, tempo de Actions, limite de hospedagem, tamanho do repositório ou banda do Pages. O script interrompe a publicação caso uma consulta falhe, para evitar atualização parcial. Consulte logs do workflow.

## Renomear estação permanentemente

A página tem botão **Renomear estação**, que altera o nome **apenas na sessão atual** e baixa um pequeno JSON de referência. Para persistir globalmente (inclusive em outros aparelhos e nas exportações futuras), o proprietário deve abrir **Actions → Renomear estação permanentemente → Run workflow**, preencher cliente, ID e novo nome, e executar. Esse workflow atualiza `clientes.json` por commit. Depois execute **Atualizar estações e publicar portal** para refletir o nome em todas as páginas. Não é necessário editar JSON manualmente. **Um site estático público não pode gravar no repositório de forma segura sem autenticação administrativa.** Nunca inclua token de escrita do GitHub no JavaScript público.

## Segurança

`FARM_USER` e `FARM_PASS` permanecem como GitHub Actions Secrets. O token da API é obtido em tempo de execução no runner e não é incluído nos arquivos de site. Não suba `farm_auth.py` legado que contenha senha no código. Como o repositório já é público, verifique os commits anteriores, os logs de Actions e a autorização de divulgação dos dados dos clientes.

## Testes

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
node --check site/app.js
```
