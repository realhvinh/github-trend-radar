# Hướng dẫn sử dụng GitHub Trend Radar

## 1. Tool làm được gì?

Tool lấy các repo có tín hiệu nổi bật từ **GitHub Trending** (toàn bộ GitHub và nhóm ngôn ngữ ưu tiên), sau đó dùng **GitHub REST API** để xác định repo nào nhận được nhiều star **trong tuần đã hoàn thành gần nhất**.

Kết quả bao gồm **Top 10**, mô tả, ngôn ngữ lập trình, phân loại chủ đề, link trực tiếp; có thể tìm kiếm/lọc và xem lại những tuần trước. Lưu thành JSON, Markdown và CSV.

> **Lưu ý quan trọng:** GitHub Trending không bao quát mọi repo. Bảng xếp hạng là Top 10 **trong tập repo đã tìm được**, không phải top 10 tuyệt đối của toàn GitHub. Ngoài ra, số star được thêm trong tuần khác với mức tăng ròng (sau khi trừ unstar).

## 2. Triển khai tự động miễn phí trên GitHub

Bạn **không cần cài Python trên máy cá nhân** để chạy theo lịch.

1. Giải nén `github-trend-radar.zip`.
2. Vào [GitHub](https://github.com/new), tạo repo công khai có tên `github-trend-radar`. Mở GitHub Desktop hoặc dùng giao diện GitHub để upload **toàn bộ thư mục bên trong** (nhớ cả thư mục ẩn `.github`).
3. Mở tab **Actions** trên repo; bật GitHub Actions nếu được hỏi.
4. Chọn workflow **GitHub Trend Radar — Weekly Report** → **Run workflow** để chạy lần đầu.
5. Khi workflow chạy thành công, vào **Settings → Pages → Build and deployment**. Chọn **Deploy from a branch**, branch `main`, folder `/docs`, rồi bấm **Save**. Nếu branch mặc định của bạn khác `main`, dùng tên branch hiện tại.
6. Truy cập `https://TEN_TAI_KHOAN.github.io/github-trend-radar/` để xem dashboard trên máy tính hay điện thoại.

Lịch chạy mặc định: **08:00 sáng Thứ Hai, giờ Việt Nam**. GitHub Actions có thể bắt đầu trễ một chút so với thời điểm cron. Bạn vẫn có thể bấm **Run workflow** bất cứ lúc nào.

Nếu không đẩy được commit: vào **Settings → Actions → General → Workflow permissions** và cho phép workflow **Read and write permissions** (nếu repo hoặc tổ chức cho phép).

## 3. Đọc báo cáo

- `docs/index.html`: dashboard; mở trên iPhone, laptop hoặc GitHub Pages.
- `reports/latest.md`: báo cáo tuần gần nhất, có mô tả từng repository.
- `reports/YYYY-MM-DD.csv`: xuất dữ liệu tuần sang Excel.
- `data/weeks/YYYY-MM-DD.json`: dữ liệu JSON từng tuần; `data/index.json` lưu tối đa 104 tuần để tải vào dashboard.
- `demo/preview.html`: **dữ liệu giả chỉ để xem giao diện**, không phải thứ hạng thực tế.

## 4. Tuỳ chỉnh

Mở `config.json`, thay danh sách `languages` để thêm/bớt các trang Trending theo ngôn ngữ. Ví dụ:

```json
{
  "languages": ["python", "typescript", "rust", "go", "javascript", "c++"],
  "max_candidates": 85,
  "top_n": 10,
  "min_stars": 1,
  "request_timeout_seconds": 20
}
```

`max_candidates` tăng lên sẽ giúp tìm nhiều repo hơn nhưng tốn thêm GitHub API requests. `top_n` thay số lượng repo xếp hạng.

## 5. Chạy thử ở máy cá nhân (tuỳ chọn)

Cần Python phiên bản 3.10 trở lên.

```bash
pip install -r requirements.txt
python -m src.radar --demo
python -m src.radar
python -m unittest discover -s tests -v
```

`--demo` dùng số liệu hư cấu để xem giao diện **không cần internet**. Lệnh chạy thật cần internet để truy cập GitHub. Trên GitHub Actions, `GITHUB_TOKEN` được cấp sẵn; trên máy cá nhân bạn có thể đặt biến môi trường `GITHUB_TOKEN` để tăng quota truy cập API.

## 6. Lưu ý về phương pháp

- API GitHub phiên bản `2026-03-10` hỗ trợ `/repos/{owner}/{repo}/stargazers/history`, giúp thống kê star theo tuần. Lấy tuần Chủ nhật–Thứ Bảy đã kết thúc; không chọn tuần hiện tại khi dữ liệu chưa đủ.
- Nếu API lịch sử sao không dùng được, tool có chế độ dự phòng dùng số “stars this week” của GitHub Trending, ghi **rõ** đây là cửa sổ 7 ngày gần nhất (rolling), không đồng nhất với tuần lịch.
- Các nhãn AI, Security, DevOps, Embedded... dựa trên từ khoá trong metadata repo; là gợi ý xu hướng, không phải đánh giá chất lượng.
- GitHub thay đổi HTML Trending có thể ảnh hưởng phần khám phá repo. Workflow báo lỗi rõ ràng nếu không thu thập được dữ liệu đủ để xếp hạng.
- Khi repo công khai không hoạt động trong thời gian dài, GitHub có thể tự tắt workflow theo lịch; kiểm tra tab Actions nếu không thấy bản cập nhật.
