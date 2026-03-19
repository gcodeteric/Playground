#!/bin/bash
cd "$(dirname "$0")"

# Activar venv
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    echo "ERRO: venv nao encontrado. Cria com: python3 -m venv venv && pip install -r requirements.txt"
    read -p "Prime Enter para sair..."
    exit 1
fi

echo ""
echo "========================================"
echo "   DASHBOARD - A ARRANCAR..."
echo "========================================"
echo ""

streamlit run dashboard/app.py --server.port 8501 --server.headless true
