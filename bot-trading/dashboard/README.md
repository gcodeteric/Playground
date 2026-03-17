# Dashboard — Bot Trading Monitor (PAPER)

## Arrancar
```bash
cd dashboard
pip install -r requirements.txt
streamlit run app.py
```

## URL
http://localhost:8501

## Notas
- PAPER MODE explícito em toda a UI
- Refresh manual e auto-refresh configurável
- Command channel local em `data/commands/`
- O dashboard é observável por defeito
- As ações apenas emitem comandos seguros (`pause`, `resume`, `reconcile_now`, `export_snapshot`)
- Funciona mesmo com o bot parado (mostra últimos dados)
- Corre em paralelo com main.py em terminal separado
- Usa apenas dados reais encontrados em `data/`
