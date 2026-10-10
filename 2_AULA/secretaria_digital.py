"""
Secretaria Digital — app da aula "Dados: da planilha ao banco"

Uma aplicação de verdade conversando com o banco escola.db.
Cada ação mostra o SQL que o app enviou ao banco.

Abas:
  1. Consultar alunos  -> SELECT ... WHERE
  2. Lançar nota       -> UPDATE (ou INSERT, se o aluno ainda não tem nota)
  3. Cadastro          -> INSERT e DELETE
  4. Desafios SQL      -> exercícios: a consulta precisa trazer o resultado certo
  5. Console SQL       -> qualquer SELECT, em modo só leitura

Os consoles das abas 4 e 5 têm AUTOCOMPLETE estilo VS Code:
  - Sugere palavras-chave SQL (SELECT, FROM, WHERE, JOIN, ...)
  - Sugere tabelas e views do banco (alunos, disciplinas, painel_turma, ...)
  - Sugere as colunas de cada tabela/view
  - Navegue com ↑ / ↓, confirme com Tab ou Enter, cancele com Esc

Precisa só do Python (tkinter e sqlite3 já vêm junto).
No Windows: dois cliques em ABRIR_APP.bat  (ou: py secretaria_digital.py)
"""
import csv
import re
import sqlite3
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

DB = Path(__file__).with_name("escola.db")

COLUNAS_PAINEL = [
    ("id", "ID", 40), ("nome", "Nome", 180), ("turma", "Turma", 55),
    ("atividade", "Atividade", 85), ("matematica", "Mat.", 50), ("portugues", "Port.", 50),
    ("logica", "Lóg.", 50), ("ciencias", "Ciên.", 50), ("media_final", "Média", 55),
    ("frequencia_pct", "Freq. %", 60), ("situacao", "Situação", 95),
]
TURMAS = ["1A", "1B"]
ATIVIDADES = ["Banda", "Futsal", "Nenhuma", "Robótica", "Teatro"]
BAIRROS = ["Boqueirão", "Capela Velha", "Centro", "Costeira", "Iguaçu", "Thomaz Coelho"]

# ---------------------------------------------------------------- autocomplete
# Palavras-chave SQL que serão sugeridas nos consoles (Desafios e Console SQL).
PALAVRAS_SQL = [
    "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "NULL", "IS", "IN", "LIKE",
    "BETWEEN", "ORDER BY", "GROUP BY", "HAVING", "LIMIT", "OFFSET",
    "JOIN", "INNER JOIN", "LEFT JOIN", "RIGHT JOIN", "ON",
    "AS", "DISTINCT", "COUNT", "SUM", "AVG", "MIN", "MAX", "ROUND",
    "ASC", "DESC", "CASE", "WHEN", "THEN", "ELSE", "END",
    "INSERT INTO", "VALUES", "UPDATE", "SET", "DELETE FROM",
    "CREATE TABLE", "CREATE VIEW", "DROP TABLE",
]


def carregar_dicionario_sql() -> dict:
    """Descobre tabelas, views e colunas do banco escola.db.

    Devolve algo como:
        {
          "tabelas": ["alunos", "disciplinas", "notas", "frequencia"],
          "views":   ["boletim", "painel_turma"],
          "colunas": {
              "alunos": ["id", "nome", "turma", "idade", "bairro", "atividade"],
              ...
          }
        }
    """
    info = {"tabelas": [], "views": [], "colunas": {}}
    if not DB.exists():
        return info
    try:
        con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
        try:
            linhas = con.execute(
                "SELECT name, type FROM sqlite_master "
                "WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            ).fetchall()
            for nome, tipo in linhas:
                chave = "views" if tipo == "view" else "tabelas"
                info[chave].append(nome)
                colunas = [l[1] for l in con.execute(f"PRAGMA table_info({nome})").fetchall()]
                info["colunas"][nome] = colunas
        finally:
            con.close()
    except sqlite3.Error:
        pass
    return info


class TextComAutocomplete(tk.Text):
    """tk.Text com autocomplete estilo VS Code (palavras-chave + tabelas + colunas).

    - Digite ao menos 1 letra para abrir o popup.
    - ↑/↓ navegam, Tab ou Enter confirmam, Esc fecha.
    - Ctrl+Enter executa o callback 'ao_executar' (se definido).
    """

    # quanto tempo (ms) esperar antes de pedir sugestões (evita re-render ao digitar rápido)
    _ATRASO_MS = 60

    def __init__(self, master, dicionario: dict, **kwargs):
        super().__init__(master, **kwargs)
        self.dicionario = dicionario
        self.ao_executar = None
        self._popup = None
        self._agendado = None
        self._sugestoes = []
        self._indice = -1
        self._ini_palavra = "1.0"

        # lista de sugestões já montada: [palavras-chave] + [tabelas/views] + [colunas]
        self._catalogo = self._montar_catalogo(dicionario)

        self.bind("<KeyRelease>", self._ao_soltar_tecla)
        self.bind("<Down>", self._proximo)
        self.bind("<Up>", self._anterior)
        self.bind("<Tab>", self._confirmar)
        self.bind("<Return>", self._ao_enter)
        self.bind("<Escape>", self._fechar_popup)
        self.bind("<FocusOut>", lambda e: self._fechar_popup())
        self.bind("<Button-1>", lambda e: self._fechar_popup())

    # -- catálogo --------------------------------------------------------
    @staticmethod
    def _montar_catalogo(d: dict) -> list:
        catalogo = []
        # palavras-chave primeiro (aparecem no topo da lista)
        for p in PALAVRAS_SQL:
            catalogo.append((p, "palavra-chave"))
        for t in d.get("tabelas", []):
            catalogo.append((t, "tabela"))
        for v in d.get("views", []):
            catalogo.append((v, "view"))
        for nome, cols in d.get("colunas", {}).items():
            for c in cols:
                catalogo.append((c, "coluna"))
        return catalogo

    # -- popup -----------------------------------------------------------
    def _ao_soltar_tecla(self, evento):
        # deixa Ctrl+Enter e setas passarem sem abrir popup
        if evento.keysym in ("Down", "Up", "Tab", "Return", "Escape", "Left", "Right"):
            return
        if evento.state & 0x4:  # Ctrl pressionado
            return
        if self._agendado:
            self.after_cancel(self._agendado)
        self._agendado = self.after(self._ATRASO_MS, self._pedir_sugestoes)

    def _pedir_sugestoes(self):
        self._agendado = None
        try:
            ini = self.index("insert -1c wordstart")
            fim = self.index("insert")
            palavra = self.get(ini, fim)
        except tk.TclError:
            return
        # se a "palavra" tiver espaço ou pontuação, não sugerimos nada
        if not palavra or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", palavra):
            self._fechar_popup()
            return

        alvo = palavra.lower()
        matches = []
        vistos = set()
        for texto, tipo in self._catalogo:
            chave = texto.lower()
            if chave in vistos:
                continue
            if chave.startswith(alvo):
                vistos.add(chave)
                matches.append((texto, tipo))
            if len(matches) >= 12:
                break
        if not matches:
            self._fechar_popup()
            return
        self._ini_palavra = ini
        self._sugestoes = matches
        self._indice = 0
        self._abrir_popup()

    def _abrir_popup(self):
        if self._popup is None:
            self._popup = tk.Toplevel(self)
            self._popup.wm_overrideredirect(True)
            self._popup.attributes("-topmost", True)
            self._lista = tk.Listbox(
                self._popup, activestyle="none", exportselection=False,
                font=("Consolas", 10), height=8, width=28,
                selectbackground="#2A6FDB", selectforeground="white",
                highlightthickness=1, highlightbackground="#888",
            )
            self._lista.pack(fill="both", expand=True)
            self._lista.bind("<Button-1>", self._clique)
        self._lista.delete(0, "end")
        for texto, tipo in self._sugestoes:
            prefixo = {"palavra-chave": "◆ ", "tabela": "▦ ", "view": "▤ ", "coluna": "· "}.get(tipo, "")
            self._lista.insert("end", f"{prefixo}{texto}")
        self._lista.selection_clear(0, "end")
        self._lista.selection_set(0)
        self._lista.activate(0)

        # posiciona perto do cursor
        try:
            bbox = self.bbox("insert")
        except tk.TclError:
            bbox = None
        if bbox:
            x = self.winfo_rootx() + bbox[0]
            y = self.winfo_rooty() + bbox[1] + bbox[3]
        else:
            x = self.winfo_rootx() + 20
            y = self.winfo_rooty() + 20
        self._popup.wm_geometry(f"+{x}+{y}")
        self._popup.deiconify()

    def _fechar_popup(self, evento=None):
        if self._popup is not None:
            self._popup.destroy()
            self._popup = None
        self._sugestoes = []
        self._indice = -1

    # -- navegação --------------------------------------------------------
    def _proximo(self, evento=None):
        if self._popup and self._sugestoes:
            self._indice = (self._indice + 1) % len(self._sugestoes)
            self._lista.selection_clear(0, "end")
            self._lista.selection_set(self._indice)
            self._lista.activate(self._indice)
            self._lista.see(self._indice)
            return "break"

    def _anterior(self, evento=None):
        if self._popup and self._sugestoes:
            self._indice = (self._indice - 1) % len(self._sugestoes)
            self._lista.selection_clear(0, "end")
            self._lista.selection_set(self._indice)
            self._lista.activate(self._indice)
            self._lista.see(self._indice)
            return "break"

    def _clique(self, evento):
        idx = self._lista.nearest(evento.y)
        self._indice = idx
        self._confirmar()
        return "break"

    def _confirmar(self, evento=None):
        if not (self._popup and self._sugestoes):
            return None
        texto, _tipo = self._sugestoes[self._indice]
        self.delete(self._ini_palavra, "insert")
        self.insert(self._ini_palavra, texto)
        self.mark_set("insert", f"{self._ini_palavra}+{len(texto)}c")
        self._fechar_popup()
        return "break"

    def _ao_enter(self, evento):
        # Se o popup está aberto, Enter confirma; senão, Ctrl+Enter executa
        if self._popup and self._sugestoes:
            return self._confirmar()
        if evento.state & 0x4 and self.ao_executar:
            self.ao_executar()
            return "break"
        return None


# ---------------------------------------------------------------- desafios
DESAFIOS = [
    {"titulo": "Todos os alunos",
     "texto": "Mostre o nome e a turma de todos os alunos (tabela alunos).",
     "dica": "SELECT coluna1, coluna2 FROM tabela;",
     "respostas": ["SELECT nome, turma FROM alunos"]},
    {"titulo": "Turma do teatro",
     "texto": "Mostre o nome dos alunos que fazem Teatro.",
     "dica": "WHERE atividade = '...'  (texto entre aspas simples, com a primeira letra maiúscula)",
     "respostas": ["SELECT nome FROM alunos WHERE atividade = 'Teatro'"]},
    {"titulo": "Os mais velhos",
     "texto": "Mostre o nome e a idade dos alunos com 17 anos ou mais.",
     "dica": "Maior ou igual se escreve >=  e número vai sem aspas.",
     "respostas": ["SELECT nome, idade FROM alunos WHERE idade >= 17"]},
    {"titulo": "Quem mora no Centro",
     "texto": "Mostre o nome dos alunos que moram no bairro Centro.",
     "dica": "A coluna se chama bairro.",
     "respostas": ["SELECT nome FROM alunos WHERE bairro = 'Centro'"]},
    {"titulo": "Turma 1B",
     "texto": "Mostre o nome dos alunos da turma 1B. Compare com o CONT.SE da planilha!",
     "dica": "WHERE turma = '1B'",
     "respostas": ["SELECT nome FROM alunos WHERE turma = '1B'"]},
    {"titulo": "Recuperação",
     "texto": "Na visão painel_turma, mostre o nome e a media_final de quem está em Recuperação.",
     "dica": "FROM painel_turma WHERE situacao = '...'  (tem acento: Recuperação)",
     "respostas": ["SELECT nome, media_final FROM painel_turma WHERE situacao = 'Recuperação'"]},
    {"titulo": "Faltando demais",
     "texto": "Na visão painel_turma, mostre o nome e a frequencia_pct de quem tem frequência abaixo de 75.",
     "dica": "Menor que se escreve <",
     "respostas": ["SELECT nome, frequencia_pct FROM painel_turma WHERE frequencia_pct < 75"]},
    {"titulo": "Robótica da 1A",
     "texto": "Mostre o nome dos alunos da 1A que fazem Robótica.",
     "dica": "Duas condições ao mesmo tempo: ... WHERE condição1 AND condição2",
     "respostas": ["SELECT nome FROM alunos WHERE turma = '1A' AND atividade = 'Robótica'"]},
    {"titulo": "Ranking de Lógica",
     "texto": "Na painel_turma, mostre nome e logica de quem tem nota de Lógica maior que 9, "
              "da maior nota para a menor.",
     "dica": "No final: ORDER BY logica DESC",
     "respostas": ["SELECT nome, logica FROM painel_turma WHERE logica > 9"],
     "ordem": (1, True)},
    {"titulo": "JOIN: notas de Matemática",
     "texto": "Junte a tabela notas com a tabela alunos e mostre o nome do aluno e a nota "
              "de Matemática (disciplina_id = 1).",
     "dica": "FROM notas JOIN alunos ON alunos.id = notas.aluno_id WHERE notas.disciplina_id = 1",
     "respostas": ["SELECT alunos.nome, notas.nota FROM notas "
                   "JOIN alunos ON alunos.id = notas.aluno_id WHERE notas.disciplina_id = 1"]},
    {"titulo": "JOIN: três tabelas",
     "texto": "Mostre o nome do aluno, o nome da disciplina e a nota de todas as notas abaixo de 5. "
              "Junte notas, alunos e disciplinas.",
     "dica": "Dois JOINs: ... JOIN alunos ON ... JOIN disciplinas ON disciplinas.id = notas.disciplina_id",
     "respostas": ["SELECT alunos.nome, disciplinas.nome, notas.nota FROM notas "
                   "JOIN alunos ON alunos.id = notas.aluno_id "
                   "JOIN disciplinas ON disciplinas.id = notas.disciplina_id WHERE notas.nota < 5"]},
    {"titulo": "Painel: 1B em recuperação",
     "texto": "DESAFIO FINAL. Quantos alunos da 1B estão em recuperação? "
              "Vale listar os nomes ou contar com COUNT(*).",
     "dica": "painel_turma, duas condições com AND.",
     "respostas": ["SELECT nome FROM painel_turma WHERE turma = '1B' AND situacao = 'Recuperação'",
                   "SELECT COUNT(*) FROM painel_turma WHERE turma = '1B' AND situacao = 'Recuperação'"]},
    {"titulo": "Painel: Ciências do Futsal",
     "texto": "DESAFIO FINAL. Qual a média de Ciências de quem faz Futsal?",
     "dica": "AVG(ciencias) faz a média. Use painel_turma.",
     "respostas": ["SELECT AVG(ciencias) FROM painel_turma WHERE atividade = 'Futsal'"]},
    {"titulo": "Painel: aprovados em risco",
     "texto": "DESAFIO FINAL. Quem está Aprovado na nota, mas com frequência abaixo de 75%? "
              "Mostre nome e frequencia_pct.",
     "dica": "situacao = 'Aprovado' AND frequencia_pct < 75",
     "respostas": ["SELECT nome, frequencia_pct FROM painel_turma "
                   "WHERE situacao = 'Aprovado' AND frequencia_pct < 75"]},
    {"titulo": "Painel: Futsal faltando",
     "texto": "DESAFIO FINAL. Quantos alunos do Futsal estão com frequência abaixo de 75%? "
              "Vale listar os nomes ou contar.",
     "dica": "atividade = 'Futsal' AND frequencia_pct < 75",
     "respostas": ["SELECT nome FROM painel_turma WHERE atividade = 'Futsal' AND frequencia_pct < 75",
                   "SELECT COUNT(*) FROM painel_turma WHERE atividade = 'Futsal' AND frequencia_pct < 75"]},
]


# ----------------------------------------------------------------- banco
def conectar(somente_leitura: bool = False) -> sqlite3.Connection:
    if not DB.exists():
        raise FileNotFoundError(f"Não achei o banco em {DB}.\nRode antes:  python criar_banco.py")
    if somente_leitura:
        return sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=5)
    con = sqlite3.connect(DB, timeout=5)
    con.execute("PRAGMA foreign_keys = ON")
    return con


def sql_para_exibir(sql: str, params) -> str:
    partes = sql.split("?")
    saida = partes[0]
    for valor, resto in zip(params, partes[1:]):
        if isinstance(valor, str):
            valor = "'" + valor.replace("'", "''") + "'"
        saida += str(valor) + resto
    return saida


def mostra(v):
    return "—" if v is None else v


def normaliza(linhas):
    saida = []
    for linha in linhas:
        nova = []
        for v in linha:
            if isinstance(v, float):
                v = round(v, 2)
                if v == int(v):
                    v = int(v)
            elif isinstance(v, str):
                v = v.strip()
            nova.append(v)
        saida.append(tuple(nova))
    return saida


def chave(linha):
    return tuple(str(v) for v in linha)


# ----------------------------------------------------------------- app
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Secretaria Digital — Colégio Fictício Pinheiral")
        self.geometry("1060x720")
        self.minsize(900, 600)
        estilo = ttk.Style(self)
        estilo.configure("Treeview", rowheight=24, font=("Arial", 10))
        estilo.configure("Treeview.Heading", font=("Arial", 10, "bold"))

        # descobre tabelas/views/colunas para o autocomplete dos consoles
        self.dicionario_sql = carregar_dicionario_sql()

        abas = ttk.Notebook(self)
        abas.pack(fill="both", expand=True, padx=8, pady=8)
        self.aba_consulta = ttk.Frame(abas, padding=8)
        self.aba_nota = ttk.Frame(abas, padding=8)
        self.aba_cadastro = ttk.Frame(abas, padding=8)
        self.aba_desafios = ttk.Frame(abas, padding=8)
        self.aba_sql = ttk.Frame(abas, padding=8)
        abas.add(self.aba_consulta, text="  1. Consultar alunos  ")
        abas.add(self.aba_nota, text="  2. Lançar nota  ")
        abas.add(self.aba_cadastro, text="  3. Cadastro  ")
        abas.add(self.aba_desafios, text="  4. Desafios SQL  ")
        abas.add(self.aba_sql, text="  5. Console SQL  ")

        self.ultimas_linhas = []
        self.resolvidos = set()
        self._montar_consulta()
        self._montar_nota()
        self._montar_cadastro()
        self._montar_desafios()
        self._montar_console()
        self.recarregar_listas()
        self.buscar()

    # ---------- utilidades de tela
    def _caixa_sql(self, pai, titulo="SQL que o app mandou para o banco", altura=6):
        quadro = ttk.LabelFrame(pai, text=titulo, padding=6)
        quadro.pack(fill="x", pady=(8, 0))
        caixa = tk.Text(quadro, height=altura, font=("Courier New", 10), bg="#14213D",
                        fg="#E6EEF9", insertbackground="white", wrap="word")
        caixa.pack(fill="x")
        caixa.configure(state="disabled")
        return caixa

    @staticmethod
    def _mostrar_sql(caixa, texto):
        caixa.configure(state="normal")
        caixa.delete("1.0", "end")
        caixa.insert("1.0", texto)
        caixa.configure(state="disabled")

    @staticmethod
    def _tabela(pai, colunas, altura=None):
        quadro = ttk.Frame(pai)
        quadro.pack(fill="both", expand=True)
        arvore = ttk.Treeview(quadro, columns=[c[0] for c in colunas], show="headings",
                              height=altura or 10)
        for chave_col, titulo, largura in colunas:
            arvore.heading(chave_col, text=titulo)
            arvore.column(chave_col, width=largura, anchor="w" if chave_col == "nome" else "center")
        rolagem = ttk.Scrollbar(quadro, orient="vertical", command=arvore.yview)
        arvore.configure(yscrollcommand=rolagem.set)
        arvore.pack(side="left", fill="both", expand=True)
        rolagem.pack(side="right", fill="y")
        arvore.tag_configure("alerta", foreground="#c00000")
        return arvore

    def recarregar_listas(self):
        with conectar() as con:
            self.alunos = con.execute("SELECT id, nome, turma FROM alunos ORDER BY nome").fetchall()
            self.disciplinas = con.execute("SELECT id, nome FROM disciplinas ORDER BY id").fetchall()
        self.cb_aluno.configure(values=[f"{a[0]} - {a[1]} ({a[2]})" for a in self.alunos])
        self.cb_disc.configure(values=[f"{d[0]} - {d[1]}" for d in self.disciplinas])
        self.atualizar_lista_cadastro()

    # ---------- aba 1: consultar
    def _montar_consulta(self):
        f = ttk.Frame(self.aba_consulta)
        f.pack(fill="x", pady=(0, 6))
        self.f_turma = tk.StringVar(value="Todas")
        self.f_ativ = tk.StringVar(value="Todas")
        self.f_sit = tk.StringVar(value="Todas")
        self.f_nome = tk.StringVar()
        self.f_freq = tk.BooleanVar()

        ttk.Label(f, text="Turma").grid(row=0, column=0, sticky="w")
        ttk.Combobox(f, textvariable=self.f_turma, values=["Todas"] + TURMAS,
                     state="readonly", width=7).grid(row=1, column=0, padx=(0, 8))
        ttk.Label(f, text="Atividade").grid(row=0, column=1, sticky="w")
        ttk.Combobox(f, textvariable=self.f_ativ, values=["Todas"] + ATIVIDADES,
                     state="readonly", width=11).grid(row=1, column=1, padx=(0, 8))
        ttk.Label(f, text="Situação").grid(row=0, column=2, sticky="w")
        ttk.Combobox(f, textvariable=self.f_sit, values=["Todas", "Aprovado", "Recuperação", "Sem notas"],
                     state="readonly", width=12).grid(row=1, column=2, padx=(0, 8))
        ttk.Label(f, text="Nome contém").grid(row=0, column=3, sticky="w")
        entrada = ttk.Entry(f, textvariable=self.f_nome, width=18)
        entrada.grid(row=1, column=3, padx=(0, 8))
        entrada.bind("<Return>", lambda e: self.buscar())
        ttk.Checkbutton(f, text="Frequência abaixo de 75%",
                        variable=self.f_freq).grid(row=1, column=4, padx=(0, 8))
        ttk.Button(f, text="Buscar", command=self.buscar).grid(row=1, column=5, padx=(0, 6))
        ttk.Button(f, text="Exportar CSV", command=self.exportar_csv).grid(row=1, column=6)

        self.tabela = self._tabela(self.aba_consulta, COLUNAS_PAINEL)
        self.lbl_total = ttk.Label(self.aba_consulta, font=("Arial", 10, "bold"))
        self.lbl_total.pack(anchor="w", pady=(4, 0))
        self.sql_consulta = self._caixa_sql(self.aba_consulta)

    def buscar(self):
        campos = ", ".join(c[0] for c in COLUNAS_PAINEL)
        filtros, params = [], []
        if self.f_turma.get() != "Todas":
            filtros.append("turma = ?"); params.append(self.f_turma.get())
        if self.f_ativ.get() != "Todas":
            filtros.append("atividade = ?"); params.append(self.f_ativ.get())
        if self.f_sit.get() != "Todas":
            filtros.append("situacao = ?"); params.append(self.f_sit.get())
        if self.f_nome.get().strip():
            filtros.append("nome LIKE ?"); params.append(f"%{self.f_nome.get().strip()}%")
        if self.f_freq.get():
            filtros.append("frequencia_pct < ?"); params.append(75)

        sql = f"SELECT {campos}\nFROM painel_turma"
        if filtros:
            sql += "\nWHERE " + "\n  AND ".join(filtros)
        sql += "\nORDER BY nome;"

        with conectar() as con:
            linhas = con.execute(sql, params).fetchall()
        self.ultimas_linhas = linhas
        self.tabela.delete(*self.tabela.get_children())
        for linha in linhas:
            freq, situacao = linha[-2], linha[-1]
            alerta = situacao == "Recuperação" or (freq is not None and freq < 75)
            self.tabela.insert("", "end", values=[mostra(v) for v in linha],
                               tags=("alerta",) if alerta else ())
        self.lbl_total.configure(text=f"{len(linhas)} aluno(s) encontrado(s)   "
                                      "· vermelho = recuperação ou frequência < 75%")
        self._mostrar_sql(self.sql_consulta, sql_para_exibir(sql, params))

    def exportar_csv(self):
        if not self.ultimas_linhas:
            messagebox.showinfo("Exportar", "Nada para exportar. Faça uma busca antes.")
            return
        destino = filedialog.asksaveasfilename(
            defaultextension=".csv", initialfile="consulta_turma.csv",
            filetypes=[("CSV (abre no LibreOffice)", "*.csv")])
        if not destino:
            return
        with open(destino, "w", newline="", encoding="utf-8-sig") as arq:
            w = csv.writer(arq, delimiter=";")
            w.writerow([c[1] for c in COLUNAS_PAINEL])
            for linha in self.ultimas_linhas:
                w.writerow(["" if v is None else str(v).replace(".", ",") if isinstance(v, float) else v
                            for v in linha])
        messagebox.showinfo("Exportar", f"Arquivo salvo:\n{destino}\n\nAbra no LibreOffice Calc!")

    # ---------- aba 2: lançar nota (UPDATE / INSERT)
    def _montar_nota(self):
        f = ttk.Frame(self.aba_nota)
        f.pack(fill="x")
        self.n_aluno = tk.StringVar()
        self.n_disc = tk.StringVar()
        self.n_nota = tk.StringVar()

        ttk.Label(f, text="Aluno").grid(row=0, column=0, sticky="w")
        self.cb_aluno = ttk.Combobox(f, textvariable=self.n_aluno, state="readonly", width=34)
        self.cb_aluno.grid(row=1, column=0, padx=(0, 8))
        ttk.Label(f, text="Disciplina").grid(row=0, column=1, sticky="w")
        self.cb_disc = ttk.Combobox(f, textvariable=self.n_disc, state="readonly", width=26)
        self.cb_disc.grid(row=1, column=1, padx=(0, 8))
        ttk.Label(f, text="Nova nota (0 a 10)").grid(row=0, column=2, sticky="w")
        ttk.Entry(f, textvariable=self.n_nota, width=8).grid(row=1, column=2, padx=(0, 8))
        ttk.Button(f, text="Salvar nota", command=self.salvar_nota).grid(row=1, column=3)
        for cb in (self.cb_aluno, self.cb_disc):
            cb.bind("<<ComboboxSelected>>", lambda e: self.ver_nota_atual())

        self.lbl_nota = ttk.Label(self.aba_nota, font=("Arial", 12), padding=(0, 14))
        self.lbl_nota.pack(anchor="w")
        ttk.Label(self.aba_nota, wraplength=950, foreground="#595959", text=(
            "Experimento: veja a média do aluno, salve uma nota nova e depois confira na aba 1 "
            "ou no Console SQL:  SELECT * FROM painel_turma WHERE id = ...  "
            "O banco é um só: todas as abas enxergam a mesma informação.")).pack(anchor="w")
        self.sql_nota = self._caixa_sql(self.aba_nota)

    def _ids_nota(self):
        if not (self.n_aluno.get() and self.n_disc.get()):
            return None
        return (int(self.n_aluno.get().split(" - ")[0]), int(self.n_disc.get().split(" - ")[0]))

    def ver_nota_atual(self):
        ids = self._ids_nota()
        if not ids:
            return
        sql = ("SELECT n.nota, p.media_final, p.situacao\nFROM painel_turma p\n"
               "LEFT JOIN notas n ON n.aluno_id = p.id AND n.disciplina_id = ?\nWHERE p.id = ?;")
        params = [ids[1], ids[0]]
        with conectar() as con:
            r = con.execute(sql, params).fetchone()
        if r:
            nota = "sem nota" if r[0] is None else f"{r[0]:.1f}"
            media = "—" if r[1] is None else f"{r[1]:.1f}"
            self.lbl_nota.configure(text=f"Nota atual: {nota}   ·   Média final: {media}   ·   {r[2]}")
        self._mostrar_sql(self.sql_nota, sql_para_exibir(sql, params))

    def salvar_nota(self):
        ids = self._ids_nota()
        if not ids:
            messagebox.showwarning("Lançar nota", "Escolha o aluno e a disciplina.")
            return
        try:
            nota = float(self.n_nota.get().replace(",", "."))
        except ValueError:
            messagebox.showwarning("Lançar nota", "A nota precisa ser um número, ex.: 7,5")
            return
        if not 0 <= nota <= 10:
            messagebox.showwarning("Lançar nota", "A nota vai de 0 a 10.")
            return
        aluno_id, disc_id = ids
        sql_up = "UPDATE notas\nSET nota = ?\nWHERE aluno_id = ? AND disciplina_id = ?;"
        sql_ins = "INSERT INTO notas (aluno_id, disciplina_id, nota)\nVALUES (?, ?, ?);"
        try:
            with conectar() as con:
                cur = con.execute(sql_up, (nota, aluno_id, disc_id))
                if cur.rowcount == 0:
                    con.execute(sql_ins, (aluno_id, disc_id, nota))
                    mostrado = ("-- o UPDATE não achou nenhuma linha, então o app fez um INSERT:\n"
                                + sql_para_exibir(sql_ins, [aluno_id, disc_id, nota]))
                else:
                    mostrado = sql_para_exibir(sql_up, [nota, aluno_id, disc_id])
                r = con.execute("SELECT media_final, situacao FROM painel_turma WHERE id = ?",
                                (aluno_id,)).fetchone()
        except sqlite3.OperationalError as erro:
            messagebox.showerror("Banco ocupado", f"Não consegui gravar ({erro}).\nFeche outros programas que "
                                 "estejam usando o escola.db e tente de novo.")
            return
        self._mostrar_sql(self.sql_nota, mostrado)
        media = "—" if r[0] is None else f"{r[0]:.1f}"
        self.lbl_nota.configure(text=f"Nota salva: {nota:.1f}   ·   Nova média final: {media}   ·   {r[1]}")
        self.buscar()

    # ---------- aba 3: cadastro (INSERT / DELETE)
    def _montar_cadastro(self):
        f = ttk.LabelFrame(self.aba_cadastro, text="Matricular aluno novo (INSERT)", padding=8)
        f.pack(fill="x")
        self.c_nome = tk.StringVar()
        self.c_turma = tk.StringVar(value="1A")
        self.c_idade = tk.StringVar(value="16")
        self.c_bairro = tk.StringVar(value="Centro")
        self.c_ativ = tk.StringVar(value="Nenhuma")
        campos = [("Nome", ttk.Entry(f, textvariable=self.c_nome, width=28)),
                  ("Turma", ttk.Combobox(f, textvariable=self.c_turma, values=TURMAS, state="readonly", width=5)),
                  ("Idade", ttk.Spinbox(f, textvariable=self.c_idade, from_=12, to=22, width=5)),
                  ("Bairro", ttk.Combobox(f, textvariable=self.c_bairro, values=BAIRROS, width=14)),
                  ("Atividade", ttk.Combobox(f, textvariable=self.c_ativ, values=ATIVIDADES,
                                             state="readonly", width=10))]
        for col, (rotulo, w) in enumerate(campos):
            ttk.Label(f, text=rotulo).grid(row=0, column=col, sticky="w")
            w.grid(row=1, column=col, padx=(0, 8))
        ttk.Button(f, text="Matricular", command=self.matricular).grid(row=1, column=len(campos))

        g = ttk.LabelFrame(self.aba_cadastro, text="Alunos cadastrados (os mais novos primeiro)", padding=8)
        g.pack(fill="both", expand=True, pady=(8, 0))
        self.tab_cad = self._tabela(g, [("id", "ID", 50), ("nome", "Nome", 240), ("turma", "Turma", 60),
                                        ("idade", "Idade", 60), ("bairro", "Bairro", 120),
                                        ("atividade", "Atividade", 100)], altura=8)
        ttk.Button(g, text="Excluir aluno selecionado (DELETE)",
                   command=self.excluir).pack(anchor="w", pady=(6, 0))
        self.sql_cad = self._caixa_sql(self.aba_cadastro, altura=5)

    def atualizar_lista_cadastro(self):
        with conectar() as con:
            linhas = con.execute("SELECT id, nome, turma, idade, bairro, atividade "
                                 "FROM alunos ORDER BY id DESC").fetchall()
        self.tab_cad.delete(*self.tab_cad.get_children())
        for linha in linhas:
            self.tab_cad.insert("", "end", iid=str(linha[0]), values=[mostra(v) for v in linha])

    def matricular(self):
        nome = self.c_nome.get().strip()
        if not nome or len(nome) > 60:
            messagebox.showwarning("Matricular", "Escreva o nome (até 60 letras).")
            return
        try:
            idade = int(self.c_idade.get())
        except ValueError:
            messagebox.showwarning("Matricular", "Idade precisa ser um número inteiro.")
            return
        if not 12 <= idade <= 22:
            messagebox.showwarning("Matricular", "Idade fora do esperado para o ensino médio (12 a 22).")
            return
        sql = ("INSERT INTO alunos (nome, turma, idade, bairro, atividade)\n"
               "VALUES (?, ?, ?, ?, ?);")
        params = [nome, self.c_turma.get(), idade, self.c_bairro.get().strip() or None, self.c_ativ.get()]
        try:
            with conectar() as con:
                novo_id = con.execute(sql, params).lastrowid
        except sqlite3.Error as erro:
            messagebox.showerror("Matricular", f"O banco recusou: {erro}")
            return
        self._mostrar_sql(self.sql_cad, sql_para_exibir(sql, params) +
                          f"\n-- o banco criou o id {novo_id} sozinho (chave primária)")
        self.c_nome.set("")
        self.recarregar_listas()
        self.buscar()

    def excluir(self):
        sel = self.tab_cad.selection()
        if not sel:
            messagebox.showinfo("Excluir", "Clique num aluno da lista antes.")
            return
        aluno_id = int(sel[0])
        nome = self.tab_cad.item(sel[0], "values")[1]
        if not messagebox.askyesno("Excluir", f"Excluir {nome} (id {aluno_id})?\n\n"
                                   "As notas e a frequência dele também somem (ON DELETE CASCADE).\n"
                                   "Para desfazer tudo depois: python criar_banco.py"):
            return
        sql = "DELETE FROM alunos\nWHERE id = ?;"
        with conectar() as con:
            con.execute(sql, (aluno_id,))
        self._mostrar_sql(self.sql_cad, sql_para_exibir(sql, [aluno_id]) +
                          "\n-- sem o WHERE, esse comando apagaria TODOS os alunos!")
        self.recarregar_listas()
        self.buscar()

    # ---------- aba 4: desafios SQL
    def _montar_desafios(self):
        esq = ttk.Frame(self.aba_desafios)
        esq.pack(side="left", fill="y")
        self.lbl_prog = ttk.Label(esq, font=("Arial", 10, "bold"))
        self.lbl_prog.pack(anchor="w", pady=(0, 4))
        self.lista_desafios = tk.Listbox(esq, width=30, font=("Arial", 10), activestyle="none",
                                         exportselection=False)
        self.lista_desafios.pack(fill="y", expand=True)
        self.lista_desafios.bind("<<ListboxSelect>>", lambda e: self.abrir_desafio())

        dir_ = ttk.Frame(self.aba_desafios, padding=(12, 0, 0, 0))
        dir_.pack(side="left", fill="both", expand=True)
        self.lbl_enunciado = ttk.Label(dir_, font=("Arial", 12), wraplength=640, justify="left")
        self.lbl_enunciado.pack(anchor="w")
        self.lbl_meta = ttk.Label(dir_, foreground="#1F4E79", font=("Arial", 10, "bold"))
        self.lbl_meta.pack(anchor="w", pady=(4, 0))

        # >>> AQUI: o console de desafios agora tem autocomplete <<<
        self.txt_desafio = TextComAutocomplete(
            dir_, dicionario=self.dicionario_sql,
            height=5, font=("Courier New", 11), wrap="word",
            undo=True,
        )
        self.txt_desafio.pack(fill="x", pady=6)
        self.txt_desafio.ao_executar = self.testar_desafio

        barra = ttk.Frame(dir_)
        barra.pack(fill="x")
        ttk.Button(barra, text="Testar (Ctrl+Enter)", command=self.testar_desafio).pack(side="left")
        ttk.Button(barra, text="Dica", command=self.dica_desafio).pack(side="left", padx=6)
        self.lbl_feedback = tk.Label(dir_, font=("Arial", 11, "bold"), anchor="w", justify="left",
                                     wraplength=640, padx=8, pady=6)
        self.lbl_feedback.pack(fill="x", pady=(8, 6))
        self.quadro_desafio = ttk.Frame(dir_)
        self.quadro_desafio.pack(fill="both", expand=True)
        self.desafio_atual = 0
        self._atualizar_lista_desafios()
        self.lista_desafios.selection_set(0)
        self.abrir_desafio()

    def _atualizar_lista_desafios(self):
        self.lista_desafios.delete(0, "end")
        for i, d in enumerate(DESAFIOS):
            marca = "✔" if i in self.resolvidos else "  "
            self.lista_desafios.insert("end", f"{marca} {i + 1}. {d['titulo']}")
            if i in self.resolvidos:
                self.lista_desafios.itemconfig(i, foreground="#2E7D4F")
        self.lbl_prog.configure(text=f"{len(self.resolvidos)} de {len(DESAFIOS)} resolvidos")

    def _referencias(self, d):
        with conectar(somente_leitura=True) as con:
            return [normaliza(con.execute(r).fetchall()) for r in d["respostas"]]

    def abrir_desafio(self):
        sel = self.lista_desafios.curselection()
        if not sel:
            return
        self.desafio_atual = sel[0]
        d = DESAFIOS[self.desafio_atual]
        self.lbl_enunciado.configure(text=f"{self.desafio_atual + 1}. {d['texto']}")
        refs = self._referencias(d)
        alvo = refs[0]
        if len(alvo) == 1 and len(alvo[0]) == 1 and not isinstance(alvo[0][0], str):
            meta = "A resposta certa é um número só."
        else:
            meta = f"A resposta certa tem {len(alvo)} linha(s) e {len(alvo[0]) if alvo else 0} coluna(s)."
        if len(refs) > 1:
            meta += "  (Ou um número só, se você usar COUNT.)"
        self.lbl_meta.configure(text=meta)
        self.txt_desafio.delete("1.0", "end")
        self.lbl_feedback.configure(text="", bg=self.cget("bg"))
        for w in self.quadro_desafio.winfo_children():
            w.destroy()

    def dica_desafio(self):
        self.lbl_feedback.configure(text="Dica: " + DESAFIOS[self.desafio_atual]["dica"],
                                    bg="#FFF2CC", fg="#3D3300")

    def testar_desafio(self):
        d = DESAFIOS[self.desafio_atual]
        sql = self.txt_desafio.get("1.0", "end").strip()
        if not sql:
            return
        for w in self.quadro_desafio.winfo_children():
            w.destroy()
        try:
            with conectar(somente_leitura=True) as con:
                cur = con.execute(sql)
                if cur.description is None:
                    raise sqlite3.Error("isso não é uma consulta (SELECT)")
                nomes = [x[0] for x in cur.description]
                brutas = cur.fetchmany(2000)
        except sqlite3.Error as erro:
            self.lbl_feedback.configure(text="Erro: " + traduz_erro(str(erro)), bg="#FBE3E3", fg="#8A1C1C")
            return

        arvore = self._tabela(self.quadro_desafio, [(f"c{i}", n, 120) for i, n in enumerate(nomes)], altura=7)
        for linha in brutas:
            arvore.insert("", "end", values=[mostra(v) for v in linha])

        minhas = normaliza(brutas)
        certo, motivo = False, ""
        for ref in self._referencias(d):
            certo, motivo = compara(minhas, ref, d.get("ordem"))
            if certo:
                break
        if certo:
            self.resolvidos.add(self.desafio_atual)
            self._atualizar_lista_desafios()
            self.lista_desafios.selection_set(self.desafio_atual)
            self.lbl_feedback.configure(text=f"Acertou! Sua consulta trouxe exatamente o resultado esperado "
                                             f"({len(minhas)} linha(s)).", bg="#DDF3E8", fg="#1E5E3E")
        else:
            self.lbl_feedback.configure(text="Ainda não. " + motivo, bg="#FBE3E3", fg="#8A1C1C")

    # ---------- aba 5: console SQL (só leitura)
    def _montar_console(self):
        ttk.Label(self.aba_sql, foreground="#595959", text=(
            "Digite um SELECT e aperte Ctrl+Enter. Esta aba abre o banco em modo SÓ LEITURA: "
            "dá para consultar à vontade sem estragar nada.  "
            "Autocomplete ativo: comece a digitar e escolha com ↑/↓ + Tab.")).pack(anchor="w")

        # >>> AQUI: o Console SQL agora tem autocomplete <<<
        self.txt_sql = TextComAutocomplete(
            self.aba_sql, dicionario=self.dicionario_sql,
            height=7, font=("Courier New", 11), wrap="word",
            undo=True,
        )
        self.txt_sql.pack(fill="x", pady=6)
        self.txt_sql.insert("1.0", "SELECT nome, turma, idade\nFROM alunos\nWHERE turma = '1A';")
        self.txt_sql.ao_executar = self.executar_console

        barra = ttk.Frame(self.aba_sql)
        barra.pack(fill="x")
        ttk.Button(barra, text="Executar (Ctrl+Enter)", command=self.executar_console).pack(side="left")
        exemplos = {
            "Tabelas": "SELECT name, type FROM sqlite_master WHERE type IN ('table','view');",
            "Robótica": "SELECT nome, turma FROM alunos WHERE atividade = 'Robótica';",
            "JOIN": "SELECT alunos.nome, disciplinas.nome, notas.nota\nFROM notas\n"
                    "JOIN alunos ON alunos.id = notas.aluno_id\n"
                    "JOIN disciplinas ON disciplinas.id = notas.disciplina_id\nWHERE notas.nota >= 9;",
            "Freq. < 75%": "SELECT nome, frequencia_pct\nFROM painel_turma\nWHERE frequencia_pct < 75;",
        }
        for rotulo, sql in exemplos.items():
            ttk.Button(barra, text=rotulo,
                       command=lambda s=sql: (self.txt_sql.delete("1.0", "end"),
                                              self.txt_sql.insert("1.0", s))).pack(side="left", padx=(6, 0))
        self.lbl_console = ttk.Label(self.aba_sql, font=("Arial", 10, "bold"), padding=(0, 6))
        self.lbl_console.pack(anchor="w")
        self.quadro_resultado = ttk.Frame(self.aba_sql)
        self.quadro_resultado.pack(fill="both", expand=True)

    def executar_console(self):
        sql = self.txt_sql.get("1.0", "end").strip()
        if not sql:
            return
        for w in self.quadro_resultado.winfo_children():
            w.destroy()
        try:
            with conectar(somente_leitura=True) as con:
                cur = con.execute(sql)
                if cur.description is None:
                    self.lbl_console.configure(text="Comando executado, mas não devolveu linhas.", foreground="black")
                    return
                nomes = [d[0] for d in cur.description]
                linhas = cur.fetchmany(500)
        except sqlite3.Error as erro:
            self.lbl_console.configure(text="Erro: " + traduz_erro(str(erro)), foreground="#c00000")
            return
        self.lbl_console.configure(text=f"{len(linhas)} linha(s)" + (" (mostrando as 500 primeiras)"
                                   if len(linhas) == 500 else ""), foreground="black")
        arvore = self._tabela(self.quadro_resultado, [(f"c{i}", n, 110) for i, n in enumerate(nomes)])
        for linha in linhas:
            arvore.insert("", "end", values=[mostra(v) for v in linha])


# ----------------------------------------------------------------- correção
def compara(minhas, ref, ordem=None):
    """Devolve (acertou?, explicação)."""
    if minhas and ref and len(minhas[0]) != len(ref[0]):
        return False, (f"Sua consulta trouxe {len(minhas[0])} coluna(s), mas a resposta tem {len(ref[0])}. "
                       "Confira o que vem depois do SELECT.")
    if len(minhas) != len(ref):
        return False, (f"Sua consulta trouxe {len(minhas)} linha(s), mas a resposta tem {len(ref)}. "
                       "Confira o WHERE.")
    iguais = sorted(map(chave, minhas)) == sorted(map(chave, ref))
    if not iguais:
        iguais = (sorted(tuple(sorted(chave(l))) for l in minhas)
                  == sorted(tuple(sorted(chave(l))) for l in ref))
    if not iguais:
        return False, ("A quantidade de linhas bate, mas os valores não. "
                       "Confira as colunas escolhidas e as condições do WHERE.")
    if ordem:
        col, desc = ordem
        valores = [l[col] for l in minhas]
        if valores != sorted(valores, reverse=desc):
            return False, "Os dados estão certos, mas a ordem não. Use ORDER BY ... DESC."
    return True, ""


def traduz_erro(msg: str) -> str:
    dicas = {
        "no such table": "essa tabela não existe. No Console, clique em 'Tabelas' para ver os nomes.",
        "no such column": "essa coluna não existe. Confira o nome (sem acento!).",
        "ambiguous column": "duas tabelas têm uma coluna com esse nome. Escreva tabela.coluna, ex.: alunos.nome",
        "syntax error": "erro de digitação no SQL. Confira vírgulas, aspas e a ordem SELECT → FROM → WHERE.",
        "readonly": "aqui é só leitura. Para alterar dados, use as abas 'Lançar nota' e 'Cadastro'.",
        "unrecognized token": "aspas abertas e não fechadas? Texto vai entre aspas simples: 'Robótica'.",
        "one statement at a time": "execute um comando por vez (apague o que vem depois do ;).",
        "não é uma consulta": "o desafio pede um SELECT.",
    }
    for k, dica in dicas.items():
        if k.lower() in msg.lower():
            return f"{dica}   [{msg}]"
    return msg


if __name__ == "__main__":
    try:
        App().mainloop()
    except FileNotFoundError as erro:
        tk.Tk().withdraw()
        messagebox.showerror("Secretaria Digital", str(erro))
