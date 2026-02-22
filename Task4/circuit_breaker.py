from locust import HttpUser, task, between, events, constant_pacing
import logging

logger = logging.getLogger("locust")

class CircuitBreakerUser(HttpUser):
    """Пользователь для тестирования Circuit Breaker"""

    # Фиксированный интервал: 1 запрос в 0.5с для контролируемой нагрузки
    wait_time = constant_pacing(0.5)

    @task
    def test_fast(self):
        """Нормальный запрос — должен всегда проходить"""
        with self.client.get(
            "/logistics/?type=fast",
            name="/logistics [fast]",  # ← name здесь
            catch_response=True
        ) as response:
            if response.status_code == 200 and "success" in response.text:
                response.success()
            else:
                response.failure(f"Unexpected: {response.status_code}")

    @task(weight=3)  # ← weight допустим
    def test_slow(self):
        """
        Запрос с эмуляцией таймаута.
        Ожидаемое поведение:
        - Первые 5 запросов: 503 (fallback, т.к. error_page перехватывает 504)
        - После 5 ошибок: Circuit Breaker открывается, все запросы → 503 fallback
        - Через 30с: CB восстанавливается, запросы снова проходят
        """
        with self.client.get(
            "/logistics/?type=slow",
            name="/logistics [slow]",  # ← name здесь
            catch_response=True,
            timeout=5.0  # Даем запас к proxy_read_timeout=3s
        ) as response:
            # Ожидаем fallback от Circuit Breaker
            if response.status_code == 503 and "circuit_breaker_open" in response.text:
                logger.info("✅ Circuit Breaker triggered: fallback received")
                response.success()  # Это ожидаемое поведение
            # Если бэкенд вернул 504 (до перехвата) — тоже ок для первых 5 запросов
            elif response.status_code == 504:
                logger.info("⚡ Backend timeout (504) — will be intercepted")
                response.success()
            # Неожиданный успех — возможно, CB восстановился
            elif response.status_code == 200:
                logger.info("🔄 Circuit Breaker recovered: backend responding")
                response.success()
            else:
                response.failure(f"Unexpected: {response.status_code} - {response.text[:100]}")

@events.request.add_listener
def on_request(request_type, name, response_time, response_length, response, exception, **kwargs):
    """Логирование ключевых событий"""
    if response and response.status_code == 503 and "circuit_breaker_open" in response.text:
        logger.info(f"🔓 CB OPEN: {name}")
    if exception:
        logger.error(f"❌ Exception: {name} - {exception}")