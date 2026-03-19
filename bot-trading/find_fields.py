import pygetwindow as gw
import pyautogui
import time

# Aguardar 5 segundos para teres tempo de abrir o TWS
print("Tens 5 segundos para garantir que a janela de login do TWS está visível...")
time.sleep(5)

# Encontrar a janela
windows = gw.getWindowsWithTitle("Iniciar sessão")
if not windows:
    print("Janela 'Iniciar sessão' não encontrada.")
else:
    win = windows[0]
    print(f"Janela: {win.title}")
    print(f"Posição: left={win.left}, top={win.top}")
    print(f"Tamanho: width={win.width}, height={win.height}")
    print()

    # Mostrar pontos de referência
    for pct in [0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]:
        y = win.top + int(win.height * pct)
        x = win.left + win.width // 2
        print(f"  {int(pct*100)}% altura → coordenada ({x}, {y})")

    # Mover o rato por cada posição para veres onde cai
    print()
    print("Vou mover o rato por cada posição. Observa onde cai o cursor.")
    time.sleep(2)
    for pct in [0.30, 0.35, 0.40, 0.45, 0.50, 0.55]:
        y = win.top + int(win.height * pct)
        x = win.left + win.width // 2
        pyautogui.moveTo(x, y, duration=0.5)
        print(f"  Rato em {int(pct*100)}% → ({x}, {y})")
        time.sleep(1)