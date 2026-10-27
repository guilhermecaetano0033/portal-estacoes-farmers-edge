# Portal Agrometeorológico V9 — nomes definitivos e Excel direto

## Nomes permanentes
Os nomes de **18 estações físicas** foram atualizados em `clientes.json`. IDs, FEIDs, coordenadas e vínculo aos dois growers não foram alterados. `site/manifest.json` é gerado a partir desse cadastro durante a execução do GitHub Actions, propagando os nomes para as páginas.

- **Tessaro:** FSE03, FSE04, FSE05, FSE07, FSE09, FSE11, FSE12, FSE13.
- **Fazenda Fênix:** FJG01, FJG02, FUA01, FUA07, FUA08, FRO01, FRO02, FEX01, FEX02, FEX03.
- `Estação Aurora 8` (ID 81256) foi mapeada para `FUA08`, correspondente ao nome fornecido como "Estação Aura 8".

O botão de renomear foi removido das páginas. A estação virtual `Fazenda inteira · estimativa` permanece como opção padrão, não participa dos Excel e não representa sensor físico.

## Exportações

Na aba **Dados brutos**, somente dois botões:

1. **Baixar Excel do período:** um XLSX gerado no navegador com todas as estações físicas e somente os registros horários do intervalo selecionado; contém abas `Horarios 1`, `Horarios 2` ... (quando necessário) e `Coordenadas`.
2. **Baixar Excel do histórico completo:** download de `site/downloads/<slug>_historico_horario.xlsx`, gerado automaticamente pelo workflow em `gerar_downloads.py` depois de coletar dados. Não monta históricos gigantes no celular.

As planilhas excluem horas sem quaisquer medições de temperatura e umidade (`offline_utils.is_offline`), mas nunca alteram a base original. Dados horários locais, chuva, temperatura, umidade, vento, rajada e radiação solar são preservados. A visualização diária na página continua disponível, sem gerar outro XLSX diário.

O Excel completo contém **o histórico já coletado**, não períodos que ainda não foram importados. Use `full_history` no workflow quando necessário, observando os limites do GitHub Actions/Pages.

## Instalação segura

**Não apague** `.git`, `site/data`, `site/manifest.json` nem `site/maps`. Copie/substitua somente os arquivos de código e `clientes.json`. Envie ao Git somente:

```powershell
git status
git add clientes.json gerar_downloads.py site/app.js site/tessaro.html site/fenix.html .github/workflows/publicar.yml README.md tests/test_v9.py
git commit -m "Portal V9 nomes definitivos e Excel horario direto"
git pull --rebase origin main
git push origin main
```

Se `git pull --rebase` apresentar `CONFLICT` ou alterações pendentes, **não use `push --force`**. O GitHub Actions atualiza o histórico por commits automatizados e deve ser sincronizado sem sobrescrever a base.

Após o workflow ficar verde, confira o rodapé `Portal V9`, os nomes no seletor e a etapa **Gerar Excel horário completo no servidor**. O histórico completo será publicado em `downloads/<slug>_historico_horario.xlsx`.

## Mapa de chuva

A V9 não altera `buscar_talhoes.py` nem a lógica geográfica do `site/app.js` anterior, exceto o código de exportação e renomeação. O mapa por talhões da V8 deve continuar funcionando. A ausência de fundo geográfico não interfere na interpretação dos polígonos.
