#!/usr/bin/env python3
"""
Le os CSVs gerados pelo Locust e produz graficos em SVG.
Compara o peso do conteudo mantendo a mesma quantidade de usuarios.
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

SCENARIO_ORDER = ["img300", "text400", "img1mb", "hybrid"]
SCENARIOS = {
    "img300": {
        "short": "Imagem 300 KB",
        "long": "Post com imagem ~300 KB",
    },
    "text400": {
        "short": "Texto 400 KB",
        "long": "Post com texto ~400 KB",
    },
    "img1mb": {
        "short": "Imagem 1 MB",
        "long": "Post com imagem ~1 MB",
    },
    "hybrid": {
        "short": "Hibrido",
        "long": "Carga hibrida dos tres posts",
    },
}
MAX_FAILURE_RATE = 12.0
STATS_RE = re.compile(r"^(?P<scenario>[a-z0-9]+)_u(?P<users>\d+)_i(?P<instances>\d+)_stats\.csv$")

USERS = []
INSTANCES = []


def ler_metricas(scenario: str, users: int, instances: int):
    path = RESULTS_DIR / f"{scenario}_u{users}_i{instances}_stats.csv"
    if not path.exists():
        return None, None, None

    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            if row.get("Name") != "Aggregated":
                continue
            p95 = float(row["95%"])
            rps = float(row["Requests/s"])
            request_count = float(row.get("Request Count", 0) or 0)
            failure_count = float(row.get("Failure Count", 0) or 0)
            failure_rate = (failure_count / request_count * 100) if request_count else 0.0
            return p95, rps, failure_rate

    return None, None, None


def descobrir_eixos():
    user_counts = {}
    instances = set()

    for path in RESULTS_DIR.glob("*_stats.csv"):
        match = STATS_RE.match(path.name)
        if not match:
            continue
        scenario = match.group("scenario")
        if scenario not in SCENARIOS:
            continue
        users = int(match.group("users"))
        user_counts[users] = user_counts.get(users, 0) + 1
        instances.add(int(match.group("instances")))

    ordered_users = sorted(
        user_counts,
        key=lambda user: (-user_counts[user], user),
    )
    selected_users = sorted(ordered_users[:3])

    return selected_users, sorted(instances)


def coletar_dados():
    global USERS
    global INSTANCES

    USERS, INSTANCES = descobrir_eixos()
    p95 = {scenario: {inst: {} for inst in INSTANCES} for scenario in SCENARIO_ORDER}
    rps = {scenario: {inst: {} for inst in INSTANCES} for scenario in SCENARIO_ORDER}
    falhas = {scenario: {inst: {} for inst in INSTANCES} for scenario in SCENARIO_ORDER}

    for scenario in SCENARIO_ORDER:
        for inst in INSTANCES:
            for users in USERS:
                p95_value, rps_value, falhas_value = ler_metricas(scenario, users, inst)
                if p95_value is None:
                    continue
                p95[scenario][inst][users] = p95_value
                rps[scenario][inst][users] = rps_value
                falhas[scenario][inst][users] = falhas_value

    return p95, rps, falhas


def escape(value):
    return html.escape(str(value), quote=True)


def format_svg_text(x, y, text, size=12, weight="normal", anchor="start", fill="#222"):
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" font-weight="{weight}" '
        f'text-anchor="{anchor}" font-family="Arial, sans-serif" fill="{fill}">{escape(text)}</text>'
    )


def grouped_bar_chart(filename, title, subtitle, x_label, y_label, categories, series, colors, y_max, threshold=None):
    width = 980
    height = 580
    margin_left = 90
    margin_right = 30
    margin_top = 84
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
        format_svg_text(width / 2, 58, subtitle, size=12, anchor="middle", fill="#556"),
        format_svg_text(width / 2, height - 18, x_label, size=14, anchor="middle"),
        f'<g transform="translate(24,{height / 2:.1f}) rotate(-90)">{format_svg_text(0, 0, y_label, size=14, anchor="middle")}</g>',
        f'<line x1="{origin_x}" y1="{origin_y}" x2="{origin_x + plot_width}" y2="{origin_y}" stroke="#333" stroke-width="1.2"/>',
        f'<line x1="{origin_x}" y1="{origin_y}" x2="{origin_x}" y2="{margin_top}" stroke="#333" stroke-width="1.2"/>',
    ]

    for idx in range(grid_steps + 1):
        value = y_max * idx / grid_steps
        y = origin_y - (plot_height * idx / grid_steps)
        parts.append(
            f'<line x1="{origin_x}" y1="{y:.1f}" x2="{origin_x + plot_width}" y2="{y:.1f}" stroke="#d8dee4" stroke-width="1"/>'
        )
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
    legend_y = margin_top - 24
    for idx, (label, _) in enumerate(series):
        y = legend_y + idx * 22
        parts.append(
            f'<rect x="{legend_x}" y="{y - 10}" width="14" height="14" fill="{colors[idx % len(colors)]}" stroke="#333" stroke-width="0.6"/>'
        )
        parts.append(format_svg_text(legend_x + 22, y + 1, label, size=12))

    if threshold is not None:
        y = legend_y + len(series) * 22
        parts.append(
            f'<line x1="{legend_x}" y1="{y - 3}" x2="{legend_x + 14}" y2="{y - 3}" stroke="#b22222" stroke-width="2" stroke-dasharray="7 5"/>'
        )
        parts.append(format_svg_text(legend_x + 22, y + 1, "Limite de falhas (12%)", size=12))

    parts.append("</svg>")
    filename.write_text("\n".join(parts), encoding="utf-8")
    print(f"[ok] {filename}")


def valores_presentes(series):
    values = []
    for _, serie_values in series:
        values.extend(value for value in serie_values if value is not None)
    return values


def rotulo_carga(users):
    if not USERS:
        return f"{users} usuarios"

    ordered = sorted(USERS)
    if len(ordered) >= 3:
        if users == ordered[0]:
            return f"Carga leve ({users} usuarios)"
        if users == ordered[1]:
            return f"Carga media ({users} usuarios)"
        if users == ordered[-1]:
            return f"Carga pesada ({users} usuarios)"
    return f"{users} usuarios"


def categorias_por_peso(dados, users):
    categories = []
    scenario_keys = []
    for scenario in SCENARIO_ORDER:
        if any(users in dados[scenario][inst] for inst in INSTANCES):
            categories.append(SCENARIOS[scenario]["short"])
            scenario_keys.append(scenario)
    return categories, scenario_keys


def grafico_metrica_por_peso(metric_data, filename_prefix, title, y_label, colors, converter=None, threshold=None):
    for users in USERS:
        categories, scenario_keys = categorias_por_peso(metric_data, users)
        if not categories:
            continue

        series = []
        for inst in INSTANCES:
            values = []
            for scenario in scenario_keys:
                raw = metric_data[scenario][inst].get(users)
                value = converter(raw) if converter and raw is not None else raw
                values.append(value if raw is not None else None)
            series.append((f"{inst} instancia{'s' if inst > 1 else ''}", values))

        values_all = valores_presentes(series)
        if not values_all:
            continue

        grouped_bar_chart(
            OUTPUT_DIR / f"{filename_prefix}_u{users}.svg",
            title,
            f"Comparacao por peso com a mesma quantidade de usuarios: {rotulo_carga(users)}",
            "Peso do conteudo",
            y_label,
            categories,
            series,
            colors,
            max(values_all) * 1.15,
            threshold=threshold,
        )


def status_for(failure):
    if isinstance(failure, float) and failure > MAX_FAILURE_RATE:
        return "ACIMA"
    return "OK"


def imprimir_tabela(p95, rps, falhas):
    print("\n=== TABELA RESUMO ===")
    print(
        f"{'Carga':<28} {'Users':<6} {'Inst':<5} {'Peso':<14} "
        f"{'p95 (ms)':<10} {'RPS':<8} {'Falhas %':<10} {'Status':<8}"
    )

    for users in USERS:
        for inst in INSTANCES:
            for scenario in SCENARIO_ORDER:
                if users not in p95[scenario][inst]:
                    continue
                p = p95[scenario][inst].get(users, "-")
                r = rps[scenario][inst].get(users, "-")
                f = falhas[scenario][inst].get(users, "-")
                p_str = f"{p:.1f}" if isinstance(p, float) else p
                r_str = f"{r:.2f}" if isinstance(r, float) else r
                f_str = f"{f:.2f}" if isinstance(f, float) else f
                print(
                    f"{rotulo_carga(users):<28} {users:<6} {inst:<5} {SCENARIOS[scenario]['short']:<14} "
                    f"{p_str:<10} {r_str:<8} {f_str:<10} {status_for(f):<8}"
                )


def salvar_tabela_csv(p95, rps, falhas):
    with SUMMARY_CSV.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "carga",
            "cenario",
            "peso_label",
            "instancias",
            "usuarios",
            "p95_ms",
            "requests_per_sec",
            "failure_rate_percent",
            "status",
        ])

        for users in USERS:
            for inst in INSTANCES:
                for scenario in SCENARIO_ORDER:
                    if users not in p95[scenario][inst]:
                        continue
                    p = p95[scenario][inst].get(users)
                    r = rps[scenario][inst].get(users)
                    failure = falhas[scenario][inst].get(users)
                    writer.writerow([
                        rotulo_carga(users),
                        scenario,
                        SCENARIOS[scenario]["short"],
                        inst,
                        users,
                        f"{p:.1f}" if isinstance(p, float) else "",
                        f"{r:.2f}" if isinstance(r, float) else "",
                        f"{failure:.2f}" if isinstance(failure, float) else "",
                        status_for(failure),
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

    grafico_metrica_por_peso(
        p95,
        "p95_por_peso",
        "Latencia p95 por peso de conteudo",
        "p95 de resposta (s)",
        ["#a8d0e6", "#fde2a7", "#f4a6a6"],
        converter=lambda raw: raw / 1000,
    )
    grafico_metrica_por_peso(
        falhas,
        "falhas_por_peso",
        "Falhas por peso de conteudo",
        "Taxa de falhas (%)",
        ["#f6bd60", "#84a59d", "#f28482"],
        threshold=MAX_FAILURE_RATE,
    )
    grafico_metrica_por_peso(
        rps,
        "rps_por_peso",
        "Throughput por peso de conteudo",
        "Requisicoes por segundo",
        ["#c8e3c5", "#bdd7e4", "#fce5b6"],
    )

    imprimir_tabela(p95, rps, falhas)
    salvar_tabela_csv(p95, rps, falhas)
    print(f"\nGraficos salvos em: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
