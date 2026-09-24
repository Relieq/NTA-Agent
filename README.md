# NTA-Agent

Trợ lý tự động chơi **Ninety Thousand Acres** (giả lập Android LDPlayer). Agent nói chuyện
thẳng với máy chủ game, tự xây dựng, chiếm đất, rèn đồ… và có bảng điều khiển trên trình duyệt.

> ⚠ **Rủi ro:** dùng bot có thể vi phạm điều khoản của game và dẫn tới **khoá tài khoản**.
> Bạn tự chịu trách nhiệm khi dùng.
>
> ⚠ **Một phiên duy nhất:** khi agent chạy, game trong giả lập sẽ bị đăng xuất (và ngược lại).
> Muốn tự chơi thì bấm **⏹ Stop** trước.

---

## Cài đặt (bản portable)

1. Tải `NTA-Agent-<phiên bản>-full.zip` từ trang Releases.
2. Giải nén vào một thư mục **bạn có quyền ghi**, ví dụ `D:\NTA-Agent\`
   (đừng để trong `C:\Program Files`).
3. Chạy **`NTA-Agent.exe`**. Trình duyệt sẽ mở bảng điều khiển tại `http://127.0.0.1:8787`.
   - Nếu Windows SmartScreen chặn: bấm **More info → Run anyway** (app chưa được ký số).
   - Nếu phần mềm diệt virus chặn `NTA-Agent.exe`: dùng **`NTA-Agent.bat`**, hai file làm y hệt nhau.
4. Lần đầu, bảng điều khiển mở tab **Thiết lập & Cài đặt**. Làm theo 7 bước bên dưới.
   Nút **▶ Start** bị khoá cho tới khi cả 7 bước đều ✅.

Không cần cài Python hay Node: app đã kèm sẵn.

## Chuẩn bị trước

- **LDPlayer 9** (Android 9). Tải ở ldplayer.net.
- Game **Ninety Thousand Acres** đã cài trong LDPlayer, **đúng phiên bản app hỗ trợ**
  (xem bước 4).
- (Tuỳ chọn) **OpenAI API key** để bật "bộ não" chiến lược + chat.

---

## Các bước thiết lập

Ở tab **Thiết lập & Cài đặt**, bấm **▶ Chạy tất cả** hoặc chạy từng bước. Bước nào ❌ sẽ
hiện gợi ý sửa, sửa xong bấm **Chạy lại**.

<a id="buoc-1-adb"></a>
### Bước 1: Tìm ADB

App tự tìm `adb.exe` của LDPlayer (thường ở `D:\LDPlayer\LDPlayer9\adb.exe` hoặc
`C:\LDPlayer\LDPlayer9\adb.exe`). Nếu cài LDPlayer ở chỗ khác, nhập đường dẫn vào ô
**Đường dẫn adb.exe** trong phần Cài đặt rồi chạy lại.

<a id="buoc-2-gia-lap"></a>
### Bước 2: Kết nối giả lập

- Mở LDPlayer.
- Vào **Cài đặt LDPlayer → Khác → Gỡ lỗi ADB** và chọn **Mở kết nối cục bộ**.
- Nếu mở nhiều máy ảo, nhập đúng thiết bị (ví dụ `emulator-5554`) vào ô **Thiết bị ADB**.

<a id="buoc-3-root"></a>
### Bước 3: Quyền root

Vào **Cài đặt LDPlayer → Khác → Quyền ROOT = Bật**, lưu lại rồi **khởi động lại LDPlayer**.
App cần root để đọc mã thiết bị và token đăng nhập của game (chỉ đọc, không sửa gì).

<a id="buoc-4-game"></a>
### Bước 4: Phiên bản game

App kiểm tra phiên bản game đang cài có khớp với bản app hỗ trợ không. Lệch phiên bản có thể
khiến agent gửi lệnh sai. Nếu game vừa cập nhật mà app chưa có bản mới, bạn có thể bấm
**Bỏ qua** (tự chịu rủi ro) hoặc chờ bản cập nhật của app.

<a id="buoc-5-du-lieu-game"></a>
### Bước 5: Dữ liệu game

App **không** kèm dữ liệu của game. Bước này lấy file cài đặt game (APK) **từ chính giả lập
của bạn**, rồi giải mã giao thức, các bảng số liệu và engine trận đánh vào thư mục dữ liệu
riêng của bạn.

- Khoá giải mã được **tự tìm trong chính bản game của bạn**, bạn không cần nhập gì.
- Mất khoảng 10–30 giây. Phải **dừng agent** trước khi chạy lại bước này.
- Khi game cập nhật phiên bản, hãy chạy lại bước này.

<a id="buoc-6-distinct-id"></a>
### Bước 6: Mã thiết bị

Đọc mã thiết bị mà game dùng khi đăng nhập. Nếu lỗi, hãy mở game một lần cho tới màn hình
chính rồi chạy lại.

<a id="buoc-7-token"></a>
### Bước 7: Token đăng nhập

1. Trong LDPlayer, mở game và **đăng nhập** (Google/Facebook…).
2. **Thoát game** (vuốt tắt hẳn).
3. Chạy lại bước này. Phải dừng agent trước.

Khi đủ 7 bước ✅, bấm **▶ Start** ở góc trên.

---

## Cài đặt (tab Thiết lập & Cài đặt)

| Mục | Ý nghĩa |
|---|---|
| OpenAI API key | Tuỳ chọn. Bật bộ não chiến lược + chat. Tính phí vào tài khoản OpenAI của bạn; nút **Kiểm tra OpenAI key** thử key miễn phí. |
| Model / Giới hạn lượt gọi | Model OpenAI (mặc định `gpt-4o-mini`) và số lần gọi tối đa mỗi phiên. |
| XXTEA key | Để trống: app tự tìm khoá trong bản game của bạn. Chỉ nhập khi bước 5 báo không tìm được. |
| adb.exe / Thiết bị ADB | Chỉ cần khi app không tự dò được. |

Key được **mã hoá bằng tài khoản Windows của bạn**: copy file sang máy khác sẽ không đọc
được. Bảng điều khiển không bao giờ hiện lại key đầy đủ.

## Cập nhật

- Khi có bản mới, thanh xanh **⬆ Có bản mới** hiện trên cùng. Bấm **Cập nhật**: agent dừng,
  app tải bản mới (kiểm tra checksum), tự khởi động lại sau khoảng 1 phút.
- Nếu bản mới không khởi động được, app **tự quay về** bản cũ.
- Muốn quay về bản trước bằng tay: phần Cài đặt → **↩ Quay về bản trước**
  (app giữ 2 bản gần nhất).
- Cập nhật không đụng tới dữ liệu, key và cài đặt của bạn.

## Dữ liệu nằm ở đâu

Mọi thứ của riêng bạn nằm ở `%LOCALAPPDATA%\NTA-Agent\`:

- `settings.json`: cài đặt, key đã mã hoá
- `token.txt`: token đăng nhập game
- `gamedata\`: dữ liệu game trích từ APK của bạn
- `run\`: trạng thái agent, nhật ký
- `backups\`: các bản app cũ

**Gỡ cài đặt:** xoá thư mục app và thư mục `%LOCALAPPDATA%\NTA-Agent`.

## Xử lý sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| Trình duyệt không mở | Tự mở `http://127.0.0.1:8787`. Nếu cổng bận, app chuyển sang 8788, 8789… |
| Start báo "Chưa hoàn tất Thiết lập" | Mở tab Thiết lập, chạy các bước còn ❌. |
| Agent chuyển sang CRASHED | Xem `%LOCALAPPDATA%\NTA-Agent\run\errors.jsonl` và `dashboard.log`. Token hết hạn thì làm lại bước 7. |
| Game trong giả lập bị đăng xuất | Bình thường: agent và game dùng chung một phiên. |
| Bước 5 báo "không tìm được khoá" | Game có thể đã đổi cách lưu khoá: báo người chia sẻ app, hoặc nhập XXTEA key thủ công ở Cài đặt. |

---

## Dành cho người phát triển

Mã nguồn Python 3.12 (venv `.venv`), sidecar mô phỏng trận Node ≥ 18. Kiến trúc và lộ trình
nằm trong `docs/ROADMAP.md`; ghi chú vận hành cho agent nằm trong `CLAUDE.md`.

```bash
.venv/Scripts/python.exe -m pytest -q                  # test
.venv/Scripts/python.exe -m ruff check nta_agent tests # lint
.venv/Scripts/python.exe tools/launch_detached.py dashboard   # chạy dashboard (dev)
```

Đóng gói bản phát hành (commit trước, vì chỉ file đã được git theo dõi mới được đóng gói):

```bash
.venv/Scripts/python.exe tools/package.py --version 0.1.0 --notes "..."
# -> dist/NTA-Agent-<v>-full.zip, dist/NTA-Agent-<v>-app.zip, dist/manifest.json
gh release create v0.1.0 dist/NTA-Agent-0.1.0-full.zip dist/NTA-Agent-0.1.0-app.zip dist/manifest.json
```

App tự cập nhật bằng cách đọc `releases/latest` của repo này. Bản `app` (nhỏ) được dùng khi
runtime (Python/Node) không đổi, ngược lại dùng bản `full`.
