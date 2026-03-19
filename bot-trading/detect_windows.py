import pygetwindow as gw

print("Todas as janelas abertas:")
for w in gw.getAllWindows():
    if w.title.strip():
        print(repr(w.title))