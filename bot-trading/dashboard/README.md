# Dashboard — Bot Trading Monitor

## Arrancar
```bash
cd dashboard
pip install -r requirements.txt
streamlit run app.py
```

## URL
http://localhost:8501

## Notas
- Refresca automaticamente a cada 5 segundos
- 100% read-only — não interfere com o bot
- Funciona mesmo com o bot parado (mostra últimos dados)
- Corre em paralelo com main.py em terminal separado
