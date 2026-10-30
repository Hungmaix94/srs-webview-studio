> **Last Updated At:** 2026-10-30 **Updated By:** srs-webview-studio

# Quyết định Kiến trúc đã chốt (Architecture Decisions)

Bảng dưới đây lưu vết các quyết định nghiệp vụ và kỹ thuật cốt lõi của hệ thống mẫu. Bấm nút **Chỉnh sửa** để thử sửa trực tiếp từng ô trong bảng.

## 1. Bảng quyết định kiến trúc

| Mã | Quyết định đã chốt | Lý do lựa chọn | Phương án khác đã xét | Người chốt | Ngày chốt | Ghi chú áp dụng |
|---|---|---|---|---|---|---|
| D01 | **Giữ tồn kho tạm thời bằng khóa nguyên tử trên Redis kèm bản ghi đối chiếu trong PostgreSQL trong 15 phút khi khách bấm Thanh toán.** Nếu sau 15 phút chưa nhận được biên lai thanh toán thành công, tiến trình nền tự động giải phóng tồn kho về giỏ hàng chung. | **(1) Chống bán vượt tồn kho (Overselling)** trong các đợt mở bán Flash Sale có hàng nghìn lượt bấm cùng giây. **(2) Tự động thu hồi hàng giữ chỗ** khi khách thoát trình duyệt ở bước quét mã QR thanh toán mà không làm nghẽn khóa cơ sở dữ liệu chính. | (a) Chỉ trừ tồn kho sau khi thanh toán xong - dẫn tới 2 khách cùng thanh toán thành công cho 1 sản phẩm cuối cùng. (b) Khóa dòng trực tiếp bằng `SELECT FOR UPDATE` xuyên suốt 15 phút chờ khách quét QR - làm cạn kiệt kết nối cơ sở dữ liệu. | Hội đồng Kiến trúc | 2026-10-20 | Áp dụng tại [1.1 BRD](features/1.1-smart-checkout/brd.md) và [1.1 FSD](features/1.1-smart-checkout/fsd.md) |
| D02 | **Mọi yêu cầu tạo đơn hàng và khởi tạo giao dịch thanh toán bắt buộc truyền khóa chống trùng lặp (`Idempotency-Key` theo chuẩn UUID v4) có hiệu lực 24 giờ.** Khi máy khách gửi lại cùng khóa do mạng chập chờn, máy chủ trả về đúng kết quả của lần xử lý đầu tiên. | Ngăn chặn triệt để lỗi tạo đúp 2 đơn hàng hoặc trừ tiền 2 lần khi người dùng bấm đúp nút *Đặt hàng* trên mạng di động 4G có độ trễ cao. | Chặn bấm nút ở riêng phía giao diện người dùng - không đủ an toàn khi ứng dụng tự động thử lại gói tin mạng hoặc khi có yêu cầu gọi thẳng vào API. | Tech Lead | 2026-10-22 | Áp dụng tại [1.1 FSD](features/1.1-smart-checkout/fsd.md) và [1.2 FSD](features/1.2-payment-orchestrator/fsd.md) |
| D03 | **Điều phối cổng thanh toán theo mô hình ưu tiên VietQR động làm kênh mặc định, tự động chuyển dự phòng sang cổng Thẻ nội địa / Ví điện tử sau 10 giây nếu cổng chính bảo trì.** | Tối ưu phí giao dịch thấp nhất qua kênh chuyển khoản QR định danh từng đơn hàng và đảm bảo tỷ lệ thanh toán thành công đạt trên 99,5% ngay cả khi một ngân hàng đối tác gặp sự cố. | Gắn cứng một nhà cung cấp cổng thanh toán duy nhất - toàn bộ luồng thanh toán bị gián đoạn khi cổng đó bảo trì định kỳ. | Product Owner | 2026-10-25 | Áp dụng tại [1.2 BRD](features/1.2-payment-orchestrator/brd.md) |

## 2. Ghi chú tra cứu

- Khi một quyết định cũ được thay thế bởi quyết định mới, giữ nguyên dòng cũ và gắn nhãn tham chiếu sang mã quyết định mới để bảo toàn lịch sử đối chiếu.
