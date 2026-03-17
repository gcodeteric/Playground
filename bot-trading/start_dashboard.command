#!/bin/bash
cd "$(dirname "$0")"
echo "📦 Instalando dependências..."
python3 -m pip install -r requirements.txt --user plotly streamlit pandas numpy ta-lib
echo "🚀 Dashboard pronto!"
streamlit run dashboard/app.py --server.port 8501 --server.headless=true
