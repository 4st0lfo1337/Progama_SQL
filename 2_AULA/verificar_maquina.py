"""
verificar_maquina.py — confere se a máquina está pronta para a aula.
Dê dois cliques em VERIFICAR.bat (ou rode: py verificar_maquina.py).
"""
import sys
from pathlib import Path

PASTA = Path(__file__).parent
ok = True

def linha(passou, texto, dica=""):
    global ok
    ok &= passou
    print(("  [OK]   " if passou else "  [FALHA] ") + texto)
    if not passou and dica:
        print("          -> " + dica)

print("\nVerificando a máquina para a aula de dados...\n")
v = sys.version_info
linha(v >= (3, 10), f"Python {v.major}.{v.minor}.{v.micro}", "Instale o Python da pasta 1_INSTALADORES do pen drive.")

try:
    import sqlite3
    linha(True, f"sqlite3 (SQLite {sqlite3.sqlite_version})")
except Exception as e:
    sqlite3 = None
    linha(False, f"sqlite3: {e}", "Reinstale o Python pelo instalador oficial.")

try:
    import tkinter
    linha(True, f"tkinter (Tk {tkinter.TkVersion})")
except Exception as e:
    tkinter = None
    linha(False, f"tkinter: {e}",
          "Rode o instalador do Python de novo > Modify > marque 'tcl/tk and IDLE'.")

db = PASTA / "escola.db"
if db.exists() and sqlite3:
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        n = con.execute("SELECT COUNT(*) FROM alunos").fetchone()[0]
        con.close()
        linha(n == 32, f"escola.db encontrado ({n} alunos)",
              "O banco foi alterado. Rode: py criar_banco.py")
    except Exception as e:
        linha(False, f"escola.db com problema: {e}", "Rode: py criar_banco.py")
else:
    linha(False, "escola.db não encontrado nesta pasta", "Rode: py criar_banco.py")

for nome in ["secretaria_digital.py", "planilha_turma_ALUNO.xlsx", "ABRIR_APP.bat"]:
    linha((PASTA / nome).exists(), f"arquivo {nome}", "Copie a pasta inteira do pen drive.")

if sys.platform == "win32":
    import os
    locais = [Path(os.environ.get(k, "")) / "LibreOffice" / "program" / "soffice.exe"
              for k in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA") if os.environ.get(k)]
    linha(any(p.exists() for p in locais), "LibreOffice instalado",
          "Instale o LibreOffice da pasta 1_INSTALADORES do pen drive.")

if tkinter:
    try:
        janela = tkinter.Tk()
        janela.title("Teste")
        tkinter.Label(janela, text="Se você está vendo esta janela, o tkinter funciona!",
                      font=("Arial", 14), padx=30, pady=30).pack()
        janela.after(2500, janela.destroy)
        janela.mainloop()
        linha(True, "janela de teste abriu")
    except Exception as e:
        linha(False, f"não consegui abrir janela: {e}")

print("\n" + ("Tudo certo! Pode abrir o app com ABRIR_APP.bat" if ok
              else "Algo falhou. Veja as dicas acima.") + "\n")
