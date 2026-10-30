> **Last Updated At:** 2026-10-30 **Updated By:** srs-webview-studio

# 1.2 Điều phối Cổng Thanh toán Đa kênh & Đối soát - Test Spec

## 1. Kịch bản kiểm thử thanh toán & đối soát

| Mã ca kiểm thử | Mức độ | Điều kiện đầu (Given) | Thao tác (When) | Kết quả kỳ vọng (Then) |
|---|---|---|---|---|
| `TC-1.2-01` | 🟢 Luồng chuẩn | Đơn hàng `ORD-101` cần thanh toán `500.000đ` đang ở trạng thái `PENDING_PAYMENT` | Webhook đối tác gửi biên lai thành công đúng `500.000đ` kèm chữ ký hợp lệ | Đơn hàng chuyển sang `PAID` trong dưới 1 giây, khóa giữ tồn kho chuyển thành xuất kho chính thức |
| `TC-1.2-02` | 🔴 Bảo mật | Đơn hàng `ORD-101` đang chờ thanh toán | Kẻ tấn công gửi gói tin giả mạo vào `/api/v1/payments/webhook` với chữ ký sai | Hệ thống từ chối với mã `401 Invalid Signature` và ghi nhật ký cảnh báo bảo mật |
