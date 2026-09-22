# NTA-Agent — Kế hoạch tổng cho phần còn lại (2026-09-17, cập nhật 2026-09-22)

Bản đồ **những gì còn lại**, phản ánh đúng hiện trạng (dự án đã đi **API-first thuần**, vượt xa
[ROADMAP.md](../../ROADMAP.md) gốc). Mỗi workstream ở §2 sẽ có spec + implementation plan riêng khi
bắt tay làm (theo flow brainstorming → write-plan). Đây là tài liệu **định hướng & trình tự**, không
phải plan thực thi từng bước.

> **Cập nhật 2026-09-22 (đã xong thêm kể từ 09-17):**
> - **Army composition** (brain đặt strike_target, hands ArmyComposer dồn/chiêu mộ) — XONG, live.
> - **Battle-sim fidelity** (reinforce tiêm vào trận đang chạy, 0 sai số) + battle-record replay tool — XONG.
> - **B (Bộ não chiến lược) — thư viện chiến thuật THẬT qua "học-từ-thất-bại"** (Inc 1–3): FailureLedger +
>   counterfactual sim + LessonStore (guard bắt buộc evidence, chống bịa) + contextual recall + dashboard.
>   XONG cả 3 đợt, verified live (PR #69/#70/#71). Xem specs/plans `2026-09-22-brain-learn-from-failure*`.
> - **F1 Auto-recover** — health monitor chủ động (probe khi staleness → recover half-open) + telemetry
>   dashboard. XONG, verified live (PR #72).
> - **F2 Regression guard** — version một-nguồn + config manifest + endpoint-catalog test. XONG.
>
> **Còn lại chính:** E1 Bazaar (chưa có code), brain Inc 4 (counterfactual đổi thành-phần-đội + recall
> theo resource/goal), A3 expansion presets (đã có `execution/expansion.py`), G1 mở rộng (đã có khung).

---

## 1. Hiện trạng (đã xong — grounded theo code + PR)

**I/O (API-first):** MQTT/protobuf session (`io/api/`), API adapter `execution/actions.py` (~30
endpoint verify-live), catalog đầy đủ 134 endpoint (`docs/re/game-api.md`). ADB `io/adb.py` (chưa dùng
nhiều). **Vision adapter (OpenCV/OCR) CHƯA dựng** — khác ROADMAP gốc.

**State:** `state/schema.py` + `store.py` (GameState từ API), snapshot cho dashboard.

**Execution ("tay chân") — rule engine `heuristics.py`:**
- CollectCityOutput, **BuildOrder** (prereq-guarded, PR#31), Recruit, **HealRouting** (PR#33),
  **OccupyCell** (farming + chest budget), ClaimTreasures, ClaimTasks.
- Predictors: `battle.py` (stats + **sim sidecar** engine thật), `treasure_model`, `economy`, `army_value`.
- Map/lãnh thổ: `territory.py` (Tier A + **Tier B full-map** enemy/frontier, PR#30), `mapchunk.py`,
  `fort_advisor.py` (C2 gợi ý Cứ Điểm, PR#16).
- `occupy_planner` (discovery robust, PR#35), `formation`, `order_strategies`, `army_health` (PR#33).

**Brain (LLM):** `brain/{llm,policies,digest,guard,lessons}.py`; `decision_service` (ceri unlock
human-in-loop), `equipment`, `brain_service`, chat. **Thư viện chiến thuật THẬT qua học-từ-thất-bại đã
có** (2026-09-22): ledger → counterfactual → lessons có-evidence → contextual recall. Xem
[[nta-agent-brain-scenarios]] / specs `2026-09-22-brain-learn-from-failure*`.

**Vận hành:** dashboard Vue 3 (control agent, map, panels), `eventlog`, `fort_service`, `proc`
(pidfile/supervisor). RE docs (`PROTOCOL.md`, `RE_FINDINGS.md`, `game-api.md`).

**Đối chiếu ROADMAP gốc:** Phase 0–4 coi như đạt (qua đường API, bỏ qua vision baseline). Phase 5
(bộ não LLM) mới ở mức hạ tầng. Phase 6 (bền bỉ/ops) làm một phần (dashboard). Vision fallback (Phase 1)
là món **cố ý hoãn**.

---

## 2. Các workstream còn lại

Ký hiệu quy mô: **S** (≤1 buổi), **M** (1–3 buổi), **L** (nhiều buổi/nhiều PR). RE = cần đọc engine;
LIVE = cần verify trên emulator.

### A. Hoàn thiện vòng đánh/farm
- **A1 — Hồi sinh lính chết** (S–M, LIVE). ✅ **XONG (PR#37, 2026-09-18).** `HD_CureInjuryPawn` + rule
  `ReviveInjured` (cost-aware, best-effort). Verify live end-to-end.
- **A2 — ~~Tonden (đồn điền)~~** — ❌ **BỎ (user quyết 2026-09-18).** Tonden = đỗ quân ô đã chiếm lấy
  rương theo thời gian, không đánh; nhưng chỉ hữu ích cho người chơi ÍT THỜI GIAN (agent đã giải quyết) +
  không lấy được scroll/đinh. RE giữ ở `docs/re/game-api.md`. Xem [[nta-agent-strategy]].
- **A3 — Chiến lược MỞ RỘNG LÃNH THỔ (expansion presets)** (M) — *định nghĩa lại* (không phải toggle UI).
  Profile `expansion: spiral|octopus|hybrid` → **bias chọn mục tiêu** cho `OccupyCell`/`discover_targets`:
  - **Xoắn ốc (spiral):** ưu tiên ứng viên **kề đúng 1 ô owned** (single-file, phơi bày tối thiểu, dễ dựng
    hàng phòng thủ khi bị đánh) — dùng khi không bật chế độ bảo vệ.
  - **Bạch tuộc (octopus):** ưu tiên ô **dễ** (loss thấp) + hướng tới / khóa ô **giàu tài nguyên lv5** (chỉ
    chiếm được ô liền kề nên vươn "vòi" để chặn địch).
  - **Hybrid:** kết hợp. *Deps: none (dựa dữ liệu owned + land config sẵn có).* Chi tiết: [[nta-agent-strategy]].

### B. Bộ não chiến lược (LLM) — ✅ **XONG (PR#41, 2026-09-18)**
Brain là **profile-editing** (đọc digest → sửa profile; hands thực thi; token thưa) — kiến trúc đã có,
nay NỐI với năng lực mới: digest thêm `injured`+`territory` (enemy/frontier/nearest_enemy_dist từ
forts.json); brain điều khiển `occupy.expansion` + `revive.enabled`; guard validate; `_SYSTEM` hướng dẫn
threat/cost-aware. Verify live: địch gần→spiral, cereal thấp→tắt revive. *Còn lại (tuỳ chọn):*
- **B2 — Policy/guardrail nâng cao** (S–M). Gọi LLM theo sự kiện (bị đánh/dư tài nguyên) thay vì chỉ cadence
  cố định; cache; ngân sách token cứng hơn. `brain/policies.py` hiện chỉ every_ticks + max_calls.

### C. Trí tuệ bản đồ / advisor
- **C1 — Advisor dùng dữ liệu địch** — ✅ **XONG (PR#40).** `recommend_forts` né địch (điểm an toàn +
  danger_radius); `fort_service` truyền enemy. Tương thích ngược khi no-enemy.
- **C2 — ~~Verify protection radius~~** — ❌ **BỎ (user biết geometry, giữ radius-6/Manhattan).**

### D. Kinh tế / giao thương
- **E1 — Bazaar tự động** (M, RE+LIVE). `HD_BazaarBuyRes/SellRes/SellToSys/...` cân bằng tài nguyên
  (bán dư, mua thiếu cho build/recruit). *Deps: RE shape + rule ROI.*

### E. Bền bỉ / vận hành (ROADMAP Phase 6)
- **F1 — Auto-recover** — ✅ **XONG (PR#72, 2026-09-22).** Reactive recovery (backoff, session/token/captcha)
  ĐÃ có từ trước; nay thêm **proactive**: `last_activity` + HealthMonitor probe khi staleness → recover
  half-open + telemetry `health.json` (dashboard header). Verify live.
- **F2 — Regression khi game update** — ✅ **XONG.** `nta_agent/version.py` GAME_VERSION một-nguồn +
  `tools/re/gen_config_manifest.py` (manifest hash/version) + tests `test_config_regression`/
  `test_endpoint_catalog`/`test_game_version`. Quy trình cập nhật trong CLAUDE.md.
- **F3 — Vision fallback adapter** (L, cố ý hoãn). OpenCV+OCR+ADB tap cho domain chưa crack / khi API đổi.
  Chỉ làm nếu đường API tỏ ra không đủ hoặc cần an toàn tài khoản cho hành động nhạy cảm. *Deps: lớn.*

### F. Ngoại giao / con người
- **D1 — Alliance** (L, phần lớn do người chơi quyết — xem memory human-in-loop). Đọc thành viên/rank/log
  trước; hành động (join/policy/flag) sau, có xác nhận người. *Deps: none, nhưng ưu tiên thấp.*
- **G1 — Mở rộng human-in-the-loop** (S–M). Đưa thêm quyết định (unlock binh chủng, policy) lên dashboard
  (đã có khung ceri/equipment). *Deps: none.*

---

## 3. Trình tự đề xuất & lý do

**Đợt gần (hoàn thiện lõi chiến đấu + độ tin cậy):**
1. **A1 Hồi sinh lính chết** — nối tiếp trực tiếp HealRouting; thương vong đang tích lũy.
2. **C2 Verify protection radius** — rẻ, chốt geometry, unblock C1.
3. **C1 Advisor dùng dữ liệu địch** — tận dụng Tier B, làm farm/fort thông minh + né địch.

**Đợt giữa (kích hoạt "bộ não" — mục tiêu headline của dự án):**
4. **B1 Thư viện chiến thuật** (dùng digest + enemy data từ C1) → **B2 policy/guardrail**.

**Đợt sau (chiều sâu kinh tế + vận hành nền dài):**
5. **A2 Tonden**, **E1 Bazaar** (chiều sâu kinh tế).
6. **F1 Auto-recover**, **F2 Regression** (trước khi chạy 24/7 không giám sát).

**Hoãn/tuỳ chọn:** **D1 Alliance**, **F3 Vision fallback**, **A3/G1** (làm xen khi cần).

Lý do thứ tự: (a) hoàn thiện vòng đánh/farm cho vững trước khi thêm chiều sâu; (b) advisor-địch làm giàu
dữ liệu cho brain; (c) brain là giá trị cốt lõi nhưng cần lõi deterministic chín (giờ đã chín) + dữ liệu
tốt; (d) ops/bền bỉ trước khi giao agent chạy dài; (e) vision/alliance tốn công, giá trị biên thấp lúc này.

---

## 4. Nguyên tắc xuyên suốt
- **Verify live kỷ luật:** RE tĩnh chỉ là giả thuyết — chạy thật mới chốt (bài học `hp={0:cur,1:max}`,
  autoBackType=0, ô chiếm không tự hồi). Mỗi workstream có bước LIVE nếu chạm cơ chế chưa xác minh.
- **An toàn tài khoản:** rate-limit/jitter giống người; hành động nhạy cảm/không đảo ngược cần cân nhắc;
  login API đá phiên client → hạn chế login thừa.
- **Tay chân vs bộ não:** LLM chỉ đọc state + phát intent, không gọi API trực tiếp. Giữ token thấp.
- **TDD + best-effort rules:** rule không bao giờ làm chết loop; test trước, verify sau, PR nhỏ + merge.
- **Hybrid vẫn là kim chỉ nam:** nếu sau này API đổi/gãy, F3 (vision) là lưới an toàn — đừng để API-only
  thành điểm gãy đơn.

## 5. Ghi chú
ROADMAP.md giữ vai trò **kiến trúc & triết lý** (tay chân/bộ não, hybrid). Tài liệu này là **trạng thái
thực + trình tự phần còn lại** tại 2026-09-17; cập nhật khi hoàn thành từng workstream.
