"""
tws_autologin.py
Auto-login para o TWS Interactive Brokers.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

try:
    import pyautogui
    import pygetwindow as gw
except ImportError:
    print("ERRO: venv\\Scripts\\pip install pyautogui pygetwindow pillow")
    sys.exit(1)

BASE_DIR = Path(__file__).parent
TWS_PATH = Path("C:/Jts/tws.exe")
CREDENTIALS_FILE = BASE_DIR / "tws_credentials.json"
LOGGED_IN_CONFIRMATION_SECONDS = 30
LOGGED_IN_CONFIRMATION_POLL_SECONDS = 2
pyautogui.PAUSE = 0.6
pyautogui.FAILSAFE = True


def parse_args():
    parser = argparse.ArgumentParser(
        description="Auto-login para o TWS Interactive Brokers.",
    )
    parser.add_argument(
        "--skip-launch",
        action="store_true",
        help="Nao tenta abrir o TWS; assume que foi iniciado externamente.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Timeout em segundos para detectar a janela de login.",
    )
    return parser.parse_args()


def load_credentials():
    if not CREDENTIALS_FILE.exists():
        print(f"ERRO: ficheiro de credenciais nao encontrado: {CREDENTIALS_FILE}")
        sys.exit(1)
    try:
        creds = json.loads(CREDENTIALS_FILE.read_text(encoding="utf-8"))
        return creds["username"], creds["password"]
    except (json.JSONDecodeError, KeyError) as exc:
        print(f"ERRO: credenciais invalidas em {CREDENTIALS_FILE}: {exc}")
        sys.exit(1)


def find_login_windows():
    windows = []
    for title in ("Iniciar sessão", "Login"):
        windows.extend(gw.getWindowsWithTitle(title))
    return windows


def find_tws_windows():
    return [
        w for w in gw.getAllWindows()
        if "TWS" in w.title or "Trader Workstation" in w.title
    ]


def wait_for_login_window(timeout=60):
    print("A aguardar janela de login...")
    for _ in range(timeout):
        windows = find_login_windows()
        if windows:
            print("Janela de login detectada.")
            return windows[0]
        time.sleep(1)
    return None


def do_login(win, username, password):
    try:
        win.activate()
        time.sleep(1)
    except Exception:
        pass

    # Centro da janela de login
    cx = win.left + win.width // 2
    cy = win.top + win.height // 2

    # Campo username — aproximadamente 35% da altura da janela
    user_y = win.top + int(win.height * 0.35)
    print(f"A clicar no campo username ({cx}, {user_y})...")
    pyautogui.click(cx, user_y)
    time.sleep(0.5)
    pyautogui.hotkey("ctrl", "a")
    pyautogui.write(username, interval=0.05)

    # Ir para o campo password com TAB
    print("A mudar para o campo password com TAB...")
    pyautogui.press("tab")
    time.sleep(0.5)

    # Escrever password
    pyautogui.write(password, interval=0.05)

    # Confirmar login com ENTER
    print("A confirmar login com ENTER...")
    pyautogui.press("enter")
    time.sleep(3)
    return True


def confirm_tws_already_logged_in():
    """Exige uma janela principal estável sem ecrã de login antes de concluir sucesso."""
    print(
        "Janela principal do TWS detectada sem ecrã de login. "
        f"A confirmar durante {LOGGED_IN_CONFIRMATION_SECONDS}s para evitar falso positivo de arranque...",
    )
    deadline = time.monotonic() + LOGGED_IN_CONFIRMATION_SECONDS
    while time.monotonic() < deadline:
        if find_login_windows():
            print("Janela de login detectada durante a confirmacao. A continuar fluxo normal de login.")
            return False
        if not find_tws_windows():
            print("Janela principal do TWS desapareceu durante a confirmacao. A continuar fluxo normal.")
            return False
        time.sleep(LOGGED_IN_CONFIRMATION_POLL_SECONDS)

    if find_login_windows():
        print("Janela de login detectada na verificacao final. A continuar fluxo normal de login.")
        return False
    if not find_tws_windows():
        print("Sem janela principal do TWS na verificacao final. A continuar fluxo normal.")
        return False
    return True


def launch_tws():
    if not TWS_PATH.exists():
        print(f"ERRO: executavel do TWS nao encontrado: {TWS_PATH}")
        sys.exit(1)
    print(f"A abrir TWS: {TWS_PATH}")
    subprocess.Popen([str(TWS_PATH)])
    time.sleep(6)


def main():
    args = parse_args()

    print("=" * 50)
    print("TWS AUTO-LOGIN")
    print("=" * 50)

    username, password = load_credentials()

    # Verificar se TWS já está aberto e logado
    existing = find_tws_windows()
    login_open = find_login_windows()

    if existing and not login_open:
        if confirm_tws_already_logged_in():
            print("TWS já está aberto e logado.")
            return
        login_open = find_login_windows()
        existing = find_tws_windows()

    # Abrir TWS se necessário
    if not login_open and not existing:
        if args.skip_launch:
            print("TWS iniciado externamente. A aguardar janela de login...")
        else:
            launch_tws()

    # Aguardar janela de login
    win = wait_for_login_window(timeout=args.timeout)
    if not win:
        print("ERRO: janela de login nao detectada no timeout. A sair sem login.")
        sys.exit(1)

    # Fazer login
    do_login(win, username, password)
    print("Login enviado. A aguardar TWS carregar...")
    time.sleep(30)
    print("TWS pronto.")


if __name__ == "__main__":
    main()
