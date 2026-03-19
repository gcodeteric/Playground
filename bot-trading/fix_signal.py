with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = '        for sig in (signal.SIGINT, signal.SIGTERM):\n            loop.add_signal_handler(sig, self._handle_shutdown_signal, sig)\n        logger.info("Handlers de sinal registados (SIGINT, SIGTERM).")'

new = '        import platform as _platform\n        use_unix = False\n        if _platform.system() != "Windows":\n            try:\n                for sig in (signal.SIGINT, signal.SIGTERM):\n                    loop.add_signal_handler(sig, self._handle_shutdown_signal, sig)\n                use_unix = True\n            except NotImplementedError:\n                pass\n        if use_unix:\n            logger.info("Caminho de sinais activo: unix_signal_handlers.")\n            return\n        registered = []\n        for sig in (signal.SIGINT, signal.SIGTERM):\n            try:\n                signal.signal(sig, lambda s, _: self._handle_shutdown_signal(s))\n                registered.append(sig.name)\n            except (OSError, ValueError, AttributeError):\n                pass\n        logger.info("Caminho de sinais activo: windows_signal_fallback (%s).", ", ".join(registered))'

if old in content:
    content = content.replace(old, new)
    with open('main.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("FIX APLICADO COM SUCESSO")
else:
    print("ERRO: texto nao encontrado")
