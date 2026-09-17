# Farming — vòng hồi máu liên tục (Heal-Routing) — Design

**Ngày:** 2026-09-17 · **Phase:** C (farming ngoài thành) · **Kiểu:** deterministic, no-LLM.

## 1. Bối cảnh & mục tiêu
Vòng farm cốt lõi đã chạy trong `RuleEngine.default`: `OccupyCell` (chiếm ô thắng được, chọn theo
loot/chest budget) + `ClaimTreasures` (mở/nhận rương). Thiếu để **farm LIÊN TỤC**: khi lính bị
thương, đội mất sức chiến; hiện không có cơ chế đưa quân đi hồi rồi quay lại. Mục tiêu đợt này:
giữ các đội luôn khoẻ để farm không gián đoạn, và không phí request lúc cạn stamina.

## 2. Cơ chế game (đã RE — `tools/re/decrypted/index.js`, xem `docs/re/game-api.md`)
- **Hồi máu lính BỊ THƯƠNG = tự động server-side khi đội trú Cứ Điểm** (hoặc thành). Không có
  endpoint client, lượng hồi không giới hạn. Giới hạn duy nhất: `maxArmyCount` (≈5 đội/ô, từ
  `n.max_army` của buildBase). ⇒ Agent chỉ cần **điều quân tới fort/thành** rồi chờ hồi.
- **Điều quân:** `HD_MoveCellArmy { indexs:[int], uids:[str], target:int, isSameSpeed:bool }`
  (giống `HD_OccupyCell` bỏ `autoBackType`).
- **Tự về sau trận:** `HD_OccupyCell.autoBackType` điều khiển đội tự quay về sau khi đánh (pref
  `BATTLE_AUTO_BACK_TYPE`); giá trị cụ thể **cần verify live** (§8).
- **Lính thương xuất hiện trong state:** pawn mang `hp:[cur,max]` (engine `curHp`/`getMaxHp`).
  Đội "bị thương" = có pawn `hp[0] < hp[1]`. (Lính CHẾT → `injuryPawns`/`curingQueues`, ngoài phạm vi.)
- **Fort/thành của ta:** `player.fortAutoSupports[{index,val}]` (Cứ Điểm) + `mainCityIndex` —
  đã có trong `execution/territory.py` (Territory model, PR#15).

## 3. Ngoài phạm vi (user chốt 2026-09-17)
- **Hồi sinh lính chết** (`HD_CureInjuryPawn`, tốn slot).
- **Tonden/đồn điền** (`HD_CellTonden` — sản lượng ô); cơ chế chưa verify, ghi ở `docs/re/game-api.md`.
- **Thu-sản-lượng-ô kiểu auto-collect:** không tồn tại (đã xác nhận).

## 4. Kiến trúc

### 4.1 State — hp đội + phát hiện thương (io/api parse + schema)
- `state/schema.py`: đảm bảo `Pawn` có `hp: tuple[int,int]` (cur,max); `Army`/đạo quân expose pawns.
- Parse từ raw player/armies (miễn phí request — dùng dữ liệu Entry/GetPlayerArmys sẵn có).
- Helper thuần: `army_is_wounded(army) -> bool` (`any(p.hp[0] < p.hp[1])`), và
  `army_wound_frac(army) -> float` (tổng hp thiếu / tổng max) để xếp ưu tiên.

### 4.2 `HealRoutingRule` (execution/heuristics.py) — deterministic, best-effort
- **`applies`:** có ≥1 đạo quân bị thương **và không đang ở/không đang về** fort/thành, và fort đích
  còn chỗ (`< maxArmyCount` đội đang trú). Rẻ: đọc từ state, không request khi không cần.
- **`act`:** với mỗi đội thương (ưu tiên `wound_frac` cao):
  - Chọn **fort/thành gần nhất còn chỗ** (Manhattan tới block, tái dùng `territory.dist_to_main`/fort
    positions). Trong bán kính-6 quanh thành → về thành (đằng nào cũng free-speed).
  - Gọi `actions.move_cell_army([army], target=fort_index)`.
  - Cap số đội điều mỗi tick (tránh spam) + tôn trọng chỗ trống fort.
- **Không chặn loop:** mọi lỗi nuốt như `ClaimTreasures` (`fired.append(name!ERR)` do RuleEngine lo).
- **Action mới** `actions.move_cell_army(armies, target, *, same_speed=False)` — build `indexs/uids`
  như `occupy_cell`, gọi `HD_MoveCellArmy`, `_apply_result`.

### 4.3 Nhịp stamina (guard trong `OccupyCell.applies`)
- Trước khi discover (tốn nhiều `GetAreaInfo`), nếu `state.resources.stamina < min_occupy_cost`
  (chi phí stamina occupy rẻ nhất, từ `landAttr`/config) → **return False** (nhả tick, khỏi phí request).
- Tái-điều-quân đã có: mỗi tick `OccupyCell` chọn mục tiêu thắng-được kế tiếp; đội đã hồi xong tự
  vào lại vòng chọn (vì hết wounded → HealRouting không giữ nữa).

### 4.4 Wiring
- `RuleEngine.default`: chèn `HealRouting()` **trước** `OccupyCell` (ưu tiên giữ quân khoẻ trước khi
  đẩy đi đánh tiếp). Thứ tự: Collect, BuildOrder, Recruit, **HealRouting**, OccupyCell, ClaimTreasures, ClaimTasks.

## 5. Data flow
```
tick → state(hp đội) → HealRouting: đội thương? → MoveCellArmy về fort gần nhất còn chỗ
     → OccupyCell: đủ stamina & có đội khoẻ? → chọn target (chest budget) → OccupyCell(autoBackType)
     → ClaimTreasures: rương mới? → open+claim (chest budget)
(đội hồi xong ở fort → hết wounded → lần tick sau quay lại OccupyCell)
```

## 6. Xử lý lỗi
- HealRouting & pacing đều **best-effort**; ecode (vd ô đầy `maxArmyCount`, đội đang march) → nuốt
  qua RuleEngine, không dừng loop. `decision_service` đã enrich ecode→lý do tiếng Việt (PR#29).
- Không điều đội đang march/đang trú đúng fort (tránh loop điều tới-lui).

## 7. Testing (TDD, `.venv/Scripts/python.exe -m pytest`)
- `army_is_wounded`/`army_wound_frac`: thuần, các case hp đầy/thiếu/nhiều pawn.
- `HealRouting.applies`: có đội thương + fort còn chỗ → True; đội khoẻ → False; đội đang ở fort → False;
  fort đầy `maxArmyCount` → False.
- `HealRouting.act`: chọn fort gần nhất còn chỗ; gọi `move_cell_army` đúng target; cap mỗi tick.
- `move_cell_army`: build `indexs/uids/target` đúng shape (fake session).
- `OccupyCell` pacing: stamina < min_cost → `applies` False, không gọi discover (đếm request qua fake).
- Regression: full suite xanh + ruff.

## 8. Câu hỏi mở — verify live (chạy thật trên emulator)
1. **Pawn hp field** đúng key/shape trong raw (Entry vs GetPlayerArmys)?
2. **`autoBackType`** giá trị nào = tự về thành sau đánh? Nếu occupy đã auto-về-thành-hồi thì
   HealRouting chỉ cần lo đội **trú ngoài** (fort xa). Điều chỉnh phạm vi theo kết quả.
3. Thành chính có hồi máu như Cứ Điểm không (để chọn đích gần nhất hợp lý)?
4. Khi nào coi là "đã hồi xong" — hp về đầy tức thì hay theo thời gian? (ảnh hưởng nhịp re-dispatch.)

> Verify live nằm **trong** đợt này (user chọn). Kết quả có thể tinh chỉnh 4.2/4.3 trước khi code
> phần phụ thuộc; phần thuần (helpers, action shape) làm TDD ngay.

## 9. Files (dự kiến — chốt ở implementation plan)
- `nta_agent/state/schema.py` — đảm bảo pawn hp.
- `nta_agent/execution/heuristics.py` — `HealRouting` + wiring.
- `nta_agent/execution/actions.py` — `move_cell_army`.
- `nta_agent/execution/army_health.py` (mới, thuần) — `army_is_wounded`/`army_wound_frac`.
- `tests/test_army_health.py`, `tests/test_heal_routing.py`, cập nhật `tests/test_occupy_rule.py`.
