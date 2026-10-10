"""
criar_banco.py — cria (ou recria do zero) o banco escola.db da aula.

Use antes da aula ou depois dela, para desfazer o que a turma alterou.
Os dados são 100% fictícios e sempre os mesmos (semente fixa).

    python criar_banco.py
"""
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB = Path(__file__).with_name("escola.db")
random.seed(2026)

NOMES = [
    "Ana Clara Souza", "Bruno Henrique Lima", "Camila Rocha", "Davi Martins",
    "Eduarda Pires", "Felipe Andrade", "Gabriela Nunes", "Heitor Campos",
    "Isabela Ferreira", "João Pedro Alves", "Kauã Ribeiro", "Larissa Mendes",
    "Lucas Gabriel Costa", "Maria Eduarda Silva", "Matheus Carvalho", "Nicole Barbosa",
    "Otávio Teixeira", "Pietra Gomes", "Rafael Moreira", "Sophia Cardoso",
    "Thiago Araújo", "Valentina Dias", "Vinícius Rezende", "Yasmin Correia",
    "Arthur Machado", "Beatriz Monteiro", "Caio Fernandes", "Débora Lopes",
    "Enzo Batista", "Fernanda Castro", "Guilherme Pinto", "Helena Duarte",
]
BAIRROS = ["Centro", "Costeira", "Capela Velha", "Thomaz Coelho", "Iguaçu", "Boqueirão"]
ATIVIDADES = ["Robótica", "Futsal", "Teatro", "Banda", "Nenhuma"]
DISCIPLINAS = [
    (1, "Matemática", "Prof.ª Helena"),
    (2, "Português", "Prof. Ricardo"),
    (3, "Lógica de Programação", "Prof.ª Marina"),
    (4, "Ciências", "Prof. Jorge"),
]

def dias_de_aula(inicio: date, quantidade: int):
    d, dias = inicio, []
    while len(dias) < quantidade:
        if d.weekday() < 5:  # segunda a sexta
            dias.append(d.isoformat())
        d += timedelta(days=1)
    return dias

def main():
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.executescript("""
    PRAGMA foreign_keys = ON;

    CREATE TABLE alunos (
        id         INTEGER PRIMARY KEY,
        nome       TEXT    NOT NULL,
        turma      TEXT    NOT NULL,      -- '1A' ou '1B'
        idade      INTEGER NOT NULL,
        bairro     TEXT,
        atividade  TEXT                   -- atividade extra no contraturno
    );

    CREATE TABLE disciplinas (
        id         INTEGER PRIMARY KEY,
        nome       TEXT NOT NULL,
        professor  TEXT
    );

    CREATE TABLE notas (
        id             INTEGER PRIMARY KEY,
        aluno_id       INTEGER NOT NULL REFERENCES alunos(id) ON DELETE CASCADE,
        disciplina_id  INTEGER NOT NULL REFERENCES disciplinas(id),
        nota           REAL    NOT NULL CHECK (nota BETWEEN 0 AND 10),
        UNIQUE (aluno_id, disciplina_id)     -- uma nota por aluno em cada disciplina
    );

    CREATE TABLE frequencia (
        id         INTEGER PRIMARY KEY,
        aluno_id   INTEGER NOT NULL REFERENCES alunos(id) ON DELETE CASCADE,
        data_aula  TEXT    NOT NULL,      -- formato AAAA-MM-DD
        presente   INTEGER NOT NULL CHECK (presente IN (0, 1)),
        UNIQUE (aluno_id, data_aula)
    );

    -- Visão "boletim": junta as tabelas num formato fácil de consultar
    CREATE VIEW boletim AS
    SELECT a.id AS aluno_id, a.nome, a.turma, d.nome AS disciplina, n.nota
    FROM notas n
    JOIN alunos a      ON a.id = n.aluno_id
    JOIN disciplinas d ON d.id = n.disciplina_id;

    -- Visão "painel_turma": a MESMA tabela da aba Base_Turma da planilha.
    -- É a "planilha que o banco monta sozinho" (um JOIN guardado com nome).
    -- LEFT JOIN: aluno recém-cadastrado aparece mesmo sem notas.
    CREATE VIEW painel_turma AS
    WITH medias AS (
        SELECT aluno_id,
               MAX(CASE WHEN disciplina_id = 1 THEN nota END) AS matematica,
               MAX(CASE WHEN disciplina_id = 2 THEN nota END) AS portugues,
               MAX(CASE WHEN disciplina_id = 3 THEN nota END) AS logica,
               MAX(CASE WHEN disciplina_id = 4 THEN nota END) AS ciencias
        FROM notas GROUP BY aluno_id
    ),
    freq AS (
        SELECT aluno_id, COUNT(*) AS aulas, SUM(presente) AS presencas
        FROM frequencia GROUP BY aluno_id
    )
    SELECT a.id, a.nome, a.turma, a.idade, a.bairro, a.atividade,
           m.matematica, m.portugues, m.logica, m.ciencias,
           f.aulas, f.presencas,
           ROUND((m.matematica + m.portugues + m.logica + m.ciencias) / 4.0, 1) AS media_final,
           ROUND(100.0 * f.presencas / f.aulas, 1) AS frequencia_pct,
           CASE WHEN m.matematica IS NULL OR m.portugues IS NULL
                     OR m.logica IS NULL OR m.ciencias IS NULL THEN 'Sem notas'
                WHEN (m.matematica + m.portugues + m.logica + m.ciencias) / 4.0 >= 6
                THEN 'Aprovado' ELSE 'Recuperação' END AS situacao
    FROM alunos a
    LEFT JOIN medias m ON m.aluno_id = a.id
    LEFT JOIN freq   f ON f.aluno_id = a.id;
    """)

    cur.executemany("INSERT INTO disciplinas VALUES (?, ?, ?)", DISCIPLINAS)

    dias = dias_de_aula(date(2026, 8, 3), 30)
    for i, nome in enumerate(NOMES, start=1):
        turma = "1A" if i <= 16 else "1B"
        idade = random.choice([15, 15, 16, 16, 16, 17])
        cur.execute(
            "INSERT INTO alunos VALUES (?, ?, ?, ?, ?, ?)",
            (i, nome, turma, idade, random.choice(BAIRROS), random.choice(ATIVIDADES)),
        )
        talento = random.gauss(6.8, 1.5)
        for disc_id, *_ in DISCIPLINAS:
            afinidade = random.gauss(0, 0.9)
            provas = []
            for _ in range(3):  # três avaliações viram uma nota só
                bruto = talento + afinidade + random.gauss(0, 0.8)
                provas.append(max(0.0, min(10.0, round(bruto * 2) / 2)))
            cur.execute(
                "INSERT INTO notas (aluno_id, disciplina_id, nota) VALUES (?, ?, ?)",
                (i, disc_id, round(sum(provas) / 3, 1)),
            )
        assiduidade = random.choice([0.97, 0.93, 0.9, 0.88, 0.85, 0.8, 0.72, 0.65])
        for d in dias:
            cur.execute(
                "INSERT INTO frequencia (aluno_id, data_aula, presente) VALUES (?, ?, ?)",
                (i, d, 1 if random.random() < assiduidade else 0),
            )
    con.commit()
    con.close()
    print(f"Banco criado em: {DB}")

if __name__ == "__main__":
    main()
