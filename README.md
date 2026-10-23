# Portal de Dados Horários — Farmers Edge

Dois portais independentes de consulta e exportação de observações **horárias** das estações meteorológicas descritas em `clientes.json`.

## Estrutura e links

- `site/tessaro.html` — Tessaro (8 estações)
- `site/fenix.html` — Fazenda Fênix (10 estações)
- `site/index.html` — página inicial
- `atualizar.py` — coleta server-to-server, nunca exposto como serviço ao visitante
- `.github/workflows/publicar.yml` — atualização automática e implantação GitHub Pages

O navegador acessa apenas JSONs estáticos gerados previamente. **As credenciais não chegam ao navegador.** Os downloads de CSV/ZIP são gerados no próprio navegador, somente com os dados selecionados.

## Atenção: confidencialidade

**O GitHub Pages padrão não implementa controle de acesso por cliente.** Todas as páginas e arquivos JSON publicados são acessíveis a quem souber ou descobrir a URL, inclusive ambos os clientes. Links diferentes não protegem a informação. Usar apenas se houver autorização para publicar esses dados. Para acesso realmente exclusivo por cliente, hospedar atrás de autenticação e autorização por cliente (ex.: backend privado + Cloudflare Access ou serviço equivalente), com storage segregado.

## Publicar no GitHub

1. Crie um repositório **sem colocar credenciais ou outros códigos legados**; suba o conteúdo desta pasta para a raiz. Os scripts de exemplo enviados não devem ir ao repositório.
2. Em **Settings → Secrets and variables → Actions → Secrets**, configure **`FARM_USER` e `FARM_PASS`** (login legado mostrado nos seus arquivos) **ou `FARM_TOKEN`** (token de API permitido). **Jamais** armazene credenciais no JavaScript/HTML ou `clientes.json`.
3. Se usar `FARM_TOKEN`, configure a variável `FARM_TOKEN_SCHEME` como `Token` (padrão) ou `Bearer`, de acordo com a autenticação realmente adotada pela sua conta.
4. Em **Settings → Pages → Build and deployment**, selecione **GitHub Actions**.
5. Em **Actions → Atualizar estações e publicar portal → Run workflow**, execute manualmente uma vez. Verifique o log; uma falha de autenticação ou de API não publicará dados novos.
6. Links, após a publicação: `https://SEU_USUARIO.github.io/NOME_REPOSITORIO/tessaro.html` e `/fenix.html`.

## Atualização

Agendada para **07:17**, timezone `America/Cuiaba` (MT), todos os dias, sujeita a atrasos da fila do GitHub Actions. Exporta até **ontem** (dia completo), com histórico inicial desde **2026-09-01**. Ajuste `BACKFILL_START` no workflow se quiser começar antes. Meses históricos completos são reaproveitados, exceto últimos cinco dias que são buscados novamente.

O código consulta `/weather/{id}/historical-summary-hourly/` em lotes mensais. Para cada observação, preserva valores `null`, sem converter chuva ausente em zero. Quando a API envia tanto o campo `total_precip_mm` quanto uma estrutura `rainfall_mm.sum`, usa o primeiro valor válido. **Amostras ausentes não são inventadas**. O CSV apresenta dados brutos horários, não consolidações diárias.

## Executar localmente

```bash
python -m pip install -r requirements.txt
# Configure FARM_USER e FARM_PASS, ou FARM_TOKEN, em variáveis do ambiente.
python atualizar.py --from 2026-09-01 --to 2026-10-22
python -m http.server 8000 --directory site
```

Abra `http://localhost:8000/tessaro.html`. O comando de exportação local consulta a API de verdade: não executa sem credenciais válidas. Não é possível conferir esse login a partir deste ambiente.

## Observações técnicas

- `clientes.json` contém apenas ID, nome e código das estações; os contatos dos cadastros originais foram eliminados.
- `site/manifest.json` e `site/data/...` são criados na primeira atualização; não comite credenciais, cookies ou respostas internas completas.
- O ZIP usa o formato padrão **STORE** (sem compressão) para funcionar sem bibliotecas de terceiros. Contém CSVs UTF-8 com BOM e separador `;` para Excel em português.
- Dados antigos fora do recorte inicial não aparecem até você ajustar `BACKFILL_START` e executar novamente.
- O fluxo inicial foi elaborado segundo exemplos de endpoints e autenticação dos scripts fornecidos, mas a autorização efetiva da sua conta e a compatibilidade da autenticação precisam ser validadas na primeira execução.
