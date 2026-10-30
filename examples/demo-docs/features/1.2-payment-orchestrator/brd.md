> **Last Updated At:** 2026-10-30 **Updated By:** srs-webview-studio

# 1.2 Điều phối Cổng Thanh toán Đa kênh & Đối soát - BRD

## 1. Bối cảnh & Mục tiêu

Hệ thống cần kết nối nhiều kênh thanh toán (mã VietQR động, thẻ nội địa NAPAS, thẻ quốc tế và ví điện tử) với khả năng tự động chuyển kênh dự phòng khi một đối tác ngân hàng bảo trì theo quyết định [D03](../../decisions.md).

## 2. Sơ đồ luồng điều phối thanh toán

```mermaid
flowchart TB
  subgraph Channels["1. Kênh thanh toán người dùng chọn"]
    C1["Quét mã VietQR động"]
    C2["Thẻ ngân hàng / Ví điện tử"]
  end

  subgraph Orchestrator["2. Bộ điều phối & Đối soát"]
    P1["2.1 Sinh mã giao dịch định danh duy nhất"]
    P2["2.2 Kiểm tra sức khỏe cổng chính & chuyển dự phòng"]
    P3["2.3 Xác thực chữ ký số Webhook & khớp số tiền"]
  end

  subgraph Ledger["3. Kết quả hạch toán"]
    L1["Cập nhật đơn Đã thanh toán tức thì"]
    L2["Ghi bút toán sổ cái đối soát tự động"]
  end

  C1 & C2 --> P1
  P1 --> P2 --> P3 --> L1 & L2
```
