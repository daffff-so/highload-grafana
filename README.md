# Highload HW1 — мониторинг Items API

Учебный проект: REST API с хранением в памяти, два экземпляра приложения, Prometheus,
Grafana, автоматическая генерация дашборда и фоновая HTTP-нагрузка.

## Требования и запуск

Нужен Docker Engine с Docker Compose v2 или новее. Java, Maven и Python на хосте
не требуются: сборка и инструменты выполняются внутри контейнеров.

```bash
cp .env.example .env
docker compose up
```

На Linux, если текущему пользователю недоступен Docker socket, используйте
`sudo docker compose up`. Первая сборка скачивает образы и Maven-зависимости.
После запуска приложений графики начинают заполняться; нагрузка нарастает за 120 секунд.
Изменив исходники, выполните `docker compose up -d --build`.

| Компонент | Адрес |
|---|---|
| Приложение 1 (pod-1, dc-1) | http://localhost:8081 |
| Приложение 2 (pod-2, dc-2) | http://localhost:8082 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 |

Дашборд: Grafana → Dashboards → **Items | Golden Signals**.
UID: `items-golden-signals`. Логин и пароль Grafana находятся в `.env`.
`.env.example` содержит только демонстрационные значения; `.env` исключён из Git.
При первом входе можно пропустить смену пароля, чтобы он оставался согласованным с
переменными окружения генератора. Grafana сохраняет учётные данные в своём томе:
последующее изменение `.env` само по себе не меняет пароль существующей базы Grafana.
Порты опубликованы только на loopback-интерфейсе хоста.

## API

| Метод | Путь | Результат |
|---|---|---|
| POST | `/items` | Создание; 201, JSON записи и Location |
| GET | `/items/{id}` | Получение; 200 или 404 |
| PUT | `/items/{id}` | Обновление существующей записи; 200 или 404 |
| GET | `/health` | Готовность приложения; 200 |
| GET | `/metrics` | Метрики в формате Prometheus |
| GET | `/handlers` | Список бизнес-ручек: HTTP-метод и шаблон пути |

Тело создания/обновления: `{"name":"Notebook"}`. Имя обязательно, не может быть пустым
или состоять из пробелов; максимальная длина — 200 символов. Некорректный ввод даёт 400.
Хранилище — ConcurrentHashMap с AtomicLong для идентификаторов.
Каждая реплика хранит собственные записи; перезапуск приложения очищает их.

```bash
curl -i -X POST http://localhost:8081/items \
  -H 'Content-Type: application/json' -d '{"name":"Notebook"}'
curl -i http://localhost:8081/items/1
curl -i -X PUT http://localhost:8081/items/1 \
  -H 'Content-Type: application/json' -d '{"name":"Updated"}'
```

## Стек

- Java 17, Spring Boot 3.5.7, Spring MVC, Actuator и Micrometer Prometheus Registry.
- Maven 3.9.11 в стадии сборки Dockerfile.
- Prometheus v3.5.0, Grafana 12.2.0.
- Python 3.12.12 для генератора дашборда и нагрузки, без сторонних Python-зависимостей.

В Compose оба приложения используют один образ и различные `POD_ID`/`DATACENTER`.
Prometheus опрашивает оба экземпляра каждые 5 секунд.
Datasource Grafana создаётся provisioning-файлом с постоянным UID `prometheus-main`.

## Сбор метрик

Используется автоматическая HTTP-инструментация Spring MVC через Actuator/Micrometer.
Фильтр MeterFilter исключает HTTP-метрики служебных путей `/health`, `/metrics`, `/handlers`.
Остальные системные метрики Actuator доступны для диагностики.

Основные серии:

| Метрика | Назначение |
|---|---|
| `http_server_requests_seconds_bucket` | Кумулятивные бакеты времени ответа, граница в лейбле `le` |
| `http_server_requests_seconds_count` | Количество завершённых запросов; основа RPS и статистики ошибок |
| `http_server_requests_seconds_sum` | Суммарное время обработки в секундах |

Лейблы `pod_id` и `datacenter` приходят из `POD_ID` и `DATACENTER`.
Стандартные HTTP-лейблы Micrometer: `method`, `uri`, `status`; также присутствуют
`outcome` и `exception`. `uri` использует шаблон `/items/{id}`, а не фактический id.
Идентификатор ручки — сочетание `method` и `uri`. Prometheus добавляет `job` и `instance`.

Для latency выбрана классическая гистограмма. Бакеты одинаковых границ можно
суммировать по нескольким репликам, а затем вычислить общий перцентиль.
Усреднение готовых p95 отдельных реплик не даёт общего p95.
Перцентили гистограммы являются оценками с точностью, зависящей от границ бакетов.

Пример p95 для GET с учётом выбранных датацентров и подов:

```promql
histogram_quantile(0.95,
  sum by (le) (
    rate(http_server_requests_seconds_bucket{
      job="items-service",method="GET",uri="/items/{id}",
      datacenter=~"${datacenter:regex}",pod_id=~"${pod_id:regex}"
    }[$__rate_interval])
  )
)
```

RPS:

```promql
sum(rate(http_server_requests_seconds_count{
  job="items-service",method="GET",uri="/items/{id}",
  datacenter=~"${datacenter:regex}",pod_id=~"${pod_id:regex}"
}[$__rate_interval]))
```

Ошибки в секунду по конкретным кодам:

```promql
sum by (status) (rate(http_server_requests_seconds_count{
  job="items-service",method="GET",uri="/items/{id}",status=~"4..|5..",
  datacenter=~"${datacenter:regex}",pod_id=~"${pod_id:regex}"
}[$__rate_interval]))
```

Тексты выше используют переменные Grafana; в интерфейсе Prometheus замените их
на конкретные значения/регулярные выражения и временной интервал, например `[1m]`.
Ошибки 4xx/5xx считаются из того же счётчика запросов с фильтром по `status`.

## Автоматический дашборд

`/handlers` обнаруживает mappings контроллеров в рантайме через
RequestMappingHandlerMapping и исключает служебные пути.
`generator/generate_dashboard.py` получает этот список по HTTP и создаёт для каждого
обработчика три панели: latency p50/p95/p99, RPS, ошибки в секунду по кодам.
Список ручек в код генератора не зашит. Дашборд имеет `editable: false`.
Селекторы Datacenter и Pod поддерживают несколько значений и All.
Запросы используют regex-интерполяцию, sum для rate и sum by (le) перед histogram_quantile.
Селекторы берут значения из метрик приложения; до появления запросов список может быть пустым.

Генератор запускается после healthy обеих реплик и Grafana. Доступ к Grafana — Basic Auth
с учётными данными администратора из environment. Стабильный UID и overwrite позволяют
повторно обновлять дашборд, в том числе после добавления ручек:

```bash
docker compose run --rm dashboard-generator
```

## Нагрузка

`load/load.py` — небольшой инструмент на стандартной библиотеке Python:
планировщик с monotonic-часами и ограниченный пул из 8 потоков.
Запуск следует после healthy приложений и успешного завершения генератора дашборда.
Запросы равномерно чередуются между двумя репликами. Начальная запись создаётся
отдельно в каждой реплике; GET и PUT используют id своей реплики.

За 120 секунд суммарная целевая нагрузка растёт с 2 до 30 RPS, затем поддерживается
до остановки контейнера. В каждом цикле из 100 запросов на реплику:
- 3 запроса GET к отсутствующему id возвращают 404;
- 3 запроса POST с пустым именем возвращают 400;
- остальные запросы распределены между успешными POST, GET и PUT.

Это около 6% ошибок на полном цикле; доля на коротком промежутке может отличаться.
Используются реальные ошибки валидации и отсутствия записи; искусственные 500 не нужны,
так как требование двух кодов выполняется сочетанием 400 и 404.
Панель ошибок PUT может показывать No data, поскольку скрипт обновляет существующие записи.
Фильтр ошибок учитывает и 5xx, если такие ответы возникнут.
Логи выводят целевой и фактический RPS, счётчики кодов, ошибки сети и пропуски при перегрузке.
Параметры задаются через APP_URLS, TARGET_RPS и RAMP_SECONDS в Compose.

## Проверка и остановка

```bash
docker compose ps -a
docker compose logs --tail=10 dashboard-generator
docker compose logs --tail=10 load
```

Генератор должен завершиться с кодом 0 и вывести `Panels: 9` для текущих трёх ручек.
В Prometheus запрос `up{job="items-service"}` должен возвращать две единицы.
В Grafana проверьте обе реплики, фильтры Datacenter/Pod и значения All.

При наличии Python 3 на хосте можно проверить CRUD: `python3 scripts/smoke_test.py`.
Тесты Java выполняются командой `mvn verify` и при сборке Docker-образа.

```bash
docker compose down
```

Останавливает стек, сохраняя тома Grafana/Prometheus.
`docker compose down -v` также удаляет эти тома. Для проверки с чистого состояния
учтите, что будут потеряны история метрик и настройки базы Grafana.

## Использование AI

При подготовке проекта использовалась помощь AI в создании кода, конфигураций и документации.

## Материалы

- https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html
- https://prometheus.io/docs/practices/histograms/
- https://grafana.com/docs/grafana/latest/administration/provisioning/
