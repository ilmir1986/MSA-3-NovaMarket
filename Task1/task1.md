# Проектирование приложения на базе EDA

## **Реестр событий для Saga-хореографии**
|  №  | Этап                         | Тип события  | Название                        | Сервис    | Комментарий                                          |
|:---:|:-----------------------------|:-------------|:--------------------------------|:----------|:-----------------------------------------------------|
|  1  | Заказ создан                 | domain       | ORDER_CREATED                   | order     | Статус: «Создан»                                     |
|     |                              |              |                                 |           |                                                      |
|  2  | Товар зарезервирован         | domain       | INVENTORY_RESERVED              | inventory | Статус: «Ожидает оплаты»                             |
| 2.1 | Ошибка резервации            | failure      | INVENTORY_RESERVATION_FAILED    | inventory | → ORDER_CANCELLED                                    |
| 2.2 | Отмена резервации            | compensation | INVENTORY_RESERVATION_CANCELLED | inventory |                                                      |
|     |                              |              |                                 |           |                                                      |
|  3  | Оплата успешна               | domain       | PAYMENT_PROCESSED               | payment   | Статус: «Оплачен и готовится к отправке»             |
| 3.1 | Оплата не удалась            | failure      | PAYMENT_FAILED                  | payment   | → INVENTORY_RESERVATION_CANCELLED                    |
| 3.2 | Возврат средств              | compensation | PAYMENT_REFUNDED                | payment   |                                                      |
|     |                              |              |                                 |           |                                                      |
|  4  | Доставка создана             | domain       | DELIVERY_SCHEDULED              | delivery  | Статус: «Передан в доставку»                         |
| 4.1 | Создание доставки не удалась | failure      | DELIVERY_SCHEDULING_FAILED      | delivery  | → PAYMENT_REFUNDED → INVENTORY_RESERVATION_CANCELLED |
| 4.2 | Отмена доставки              | compensation | DELIVERY_CANCELLED              | delivery  |                                                      |
|     |                              |              |                                 |           |                                                      |
|  5  | Доставка завершена           | domain       | DELIVERY_COMPLETED              | delivery  | Статус: «Доставлен»                                  |
|     |                              |              |                                 |           |                                                      |
|  6  | Заказ завершён               | domain       | ORDER_COMPLETED                 | order     | Финальное состояние после DELIVERY_COMPLETED         |
|     |                              |              |                                 |           |                                                      |
|  7  | Заказ отменён                | domain       | ORDER_CANCELLED                 | order     | Инициируется при любом failure-событии               |


## Диаграммы последовательности

### 1. Успешный сценарий (Happy Path)
```mermaid
sequenceDiagram
    participant User as Покупатель
    participant Order as Order Service
    participant Kafka as Event Bus (Kafka)
    participant Inventory as Inventory Service
    participant Payment as Payment Service
    participant Delivery as Delivery Service
    participant Notification as Notification Service

    User->>Order: createOrder(orderData)
    activate Order
    Order->>Kafka: ORDER_CREATED
    Order-->>User: 202 Accepted<br/>orderId, status=CREATED
    deactivate Order

    Kafka->>Inventory: ORDER_CREATED
    activate Inventory
    Note over Inventory: Проверка наличия и резервация
    Inventory->>Kafka: INVENTORY_RESERVED<br/>(orderId, reservedItems)
    deactivate Inventory

    Kafka->>Payment: INVENTORY_RESERVED
    activate Payment
    Note over Payment: Обработка платежа через шлюз
    Payment->>Kafka: PAYMENT_PROCESSED<br/>(orderId, paymentId, amount)
    deactivate Payment

    Kafka->>Delivery: PAYMENT_PROCESSED
    activate Delivery
    Note over Delivery: Создание заявки в логистике
    Delivery->>Kafka: DELIVERY_SCHEDULED<br/>(orderId, trackingNumber, estimatedDate)
    deactivate Delivery

    Kafka->>Order: DELIVERY_SCHEDULED
    activate Order
    Note over Order: Обновление статуса → IN_DELIVERY
    Order->>Kafka: ORDER_STATUS_UPDATED<br/>(orderId, status=IN_DELIVERY)
    deactivate Order

    Kafka->>Notification: DELIVERY_SCHEDULED
    activate Notification
    Note over Notification: Уведомление покупателя о трек-номере
    Notification-->>User: Email/SMS: "Заказ в пути"
    deactivate Notification

    Note over Delivery: Логистический провайдер завершает доставку
    activate Delivery
    Delivery->>Kafka: DELIVERY_COMPLETED<br/>(orderId, deliveredAt)
    deactivate Delivery

    Kafka->>Order: DELIVERY_COMPLETED
    activate Order
    Note over Order: Обновление статуса → DELIVERED
    Order->>Kafka: ORDER_COMPLETED<br/>(orderId, completedAt)
    deactivate Order

    Kafka->>Notification: ORDER_COMPLETED
    activate Notification
    Note over Notification: Уведомление покупателя и продавца
    Notification-->>User: Email: "Заказ доставлен"
    Notification-->>Seller: Email: "Заказ завершён"
    deactivate Notification
```

### 2. Ошибка резервации товара
```mermaid
sequenceDiagram
    participant User as Покупатель
    participant Order as Order Service
    participant Kafka as Event Bus (Kafka)
    participant Inventory as Inventory Service
    participant Notification as Notification Service

    User->>Order: createOrder(orderData)
    activate Order
    Order->>Kafka: ORDER_CREATED
    Order-->>User: 202 Accepted<br/>orderId, status=CREATED
    deactivate Order

    Kafka->>Inventory: ORDER_CREATED
    activate Inventory
    Note over Inventory: Недостаточно товара на складе
    Inventory->>Kafka: INVENTORY_RESERVATION_FAILED<br/>(orderId, reason=OUT_OF_STOCK)
    deactivate Inventory

    Kafka->>Order: INVENTORY_RESERVATION_FAILED
    activate Order
    Note over Order: Обновление статуса → CANCELLED
    Order->>Kafka: ORDER_CANCELLED<br/>(orderId, reason=INVENTORY_FAILED)
    deactivate Order

    Kafka->>Notification: ORDER_CANCELLED
    activate Notification
    Note over Notification: Уведомление покупателя
    Notification-->>User: Email: "Заказ отменён: товар отсутствует"
    deactivate Notification
```


### 3. Ошибка оплаты
```mermaid
sequenceDiagram
    participant User as Покупатель
    participant Order as Order Service
    participant Kafka as Event Bus (Kafka)
    participant Inventory as Inventory Service
    participant Payment as Payment Service
    participant Notification as Notification Service

    User->>Order: createOrder(orderData)
    activate Order
    Order->>Kafka: ORDER_CREATED
    Order-->>User: 202 Accepted<br/>orderId, status=CREATED
    deactivate Order

    Kafka->>Inventory: ORDER_CREATED
    activate Inventory
    Inventory->>Kafka: INVENTORY_RESERVED
    deactivate Inventory

    Kafka->>Payment: INVENTORY_RESERVED
    activate Payment
    Note over Payment: Отказ платежного шлюза<br/>(insufficient funds, declined)
    Payment->>Kafka: PAYMENT_FAILED<br/>(orderId, reason=PAYMENT_DECLINED)
    deactivate Payment

    Kafka->>Inventory: PAYMENT_FAILED
    activate Inventory
    Note over Inventory: Отмена резервации
    Inventory->>Kafka: INVENTORY_RESERVATION_CANCELLED<br/>(orderId, cancelledAt)
    deactivate Inventory

    Kafka->>Order: INVENTORY_RESERVATION_CANCELLED
    activate Order
    Order->>Kafka: ORDER_CANCELLED<br/>(orderId, reason=PAYMENT_FAILED)
    deactivate Order

    Kafka->>Notification: ORDER_CANCELLED
    activate Notification
    Notification-->>User: Email: "Заказ отменён: оплата не прошла"
    deactivate Notification
```


### 4. Ошибка создания доставки
```mermaid
sequenceDiagram
    participant User as Покупатель
    participant Order as Order Service
    participant Kafka as Event Bus (Kafka)
    participant Inventory as Inventory Service
    participant Payment as Payment Service
    participant Delivery as Delivery Service
    participant Notification as Notification Service

    User->>Order: createOrder(orderData)
    activate Order
    Order->>Kafka: ORDER_CREATED
    Order-->>User: 202 Accepted
    deactivate Order

    Kafka->>Inventory: ORDER_CREATED
    activate Inventory
    Inventory->>Kafka: INVENTORY_RESERVED
    deactivate Inventory

    Kafka->>Payment: INVENTORY_RESERVED
    activate Payment
    Payment->>Kafka: PAYMENT_PROCESSED
    deactivate Payment

    Kafka->>Delivery: PAYMENT_PROCESSED
    activate Delivery
    Note over Delivery: Ошибка интеграции с логистикой
    Delivery->>Kafka: DELIVERY_SCHEDULING_FAILED<br/>(orderId, reason=INTEGRATION_ERROR)
    deactivate Delivery

    Kafka->>Payment: DELIVERY_SCHEDULING_FAILED
    activate Payment
    Note over Payment: Возврат средств
    Payment->>Kafka: PAYMENT_REFUNDED<br/>(orderId, refundId, refundedAt)
    deactivate Payment

    Kafka->>Inventory: PAYMENT_REFUNDED
    activate Inventory
    Inventory->>Kafka: INVENTORY_RESERVATION_CANCELLED
    deactivate Inventory

    Kafka->>Order: INVENTORY_RESERVATION_CANCELLED
    activate Order
    Order->>Kafka: ORDER_CANCELLED<br/>(orderId, reason=DELIVERY_FAILED)
    deactivate Order

    Kafka->>Notification: ORDER_CANCELLED
    activate Notification
    Notification-->>User: Email: "Заказ отменён: ошибка доставки"
    deactivate Notification
```
