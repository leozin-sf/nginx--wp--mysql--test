from locust import HttpUser, task, between

class WordpressUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def acessar_home(self):
        self.client.get("/")