#!/usr/bin/env python3
"""
Le os CSVs gerados pelo Locust e produz os graficos do relatorio em SVG.
"""

import csv
import html
import re
import sys
from pathlib import Path

RESULTS_DIR = Path("resultados")
OUTPUT_DIR = Path("graficos")
OUTPUT_DIR.mkdir(exist_ok=True)
SUMMARY_CSV = RESULTS_DIR / "resumo_testes.csv"

SCENARIOS = {
    "img1mb": "Post com imagem ~1MB",
    "text400": "Post com texto ~400KB",
    "img300": "Post com imagem ~300KB",
    "hybrid": "Carga hibrida dos tres posts",
}
USERS = []
INSTANCES = []
MAX_FAILURE_RATE = 12.0
STATS_RE = re.compile(r"^(?P<scenario>[a-z0-9]+)_u(?P<users>\d+)_i(?P<instances>\d+)_stats\.csv$")
SCENARIO_USERS = {}
SCENARIO_INSTANCES = {}


def ler_metricas(scenario: str, users: int, instances: int):
    path = RESULTS_DIR / f"{scenario}_u{users}_i{instances}_stats.csv"
    if not path.exists():
        return None, None, None

    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            if row.get("Name") == "Aggregated":
                p95 = float(row["95%"])
                rps = float(row["Requests/s"])
                request_count = float(row.get("Request Count", 0) or 0)
                failure_count = float(row.get("Failure Count", 0) or 0)
                failure_rate = (failure_count / request_count * 100) if request_count else 0.0
                return p95, rps, failure_rate
    return None, None, None


def descobrir_eixos():
    users = set()
    instances = set()
    scenario_users = {scenario: set() for scenario in SCENARIOS}
    scenario_instances = {scenario: set() for scenario in SCENARIOS}

    for path in RESULTS_DIR.glob("*_stats.csv"):
        match = STATS_RE.match(path.name)
        if not match:
            continue
        scenario = match.group("scenario")
        user = int(match.group("users"))
        instance = int(match.group("instances"))
        users.add(user)
        instances.add(instance)
        if scenario in scenario_users:
            scenario_users[scenario].add(user)
            scenario_instances[scenario].add(instance)

    return (
        sorted(users),
        sorted(instances),
        {scenario: sorted(values) for scenario, values in scenario_users.items()},
        {scenario: sorted(values) for scenario, values in scenario_instances.items()},
    )


def coletar_dados():
    global USERS
    global INSTANCES
    global SCENARIO_USERS
    global SCENARIO_INSTANCES

    USERS, INSTANCES, SCENARIO_USERS, SCENARIO_INSTANCES = descobrir_eixos()
    p95 = {s: {i: {} for i in INSTANCES} for s in SCENARIOS}
    rps = {s: {i: {} for i in INSTANCES} for s in SCENARIOS}
    falhas = {s: {i: {} for i in INSTANCES} for s in SCENARIOS}

    for scen in SCENARIOS:
        for inst in INSTANCES:
            for u in USERS:
                p, r, f = ler_metricas(scen, u, inst)
                if p is not None:
                    p95[scen][inst][u] = p
                    rps[scen][inst][u] = r
                    falhas[scen][inst][u] = f
    return p95, rps, falhas


def escape(value):
    return html.escape(str(value), quote=True)


def format_svg_text(x, y, text, size=12, weight="normal", anchor="start", fill="#222"):
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" '
        f'text-anchor="{anchor}" font-family="Arial, sans-serif" fill="{fill}">{escape(text)}</text>'
    )


def grouped_bar_chart(filename, title, x_label, y_label, categories, series, colors, y_max, threshold=None):
    width = 980
    height = 560
    margin_left = 90
    margin_right = 30
    margin_top = 70
    margin_bottom = 110
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    origin_x = margin_left
    origin_y = height - margin_bottom

    y_max = max(y_max, 1.0)
    grid_steps = 5
    group_count = len(categories)
    series_count = len(series)
    group_width = plot_width / max(group_count, 1)
    bar_width = min(42.0, group_width / max(series_count + 1, 2))

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        format_svg_text(width / 2, 34, title, size=22, weight="bold", anchor="middle"),
        format_svg_text(width / 2, height - 18, x_label, size=14, anchor="middle"),
        f'<g transform="translate(24,{height / 2:.1f}) rotate(-90)">{format_svg_text(0, 0, y_label, size=14, anchor="middle")}</g>',
        f'<line x1="{origin_x}" y1="{origin_y}" x2="{origin_x + plot_width}" y2="{origin_y}" stroke="#333" stroke-width="1.2"/>',
        f'<line x1="{origin_x}" y1="{origin_y}" x2="{origin_x}" y2="{margin_top}" stroke="#333" stroke-width="1.2"/>',
    ]

    for idx in range(grid_steps + 1):
        value = y_max * idx / grid_steps
        y = origin_y - (plot_height * idx / grid_steps)
        parts.append(f'<line x1="{origin_x}" y1="{y:.1f}" x2="{origin_x + plot_width}" y2="{y:.1f}" stroke="#d8dee4" stroke-width="1"/>')
        parts.append(format_svg_text(origin_x - 12, y + 4, f"{value:.1f}", size=11, anchor="end", fill="#555"))

    if threshold is not None:
        threshold_y = origin_y - (threshold / y_max) * plot_height
        parts.append(
            f'<line x1="{origin_x}" y1="{threshold_y:.1f}" x2="{origin_x + plot_width}" y2="{threshold_y:.1f}" '
            'stroke="#b22222" stroke-width="2" stroke-dasharray="7 5"/>'
        )

    for group_index, category in enumerate(categories):
        center_x = origin_x + group_width * (group_index + 0.5)
        total_series_width = series_count * bar_width
        first_bar_x = center_x - total_series_width / 2

        for series_index, (label, values) in enumerate(series):
            value = values[group_index]
            if value is None:
                continue
            bar_height = 0 if y_max == 0 else (value / y_max) * plot_height
            x = first_bar_x + series_index * bar_width
            y = origin_y - bar_height
            color = colors[series_index % len(colors)]
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width - 4:.1f}" height="{bar_height:.1f}" '
                f'fill="{color}" stroke="#333" stroke-width="0.8"/>'
            )

        parts.append(format_svg_text(center_x, origin_y + 24, category, size=12, anchor="middle"))

    legend_x = origin_x + plot_width - 200
    legend_y = margin_top - 18
    for idx, (label, _) in enumerate(series):
        y = legend_y + idx * 22
        parts.append(f'<rect x="{legend_x}" y="{y - 10}" width="14" height="14" fill="{colors[idx % len(colors)]}" stroke="#333" stroke-width="0.6"/>')
        parts.append(format_svg_text(legend_x + 22, y + 1, label, size=12))

    if threshold is not None:
        y = legend_y + len(series) * 22
        parts.append(f'<line x1="{legend_x}" y1="{y - 3}" x2="{legend_x + 14}" y2="{y - 3}" stroke="#b22222" stroke-width="2" stroke-dasharray="7 5"/>')
        parts.append(format_svg_text(legend_x + 22, y + 1, "Limite de falhas (12%)", size=12))

    parts.append("</svg>")
    filename.write_text("\n".join(parts), encoding="utf-8")
    print(f"[ok] {filename}")


def grafico_p95_vs_usuarios(p95, scenario):
    scenario_users = SCENARIO_USERS[scenario]
    series = []
    colors = ["#a8d0e6", "#fde2a7", "#f4a6a6"]
    values_all = []
    for inst in INSTANCES:
        values = []
        for u in scenario_users:
            raw = p95[scenario][inst].get(u)
            values.append((raw / 1000) if raw is not None else None)
            if raw is not None:
                values_all.append(raw / 1000)
        series.append((f"{inst} instância{'s' if inst > 1 else ''}", values))

    grouped_bar_chart(
        OUTPUT_DIR / f"p95_{scenario}.svg",
        f"Latência p95 — {SCENARIOS[scenario]}",
        "Número de usuários",
        "p95 de resposta (s)",
        [str(u) for u in scenario_users],
        series,
        colors,
        max(values_all) * 1.15,
    )


def grafico_falhas_vs_usuarios(falhas, scenario):
    scenario_users = SCENARIO_USERS[scenario]
    series = []
    colors = ["#f6bd60", "#84a59d", "#f28482"]
    values_all = []
    for inst in INSTANCES:
        values = []
        for u in scenario_users:
            raw = falhas[scenario][inst].get(u)
            values.append(raw if raw is not None else None)
            if raw is not None:
                values_all.append(raw)
        series.append((f"{inst} instância{'s' if inst > 1 else ''}", values))

    grouped_bar_chart(
        OUTPUT_DIR / f"falhas_{scenario}.svg",
        f"Falhas agregadas — {SCENARIOS[scenario]}",
        "Número de usuários",
        "Taxa de falhas (%)",
        [str(u) for u in scenario_users],
        series,
        colors,
        max(max(values_all) * 1.2, MAX_FAILURE_RATE * 1.25),
        threshold=MAX_FAILURE_RATE,
    )


def grafico_rps_vs_instancias(rps, scenario):
    scenario_users = SCENARIO_USERS[scenario]
    series = []
    colors = ["#c8e3c5", "#bdd7e4", "#fce5b6"]
    values_all = []
    for users in scenario_users:
        values = []
        for inst in INSTANCES:
            raw = rps[scenario][inst].get(users)
            values.append(raw if raw is not None else None)
            if raw is not None:
                values_all.append(raw)
        series.append((f"{users} usuários", values))

    grouped_bar_chart(
        OUTPUT_DIR / f"rps_{scenario}.svg",
        f"Throughput — {SCENARIOS[scenario]}",
        "Número de instâncias",
        "Requisições por segundo",
        [str(inst) for inst in INSTANCES],
        series,
        colors,
        max(values_all) * 1.15,
    )


def status_for(scenario, users, failure):
    if isinstance(failure, float) and (scenario == "hybrid" or users == max(SCENARIO_USERS[scenario])) and failure > MAX_FAILURE_RATE:
        return "ACIMA"
    return "OK"


def imprimir_tabela(p95, rps, falhas):
    print("\n=== TABELA RESUMO ===")
    print(
        f"{'Cenario':<10} {'Inst':<5} {'Users':<6} "
        f"{'p95 (ms)':<10} {'RPS':<8} {'Falhas %':<10} {'Status':<8}"
    )
    for scen in SCENARIOS:
            for inst in INSTANCES:
                for u in SCENARIO_USERS[scen]:
                    if u not in p95[scen][inst]:
                        continue
                    p = p95[scen][inst].get(u, "-")
                    r = rps[scen][inst].get(u, "-")
                    f = falhas[scen][inst].get(u, "-")
                p_str = f"{p:.1f}" if isinstance(p, float) else p
                r_str = f"{r:.2f}" if isinstance(r, float) else r
                f_str = f"{f:.2f}" if isinstance(f, float) else f
                print(f"{scen:<10} {inst:<5} {u:<6} {p_str:<10} {r_str:<8} {f_str:<10} {status_for(scen, u, f):<8}")


def salvar_tabela_csv(p95, rps, falhas):
    with SUMMARY_CSV.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "cenario",
            "instancias",
            "usuarios",
            "p95_ms",
            "requests_per_sec",
            "failure_rate_percent",
            "status",
        ])

        for scen in SCENARIOS:
            for inst in INSTANCES:
                for u in SCENARIO_USERS[scen]:
                    if u not in p95[scen][inst]:
                        continue
                    p = p95[scen][inst].get(u)
                    r = rps[scen][inst].get(u)
                    failure = falhas[scen][inst].get(u)
                    writer.writerow([
                        scen,
                        inst,
                        u,
                        f"{p:.1f}" if isinstance(p, float) else "",
                        f"{r:.2f}" if isinstance(r, float) else "",
                        f"{failure:.2f}" if isinstance(failure, float) else "",
                        status_for(scen, u, failure),
                    ])

    print(f"[ok] {SUMMARY_CSV}")


def main():
    if not RESULTS_DIR.exists():
        print(f"Erro: diretorio {RESULTS_DIR} nao existe. Rode primeiro os testes.")
        sys.exit(1)

    p95, rps, falhas = coletar_dados()
    if not USERS or not INSTANCES:
        print("Erro: nenhum CSV de estatisticas encontrado em resultados/.")
        sys.exit(1)

    for scen in SCENARIOS:
        grafico_p95_vs_usuarios(p95, scen)
        grafico_falhas_vs_usuarios(falhas, scen)
        grafico_rps_vs_instancias(rps, scen)

    imprimir_tabela(p95, rps, falhas)
    salvar_tabela_csv(p95, rps, falhas)
    print(f"\nGraficos salvos em: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
