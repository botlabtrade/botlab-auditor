# Hướng dẫn đưa BOTLAB Auditor lên Vultr (dành cho người không chuyên kỹ thuật)

Tài liệu này viết cho chủ sở hữu, không cần biết lập trình. Bạn chỉ cần **sao chép từng dòng lệnh và
dán vào cửa sổ đen (Terminal)**, theo đúng thứ tự. Mỗi bước đều nói rõ bạn sẽ thấy gì.

Tổng thời gian: khoảng 25–35 phút. Chi phí: một máy chủ nhỏ nhất của Vultr (khoảng 6 USD/tháng) và
tiền dùng Serverless Inference theo lượng (rất nhỏ với mức demo).

> **Quy tắc an toàn quan trọng:** khoá API (API key) của Vultr **không bao giờ** được đưa vào mã
> nguồn hay đẩy lên GitHub. Bạn sẽ chỉ dán nó vào một tệp tên `.env` nằm trên máy chủ, ở Bước 7.
> Tệp `.env` đã được chặn không cho đưa lên GitHub.

---

## Bước 1 — Tạo máy chủ (VM) trên Vultr

1. Mở trang <https://my.vultr.com> và đăng nhập.
2. Bấm nút **Deploy** (hoặc dấu **+** màu xanh) → chọn **Deploy New Server**.
3. Chọn như sau:
   - Loại: **Cloud Compute – Shared CPU**
   - Vị trí: chọn nơi gần bạn (ví dụ **Singapore**)
   - Hệ điều hành (Operating System): **Ubuntu 24.04 LTS x64**
   - Kích thước (Plan): **1 vCPU / 2 GB RAM** (tối thiểu nên dùng 2 GB)
   - Phần **Additional Features**: không cần bật gì thêm
   - **Server Hostname**: gõ `botlab-auditor`
4. Bấm **Deploy Now** và chờ khoảng 2–3 phút cho tới khi trạng thái chuyển thành **Running**.
5. Bấm vào tên máy chủ vừa tạo. Bạn sẽ thấy:
   - **IP Address** — ví dụ `192.0.2.45` (ghi lại, sẽ dùng nhiều lần)
   - **Username** — là `root`
   - **Password** — bấm hình con mắt để xem, rồi bấm hình cái kẹp để sao chép

---

## Bước 2 — Tạo khoá Vultr Serverless Inference

1. Vẫn ở <https://my.vultr.com>, trong thanh menu bên trái bấm **Products** → **Serverless** →
   **Inference**.
2. Bấm **Add Serverless Inference**, đặt tên `botlab-auditor`, bấm **Add**.
3. Bấm vào mục vừa tạo, mở tab **API Keys** (hoặc **Overview**).
4. Bấm **Copy** để sao chép khoá. Khoá là một dãy chữ và số dài.
5. **Dán tạm khoá đó vào ứng dụng Ghi chú (Notepad) của riêng bạn.** Đừng gửi cho ai, đừng dán vào
   chat hay vào GitHub. Bước 7 sẽ dùng tới nó.

---

## Bước 3 — Mở cửa sổ đen và kết nối vào máy chủ

- Trên **Windows**: bấm phím Windows, gõ `powershell`, mở **Windows PowerShell**.
- Trên **macOS**: bấm `Cmd + dấu cách`, gõ `terminal`, mở **Terminal**.

Dán dòng dưới đây, **thay `IP_CUA_BAN` bằng IP ở Bước 1**, rồi bấm Enter:

```
ssh root@IP_CUA_BAN
```

- Lần đầu nó hỏi `Are you sure you want to continue connecting (yes/no)?` → gõ `yes` rồi Enter.
- Nó hỏi `password:` → dán mật khẩu đã sao chép ở Bước 1 rồi Enter.
  (Khi dán mật khẩu, màn hình **không hiện gì cả** — đó là bình thường, cứ bấm Enter.)

Khi thành công, dòng đầu cửa sổ sẽ đổi thành đại ý `root@botlab-auditor:~#`.

---

## Bước 4 — Cập nhật máy chủ

Dán cả khối sau (một lần), rồi Enter:

```
apt-get update -y && apt-get upgrade -y
```

Chờ 1–3 phút. Nếu màn hình xanh hỏi về việc khởi động lại dịch vụ, bấm Enter để chọn **Ok**.

---

## Bước 5 — Tải mã nguồn về máy chủ

```
apt-get install -y git
git clone https://github.com/botlabtrade/botlab-auditor.git /opt/botlab-auditor
cd /opt/botlab-auditor
```

Nếu sau này cần lấy bản mới nhất:

```
cd /opt/botlab-auditor && git pull
```

---

## Bước 6 — Chạy trình cài đặt tự động

Dán dòng sau rồi Enter:

```
sudo bash deploy/install.sh
```

Quá trình này mất khoảng 5–10 phút và tự làm mọi việc: cài Docker, dựng hộp cát (sandbox), tạo môi
trường Python, đăng ký dịch vụ tự khởi động, cài Caddy để có HTTPS.

Khi xong, phần cuối màn hình in ra địa chỉ web của bạn, dạng:

```
Public URL : https://192-0-2-45.sslip.io
```

(Đây là tên miền miễn phí sinh ra từ IP, không cần đi mua tên miền.)
**Hãy ghi lại địa chỉ này** — đó chính là đường dẫn demo công khai bạn nộp cho hackathon.

---

## Bước 7 — Dán khoá Vultr Serverless Inference vào tệp `.env`

Đây là bước **duy nhất** liên quan tới khoá bí mật. Dán dòng sau:

```
nano /opt/botlab-auditor/.env
```

Một trình soạn thảo chữ mở ra. Bạn sẽ thấy một dòng:

```
LLM_API_KEY=
```

Làm như sau:

1. Dùng phím mũi tên xuống/phải để đưa con trỏ về **cuối dòng `LLM_API_KEY=`** (ngay sau dấu `=`).
2. Dán khoá đã sao chép ở Bước 2 (Windows: bấm chuột phải; macOS: `Cmd + V`).
   Dòng đó sẽ thành `LLM_API_KEY=abc123...`
   **Không** thêm dấu ngoặc kép, **không** thêm dấu cách.
3. Kiểm tra hai dòng sau có đúng như vậy (chỉnh nếu khác):
   ```
   LLM_BASE_URL=https://api.vultrinference.com/v1
   LLM_MODEL=llama-3.3-70b-instruct
   ```
4. Lưu lại: bấm `Ctrl + O` → Enter → rồi `Ctrl + X` để thoát.

Khởi động lại ứng dụng để nó đọc khoá mới:

```
sudo systemctl restart botlab-auditor
```

Kiểm tra xem khoá đã được nhận chưa:

```
curl -s http://127.0.0.1:8780/api/health
```

- Nếu thấy `"inference":"vultr-serverless"` → **đã dùng Vultr Serverless Inference**. Xong.
- Nếu thấy `"inference":"offline-planner"` → khoá chưa được nhận (có thể dán thiếu). Làm lại Bước 7.
  Lưu ý: ứng dụng vẫn chạy đầy đủ ở chế độ `offline-planner`, chỉ là phần suy luận do bộ lập kế hoạch
  cố định đảm nhiệm thay cho mô hình ngôn ngữ.

---

## Bước 8 — Mở trang web và thử bốn bản demo

Mở trình duyệt, vào địa chỉ ở Bước 6, ví dụ `https://192-0-2-45.sslip.io`.

Bấm lần lượt bốn nút demo và bấm **Run the audit**. Kết quả đúng phải là:

| Nút demo | Kết luận phải ra |
|---|---|
| Honest trend-follower | `WATCH` |
| Overfit curve-fit | `NOT_READY` |
| Look-ahead peeker | `REJECTED_LOOKAHEAD` |
| Malicious upload | `REJECTED_UNSAFE` + 12 hành vi bị chặn hiện màu đỏ |

Nếu cả bốn ra đúng như bảng trên là hệ thống đã chạy chuẩn.

---

## Những lệnh hữu ích về sau

Xem ứng dụng còn sống không:

```
systemctl status botlab-auditor
```

Xem bản ghi (log) đang chạy (bấm `Ctrl + C` để thoát):

```
journalctl -u botlab-auditor -f
```

Khởi động lại ứng dụng:

```
sudo systemctl restart botlab-auditor
```

Cập nhật mã nguồn rồi chạy lại cài đặt (giữ nguyên tệp `.env`):

```
cd /opt/botlab-auditor && git pull && sudo bash deploy/install.sh
```

Dựng lại hộp cát sau khi mã nguồn thay đổi:

```
cd /opt/botlab-auditor && docker build -f sandbox/Dockerfile -t botlab-sandbox:latest .
```

---

## Khi gặp sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| Trình duyệt báo lỗi chứng chỉ / không vào được HTTPS | Chờ 2 phút cho Caddy lấy chứng chỉ, tải lại trang. Nếu vẫn lỗi: `systemctl restart caddy` |
| Trang trắng hoặc lỗi 502 | `journalctl -u botlab-auditor -n 50` để xem lý do, rồi `sudo systemctl restart botlab-auditor` |
| Bản demo chạy mãi không ra kết quả | `docker images` phải có dòng `botlab-sandbox`. Nếu không, dựng lại bằng lệnh `docker build` ở trên |
| Máy chủ hết RAM | Nâng plan Vultr lên 2 GB hoặc hơn, hoặc giảm `SANDBOX_MEM_MB` trong `.env` |
| Lỡ làm lộ khoá API | Vào Vultr → Serverless Inference → xoá khoá cũ (**Revoke**), tạo khoá mới, làm lại Bước 7 |

---

## Nhắc lại về an toàn

- Khoá API chỉ nằm trong `/opt/botlab-auditor/.env` trên máy chủ, quyền đọc `600`, **không** có trong
  mã nguồn và **không** được đưa lên GitHub.
- Mã người dùng tải lên chỉ chạy bên trong container không có mạng, hệ thống tệp chỉ đọc, chạy bằng
  người dùng không đặc quyền, có giới hạn tiến trình/bộ nhớ/CPU và bị giết sau 20 giây.
- Trang web không có đăng nhập, không có cookie, không lưu tệp người dùng tải lên và **không ghi nội
  dung tệp vào log**.
