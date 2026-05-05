#!/usr/bin/env bash
# =============================================================================
# Script de execucao automatica dos testes de carga
# 3 cenarios x 3 quantidades de usuarios x 3 quantidades de instancias = 27 testes
# =============================================================================

set -e

# --- CONFIGURACAO ---------------------------------------------------------
# IDs dos posts criados no WordPress.
# IMPORTANTE: edite esses valores apos criar os posts no painel do WordPress.
export POST_ID_IMG1MB="${POST_ID_IMG1MB:-2}"   # post com imagem ~1MB
export POST_ID_TEXT400="${POST_ID_TEXT400:-3}" # post com texto ~400KB
export POST_ID_IMG300="${POST_ID_IMG300:-4}"   # post com imagem ~300KB

# Duracao de cada teste (segundos). 60s e o suficiente para estatisticas estaveis.
DURATION="60s"

# Spawn rate: usuarios criados por segundo. Mantemos 10/s para subida progressiva.
SPAWN_RATE=10

# Listas de variacao
SCENARIOS=("img1mb" "text400" "img300")
USERS=(10 100 1000)
INSTANCES=(1 2 3)

RESULTS_DIR="./resultados"
NGINX_DIR="./nginx_configs"

# --------------------------------------------------------------------------

mkdir -p "$RESULTS_DIR"

echo "============================================================"
echo "  Iniciando bateria de 27 testes de carga"
echo "  Duracao por teste: $DURATION"
echo "  Post IDs: img1mb=$POST_ID_IMG1MB | text400=$POST_ID_TEXT400 | img300=$POST_ID_IMG300"
echo "============================================================"

# Sobe o stack base (mysql + 3 wordpress) uma unica vez
echo "[setup] Subindo MySQL e instancias do WordPress..."
docker compose up -d mysql wordpress1 wordpress2 wordpress3
sleep 5

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

            # Executa o locust em modo headless dentro de um container efemero
            docker compose run --rm \
                -e SCENARIO="$SCEN" \
                -e POST_ID_IMG1MB="$POST_ID_IMG1MB" \
                -e POST_ID_TEXT400="$POST_ID_TEXT400" \
                -e POST_ID_IMG300="$POST_ID_IMG300" \
                locust \
                -f /mnt/locust/locustfile.py \
                --headless \
                -u "$U" \
                -r "$SPAWN_RATE" \
                -t "$DURATION" \
                --host=http://nginx \
                --csv="$CSV_PREFIX" \
                --only-summary \
                || echo "[aviso] teste $TAG terminou com erro (provavel sob carga alta)"

            # pequena pausa para o sistema respirar entre testes
            sleep 3
        done
    done
done

echo ""
echo "============================================================"
echo "  TODOS OS 27 TESTES CONCLUIDOS"
echo "  Resultados em: $RESULTS_DIR"
echo "============================================================"
echo ""
echo "Proximo passo: python3 scripts/gerar_graficos.py"
