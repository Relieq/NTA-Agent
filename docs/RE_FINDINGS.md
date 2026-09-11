# Reverse-Engineering Findings — tầng API của Ninety Thousand Acres

Kết quả khảo sát tĩnh `base.apk` (v4.4.0, pull 2026-09-01). Mục tiêu: xác định độ khả thi &
đường đi tới tầng API (Phase 2 trong [ROADMAP](ROADMAP.md)). **Kết luận: API-first rất khả thi.**

## Engine & build
- **Cocos Creator** (không phải cocos2d-x thuần). Layout `assets/assets/app/import/**` + UUID +
  `index.jsc` + `config.json`.
- Codename nội bộ: **`jwm`** (SLG). Game version chuỗi boot: `4.4.3` (APK versionName 4.4.0).
- 4 ABI native: `lib/{arm64-v8a,armeabi-v7a,x86,x86_64}/libcocos2djs.so`. Emulator dùng **x86_64**.

## Protocol = Protocol Buffers (protobuf.js)
`assets/assets/app/config.json` liệt kê `paths`:
- `lib/pb/protobuf/protobuf.js`, `lib/pb/long/long.js` → runtime **protobuf.js**.
- **`proto/msg.d`** → toàn bộ định nghĩa message của game (bundled asset, đang mã hoá).
- `core/@api/api.d`, `core/@api/mc.d`, `core/@api/ut.d`, `core/@api/cc.d` → **tầng API trong code**.

⇒ Traffic mạng gần như chắc chắn là **protobuf over HTTPS/WebSocket**. Có schema (`proto/msg.d`)
là giải mã được toàn bộ message tĩnh, không phải đoán.
(Lưu ý: 14 file `.proto` ở root APK — `client_analytics`, `firebase/perf`, `google/protobuf/*`,
`messaging_event` — chỉ là của **Firebase/analytics**, KHÔNG phải protocol game.)

## Mã hoá code: XXTEA
- `config.json`: `"encrypted": true`. Các `.jsc` (gồm `app/index.jsc` 1.17MB và `proto/msg.d`) bị
  **XXTEA-encrypt**. Header `index.jsc` không có magic bytecode → khớp XXTEA.
- Native export trong `libcocos2djs.so`: `jsb_set_xxtea_key`, `xxtea_decrypt`, `xxtea_encrypt`.
- Key **KHÔNG** nằm trong `main.js`/`jsb-*.js` (đã grep) ⇒ set từ native.

### Cách lấy XXTEA key (Phase 2)
1. **Frida hook `jsb_set_xxtea_key`** (khuyến nghị): hook hàm này lúc boot, dump tham số string =
   key. Sau đó `xxtea_decrypt` toàn bộ `.jsc` offline → đọc `proto/msg.d` + `core/@api/*` để có
   full schema + endpoint. Cần Frida chạy được (xem "Chặn kỹ thuật" bên dưới).
2. Static: dịch ngược `libcocos2djs.so` (Ghidra) tìm chuỗi key truyền vào `jsb_set_xxtea_key`.

## Mạng
- Game nói **HTTPS (443)** (đã thấy connection trong /proc/net/tcp). Cần:
  - Cài **CA của mitmproxy** trong emulator.
  - **Bypass certificate pinning** (Frida SSL-unpin) nếu có pinning.
- Có `assets/resources/native/7d/...pem` (225KB) — chứng chỉ/khoá đóng gói, cần soi kỹ (có thể là
  cert dùng cho pinning hoặc mã hoá payload).

## Hot-update — nguồn code/proto "live"
- `main.js` có cơ chế hot-update: tải code mới về `<writable>/slg-hot-update/`, lưu
  `HotUpdateSearchPaths` trong localStorage. ⇒ Code/proto đang chạy có thể **mới hơn APK** và khớp
  đúng server hiện tại. Ưu tiên đọc bản hot-update khi truy cập được.

## Chặn kỹ thuật hiện tại (cần xử lý cho Phase 2)
- BlueStacks emulator **không root**, `su` không có, `run-as twgame.global.acers` bị chặn ⇒ **chưa
  đọc được** `/data/data/.../files/slg-hot-update` và chưa chạy được Frida server kiểu root.
- **Hướng xử lý:**
  - Bật **Root access trong BlueStacks Settings** (BlueStacks_nxt hỗ trợ toggle) → có su → chạy
    `frida-server` + đọc private files. **Đây là bước mở khoá chính cho Phase 2.**
  - Hoặc **Frida gadget** nhúng (repack APK) nếu không muốn root.
  - Hoặc chỉ cần MITM: cài CA + set proxy emulator, chấp nhận decode protobuf bằng schema lấy được.

## Việc cụ thể tiếp theo cho Phase 2 (thứ tự)
1. Bật root BlueStacks (hoặc chuẩn bị Frida gadget). *(cần user hoặc thao tác settings)*
2. Cài `frida-tools` + `frida-server` (x86_64) → hook `jsb_set_xxtea_key`, dump key.
3. Viết `tools/re/decrypt_jsc.py` (XXTEA) → giải mã `index.jsc` + `proto/msg.d`.
4. Trích `.proto` schema từ `proto/msg.d` → sinh Python protobuf classes.
5. Dựng mitmproxy + SSL-unpin → capture traffic khi chơi tay, map endpoint ↔ message.
6. `nta_agent/io/api/` : `protocol.py` (encode/decode), `client.py` (gửi request).
