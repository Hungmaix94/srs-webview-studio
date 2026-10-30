> **Last Updated At:** 2026-10-30 **Updated By:** srs-webview-studio

# 1.1 Đặt hàng nhanh & Giữ tồn kho thời gian thực - Test Spec

## 1. Danh mục Kịch bản Kiểm thử

### 1.1 Kiểm thử luồng chính và cạnh tranh tồn kho

| Mã ca kiểm thử | Mức độ | Điều kiện đầu (Given) | Thao tác (When) | Kết quả kỳ vọng (Then) |
|---|---|---|---|---|
| `TC-1.1-01` | 🟢 Luồng chuẩn | Sản phẩm `SKU-01` còn tồn khả dụng `10` chiếc, khách đã chọn địa chỉ giao hợp lệ | Khách bấm *Đặt hàng* với số lượng `2` chiếc | Tạo đơn `PENDING_PAYMENT` thành công, tồn khả dụng giảm ngay về `8` chiếc và đồng hồ đếm ngược 15 phút bắt đầu chạy |
| `TC-1.1-02` | 🟡 Trường hợp biên | Khách gửi yêu cầu đặt hàng kèm `Idempotency-Key = K1`, sau đó bấm đúp gửi lại đúng `K1` lần thứ hai | Máy chủ nhận 2 yêu cầu trùng khóa `K1` trong vòng 2 giây | Chỉ tạo duy nhất 1 đơn hàng và chỉ trừ tạm `2` chiếc trong kho; lần gọi thứ hai trả về lại kết quả của đơn đầu tiên |
| `TC-1.1-03` | 🔴 Luồng lỗi / Cạnh tranh | Sản phẩm `SKU-99` chỉ còn đúng `1` chiếc cuối cùng trong kho | Hai khách hàng `A` và `B` cùng bấm *Đặt hàng* `1` chiếc ở cùng một thời điểm | Đúng 1 người nhận mã `201 Created`, người còn lại nhận thông báo `409 OUT_OF_STOCK` (tồn kho không bao giờ âm) |
| `TC-1.1-04` | 🟡 Hết hạn giữ chỗ | Đơn hàng đang ở trạng thái `PENDING_PAYMENT` giữ `2` chiếc `SKU-01` | Quá 15 phút khách chưa thanh toán | Hệ thống tự động chuyển đơn sang `EXPIRED` và cộng trả `2` chiếc về lại tồn kho khả dụng |
