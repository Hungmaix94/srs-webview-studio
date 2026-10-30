> **Last Updated At:** 2026-10-30 **Updated By:** srs-webview-studio

# 1.1 Đặt hàng nhanh & Giữ tồn kho thời gian thực - FSD

## 1. Kiến trúc kỹ thuật & Luồng xử lý

### 1.1 Sơ đồ kiến trúc thành phần

```mermaid
flowchart LR
  subgraph Client["Tầng Giao diện (Web / App)"]
    UI["Màn hình Thanh toán & Đếm ngược 15 phút"]
  end

  subgraph API["Tầng Điều phối API"]
    EP["POST /api/v1/orders/checkout"]
    IDEM["Middleware kiểm tra Idempotency-Key"]
  end

  subgraph Storage["Tầng Lưu trữ & Hàng đợi"]
    REDIS["Redis Atomic Stock Lock"]
    PG["PostgreSQL (orders, inventory_reservations)"]
  end

  UI --> EP --> IDEM --> REDIS --> PG
```

### 1.2 Sơ đồ tuần tự xử lý đặt hàng

```mermaid
sequenceDiagram
  autonumber
  actor User as Khách hàng
  participant API as Checkout API
  participant Redis as Redis Stock Guard
  participant DB as PostgreSQL

  User->>API: POST /api/v1/orders/checkout (Idempotency-Key)
  API->>Redis: DECRBY tồn kho khả dụng (TTL 900s)
  Redis-->>API: Trả về số dư tồn kho >= 0
  API->>DB: INSERT orders & inventory_reservations (PENDING)
  DB-->>API: Trả về order_id & expires_at
  API-->>User: HTTP 201 Created (kèm thông tin QR thanh toán)
```

## 2. Đặc tả Hợp đồng API

| Phương thức & Đường dẫn | Đầu vào chính | Phản hồi thành công | Mã lỗi nghiệp vụ |
|---|---|---|---|
| `POST /api/v1/orders/checkout` | Header `Idempotency-Key`, mảng `items[{sku, qty}]`, `shipping_address_id` | `201 Created` kèm `order_id`, `status = "PENDING_PAYMENT"`, `expires_at` | `409 OUT_OF_STOCK`, `422 INVALID_VOUCHER` |
| `POST /api/v1/orders/{id}/cancel` | `reason` | `200 OK` kèm trạng thái `CANCELLED` và hoàn lại tồn kho tức thì | `400 ORDER_ALREADY_PAID` |
