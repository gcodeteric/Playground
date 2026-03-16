# Bot de Trading Autonomo — Grid Engine com Estrategia Kotegawa

Bot de trading 100% autonomo em Python que opera sem intervencao humana via Interactive Brokers.

## Arquitectura

O bot combina a **estrategia Kotegawa** (desvio da SMA25 como filtro de entrada) com um **motor de grid trading** para execucao automatica em multiplos niveis.

### Modulos

| Modulo | Ficheiro | Funcao |
|--------|----------|--------|
| Data Feed | `src/data_feed.py` | Conexao IB + dados de mercado + indicadores |
| Signal Engine | `src/signal_engine.py` | Regime detection + sinal Kotegawa |
| Grid Engine | `src/grid_engine.py` | Logica de grid autonoma |
| Risk Manager | `src/risk_manager.py` | Gestao de risco + Half-Kelly sizing |
| Execution | `src/execution.py` | Ordens bracket no IB |
| Logger | `src/logger.py` | Logs imutaveis + alertas Telegram |

### Ciclo Autonomo

```
LOOP INFINITO:
  1. Verificar conexao IB (reconnect automatico)
  2. Obter dados de mercado (barras diarias)
  3. Calcular regime (BULL/BEAR/SIDEWAYS)
  4. Calcular sinal Kotegawa (deviation SMA25 + confirmacoes)
  5. SE sinal valido E risco ok → Criar grid
  6. Monitorizar grids ativas (compras, vendas, stops)
  7. Verificar limites de risco (kill switches)
  8. Persistir estado
  9. Dormir ate proximo ciclo
```

---

## Pre-requisitos

- **Python 3.10+**
- **IB Gateway** ou **TWS** (Trader Workstation) instalado e configurado
  - Descarregar: https://www.interactivebrokers.com/en/trading/ibgateway-stable.php
  - Activar API: Configuration > API > Settings > Enable ActiveX and Socket Clients
  - Desmarcar "Read-Only API"
- **Conta IB** (paper trading ou real)
- **Bot Telegram** (opcional, para alertas)
  - Criar bot via @BotFather no Telegram
  - Obter o token e o chat_id

---

## Instalacao

```bash
# 1. Clonar o repositorio
cd bot-trading

# 2. Criar ambiente virtual
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variaveis de ambiente
cp .env.example .env
# Editar .env com as tuas credenciais
```

---

## Configuracao do .env

```bash
# === MODO DE OPERACAO ===
PAPER_TRADING=true          # SEMPRE true para comecar
USE_GATEWAY=false           # true=IB Gateway, false=TWS

# === Interactive Brokers ===
IB_HOST=127.0.0.1
IB_PORT=                    # vazio = auto
# auto => paper+tws=7497 | paper+gateway=4002 | live+tws=7496 | live+gateway=4001
IB_CLIENT_ID=1

# === Telegram (opcional) ===
TELEGRAM_BOT_TOKEN=<token do @BotFather>
TELEGRAM_CHAT_ID=<chat_id>

# === Risco ===
RISK_PER_LEVEL=0.01         # 1% do capital por nivel
STOP_ATR_MULT=1.0           # stop-loss = 1x ATR14
TP_ATR_MULT=2.5             # take-profit = 2.5x ATR14
DAILY_LOSS_LIMIT=0.03       # 3% perda diaria -> pausa
WEEKLY_LOSS_LIMIT=0.06      # 6% perda semanal -> pausa
MONTHLY_DD_LIMIT=0.10       # 10% drawdown mensal -> kill switch

# === Grid ===
MAX_POSITIONS=8
MAX_GRIDS=3
MIN_RR=2.5
CYCLE_INTERVAL_SECONDS=300
```

---

## Configuracao do IB Gateway

1. Abrir IB Gateway / TWS
2. Login com conta paper trading
3. Ir a **Configuration > API > Settings**:
   - Activar "Enable ActiveX and Socket Clients"
   - Gateway: 4002 (paper) ou 4001 (live)
   - TWS: 7497 (paper) ou 7496 (live)
   - Desmarcar "Read-Only API"
   - Trusted IPs: 127.0.0.1
4. Ir a **Configuration > API > Precautions**:
   - Desmarcar todos os avisos (para operacao autonoma)

---

## Como Arrancar

### Paper Trading (RECOMENDADO para comecar)

```bash
# 1. Garantir que IB Gateway/TWS esta a correr na porta esperada
# 2. Garantir que PAPER_TRADING=true no .env
# 3. Arrancar o bot
python main.py
```

O bot vai:
- Validar Risk of Ruin no arranque (recusa se > 1%)
- Mostrar banner "MODO: PAPER TRADING"
- Conectar ao IB Gateway
- Iniciar o ciclo autonomo

### Parar o Bot

- `Ctrl+C` — paragem graceful (cancela ordens pendentes, persiste estado)
- O bot pode ser reiniciado a qualquer momento — retoma estado de `data/grids_state.json`

---

## Monitorizar

### Via Telegram
Todos os eventos autonomos geram alertas:
- Nova grid aberta
- Compra/venda executada
- Stop-loss atingido
- Kill switch activado
- Mudanca de regime
- Resumo diario as 23:00

### Via Logs
```bash
# Logs na consola com nivel configuravel (LOG_LEVEL no .env)
# Trades registados em data/trades_log.json
# Metricas em data/metrics.json
# Estado das grids em data/grids_state.json
```

---

## Testes

```bash
# Correr todos os testes
pytest tests/ -v

# Correr testes de um modulo especifico
pytest tests/test_signal_engine.py -v
pytest tests/test_risk_manager.py -v

# Com cobertura
pytest tests/ --cov=src --cov-report=term-missing
```

---

## Gestao de Risco

### Regras de Ferro (NUNCA violadas)
1. **Stop-loss em CADA ordem** — sem excepcao
2. **ZERO averaging down** — nunca comprar mais num nivel em perda
3. **PAPER_TRADING=true** por defeito
4. **Kill switch a 10%** drawdown mensal — para tudo
5. **Risk of Ruin < 0.1%** — validado no arranque

### Limites Automaticos
| Limite | Valor | Accao |
|--------|-------|-------|
| Perda diaria | 3% | Pausa automatica |
| Perda semanal | 6% | Pausa automatica |
| Drawdown mensal | 10% | Kill switch — para tudo |

### Position Sizing
- Half-Kelly Criterion com cap de 5%
- Risco por nivel: maximo 1% do capital

---

## Passar para Conta Real

**AVISO: Trading envolve risco significativo de perda de capital. Apenas operar com capital que se pode perder.**

1. Verificar que paper trading correu **30+ minutos sem erros**
2. Verificar que pelo menos **1 grid foi aberta e gerida** autonomamente
3. Verificar que **alertas Telegram** funcionam
4. Verificar que **estado persiste** apos reinicio
5. Alterar no `.env`:
   ```
   PAPER_TRADING=false
   USE_GATEWAY=false
   # ou USE_GATEWAY=true para Gateway
   IB_PORT=
   ```
6. Comecar com **25% do capital** disponivel
7. Monitorizar as **primeiras 24h manualmente**
8. So escalar capital apos **100+ trades** em conta real

---

## FAQ / Troubleshooting

**O bot nao conecta ao IB:**
- Verificar que IB Gateway/TWS esta a correr
- Verificar porta (Gateway: 4002/4001, TWS: 7497/7496)
- Verificar que API esta activada nas Settings
- Verificar que 127.0.0.1 esta nos Trusted IPs

**O bot recusa arrancar (Risk of Ruin):**
- Os parametros de risco actuais resultam em Risk of Ruin > 1%
- Reduzir RISK_PER_LEVEL ou ajustar outros parametros

**Alertas Telegram nao chegam:**
- Verificar TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID no .env
- Verificar que o bot foi iniciado (enviar /start ao bot)
- Verificar que o chat_id esta correcto

**Estado corrompido (grids_state.json):**
- O bot tenta reconstruir estado a partir das posicoes reais no IB
- Se falhar, renomear o ficheiro e reiniciar (comecar limpo)

**Bot crashou — como retomar?**
- Simplesmente reiniciar: `python main.py`
- O bot le `data/grids_state.json` e retoma o estado anterior

---

## Estrutura do Projeto

```
bot-trading/
├── .env.example                    # Template de variaveis de ambiente
├── .gitignore                      # .env, __pycache__, data/*.json
├── config.py                       # Configuracao centralizada (pydantic)
├── main.py                         # Entry point — loop autonomo
├── requirements.txt                # Dependencias Python
├── context.md                      # Estado do projeto
├── EXTRACTED_PARAMS.md             # Parametros extraidos da investigacao
├── README.md                       # Este ficheiro
├── src/
│   ├── __init__.py
│   ├── data_feed.py                # Conexao IB + indicadores
│   ├── grid_engine.py              # Grid autonoma
│   ├── signal_engine.py            # Kotegawa + regime detection
│   ├── risk_manager.py             # Gestao de risco
│   ├── execution.py                # Ordens IB
│   └── logger.py                   # Logs + Telegram
├── tests/
│   ├── test_data_feed.py
│   ├── test_grid_engine.py
│   ├── test_signal_engine.py
│   ├── test_risk_manager.py
│   ├── test_execution.py
│   ├── test_logger.py
│   └── test_integration.py
├── data/
│   ├── grids_state.json            # Estado persistente das grids
│   ├── trades_log.json             # Log imutavel de trades
│   └── metrics.json                # Metricas de performance
└── research/                       # Investigacao (5 ficheiros .md)
```

---

## Licenca

Uso pessoal. Nao constitui aconselhamento financeiro.
