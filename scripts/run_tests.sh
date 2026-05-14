#!/usr/bin/env bash
# =============================================================================
# Script de execucao automatica dos testes de carga
# Primeiro calibra a carga pesada e depois executa a bateria principal.
# =============================================================================

set -e

# --- CONFIGURACAO ---------------------------------------------------------
# IDs dos posts criados no WordPress.
# IMPORTANTE: edite esses valores apos criar os posts no painel do WordPress.
export POST_ID_IMG1MB="${POST_ID_IMG1MB:-2}"   # post com imagem ~1MB
export POST_ID_TEXT400="${POST_ID_TEXT400:-3}" # post com texto ~400KB
export POST_ID_IMG300="${POST_ID_IMG300:-4}"   # post com imagem ~300KB

# Duracao de cada teste (segundos). 75s deixa o p95 mais estavel.
DURATION="${DURATION:-75s}"

# Perfil calibrado para WSL com 6 GB de RAM e 6 nucleos.
# Evita os picos de erro observados com 1000 usuarios.
SPAWN_RATE="${SPAWN_RATE:-6}"
WAIT_MIN_SECONDS="${WAIT_MIN_SECONDS:-1.5}"
WAIT_MAX_SECONDS="${WAIT_MAX_SECONDS:-3.0}"
MAX_FAILURE_RATE="${MAX_FAILURE_RATE:-12}"
MIN_FAILURE_RATE_HIGH="${MIN_FAILURE_RATE_HIGH:-1}"
HEAVY_SPAWN_RATE="${HEAVY_SPAWN_RATE:-8}"
HEAVY_WAIT_MIN_SECONDS="${HEAVY_WAIT_MIN_SECONDS:-1.0}"
HEAVY_WAIT_MAX_SECONDS="${HEAVY_WAIT_MAX_SECONDS:-2.0}"
MAX_TUNING_ATTEMPTS="${MAX_TUNING_ATTEMPTS:-2}"
SKIP_EXISTING="${SKIP_EXISTING:-1}"
HEAVY_USERS_PRIMARY="${HEAVY_USERS_PRIMARY:-300}"
HEAVY_USERS_FALLBACK="${HEAVY_USERS_FALLBACK:-300}"
LIGHT_USERS="${LIGHT_USERS:-24}"
MEDIUM_USERS="${MEDIUM_USERS:-96}"
HEAVY_DISCOVERY_INSTANCES="${HEAVY_DISCOVERY_INSTANCES:-1}"
HEAVY_DISCOVERY_SCENARIOS=(${HEAVY_DISCOVERY_SCENARIOS:-img1mb hybrid})
HEAVY_USER_CANDIDATES=("$HEAVY_USERS_PRIMARY")
if [[ "$HEAVY_USERS_FALLBACK" -gt "$HEAVY_USERS_PRIMARY" ]]; then
    HEAVY_USER_CANDIDATES+=("$HEAVY_USERS_FALLBACK")
fi

# Listas de variacao
SCENARIOS=("img1mb" "text400" "img300" "hybrid")
INSTANCES=(1 2 3)

RESULTS_DIR="./resultados"
NGINX_DIR="./nginx_configs"

# --------------------------------------------------------------------------

mkdir -p "$RESULTS_DIR"

failure_rate_for() {
    local stats_file="$1"
    python3 - "$stats_file" <<'PY'
import csv
import sys

path = sys.argv[1]
with open(path, newline="") as f:
    for row in csv.DictReader(f):
        if row.get("Name") == "Aggregated":
            requests = float(row.get("Request Count", 0) or 0)
            failures = float(row.get("Failure Count", 0) or 0)
            rate = (failures / requests * 100) if requests else 0.0
            print(f"{rate:.2f}")
            break
    else:
        print("0.00")
PY
}

should_enforce_failure_cap() {
    local users="$2"
    [[ "${HEAVY_USERS_SELECTED:-$HEAVY_USERS_PRIMARY}" -eq "$users" ]]
}

stats_file_is_complete() {
    local stats_file="$1"
    [[ -f "$stats_file" ]] || return 1

    python3 - "$stats_file" <<'PY'
import csv
import sys

with open(sys.argv[1], newline="") as f:
    for row in csv.DictReader(f):
        if row.get("Name") == "Aggregated":
            sys.exit(0)
sys.exit(1)
PY
}

run_locust_test() {
    local scenario="$1"
    local users="$2"
    local instances="$3"
    local csv_prefix="$4"
    local spawn_rate="$5"
    local wait_min="$6"
    local wait_max="$7"

    docker compose run --rm \
        -e SCENARIO="$scenario" \
        -e POST_ID_IMG1MB="$POST_ID_IMG1MB" \
        -e POST_ID_TEXT400="$POST_ID_TEXT400" \
        -e POST_ID_IMG300="$POST_ID_IMG300" \
        -e WAIT_MIN_SECONDS="$wait_min" \
        -e WAIT_MAX_SECONDS="$wait_max" \
        locust \
        -f /mnt/locust/locustfile.py \
        --headless \
        -u "$users" \
        -r "$spawn_rate" \
        -t "$DURATION" \
        --host=http://nginx \
        --csv="$csv_prefix" \
        --only-summary
}

tune_failure_band() {
    local scenario="$1"
    local users="$2"
    local instances="$3"
    local tag="$4"
    local csv_prefix="$5"
    local stats_file="$6"

    local spawn_rate="$HEAVY_SPAWN_RATE"
    local wait_min="$HEAVY_WAIT_MIN_SECONDS"
    local wait_max="$HEAVY_WAIT_MAX_SECONDS"
    local failure_rate="0.00"

    for attempt in $(seq 1 "$MAX_TUNING_ATTEMPTS"); do
        echo "[ajuste] tentativa $attempt para manter falhas entre ${MIN_FAILURE_RATE_HIGH}% e ${MAX_FAILURE_RATE}%" >&2
        if ! run_locust_test "$scenario" "$users" "$instances" "$csv_prefix" "$spawn_rate" "$wait_min" "$wait_max"; then
            echo "[aviso] teste $tag terminou com erro na tentativa $attempt" >&2
        fi

        if [[ ! -f "$stats_file" ]]; then
            echo "[alerta] arquivo de estatisticas nao foi gerado para $tag" >&2
            break
        fi

        failure_rate="$(failure_rate_for "$stats_file")"
        echo "[ajuste] spawn=$spawn_rate wait=${wait_min}-${wait_max}s falhas=${failure_rate}%" >&2

        if python3 - "$failure_rate" "$MIN_FAILURE_RATE_HIGH" "$MAX_FAILURE_RATE" <<'PY'
import sys
rate = float(sys.argv[1])
min_rate = float(sys.argv[2])
max_rate = float(sys.argv[3])
sys.exit(0 if min_rate <= rate <= max_rate else 1)
PY
        then
            break
        fi

        if python3 - "$failure_rate" "$MIN_FAILURE_RATE_HIGH" <<'PY'
import sys
sys.exit(0 if float(sys.argv[1]) < float(sys.argv[2]) else 1)
PY
        then
            spawn_rate=$((spawn_rate + 1))
            wait_min=$(python3 - "$wait_min" <<'PY'
import sys
print(f"{max(0.3, float(sys.argv[1]) - 0.2):.1f}")
PY
)
            wait_max=$(python3 - "$wait_max" <<'PY'
import sys
print(f"{max(0.8, float(sys.argv[1]) - 0.2):.1f}")
PY
)
        else
            spawn_rate=$((spawn_rate > 2 ? spawn_rate - 1 : 2))
            wait_min=$(python3 - "$wait_min" <<'PY'
import sys
print(f"{float(sys.argv[1]) + 0.4:.1f}")
PY
)
            wait_max=$(python3 - "$wait_max" <<'PY'
import sys
print(f"{float(sys.argv[1]) + 0.6:.1f}")
PY
)
        fi
    done

    echo "$failure_rate"
}

is_failure_in_band() {
    local failure_rate="$1"
    python3 - "$failure_rate" "$MIN_FAILURE_RATE_HIGH" "$MAX_FAILURE_RATE" <<'PY'
import sys
rate = float(sys.argv[1])
min_rate = float(sys.argv[2])
max_rate = float(sys.argv[3])
sys.exit(0 if min_rate <= rate <= max_rate else 1)
PY
}

discover_heavy_users() {
    local selected="${HEAVY_USER_CANDIDATES[0]}"
    local best_rate="-1"

    echo "============================================================" >&2
    echo "  Descobrindo a carga pesada de referencia" >&2
    echo "  Candidatos: ${HEAVY_USER_CANDIDATES[*]}" >&2
    echo "  Cenarios de calibracao: ${HEAVY_DISCOVERY_SCENARIOS[*]}" >&2
    echo "============================================================" >&2

    for candidate in "${HEAVY_USER_CANDIDATES[@]}"; do
        for scenario in "${HEAVY_DISCOVERY_SCENARIOS[@]}"; do
            local probe_tag="probe_${scenario}_u${candidate}_i${HEAVY_DISCOVERY_INSTANCES}"
            local probe_prefix="/mnt/resultados/${probe_tag}"
            local probe_stats_file="${RESULTS_DIR}/${probe_tag}_stats.csv"
            local failure_rate

            echo "[probe] cenario=$scenario | usuarios=$candidate | instancias=$HEAVY_DISCOVERY_INSTANCES" >&2
            failure_rate="$(
                tune_failure_band \
                    "$scenario" \
                    "$candidate" \
                    "$HEAVY_DISCOVERY_INSTANCES" \
                    "$probe_tag" \
                    "$probe_prefix" \
                    "$probe_stats_file"
            )"

            echo "[probe] taxa de falhas agregada: ${failure_rate}%" >&2

            if python3 - "$failure_rate" "$best_rate" <<'PY'
import sys
sys.exit(0 if float(sys.argv[1]) > float(sys.argv[2]) else 1)
PY
            then
                best_rate="$failure_rate"
                selected="$candidate"
            fi

            if is_failure_in_band "$failure_rate"; then
                echo "[probe] carga pesada escolhida: ${candidate} usuarios" >&2
                echo "$candidate"
                return
            fi
        done
    done

    echo "[probe] nenhuma combinacao caiu exatamente na faixa; usando melhor candidato observado: ${selected} usuarios" >&2
    echo "$selected"
}

echo "============================================================"
echo "  Iniciando calibracao e bateria principal de testes"
echo "  Duracao por teste: $DURATION"
echo "  p95 como metrica principal de latencia"
echo "  Faixa de falhas desejada para carga alta/hibrida: ${MIN_FAILURE_RATE_HIGH}% a ${MAX_FAILURE_RATE}%"
echo "  Limite de falhas para cenarios pesados/hibridos: ${MAX_FAILURE_RATE}%"
echo "  Usuarios leve/medio candidatos: ${LIGHT_USERS}/${MEDIUM_USERS}"
echo "  Carga pesada primaria: ${HEAVY_USERS_PRIMARY} usuarios"
echo "  Fallback de carga pesada: ${HEAVY_USERS_FALLBACK} usuarios"
echo "  Pular testes ja concluidos: ${SKIP_EXISTING}"
echo "  Post IDs: img1mb=$POST_ID_IMG1MB | text400=$POST_ID_TEXT400 | img300=$POST_ID_IMG300"
echo "============================================================"

# Sobe o stack base (mysql + 3 wordpress) uma unica vez
echo "[setup] Subindo MySQL e instancias do WordPress..."
docker compose up -d mysql wordpress1 wordpress2 wordpress3
sleep 5

HEAVY_USERS_SELECTED="$(discover_heavy_users)"
USERS=("$LIGHT_USERS" "$MEDIUM_USERS" "$HEAVY_USERS_SELECTED")

echo "============================================================"
echo "  Bateria principal: ${#SCENARIOS[@]} cenarios x ${#USERS[@]} cargas x ${#INSTANCES[@]} instancias = $((${#SCENARIOS[@]} * ${#USERS[@]} * ${#INSTANCES[@]})) testes"
echo "  Carga pesada selecionada: ${HEAVY_USERS_SELECTED} usuarios"
echo "  Cargas avaliadas: ${USERS[*]}"
echo "============================================================"

for INST in "${INSTANCES[@]}"; do
    echo ""
    echo "============================================================"
    echo "  Configurando NGINX para $INST instancia(s)"
    echo "============================================================"

    # Troca a configuracao do nginx
    cp "$NGINX_DIR/nginx_${INST}.conf" ./nginx.conf

    # Recria o nginx para pegar a nova config
    docker compose up -d --force-recreate nginx
    sleep 4  # espera nginx ficar pronto

    for SCEN in "${SCENARIOS[@]}"; do
        for U in "${USERS[@]}"; do
            TAG="${SCEN}_u${U}_i${INST}"
            CSV_PREFIX="/mnt/resultados/${TAG}"

            echo ""
            echo "[teste] cenario=$SCEN | usuarios=$U | instancias=$INST"
            echo "[teste] -> arquivo CSV: resultados/${TAG}_stats.csv"

            STATS_FILE="${RESULTS_DIR}/${TAG}_stats.csv"
            if [[ "$SKIP_EXISTING" == "1" ]] && stats_file_is_complete "$STATS_FILE"; then
                echo "[skip] teste ja concluido anteriormente"
                continue
            fi

            if should_enforce_failure_cap "$SCEN" "$U"; then
                FAILURE_RATE="$(tune_failure_band "$SCEN" "$U" "$INST" "$TAG" "$CSV_PREFIX" "$STATS_FILE")"
            else
                if ! run_locust_test "$SCEN" "$U" "$INST" "$CSV_PREFIX" "$SPAWN_RATE" "$WAIT_MIN_SECONDS" "$WAIT_MAX_SECONDS"; then
                    echo "[aviso] teste $TAG terminou com erro (provavel sob carga alta)"
                fi
                if [[ -f "$STATS_FILE" ]]; then
                    FAILURE_RATE="$(failure_rate_for "$STATS_FILE")"
                else
                    FAILURE_RATE="0.00"
                fi
            fi

            if [[ -f "$STATS_FILE" ]]; then
                echo "[teste] taxa de falhas agregada: ${FAILURE_RATE}%"

                if should_enforce_failure_cap "$SCEN" "$U"; then
                    if python3 - "$FAILURE_RATE" "$MIN_FAILURE_RATE_HIGH" "$MAX_FAILURE_RATE" <<'PY'
import sys
rate = float(sys.argv[1])
min_rate = float(sys.argv[2])
max_rate = float(sys.argv[3])
sys.exit(0 if min_rate <= rate <= max_rate else 1)
PY
                    then
                        echo "[ok] teste pesado/hibrido ficou na faixa de falhas desejada"
                    else
                        echo "[alerta] teste $TAG nao ficou na faixa desejada de falhas"
                    fi
                fi
            fi

            # pequena pausa para o sistema respirar entre testes
            sleep 3
        done
    done
done

echo ""
echo "============================================================"
echo "  TODOS OS TESTES PRINCIPAIS CONCLUIDOS"
echo "  Resultados em: $RESULTS_DIR"
echo "============================================================"
echo ""
echo "Proximo passo: python3 scripts/gerar_graficos.py"
