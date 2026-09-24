# Đóng gói NTA-Agent thành app (bản portable cho nhóm nhỏ)

Ngày: 2026-09-24 · Trạng thái: chờ duyệt spec

## 1. Mục tiêu và phạm vi

**Mục tiêu:** bạn bè (nhóm nhỏ, mỗi người tự có LDPlayer + game) tải một file zip, giải nén, bấm
`NTA-Agent.exe` là chạy được agent + dashboard; tự nhập API key sau; nhận bản mới bằng một nút.

**Đã chốt với người dùng:**
- Đối tượng: bạn bè / nhóm nhỏ, **không phát hành công khai rộng rãi**. Chỉ Windows (LDPlayer).
- Hình thức: **thư mục portable + mở dashboard trong trình duyệt** (không installer, không cửa sổ riêng).
- Battle sim: **kèm Node portable**.
- Cập nhật: **nút "Kiểm tra cập nhật"** lấy từ GitHub Releases (repo `Relieq/NTA-Agent` đang public).
- Kỹ thuật: **hướng A** — Python 3.12 embeddable + code `.py` nguyên dạng (không PyInstaller cho app).

**Ngoài phạm vi (YAGNI):** installer/MSI, cửa sổ app riêng, macOS/Linux, ký số (code signing),
GitHub Actions tự build, nhiều người dùng trên một máy, đa ngôn ngữ ngoài tiếng Việt, TypeSafe/Jev.

**Nguyên tắc bất biến:**
- Bản phát hành **chỉ chứa code của mình**, **không chứa dữ liệu game** (config/engine trích từ APK có
  bản quyền) và **không chứa khoá XXTEA**. Dữ liệu game được trích trên máy từng người từ APK của họ.
- Không có key/bí mật nào nằm trong thư mục app hay trong log.
- Môi trường phát triển hiện tại (`.env`, `build\…`, chạy từ repo) **giữ nguyên hành vi**.

## 2. Cấu trúc thư mục và đường dẫn

```
NTA-Agent\                         ← thư mục app; bị thay khi cập nhật
  NTA-Agent.exe                    launcher (mục 6)
  NTA-Agent.bat                    launcher dự phòng (khi antivirus chặn exe)
  VERSION                          vd "0.1.0"
  runtime\python\                  Python 3.12 embeddable + site-packages (paho-mqtt, numpy, pillow)
  runtime\node\                    node.exe portable (>= 18)
  app\nta_agent\                   package
  app\tools\battlesim\             sidecar Node
  app\tools\re\decrypt_jsc.py      chỉ các script cần cho trích xuất
  app\tools\re\extract_config.py

%LOCALAPPDATA%\NTA-Agent\          ← dữ liệu người dùng; cập nhật không bao giờ đụng tới
  settings.json                    cài đặt (bí mật mã hoá DPAPI — mục 4)
  token.txt
  gamedata\config\*.json           trích từ base.apk
  gamedata\schema.json             schema protobuf (giải mã msg.jsc — BẮT BUỘC, xem mục 9)
  gamedata\engine\index.js         engine đã giải mã
  gamedata\meta.json               {game_version, extracted_at}
  run\                             events/state/profile/alerts… (thay build\run)
  backups\app-<ver>\               tối đa 2 bản
```

**`nta_agent/paths.py`** — nguồn duy nhất cho đường dẫn:
- `APP_DIR`: suy từ vị trí package (`…\app` khi đóng gói, gốc repo khi dev).
- `PACKAGED`: True khi tồn tại `APP_DIR.parent / "runtime"` và `VERSION`.
- `DATA_DIR`: `NTA_DATA_DIR` (env) > `%LOCALAPPDATA%\NTA-Agent` (khi PACKAGED) > `build` (dev).
- Các getter: `run_dir()`, `token_path()`, `config_dir()`, `engine_js()`, `settings_path()`,
  `backups_dir()`, `node_exe()` (`runtime\node\node.exe` khi PACKAGED, ngược lại `"node"`).
- Dev: `config_dir()` = `nta_agent/data/config`, `engine_js()` = `tools/re/decrypted/index.js`,
  `run_dir()` = `build/run` — **y như hiện tại**.

**Chỗ phải đổi sang `paths.py`:** `data/config.py` (`_CONFIG_DIR`), `runtime/config.py`
(`token_path`, `log_dir`), `dashboard/names.py`, `execution/predictors/sim_bridge.py` (node exe +
truyền `NTA_ENGINE_JS`/`NTA_CONFIG_DIR` cho sidecar), `tools/launch_detached.py`, dashboard supervisor.

## 3. Thiết lập lần đầu

### 3.1 README.md — phần người dùng tự làm
1. Cài LDPlayer 9, bật **Root** và **ADB** trong cài đặt LDPlayer (kèm ảnh).
2. Cài game từ Play Store, **đăng nhập Google một lần** (OAuth — bắt buộc do người làm).
3. Giải nén zip, chạy `NTA-Agent.exe` (SmartScreen: More info → Run anyway; antivirus chặn → dùng
   `NTA-Agent.bat`).
4. Làm theo trang **Thiết lập** trên dashboard.
5. (Tuỳ chọn) nhập OpenAI key và khoá giải mã dữ liệu game trong **Cài đặt**.
6. **Cảnh báo:** dùng bot có thể bị khoá tài khoản; mỗi lúc chỉ một phiên đăng nhập (agent chạy thì
   không vào game trên LDPlayer được và ngược lại — dừng agent trước khi vào game).
7. Gỡ lỗi thường gặp (liên kết từ từng bước của trang Thiết lập, dạng `README.md#buoc-3-root`).

### 3.2 Trang "Thiết lập" (dashboard) — app tự kiểm tra và tự làm
Module mới `nta_agent/setup/` (mỗi bước một hàm thuần có thể test, trả `{ok, detail, fix_hint, doc}`),
backend `GET /api/setup` (trạng thái), `POST /api/setup/run {step}`:

| # | Bước | Cách làm | Bắt buộc |
|---|---|---|---|
| 1 | Tìm ADB | `NTA_ADB_PATH`/settings > registry LDPlayer > `C:\`, `D:\LDPlayer\LDPlayer9\adb.exe` | ✓ |
| 2 | Giả lập | `adb devices`; nhiều máy → cho chọn, lưu `adb_serial` | ✓ |
| 3 | Root | `su -c id` chứa `uid=0` | ✓ |
| 4 | Game + phiên bản | `dumpsys package twgame.global.acers` → versionName; so `SUPPORTED_GAME_VERSION` | ✓ |
| 5 | Dữ liệu game | tự dò khoá XXTEA từ `libcocos2djs.so`; `pm path` → pull `base.apk` (temp) → giải mã `msg.jsc` → `gamedata\schema.json`; bảng config → `gamedata\config`; giải mã engine → `gamedata\engine\index.js`; ghi `meta.json`; xoá apk tạm | ✓ |
| 6 | Distinct id | root đọc `shared_prefs/com.thinkingdata.analyse.xml` (randomID) → settings | ✓ |
| 7 | Token | `bootstrap.read_account_token` → `token.txt` (chưa có → hướng dẫn đăng nhập Google trong game rồi thử lại) | ✓ |
| 8 | Key | trỏ sang trang Cài đặt | ✗ |

- Chưa xong bước 1–7 → dashboard mở thẳng trang Thiết lập; **nút Start agent bị khoá**
  (`/api/agent/start` trả lỗi có lý do).
- Bước 5 tự chạy lại khi `meta.json.game_version` ≠ phiên bản game đang cài.
- Phiên bản game **khác** `SUPPORTED_GAME_VERSION` → cảnh báo đỏ, khoá Start (giao thức có thể đổi);
  cho phép "vẫn chạy" có xác nhận (dành cho bạn — người sẽ vá).
- `SUPPORTED_GAME_VERSION` = `nta_agent/version.py` `GAME_VERSION` (đã là nguồn duy nhất).

## 4. Cài đặt và bí mật

- File `%LOCALAPPDATA%\NTA-Agent\settings.json`; module `nta_agent/settings.py`
  (`load()`, `save()`, `get(key)`), ghi nguyên tử (tmp + replace).
- **Bí mật** (`openai_api_key`, `xxtea_key`) lưu dạng **DPAPI** (`CryptProtectData`, phạm vi user, qua
  `ctypes`, base64) — chỉ đúng user Windows trên đúng máy giải mã được. Không phải Windows (test/CI) →
  lưu nguyên + cờ `plain` (chỉ dùng cho test).
- Thứ tự ưu tiên: **biến môi trường / `.env` > `settings.json` > mặc định**. Dev không đổi.
- **Không bao giờ** ghi bí mật vào events/errors/log; API trả dạng che (`sk-…a1b2`); dashboard vẫn chỉ
  bind `127.0.0.1`.
- Trang **"Cài đặt"**: OpenAI key (ẩn ký tự + nút "Kiểm tra key" gọi `GET /v1/models`), model brain
  (mặc định `gpt-4o-mini`), `brain_max_calls`, **khoá giải mã dữ liệu game** (XXTEA —
  tuỳ chọn, chỉ để nhập đè khoá tự dò — xem mục 9), giả lập/ADB serial.
- `llm.default_chat()` đọc key qua `settings.get` **mỗi lần gọi** → đổi key không cần restart;
  trống key → `BrainUnavailable` như hiện tại.

## 5. Cập nhật

**Phát hành (bạn chạy):** `python tools/package.py --version X.Y.Z` tạo trong `dist\`:
- `NTA-Agent-X.Y.Z-full.zip` (runtime + app + launcher), `NTA-Agent-X.Y.Z-app.zip` (chỉ `app\` +
  `VERSION`), `manifest.json` = `{version, game_version, runtime: {python, node}, assets: {name: sha256},
  notes}`. Script tải Python embeddable + Node portable (có cache, kiểm sha256 của nguồn), cài gói bằng
  `pip install --target`, loại `tests/`, `tools/re` (trừ 2 script trích xuất), dữ liệu gitignored.
- Đăng: `gh release create vX.Y.Z dist\* --notes-file …` (thủ công).

**Kiểm tra:** `GET https://api.github.com/repos/Relieq/NTA-Agent/releases/latest` lúc khởi động (tối đa
1 lần/6 giờ) và khi bấm nút → so `VERSION` (semver) → banner "Có bản X.Y.Z" + ghi chú.

**Áp dụng** (`nta_agent/updater.py`, chạy như tiến trình riêng):
1. Dashboard dừng agent, copy `updater.py` ra thư mục tạm, chạy nó bằng `runtime\python`, rồi thoát.
2. Updater chờ PID dashboard/agent kết thúc (tối đa 30s).
3. Tải asset (app.zip; nếu `manifest.runtime` khác bản đang cài → full.zip) → **kiểm sha256**, sai → huỷ.
4. Giải nén vào `…\app.new` (và `runtime.new` nếu cần) → chuyển `app` sang
   `DATA_DIR\backups\app-<cũ>` → đổi tên `app.new` → `app` → cập nhật `VERSION`.
5. Mở lại launcher; chờ dashboard trả lời `/api/health` trong 30s → không được thì **khôi phục** bản cũ
   và mở lại.
- Nút "Quay lại bản trước" trong Cài đặt; giữ 2 backup.
- Chỉ tải từ `github.com/Relieq/NTA-Agent` release assets qua HTTPS.

## 6. Launcher

- `NTA-Agent.exe`: stub nhỏ chỉ dùng stdlib (build bằng PyInstaller onefile **chỉ cho launcher**) —
  chạy `runtime\python\pythonw.exe -m nta_agent.app` với `cwd=app\`.
- `nta_agent/app.py`: nếu dashboard đã chạy (pidfile + `/api/health`) → chỉ mở trình duyệt; ngược lại
  khởi động dashboard **detached** (tái dùng logic `tools/launch_detached.py`), chờ cổng sẵn sàng, mở
  `http://127.0.0.1:<port>`. Cổng bận → thử cổng kế tiếp, lưu vào settings.
- `NTA-Agent.bat`: cùng lệnh, cho trường hợp antivirus chặn exe.
- Agent vẫn được bật/tắt qua dashboard (supervisor hiện có), dùng `sys.executable` của runtime.

## 7. Xử lý lỗi

- Mỗi bước Thiết lập trả lỗi có **hướng dẫn sửa + link README**; không bước nào làm crash dashboard.
- Trích xuất dữ liệu: ghi vào thư mục tạm rồi mới đổi tên → không để lại dữ liệu nửa vời.
- Cập nhật: mọi lỗi trước bước đổi tên → không thay đổi gì; sau bước đổi tên → khôi phục backup.
- Không có mạng khi kiểm tra cập nhật → im lặng, thử lại lần sau.

## 8. Kiểm thử

- Unit (pytest, không cần thiết bị): `paths` (dev vs packaged vs `NTA_DATA_DIR`), `settings` (ưu tiên
  env, che key, DPAPI round-trip trên Windows), từng bước `setup` với ADB giả, `updater` (semver,
  sha256 sai → huỷ, đổi tên + rollback trên thư mục tạm), `package.py` (danh sách file: có `app\`,
  không có `tests\`, dữ liệu game, `KEY.txt`, `.env`).
- Test "không rò rỉ": quét `dist\*.zip` không chứa `nta_agent/data/config/*.json` (trừ `manifest`),
  `tools/re/decrypted`, `KEY.txt`, `.env`, `build/`.
- Thử thật (thủ công): giải nén full.zip vào thư mục mới trên máy này với `NTA_DATA_DIR` tạm → chạy
  launcher → đi hết trang Thiết lập với LDPlayer thật → Start agent → cập nhật lên bản giả (release
  nháp) → rollback.

## 9. Rủi ro và điểm cần lưu ý

- **Khoá XXTEA:** không nhúng vào bản phát hành (tránh phát tán công cụ bẻ mã hoá tài nguyên game).
  **Sửa khi triển khai:** khoá là BẮT BUỘC (`schema.json` — giao thức protobuf, sinh từ `msg.jsc` mã
  hoá XXTEA — là dữ liệu game gitignore; thiếu nó agent không đăng nhập được). Giải pháp cuối: khoá
  nằm dạng chuỗi rõ trong `libcocos2djs.so` của game, nên bước 5 **tự dò** khoá từ APK của người
  dùng (`gamedata.find_xxtea_key`: thử các chuỗi ≥16 ký tự lên file `internal/index.jsc` 320 byte,
  ~1.6s). Không repo/bản phát hành nào chứa khoá; ô XXTEA trong Cài đặt chỉ để nhập đè.
- **Điều khoản game:** bot có thể bị khoá tài khoản — nêu rõ trong README và màn hình đầu.
- **Antivirus/SmartScreen:** exe không ký số có thể bị cảnh báo → có `.bat` dự phòng + hướng dẫn.
- **Giao thức đổi khi game cập nhật:** khoá Start khi phiên bản game không khớp; bạn phát hành bản vá.
- **Nhiều máy ảo LDPlayer:** chọn serial ở bước 2.
