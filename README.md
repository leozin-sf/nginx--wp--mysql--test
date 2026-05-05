# Trabalho 3 — Testes de carga com Locust + WordPress

Bateria de **27 testes** (3 cenários × 3 quantidades de usuários × 3 quantidades de instâncias) usando Locust contra um cluster WordPress balanceado por Nginx.

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
│   └── locustfile.py           # script de carga (3 cenários)
├── scripts/
│   ├── run_tests.sh            # executa os 27 testes
│   └── gerar_graficos.py       # gera gráficos a partir dos CSVs
├── resultados/                 # CSVs do Locust (criado pelos testes)
└── graficos/                   # PNGs gerados (criado pelo script Python)
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

### 4. Rodar os 27 testes

```bash
chmod +x scripts/run_tests.sh
./scripts/run_tests.sh
```

Cada teste dura 60s, mais alguns segundos de setup. Total: **~30 a 40 minutos**.

Os resultados ficam em `resultados/` no formato `<cenario>_u<usuarios>_i<instancias>_stats.csv`.

### 5. Gerar os gráficos

```bash
python3 scripts/gerar_graficos.py
```

Saída em `graficos/`:
- `tempo_img1mb.png`, `tempo_text400.png`, `tempo_img300.png` — tempo de resposta vs usuários
- `rps_img1mb.png`, `rps_text400.png`, `rps_img300.png` — RPS vs número de instâncias

O script também imprime uma tabela-resumo no console.

### 6. Encerrar o ambiente

```bash
docker compose down -v   # -v remove os volumes (zera o WordPress)
```

## Dicas e troubleshooting

**1000 usuários travando seu PC?**
É normal — uma única instância WordPress não aguenta 1000 conexões simultâneas. Os timeouts e falhas fazem parte da medição. Se quiser reduzir, edite `USERS=(10 100 1000)` em `run_tests.sh`.

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
