"""
Locustfile para testes de carga do WordPress com 3 cenarios.

O cenario ativo e escolhido via variavel de ambiente SCENARIO:
  - SCENARIO=img1mb  -> Blog post com imagem de ~1MB
  - SCENARIO=text400 -> Blog post com texto de ~400KB
  - SCENARIO=img300  -> Blog post com imagem de ~300KB

Os IDs dos posts sao definidos via variaveis de ambiente:
  - POST_ID_IMG1MB
  - POST_ID_TEXT400
  - POST_ID_IMG300

Exemplo de execucao headless (controlado pelo script run_tests.sh):
  locust -f locustfile.py --headless -u 100 -r 10 -t 60s \
         --host=http://nginx --csv=/mnt/resultados/exec_xxx
"""

import os
from locust import HttpUser, task, between, constant

SCENARIO = os.getenv("SCENARIO", "img1mb")

POST_IDS = {
    "img1mb": os.getenv("POST_ID_IMG1MB", "2"),
    "text400": os.getenv("POST_ID_TEXT400", "3"),
    "img300": os.getenv("POST_ID_IMG300", "4"),
}

TARGET_PATH = f"/?p={POST_IDS[SCENARIO]}"


class WordpressUser(HttpUser):
    # wait_time pequeno para gerar carga consistente nos 60s de teste
    wait_time = between(1, 2)

    @task
    def visitar_post(self):
        # name fixa o rotulo nas estatisticas (independente do ID do post)
        self.client.get(TARGET_PATH, name=f"post_{SCENARIO}")
