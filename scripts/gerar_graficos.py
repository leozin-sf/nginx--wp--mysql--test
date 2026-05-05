#!/usr/bin/env python3
"""
Le os CSVs gerados pelo Locust e produz os graficos do relatorio.

Para cada cenario gera dois graficos:
  - Tempo medio de resposta (ms) X numero de usuarios, agrupado por instancias
  - Requisicoes por segundo X numero de instancias, agrupado por usuarios

Os arquivos CSV do Locust seguem o padrao:
  <prefix>_stats.csv  -> estatisticas agregadas
  <prefix>_failures.csv
  <prefix>_stats_history.csv
  <prefix>_exceptions.csv

Usamos o _stats.csv e pegamos a linha "Aggregated" (resumo do teste).
"""

import csv
import os
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

RESULTS_DIR = Path("resultados")
OUTPUT_DIR = Path("graficos")
OUTPUT_DIR.mkdir(exist_ok=True)

SCENARIOS = {
    "img1mb": "Post com imagem ~1MB",
    "text400": "Post com texto ~400KB",
    "img300": "Post com imagem ~300KB",
}
USERS = [10, 100, 1000]
INSTANCES = [1, 2, 3]


def ler_metricas(scenario: str, users: int, instances: int):
    """Le o CSV _stats.csv de um teste e devolve (avg_response_ms, rps)."""
    path = RESULTS_DIR / f"{scenario}_u{users}_i{instances}_stats.csv"
    if not path.exists():
        print(f"[aviso] arquivo nao encontrado: {path}")
        return None, None

    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            # A linha "Aggregated" agrega todas as requisicoes do teste
            if row.get("Name") == "Aggregated":
                avg = float(row["Average Response Time"])
                rps = float(row["Requests/s"])
                return avg, rps
        # fallback: pega a primeira linha
        f.seek(0)
        reader = csv.DictReader(f)
        first = next(reader, None)
        if first:
            return float(first["Average Response Time"]), float(first["Requests/s"])
    return None, None


def coletar_dados():
    """Monta dois dicionarios: tempo[scenario][instances][users] e rps[...]."""
    tempo = {s: {i: {} for i in INSTANCES} for s in SCENARIOS}
    rps = {s: {i: {} for i in INSTANCES} for s in SCENARIOS}

    for scen in SCENARIOS:
        for inst in INSTANCES:
            for u in USERS:
                t, r = ler_metricas(scen, u, inst)
                if t is not None:
                    tempo[scen][inst][u] = t
                    rps[scen][inst][u] = r
    return tempo, rps


def grafico_tempo_vs_usuarios(tempo, scenario):
    """Grafico estilo PDF: tempo de resposta X usuarios, barras por instancia."""
    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(len(USERS))
    width = 0.25

    cores = ["#a8d0e6", "#fde2a7", "#f4a6a6"]  # cores parecidas com o PDF
    for i, inst in enumerate(INSTANCES):
        valores = [tempo[scenario][inst].get(u, 0) / 1000 for u in USERS]  # ms -> s
        ax.bar(x + i * width, valores, width,
               label=f"{inst} instância{'s' if inst > 1 else ''}",
               color=cores[i], edgecolor="black", linewidth=0.5)

    ax.set_xlabel("Número de usuários")
    ax.set_ylabel("Tempo de resposta (s)")
    ax.set_title(f"Tempo de resposta — {SCENARIOS[scenario]}")
    ax.set_xticks(x + width)
    ax.set_xticklabels(USERS)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    out = OUTPUT_DIR / f"tempo_{scenario}.png"
    plt.tight_layout()
    plt.savefig(out, dpi=130)
    plt.close()
    print(f"[ok] {out}")


def grafico_rps_vs_instancias(rps, scenario):
    """Grafico estilo PDF: RPS X numero de instancias, barras por usuarios."""
    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(len(INSTANCES))
    width = 0.25

    cores = ["#c8e3c5", "#bdd7e4", "#fce5b6"]
    for i, u in enumerate(USERS):
        valores = [rps[scenario][inst].get(u, 0) for inst in INSTANCES]
        ax.bar(x + i * width, valores, width,
               label=f"{u} usuários",
               color=cores[i], edgecolor="black", linewidth=0.5)

    ax.set_xlabel("Número de instâncias")
    ax.set_ylabel("Requisições por segundo")
    ax.set_title(f"Throughput — {SCENARIOS[scenario]}")
    ax.set_xticks(x + width)
    ax.set_xticklabels(INSTANCES)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    out = OUTPUT_DIR / f"rps_{scenario}.png"
    plt.tight_layout()
    plt.savefig(out, dpi=130)
    plt.close()
    print(f"[ok] {out}")


def imprimir_tabela(tempo, rps):
    """Imprime tabela resumo no console (util para o relatorio)."""
    print("\n=== TABELA RESUMO ===")
    print(f"{'Cenario':<10} {'Inst':<5} {'Users':<6} {'Tempo (ms)':<12} {'RPS':<8}")
    for scen in SCENARIOS:
        for inst in INSTANCES:
            for u in USERS:
                t = tempo[scen][inst].get(u, "-")
                r = rps[scen][inst].get(u, "-")
                t_str = f"{t:.1f}" if isinstance(t, float) else t
                r_str = f"{r:.2f}" if isinstance(r, float) else r
                print(f"{scen:<10} {inst:<5} {u:<6} {t_str:<12} {r_str:<8}")


def main():
    if not RESULTS_DIR.exists():
        print(f"Erro: diretorio {RESULTS_DIR} nao existe. Rode primeiro os testes.")
        sys.exit(1)

    tempo, rps = coletar_dados()

    for scen in SCENARIOS:
        grafico_tempo_vs_usuarios(tempo, scen)
        grafico_rps_vs_instancias(rps, scen)

    imprimir_tabela(tempo, rps)
    print(f"\nGraficos salvos em: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
