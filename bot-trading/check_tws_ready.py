"""
check_tws_ready.py
Probe TCP na porta da API do TWS para confirmar que esta pronta.

Uso:
    python check_tws_ready.py [--host 127.0.0.1] [--port 7497] [--timeout 120] [--interval 3]

Exit codes:
    0 = API pronta
    1 = timeout atingido, API nao respondeu
"""
import argparse
import socket
import sys
import time


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verifica se a API do TWS esta pronta.")
    parser.add_argument("--host", default="127.0.0.1", help="Host da API (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=7497, help="Porta da API (default: 7497)")
    parser.add_argument("--timeout", type=int, default=120, help="Timeout total em segundos (default: 120)")
    parser.add_argument("--interval", type=int, default=3, help="Intervalo entre tentativas em segundos (default: 3)")
    return parser.parse_args()


def probe_tcp(host: str, port: int, connect_timeout: float = 5.0) -> bool:
    """Tenta uma conexao TCP. Retorna True se a porta aceitar conexao."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(connect_timeout)
    try:
        result = sock.connect_ex((host, port))
        return result == 0
    except (OSError, socket.timeout):
        return False
    finally:
        sock.close()


def main() -> None:
    args = parse_args()
    start = time.monotonic()
    attempt = 0

    print(f"A verificar API TWS em {args.host}:{args.port} (timeout={args.timeout}s)...")

    while (time.monotonic() - start) < args.timeout:
        attempt += 1
        if probe_tcp(args.host, args.port):
            elapsed = time.monotonic() - start
            print(f"API TWS pronta em {args.host}:{args.port} (tentativa {attempt}, {elapsed:.1f}s)")
            sys.exit(0)
        remaining = args.timeout - (time.monotonic() - start)
        if remaining <= 0:
            break
        wait = min(args.interval, remaining)
        print(f"  Tentativa {attempt}: porta {args.port} nao responde. Proximo retry em {wait:.0f}s...")
        time.sleep(wait)

    elapsed = time.monotonic() - start
    print(f"ERRO: API TWS nao respondeu em {args.host}:{args.port} apos {elapsed:.1f}s ({attempt} tentativas)")
    sys.exit(1)


if __name__ == "__main__":
    main()
