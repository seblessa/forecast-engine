# Forecast Engine

Servidor REST para executar previsões com o
[`chronos_forecaster`](https://github.com/seblessa/chronos-forecaster). O processo
mantém os modelos carregados entre pedidos com a mesma configuração, evitando
recarregá-los em cada chamada.

## Requisitos

- Python 3.10–3.13
- [`uv`](https://docs.astral.sh/uv/) (recomendado) ou `pip`
- Espaço em disco e memória suficientes para o modelo Chronos escolhido

Na primeira previsão, o `chronos_forecaster` descarrega o modelo da Hugging Face.
Essa chamada demora mais; as seguintes reutilizam o modelo enquanto o servidor
estiver ligado.

## Instalação e arranque

Com `uv`:

```bash
uv sync
uv run python server.py
```

Com `pip`:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .
python server.py
```

O servidor escuta em todas as interfaces na porta `8000`, ficando acessível na
rede local. É possível alterar estes valores:

```bash
HOST=127.0.0.1 PORT=9000 uv run python server.py
```

- Health check: `GET http://localhost:8000/health`
- Previsão: `POST http://localhost:8000/forecast`
- Documentação interativa: `http://localhost:8000/docs`
- Especificação OpenAPI: `http://localhost:8000/openapi.json`

## Fazer uma previsão

```bash
curl -X POST http://localhost:8000/forecast \
  -H 'Content-Type: application/json' \
  -d '{
    "data": [
      {"date": "2025-01-01T00:00:00", "target": 84.2},
      {"date": "2025-01-01T01:00:00", "target": 86.1},
      {"date": "2025-01-01T02:00:00", "target": 85.7}
    ],
    "forecast_horizon": 3,
    "frequency": "h",
    "engine": "chronos2"
  }'
```

Resposta:

```json
{
  "predictions": [
    {
      "date": "2025-01-01T03:00:00.000",
      "target_predicted": 86.4,
      "lower_bound": 82.1,
      "upper_bound": 90.8
    }
  ]
}
```

O corpo aceita ainda:

- `datetime_col` e `target_col` (defaults: `date` e `target`)
- `item_id_col` para várias séries
- `random_state`
- `past_covariates` e `future_covariates` com `engine: "chronos2"`

O schema completo e exemplos podem ser consultados em `/docs`. O serviço não
inclui autenticação nem TLS e deve permanecer numa rede de confiança; não o
exponhas diretamente à Internet.

## Desenvolvimento

```bash
uv sync --group dev
uv run pytest
```

As instruções para agentes implementadores estão em [AGENTS.md](AGENTS.md). A
skill para agentes que consomem este serviço está em
[`skills/chronos-forecast-api/SKILL.md`](skills/chronos-forecast-api/SKILL.md).
