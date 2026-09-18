# A1 — Hồi sinh lính chết (Revive Injured) — Design

**Ngày:** 2026-09-18 · **Phase:** A (hoàn thiện farm) · **Kiểu:** deterministic, no-LLM, best-effort.
**Spec master:** [master-plan-remaining](../plans/2026-09-17-master-plan-remaining.md) §2.A1.

## 1. Mục tiêu
Sau mỗi trận farm có thể có lính **chết** (khác lính **bị thương** — thương tự hồi ở fort/thành, xem
[heal-loop](2026-09-17-farming-heal-loop-design.md)). Lính chết vào `injuryPawns`, phải **hồi sinh**
(`HD_CureInjuryPawn`) để lấy lại giá trị. Đợt này: rule tự hồi sinh, cost-aware, an toàn.

## 2. Cơ chế (RE + VERIFY LIVE 2026-09-18)
- **API:** `HD_CureInjuryPawn{index, armyUid, armyName, pawnUid}`.
  - `index` = ô thành hồi sinh vào (main city). `pawnUid` = uid lính chết.
  - `armyUid` = đội **đang ở thành** để nhận lính; **hoặc `armyUid=""` + `armyName`** → tạo đội mới.
- **`player.injuryPawns[]`** item = `{uid, id, lv, deadTime}` — KHÔNG mang index/army (đích do ta chọn).
- **Tốn tài nguyên**: verify live 1 revive = **−56 cereal** (free-budget `CURE_FREE_COUNT` hết → tính phí).
- **Có thời gian**: reply `queues[{uid,auid,index,needTime:54000,surplusTime,id,lv}]` (54s); lính vào
  `army.curingPawns[{uid,id,lv,curing:true,deadTime}]`. Xong thời gian mới nhập đội.
- **Giới hạn (user caveat):** slot hàng đợi = policy effect `CURE_QUEUE`, free-count = `CURE_FREE_COUNT`
  — **do policy chi phối, KHÔNG cố định** → ta **không hardcode**, để **server enforce** (attempt +
  cooldown khi bị từ chối).
- **ecode:** `500019` = đội đích đầy (4 đội hiện đều 9 lính); (dự) hết slot/không đủ tài nguyên → ecode khác.

## 3. Ngoài phạm vi
- `SpeedUpCuringPawn` (tăng tốc, tốn vật phẩm), `GiveupInjuryPawn` (bỏ lính).
- Tính chính xác free-count/slot client-side (fragile) — dựa vào server enforce.

## 4. Kiến trúc
### 4.1 State
`GameState` thêm `injury_pawns: list[dict]` (parse từ `player.injuryPawns`). Miễn phí request.

### 4.2 Action
`actions.cure_injury_pawn(index, army_uid, army_name, pawn_uid) -> dict` → `HD_CureInjuryPawn`,
`_apply_result(reply)` (cập nhật resources từ `output`).

### 4.3 Rule `ReviveInjured` (best-effort, như ClaimTreasures)
- **applies:** có `injury_pawns`, profile cho phép (`revive.enabled`, mặc định True), không cooldown,
  và tài nguyên ≥ sàn an toàn (`revive.min_cereal` floor, tránh đốt sạch — cost-aware vì revive tốn phí).
- **chọn đích:** đội ở thành (`index==main`) còn chỗ (`len(pawns)+len(curingPawns) < capacity_hint`,
  mặc định 9); nếu tất cả đầy → đội mới (`army_uid="", army_name="Cứu Hộ"`). *(capacity_hint chỉ là gợi ý;
  nếu sai server trả `500019` → cooldown, không hardcode cứng.)*
- **act:** hồi sinh lính **giá trị cao nhất** (lv, rồi id) trước; cap `max_per_tick` (mặc định 1); ecode →
  `_cooldown` (tránh spam request bị từ chối). Không bao giờ làm chết loop.
- Action mới + parse curingPawns của đội để tính occupancy.

### 4.4 Wire
`RuleEngine.default`: chèn `ReviveInjured()` cạnh `HealRouting`/`ClaimTreasures` (sau farm).

## 5. Cost-safety
Revive tốn tài nguyên ⇒ mặc định **cap 1/tick** + **sàn tài nguyên** + cooldown-on-ecode. Người chơi
chỉnh qua `profile.revive`. Không tự tăng tốc/bỏ lính.

## 6. Testing (TDD)
- `injury helpers`: parse + chọn lính giá trị cao; chọn đích (đội còn chỗ / đội mới).
- `cure_injury_pawn`: build request đúng shape (fake session).
- `ReviveInjured.applies/act`: có lính chết + đội còn chỗ → cure; tất cả đầy → đội mới; hết tài nguyên
  (dưới sàn) → False; cap/tick; ecode → cooldown, không raise.
- Full suite + ruff.

## 7. Verify live — ✅ END-TO-END (2026-09-18)
Chạy `ReviveInjured` thật: 3 lính chết còn lại → hồi sinh hết vào đội "Cứu Hộ" (4 đội gốc đầy 9 lính →
`revive_target` chọn đội còn chỗ); `injuryPawns` về rỗng; cereal −220 (~73/lính, cost-aware, trừ đúng);
đội "Cứu Hộ" `curingPawns=3`. Chọn lính giá trị cao trước (id 3305 lv cao cure đầu). Không ecode (đủ slot
lần này); đường ecode.500019 (đội đầy) → cooldown đã test unit. 362 test pass.
