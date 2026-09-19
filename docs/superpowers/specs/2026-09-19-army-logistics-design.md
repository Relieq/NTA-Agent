# Army Logistics (dồn/nạp/điều đội) — Design

**Goal:** tự động lấp đầy lính cho các đội thiếu quân: dồn lính giữa các đội cùng ô
(ưu tiên giữ lính nhiều máu), kéo đội thiếu về thành để `Recruit` nạp đầy, rồi để
**brain** quyết điều đội đi đâu.

**Bối cảnh (verified):**
- Recruit chỉ nạp đội `state==NONE` **ở đúng ô thành chính** (`hasNotFullArmy`:
  `state===MARCH || index!==mainCityIndex → không nạp`). Đội ở ô khác không nạp được.
- `HD_ChangePawnArmy` dồn lính giữa 2 đội **cùng `index`** (KHÔNG bắt buộc ở thành);
  chặn khi ô đang đánh (500036) hoặc đội đích đầy (500019). Cùng-ô mới dồn được.
- Cap lính/đội đầy = engine `ARMY_PAWN_MAX_COUNT=9`; game báo 500019 khi thật sự đầy.
- Brain sửa **profile** (không phát intent). Xem [[nta-agent-strategy]] "dồn/lấp lính".

## Kiến trúc: rule `Logistics` (hands) + seam brain

**Profile** (mặc định TẮT):
```
logistics: {enabled: false, target: 9, heal_skip_frac: 0.2,
            exclude: [], min_shortfall: 1}
```

### A — hands (dồn + kéo về + nạp)
Mỗi N tick sweep `get_player_armys()`. Mỗi tick chỉ phát 1 nhóm hành động (an toàn/audit).

1. **Lọc đủ điều kiện:** `state==0` (rảnh); `index` KHÔNG thuộc Cứ Điểm và KHÔNG trong
   `exclude`; `army_wound_frac < heal_skip_frac` (thương nặng nhường `HealRouting`).
2. **Dồn tại chỗ** (mỗi cụm ≥2 đội cùng `index`, ngoài thành): gộp lính, xếp theo máu
   giảm dần, lấp đầy đội "giữ" bằng lính nhiều máu trước (`change_pawn_army`), đẩy lính
   yếu-máu về đội sẽ đưa về. Tôn trọng 500019/500036/500037.
3. **Kéo về:** đội còn thiếu (shortfall ≥ `min_shortfall`) → `move_cell_army` về thành →
   `Recruit` (đã có) nạp đầy.

Thuật toán thuần: `nta_agent/execution/logistics.py`
- `plan_logistics(armies, main_city, forts, *, target, heal_skip_frac, exclude,
   min_shortfall) -> LogisticsAction | None` với `kind ∈ {consolidate, bring_home}`.
- `consolidate`: `{index, from_uid, to_uid, pawn_uids:[...]}` (di chuyển lính nhiều-máu
  vào đội giữ; hoặc dồn lính yếu về đội đi).
- `bring_home`: `{army}` (AreaArmyInfo để `move_cell_army`).

### B — brain quyết điều đội đi đâu
Hands KHÔNG tự đưa đội ra. Đội **đầy + rảnh + ở ô thành** = "sẵn sàng":
- `ready_armies(armies, main_city, target)` → đưa vào **digest** cho brain +
  `/api/armies`/dashboard.
- Brain sửa profile: gán đội vào `army.group` (nhập đội farm) hoặc field mới
  `logistics.redeploy = {armyUid: targetIndex}`.
- Hands rule đọc `logistics.redeploy` → `move_cell_army([army], target)` rồi xoá entry.

## Tương tác rule
- `HealRouting` chạy TRƯỚC (đội thương nặng về hồi máu); Logistics bỏ qua đội wound cao.
- `Recruit` nạp đội Logistics kéo về (không đổi Recruit).
- Không đụng đội trên Cứ Điểm/exclude (phòng thủ) — an toàn bố trí người chơi.

## Test (TDD)
- `plan_logistics`: dồn ưu tiên máu; bỏ qua wound cao/Cứ Điểm/exclude; chọn bring_home
  đúng đội thiếu; không hành động khi mọi đội đủ; tôn trọng min_shortfall.
- `ready_armies`: chỉ đội đầy+rảnh+ở ô thành.
- rule `Logistics.applies/act`: enabled gate; phát đúng action; back-off khi 500019/500036.
- brain redeploy: profile edit hợp lệ → hands điều đội → xoá entry.
