"""
Locustfile para testes de carga do WordPress.

Cenarios suportados:
  - img1mb  -> Blog post com imagem de ~1MB
  - text400 -> Blog post com texto de ~400KB
  - img300  -> Blog post com imagem de ~300KB
  - hybrid  -> mistura dos tres posts, priorizando os mais pesados
"""

import os
import random
import re
from urllib.parse import urlparse
from locust import HttpUser, task, between

SCENARIO = os.getenv("SCENARIO", "img1mb")
WAIT_MIN = float(os.getenv("WAIT_MIN_SECONDS", "1.5"))
WAIT_MAX = float(os.getenv("WAIT_MAX_SECONDS", "3.0"))

POST_IDS = {
    "img1mb": os.getenv("POST_ID_IMG1MB", "2"),
    "text400": os.getenv("POST_ID_TEXT400", "3"),
    "img300": os.getenv("POST_ID_IMG300", "4"),
}

if SCENARIO not in {"img1mb", "text400", "img300", "hybrid"}:
    raise ValueError(f"SCENARIO invalido: {SCENARIO}")

TARGET_PATHS = {
    "img1mb": f"/?p={POST_IDS['img1mb']}",
    "text400": f"/?p={POST_IDS['text400']}",
    "img300": f"/?p={POST_IDS['img300']}",
}

HYBRID_FLOW = [
    ("img1mb", 4),
    ("text400", 2),
    ("img300", 3),
]

IMG_SRC_RE = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)


class WordpressUser(HttpUser):
    # Um intervalo um pouco maior ajuda a estabilizar os testes pesados
    # na maquina de 6 GB / 6 nucleos sem descaracterizar a carga.
    wait_time = between(WAIT_MIN, WAIT_MAX)

    @task
    def visitar_post(self):
        if SCENARIO == "hybrid":
            target, _ = random.choices(
                HYBRID_FLOW,
                weights=[weight for _, weight in HYBRID_FLOW],
                k=1,
            )[0]
        else:
            target = SCENARIO

        # name fixa o rotulo nas estatisticas independentemente do ID real.
        with self.client.get(TARGET_PATHS[target], name=f"post_{target}", catch_response=True) as response:
            if response.status_code >= 400:
                response.failure(f"Falha ao carregar post {target}: {response.status_code}")
                return

            for asset_path in self._extract_image_paths(response.text):
                self.client.get(asset_path, name=f"asset_{target}")

    def _extract_image_paths(self, html):
        image_paths = []
        for src in IMG_SRC_RE.findall(html or ""):
            parsed = urlparse(src)
            if parsed.scheme and parsed.netloc:
                path = parsed.path or "/"
                if parsed.query:
                    path = f"{path}?{parsed.query}"
            else:
                path = src

            if not path.startswith("/"):
                path = f"/{path.lstrip('./')}"

            image_paths.append(path)

        return image_paths
