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
echo "   A ARRANCAR BOT + DASHBOARD"
echo "========================================"
echo ""

# Limpar locks de sessoes anteriores
rm -f data/bot.instance.lock
rm -f /tmp/bot-trading-instance-locks/*.lock 2>/dev/null
echo "Locks anteriores removidos."

# Abrir dashboard numa janela separada do Terminal
open -a Terminal "$(pwd)/start_dashboard.command"

# Aguardar 3 segundos para o dashboard arrancar
sleep 3

# Abrir browser
open http://localhost:8501

# Arrancar bot nesta janela
echo "A arrancar bot..."
echo ""
python main.py
