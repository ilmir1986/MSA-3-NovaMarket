from locust import HttpUser, task, between, events
import logging

logger = logging.getLogger("locust")

class RateLimiterUser(HttpUser):
    """Пользователь для тестирования Rate Limiter"""

    # Быстрая генерация нагрузки: 0.01-0.05с между запросами = 20-100 RPS на пользователя
    wait_time = between(0.01, 0.05)

    # Тест для веб-клиента (лимит 50 r/s)
    @task
    def test_web(self):
        self.client.get(
            "/api/test",
            headers={"X-Client-Type": "web"},
            name="/api [web]"  # ← name здесь, для группировки в UI
        )

    # Тест для мобильного клиента (лимит 30 r/s) — вес 2, чтобы создать больше нагрузки
    @task(weight=2)  # ← weight допустим, name — нет
    def test_mobile(self):
        self.client.get(
            "/api/test",
            headers={"X-Client-Type": "mobile"},
            name="/api [mobile]"  # ← name здесь
        )

@events.request.add_listener
def on_request(request_type, name, response_time, response_length, response, exception, **kwargs):
    """Логирование для отладки"""
    if exception:
        logger.warning(f"Request failed: {name} - {exception}")

    # Логируем 503 для подтверждения работы лимитера
    if response and response.status_code == 503:
        logger.info(f"⚠️ Rate limited: {name} → 503")