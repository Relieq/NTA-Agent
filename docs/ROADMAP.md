# NTA-Agent — Roadmap & Kiến trúc

Agent tự động chơi **Ninety Thousand Acres** (`twgame.global.acers`) trên BlueStacks.
Kế thừa ý tưởng chức năng từ [NTA-AutoBot](https://github.com/Relieq/NTA-AutoBot) (bản cũ, thuần
vision) nhưng nâng cấp lên kiến trúc **hybrid API-first + vision fallback** với **LLM làm bộ não
chiến lược**.

> **File này = kiến trúc & triết lý (ổn định).** Trạng thái thực + trình tự phần còn lại (cập nhật
> 2026-09-17): [superpowers/plans/2026-09-17-master-plan-remaining.md](superpowers/plans/2026-09-17-master-plan-remaining.md).
> Catalog API: [re/game-api.md](re/game-api.md). *Lưu ý: dự án đã đi API-first thuần — vision (Phase 1)
> cố ý hoãn.*

## 0. Bối cảnh kỹ thuật (đã xác minh 2026-09-01)

| Hạng mục | Giá trị |
|---|---|
| Package | `twgame.global.acers` v4.4.0 (versionCode 68), targetSdk 36 |
| Engine | **Cocos2d-x JavaScript** (`org.cocos2dx.javascript.AppActivity`) |
| Emulator | BlueStacks_nxt, Android 9, x86_64, **1600x900**, density 240 |
| ADB | `HD-Adb.exe` tại `C:\Program Files\BlueStacks_nxt\`, device `emulator-5554` (port 5555) |
| Mạng | Game nói **HTTPS (443)** → cần SSL-unpin (Frida) + mitmproxy để đọc protocol |
| APK | `/data/app/twgame.global.acers-*/base.apk` |

**Hệ quả thiết kế:**
- Engine Cocos JS ⇒ logic game & protocol nằm trong JS bundle (`assets/`, thường jsc-compiled
  hoặc XXTEA-encrypt). Có thể RE dần để hiểu message format.
- HTTPS ⇒ không đọc được traffic nếu chưa cài CA của mitmproxy + bypass cert pinning bằng Frida.
- Chính vì RE tốn công và rủi ro ⇒ **hybrid**: crack tới đâu dùng API tới đó, phần còn lại giữ
  vision (ADB tap) để agent luôn chơi được.

## 1. Triết lý kiến trúc: "Tay chân" vs "Bộ não"

```
┌──────────────────────────────────────────────────────────────┐
│  BỘ NÃO (Strategy)  —  LLM (Claude) cho quyết định lớn, định kỳ │
│  • build order dài hạn, phân bổ tài nguyên/quân                 │
│  • ngoại giao alliance, chọn mục tiêu tấn công/phòng thủ        │
│  • đọc "game state" đã chuẩn hoá, trả về "intents"              │
└───────────────▲───────────────────────────┬────────────────────┘
                │ state (JSON)               │ intents
┌───────────────┴───────────────────────────▼────────────────────┐
│  TAY CHÂN (Execution)  —  rule/heuristic engine, deterministic  │
│  • vòng lặp hằng ngày (thu tài nguyên, quay, daily task)         │
│  • công cụ dự đoán (battle outcome predictor, ROI build...)      │
│  • dịch "intent" → chuỗi hành động cụ thể                        │
└───────────────▲───────────────────────────┬────────────────────┘
                │ observations               │ actions
┌───────────────┴───────────────────────────▼────────────────────┐
│  I/O LAYER (Hybrid)                                              │
│  • API adapter: đọc/gửi request game (khi đã RE được)            │
│  • Vision adapter: OpenCV+OCR đọc màn hình, ADB tap (fallback)   │
│  • State store: hợp nhất 2 nguồn → 1 game-state chuẩn hoá        │
└─────────────────────────────────────────────────────────────────┘
```

Nguyên tắc: **LLM không bao giờ gọi tap/API trực tiếp.** Nó chỉ đọc state đã chuẩn hoá và phát
"intent" cấp cao (vd `{"action":"attack","target":"tile:1234,5678","troops":"preset_A"}`). Tay
chân dịch intent thành hành động và tự verify. Điều này giữ chi phí token thấp, chạy 24/7 bằng
rule, chỉ gọi LLM ở các "điểm quyết định" thưa.

## 2. Layout dự kiến (Python 3.12)

```
nta_agent/
  io/
    adb.py            # DeviceManager: tap/swipe/drag/screenshot (port từ core/device.py cũ)
    vision.py         # template matching + OCR (port từ core/vision.py cũ)
    api/
      capture.py      # mitmproxy addon ghi lại traffic game
      frida_ssl.py    # script Frida bypass cert pinning
      protocol.py     # parse/build message (điền dần khi RE)
      client.py       # API adapter gửi request thay cho tap
  state/
    schema.py         # dataclasses: Resources, Buildings, Troops, MapTile, Timers...
    store.py          # hợp nhất API + vision → GameState chuẩn hoá
  execution/
    heuristics.py     # rule engine (priority loop, daily tasks)
    predictors/
      battle.py       # dự đoán kết quả trận (dùng dữ liệu quân/tướng)
      build_roi.py    # tính ROI nâng cấp công trình
    intents.py        # định nghĩa Intent + resolver intent→actions
  brain/
    llm.py            # gọi Claude, đóng gói state→prompt, parse intents
    policies.py       # khi nào gọi LLM, guardrails, ngân sách token
  modules/            # port từ repo cũ: combat, builder, daily_task, captcha, scene
  config/             # build_order, timing, thresholds (JSON, giữ pattern cũ)
  data/               # map_data.json, captured traffic, replay logs
  main.py             # orchestrator: observe → decide → act loop
tools/
  re/                 # script RE: pull apk, decompile jsc, phân tích XXTEA key
tests/
docs/
```

## 3. Lộ trình phát triển (giai đoạn, tăng dần)

### Phase 0 — Nền tảng & scaffolding
- Khởi tạo project Python (venv, `pyproject.toml`/`requirements.txt`, ruff/pytest).
- Port & làm sạch `DeviceManager` (ADB tap/screenshot) + `VisionManager` từ repo cũ.
- Wrapper ADB trỏ đúng `HD-Adb.exe`, auto-detect port từ `bluestacks.conf`.
- Chuẩn hoá `GameState` schema (dataclasses) + state store rỗng.
- **Mốc:** agent chụp màn hình, tap được, có vòng lặp observe/act tối thiểu bằng vision.

### Phase 1 — Vision baseline vững (thay thế bản cũ)
- Port combat/builder/daily_task/captcha/scene; refactor theo boundary tay chân/IO.
- Bộ test template matching + hiệu chỉnh threshold (giữ debug_img/).
- Rule engine cho vòng lặp hằng ngày ổn định 24/7.
- **Mốc:** agent chơi được các tác vụ cơ bản ổn định hơn bản cũ, hoàn toàn bằng vision.

### Phase 2 — RE tầng API (đọc trước, chưa gửi)
- `tools/re/`: pull `base.apk`, tách `assets/`, xác định JS bundle bị jsc/XXTEA; tìm key giải mã.
- Dựng lab intercept: cài CA mitmproxy trong emulator + Frida SSL-unpin cho Cocos.
- Ghi lại traffic khi chơi tay từng chức năng → lập bảng ánh xạ endpoint/message.
- `protocol.py`: parse các message quan trọng nhất (resources, buildings, march, battle result).
- State store đọc **thêm** từ API để làm giàu/kiểm chứng state vision.
- **Mốc:** GameState chính xác & realtime từ API cho các domain đã crack; vision vẫn là nguồn dự phòng.

### Phase 3 — API actions (gửi request thay tap)
- `client.py`: gửi request cho các hành động an toàn, lặp nhiều (thu tài nguyên, quay, daily).
- Cơ chế an toàn: rate-limit giống người, jitter, fallback sang tap nếu API lỗi/đổi.
- **Mốc:** các tác vụ nền chạy bằng API (nhanh/nhẹ), phần rủi ro cao vẫn dùng vision.

### Phase 4 — Predictors (công cụ dự đoán "tay chân thông minh")
- `battle.py`: mô hình dự đoán kết quả trận từ thành phần quân/tướng/tech (data từ API + trận thật).
- `build_roi.py`: xếp hạng nâng cấp theo lợi ích/thời gian/tài nguyên.
- **Mốc:** agent tự chọn mục tiêu đánh & thứ tự build dựa trên dự đoán, không hardcode.

### Phase 5 — Bộ não LLM (chiến lược)
- `brain/llm.py`: đóng gói GameState → prompt gọn; Claude trả JSON intents có schema.
- `policies.py`: chỉ gọi LLM ở điểm quyết định (đầu ngày, khi tài nguyên dư, khi bị tấn công,
  quyết định alliance...), ngân sách token, guardrail chống hành động phá game.
- Vòng khép kín: state → LLM intent → resolver → action → verify → cập nhật state.
- **Mốc:** agent ra quyết định chiến lược linh hoạt, giải thích được, chạy nền bằng rule.

### Phase 6 — Vận hành & bền bỉ
- Logging/telemetry, dashboard theo dõi, auto-recover khi ADB/emulator chập chờn.
- Regression test khi game update (protocol/asset đổi) + quy trình cập nhật template/protocol.
- (Tuỳ chọn) đóng gói lại như bản cũ (PyInstaller) nếu cần phân phối.

## 4. Mục tiêu tối ưu cụ thể (đo lường được)

1. **Độ ổn định:** uptime 24/7, tự phục hồi lỗi ADB/emulator không cần can thiệp tay.
2. **Độ chính xác state:** sai số đọc tài nguyên/quân ~0 khi dùng API (so với OCR hay lệch).
3. **Chi phí:** phần lớn thời gian chạy 0 token (rule); LLM chỉ ở điểm quyết định thưa.
4. **Độ thông minh:** chọn mục tiêu đánh/build theo predictor thay vì kịch bản cứng.
5. **Khả năng bảo trì:** game update → chỉ sửa adapter/protocol/template, không viết lại lõi.
6. **An toàn tài khoản:** hành vi giống người (jitter, nghỉ), tránh pattern dễ bị phát hiện.

## 5. Rủi ro & giảm thiểu

- **Cert pinning / JS mã hoá mạnh** → RE lâu ⇒ hybrid đảm bảo vẫn chạy bằng vision trong lúc chờ.
- **Ban tài khoản** → ưu tiên vision cho hành động nhạy cảm, rate-limit, dùng tài khoản phụ để test.
- **Game update phá protocol/asset** → tách adapter, có regression test & quy trình cập nhật.
- **Chi phí LLM** → policy gọi thưa + cache quyết định + ngân sách token cứng.

## 6. Bước kế tiếp ngay

1. `/init` sinh `CLAUDE.md` (đã làm sau khi có roadmap này).
2. Dùng superpowers `brainstorming` để chốt chi tiết Phase 0–1 rồi `write-plan`.
3. Scaffold project Python + port `DeviceManager`/`VisionManager`.
4. Lập lab RE (tools/re/) song song để bắt đầu Phase 2.
