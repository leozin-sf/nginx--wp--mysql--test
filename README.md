# Trabalho 3 — Testes de carga com Locust + WordPress

Bateria principal de **36 testes** (4 cenários × 3 cargas × 3 quantidades de instâncias) usando Locust contra um cluster WordPress balanceado por Nginx, com uma etapa anterior de calibração da carga pesada.

## Estrutura do projeto

```
.
├── docker-compose.yml          # MySQL + 3 WordPress + Nginx + Locust
├── nginx.conf                  # criado dinamicamente pelo script
├── nginx_configs/
│   ├── nginx_1.conf            # 1 backend WordPress
│   ├── nginx_2.conf            # 2 backends
│   └── nginx_3.conf            # 3 backends
├── locust/
│   └── locustfile.py           # script de carga (3 cenários + híbrido)
├── scripts/
│   ├── run_tests.sh            # calibra a carga pesada e executa a bateria principal
│   └── gerar_graficos.py       # gera gráficos a partir dos CSVs
├── resultados/                 # CSVs do Locust (criado pelos testes)
└── graficos/                   # SVGs gerados (criado pelo script Python)
```

## Pré-requisitos

- Docker + Docker Compose (`docker compose version` deve funcionar)
- Python 3 com `matplotlib` e `numpy`:
  ```bash
  pip install matplotlib numpy
  ```

## Passo-a-passo

### 1. Subir o ambiente e configurar o WordPress

```bash
# Inicia tudo com 3 instâncias para a configuração inicial
cp nginx_configs/nginx_3.conf nginx.conf
docker compose up -d mysql wordpress1 wordpress2 wordpress3 nginx
```

Acesse `http://localhost` no navegador. Faça a instalação inicial do WordPress (idioma, título, usuário admin, senha — qualquer coisa serve).

### 2. Criar os 3 posts de teste

No painel do WordPress (`http://localhost/wp-admin`), crie **3 posts**:

| # | Cenário | Conteúdo |
|---|---------|----------|
| 1 | `img1mb` | Post com **uma imagem de ~1 MB** anexada |
| 2 | `text400` | Post com **texto de ~400 KB** (cole bastante Lorem Ipsum) |
| 3 | `img300` | Post com **uma imagem de ~300 KB** |

**Anote o ID de cada post** — aparece na URL ao editar (`?post=ID`) ou ao visualizar (`?p=ID`).

### 3. Configurar os IDs dos posts

Edite as variáveis no topo de `scripts/run_tests.sh`:

```bash
export POST_ID_IMG1MB="2"   # id do post com imagem 1MB
export POST_ID_TEXT400="3"  # id do post com texto 400KB
export POST_ID_IMG300="4"   # id do post com imagem 300KB
```

Antes de rodar a bateria, **valide manualmente** que cada URL retorna o post certo:
```
http://localhost/?p=2
http://localhost/?p=3
http://localhost/?p=4
```

### 4. Rodar a calibração e a bateria principal

```bash
chmod +x scripts/run_tests.sh
./scripts/run_tests.sh
```

O script primeiro roda testes pesados de calibração para escolher a carga alta de referência. Em seguida executa a bateria principal com cargas leve, média e pesada.

Cada teste dura 75s, mais alguns segundos de setup. O tempo total varia conforme a carga pesada escolhida.

Os resultados ficam em `resultados/` no formato `<cenario>_u<usuarios>_i<instancias>_stats.csv`.

Configuracao padrao calibrada para um subsistema Linux com **6 GB de RAM** e **6 nucleos**:

- usuarios leve/medio: `12`, `48`
- usuarios pesados candidatos: `300`, `500`
- spawn rate: `6`
- wait time por usuario: `1.5s` a `3.0s`
- metrica principal de latencia: `p95`
- faixa de falhas desejada para testes pesados e hibridos: entre `1%` e `12%`

### 5. Gerar os gráficos

```bash
python3 scripts/gerar_graficos.py
```

Saída em `graficos/`:
- `p95_por_peso_u*.svg` — latência `p95` por peso do conteúdo, mantendo o mesmo número de usuários
- `falhas_por_peso_u*.svg` — taxa de falhas por peso do conteúdo, com linha de referência de `12%`
- `rps_por_peso_u*.svg` — throughput por peso do conteúdo, mantendo o mesmo número de usuários

O script também imprime uma tabela-resumo ordenada por carga (`leve`, `média`, `pesada`), instâncias e peso do conteúdo.

### 6. Encerrar o ambiente

```bash
docker compose down -v   # -v remove os volumes (zera o WordPress)
```

## Dicas e troubleshooting

**Quer subir ou descer a carga?**
Edite `LIGHT_USERS`, `MEDIUM_USERS`, `HEAVY_USERS_PRIMARY` e `HEAVY_USERS_FALLBACK` em `scripts/run_tests.sh`.

**Permissão negada no docker compose?**
Adicione seu usuário ao grupo docker: `sudo usermod -aG docker $USER` e faça logout/login.

**WordPress não abre?**
Veja os logs: `docker compose logs wordpress1`. Pode levar 30s para o MySQL terminar de iniciar na primeira vez.

**Quero ver a interface web do Locust ao invés do modo headless?**
Rode manualmente:
```bash
docker compose run --rm -p 8089:8089 \
    -e SCENARIO=img1mb \
    -e POST_ID_IMG1MB=2 -e POST_ID_TEXT400=3 -e POST_ID_IMG300=4 \
    locust -f /mnt/locust/locustfile.py --host=http://nginx
```
Acesse `http://localhost:8089`.
