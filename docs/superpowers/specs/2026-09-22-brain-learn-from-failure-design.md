# Brain học-từ-thất-bại — Thiết kế (2026-09-22)

Cho brain (LLM) **học từ kết cục xấu** (lính chết, cạn tài nguyên, mục tiêu kẹt) và **lưu hướng
giải quyết** để tái dùng. Giữ nguyên kiến trúc "hands = sự thật, brain = diễn giải"; brain KHÔNG
gọi tool/API trực tiếp.

> Bối cảnh: [ROADMAP.md](../../ROADMAP.md) (kiến trúc), [master-plan-remaining](../plans/2026-09-17-master-plan-remaining.md)
> (§B workstream brain). Đây là spec cho workstream đó, phần "thư viện chiến thuật + học từ thất bại".

## 1. Vấn đề

Verify từ code (2026-09-22): brain hiện là profile-editor hoàn chỉnh (digest → LLM → guard → apply),
đã có gọi-theo-sự-kiện (`brain_service._urgent`) và field `notes` (trí nhớ tự do). NHƯNG brain **mù
kết cục**:
- Trận vừa đánh mất bao lính / vì quái nào / chiêu gì — nằm trong Chiến Báo nhưng **loop không đọc**.
- Rule bị game từ chối vì hết tài nguyên (`500012`) — cooldown rải rác từng rule, **không gom** cho brain.
- `notes` do LLM tự viết, **không neo sự kiện thật** → dễ bịa nhân quả (vi phạm "đừng tự bịa").

## 2. Mục tiêu & phi-mục-tiêu

**Mục tiêu:**
1. Hands ghi lại **thất bại có thật** (deterministic) vào một ledger bounded.
2. Trên trận thua, hands chạy **counterfactual sim** (thứ tự đội khác) → gợi ý sửa được engine xác nhận.
3. Digest đưa failures + lessons cho brain thấy.
4. Brain **chưng cất bài học có-bằng-chứng** vào lessons store, nạp lại prompt, hiện trên dashboard.
5. Tự chủ **hỗn hợp**: lesson chỉnh lever an toàn → brain tự áp trong guardrail; việc lớn/không đảo
   ngược → chỉ advice cho người duyệt.

**Phi-mục-tiêu (đợt này):**
- Brain KHÔNG tự gọi tool/replay (Cách A: hands chủ động chạy, brain đọc kết quả — user chốt).
- Counterfactual chỉ xét **thứ tự đội**, chưa xét đổi thành phần đội / chiêu mộ thêm tank.
- Chưa làm **trigger-matching retrieval / auto-recall** (đó là Inc 3, để sau).
- Không đụng `max_loss`, build.order, army.group (của người).

## 3. Nguyên tắc chống bịa (load-bearing)

**Hands sinh SỰ THẬT; brain chỉ diễn giải có trích dẫn.** Mọi lesson LLM viết ra **bắt buộc trỏ tới
`event_id` tồn tại trong ledger**; guard **loại** lesson không có/evidence sai. Đây là cách ép luật
"verify before assert / đừng tự bịa" thành code. Counterfactual dùng engine thật (sim) làm bằng chứng
cho "hướng giải quyết", không phải suy đoán LLM.

## 4. Kiến trúc & luồng

```
HANDS (deterministic, 0 token)                    BRAIN (LLM, thưa)
occupy đánh → injuryPawns tăng (trigger rẻ)
  → actions.get_battle_record (cùng session MQTT)
  → sidecar replay: {selfDead, enemyDead, quái, AoE}
  → sidecar counterfactual: order nào giảm loss
  → FailureLedger.record(battle_loss, evidence)
res-block 500012 / stuck goal → ledger.record(...)
        │
        ▼
   failures.json (bounded, atomic)
        │  digest.failures (tóm tắt) + lessons hiện hành
        ▼
                                          brain tick: đọc failures+lessons →
                                          (a) chỉnh lever an toàn NGAY
                                          (b) emit lessons[{trigger,diagnosis,
                                              resolution,evidence}]
                                          (c) việc lớn → advice
        ┌─────────────────────────────────────┘
        ▼
   guard: evidence phải khớp ledger; resolution.lever qua guard lever hiện tại
        ▼
   lessons.json (bounded, dedup theo trigger) → nạp lại digest lần sau
        ▼
   dashboard: panel Failures + Lessons (người pin/retire)
```

## 5. Thành phần & interface

### 5.1 FailureLedger — `nta_agent/execution/ledger.py` (mới)
Append-only, bounded (giữ N gần nhất, mặc định 100), ghi atomic (tmp+os.replace) vào
`build/run/failures.json`. Thuần, không phụ thuộc loop.

```python
@dataclass
class FailureEvent:
    id: str            # "<epoch_ms>-<seq>"
    ts: float
    kind: str          # "battle_loss" | "res_depletion" | "stuck_goal"
    context: dict      # kind-specific (xem 6)
    # battle_loss: {cell, army_uids, self_dead, enemy_ids, aoe:bool, predicted_loss,
    #               counterfactual:{best_order, loss}|None}
    # res_depletion: {rule, resource|None}
    # stuck_goal: {goal, detail}

class FailureLedger:
    def __init__(self, path, cap=100): ...
    def record(self, kind: str, context: dict) -> str          # trả event_id
    def recent(self, n: int = 10, kind: str | None = None) -> list[FailureEvent]
    def has(self, event_id: str) -> bool                        # guard dùng để kiểm evidence
    def aggregate_res(self, window_s: float) -> dict            # {resource: count} cho digest
```
Chống spam: res_depletion **gộp** theo (rule, resource) trong cửa sổ (không ghi mỗi tick); battle_loss
chỉ ghi khi self_dead > 0.

### 5.2 Counterfactual + record summary — sidecar + Python
**Sidecar** (`tools/battlesim/server.js`) thêm 2 method JSON-RPC:
- `replay(record)` → `{summary:{self_dead,enemy_dead,frames,is_win}, hits:[{by_id,target_id,dmg,frame}], enemy_ids:[...]}`.
  Tái dùng logic replay-log qua **module dùng chung mới** `tools/battlesim/record-summary.js` (tách từ
  `replay-log.js`; cả CLI replay-log lẫn method này gọi vào — tránh 2 bản đọc trận lệch nhau).
- `counterfactual(record, orders)` → `{by_order:{tank_first:{loss},dps_first:{loss},auto:{loss}}}`.
  Dùng đường `forecast` với thành phần quái lấy từ record + đội mình reorder theo từng order.

**Python** `nta_agent/execution/counterfactual.py` (mới): gọi `SimBridge` với method mới; fail
(`SimUnavailable`/no Node) → trả None, ledger vẫn ghi loss (best-effort, không chết loop).
- `summarize_record(bridge, record) -> RecordSummary|None`
- `best_counterfactual_order(bridge, record) -> {best_order, loss}|None`
- AoE detect: một `by_id` (quái) gây `hit` lên **>1 target** cùng frame → `aoe=True`.

### 5.3 Digest — mở rộng `nta_agent/brain/digest.py`
Thêm khi có dữ liệu:
- `failures`: `[{id, kind, ...compact}]` — last ~8 event; battle_loss kèm `counterfactual.best_order`.
- `res_pressure`: `aggregate_res(window)` — {resource: count} (vd {"cereal": 6}).
- `lessons`: bài học active hiện hành (id, trigger, diagnosis, resolution tóm tắt).

### 5.4 Lessons store — `nta_agent/brain/lessons.py` (mới) + `build/run/lessons.json`
```python
@dataclass
class Lesson:
    id: str
    created: float; last_seen: float; times_seen: int
    trigger: dict           # {kind, match:{monster_id?|resource?|goal?}}
    diagnosis: str          # LLM, <=200 ký tự
    resolution: dict        # {"lever_edits": {...}}  hoặc  {"advice": "..."}
    evidence: list[str]     # event_id (>=1, phải có thật trong ledger)
    validated_by: str | None  # "sim: tank_first loss 0 vs 1"
    status: str             # "active" | "retired"
```
Bounded (mặc định 50), dedup theo `trigger` (trùng → cập nhật last_seen/times_seen thay vì thêm mới).
API: `load/save`, `upsert(lesson)`, `active() -> list`, `retire(id)`, `pin(id)`.

### 5.5 Guard — mở rộng `nta_agent/brain/guard.py`
`sanitize_lessons(edits, ledger, existing, valid_army_uids, valid_build_ids) -> list[Lesson]`:
- **evidence**: lọc `event_id` qua `ledger.has(...)`; **không còn evidence nào ⇒ loại cả lesson** (chống bịa).
- `resolution.lever_edits`: chạy qua `sanitize_edits` hiện có → chỉ giữ lever hợp lệ, đã clamp; nếu
  chạm field human-owned/`max_loss` → **chuyển thành `resolution.advice`** (tự chủ hỗn hợp).
- `diagnosis/advice`: cắt 200 ký tự; `trigger.match` whitelist khoá cho phép.
- clamp số lesson & độ dài như notes/advice.

### 5.6 BrainService — mở rộng `nta_agent/runtime/brain_service.py`
- Nạp `FailureLedger` + `Lessons` (đường từ cfg); đưa vào digest.
- Sau khi LLM trả: tách `edits["lessons"]` → `sanitize_lessons` → `lessons.upsert` → save.
  Lesson có `resolution.lever_edits` an toàn thì các lever đó **cũng nằm trong `edits`** (brain tự áp
  ngay); phần chuyển-thành-advice thì gộp vào `advice` (đã có đường ghi `brain_advice.json`).
- `_urgent`: thêm điều kiện fire khi có battle_loss mới hoặc res_pressure vượt ngưỡng.

### 5.7 Runner — `nta_agent/runtime/runner.py`
- Khởi tạo ledger + counterfactual bridge; truyền `ledger` (status_sink kiểu như composer) cho các rule
  để report res_depletion/stuck; OccupyCell báo battle_loss (đọc injury delta → fetch record → summarize
  → counterfactual → ledger.record).
- Đặt phần "phát hiện + ghi battle_loss" ở **hands** (OccupyCell hoặc một observer nhẹ trong loop), 0 token.

### 5.8 Config — `nta_agent/runtime/config.py`
Thêm `failures_path`, `lessons_path` (mặc định dưới `build/run/`), `res_pressure_window_s`,
`ledger_cap`, `lessons_cap`.

### 5.9 LLM prompt — `nta_agent/brain/llm.py`
Thêm mô tả: schema `lessons[]`; **luật bắt buộc evidence trỏ event_id trong digest.failures**; khi nào
dùng lever-edit vs advice; đọc `res_pressure` để hạ tham vọng recruit/build; đọc `counterfactual.best_order`
để đặt `occupy.policy.order`.

### 5.10 Dashboard (Inc 2)
Panel **Failures** (gần đây + counterfactual) và **Lessons** (list, nút retire/pin). Đọc failures.json +
lessons.json; pin/retire ghi qua control file như các panel khác. (Vue 3 no-build, theo mẫu panel sẵn có.)

## 6. Nguồn sự kiện (chi tiết)

| kind | phát hiện (hands) | context |
|---|---|---|
| `battle_loss` | `injuryPawns` tăng sau occupy → fetch record → summarize | cell, army_uids, self_dead, enemy_ids, aoe, predicted_loss, counterfactual |
| `res_depletion` | rule back-off trên `ecode.500012` | rule, resource (suy ra nếu biết), gộp theo cửa sổ |
| `stuck_goal` | composition blocked (composition_status.json) / occupy kẹt 1 target lâu | goal, detail |

## 7. Xử lý lỗi (không bao giờ chết loop)
- Fetch record / sidecar hỏng → bỏ qua enrichment, ledger vẫn ghi loss từ injury-delta.
- Không có Node/engine → counterfactual = None (giống occupy đã fallback stats).
- Ghi file atomic; đọc lỗi → coi như rỗng. Mọi hook bọc try/except như brain hiện tại.

## 8. Kiểm thử (TDD)
- **ledger**: record/bound/rotate; res_depletion gộp cửa sổ; `has()` cho guard. (unit thuần)
- **counterfactual/summary**: trên **fixture record 1-tile có thật** → self_dead khớp; AoE detect đúng
  (quái trúng >1 target/frame); best order hợp lý. (dùng lại fixture golden sẵn có)
- **digest**: shape failures/res_pressure/lessons.
- **guard**: lesson thiếu evidence → loại; evidence sai id → loại; lever an toàn → giữ+clamp; chạm
  human-owned/max_loss → chuyển advice.
- **brain_service**: fake chat emit lesson hợp lệ → apply+persist; emit lesson bịa (no evidence) → drop;
  battle_loss mới → `_urgent` fire.
- Integration Python↔sidecar (replay/counterfactual) skip nếu thiếu Node+engine (theo mẫu hiện có).

## 9. File đụng tới
Mới: `execution/ledger.py`, `execution/counterfactual.py`, `brain/lessons.py`,
`tools/battlesim/record-summary.js`. Sửa: `brain/{digest,guard,llm}.py`,
`runtime/{brain_service,runner,config}.py`, `tools/battlesim/{server.js,replay-log.js}` (refactor dùng
chung), dashboard (Inc 2). Tests theo §8.

## 10. Phân đợt
- **Inc 1**: §5.1–5.3, 5.7–5.9 phần failures/counterfactual/digest + prompt đọc failures. (brain thấy
  sự thật + tự chỉnh lever theo counterfactual; chưa có lesson store)
- **Inc 2**: §5.4–5.6, 5.10 lessons store + guard evidence + dashboard. (chưng cất & lưu bài học)
