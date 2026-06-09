# Dashboard — Direção ENAMED (Captação da Live)

Relatório de acompanhamento da captação da Live Direção ENAMED (Aristo).
Atualiza sozinho todo dia às **07:00 BRT** via GitHub Action, lendo a planilha
de acompanhamento e republicando no GitHub Pages.

- **Link:** https://vianapatrick15-max.github.io/direcao-enamed-dashboard/
- **Fonte:** planilha `DASH_ENAMED` — abas `DADOS_GERENCIADOR` (Meta) e `DADOS_HUBSPOT` (inscrições).
- **Definição:** inscrito por anúncio = UTM da campanha contém `direcaoenamed`.

## Como funciona
- `refresh.py` lê a planilha, calcula os indicadores e gera `data.json` + `index.html`
  (auto-contido, gráficos em SVG nativo, sem dependências externas).
- O Action roda `refresh.py` no cron e commita o resultado; o Pages serve o `index.html`.

## Editar metas
As metas (CPL, verba, leads, data do evento) ficam no topo do `refresh.py`.

## Rodar local
```
pip install -r requirements.txt
python refresh.py   # usa a credencial local da service account
```
