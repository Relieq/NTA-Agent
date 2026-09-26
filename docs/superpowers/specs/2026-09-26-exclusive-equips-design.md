# Trang bị chuyên dụng: chọn, dung luyện, rèn lại có khoá — thiết kế

**Ngày:** 2026-09-26 · **Trạng thái:** bản nháp chờ user duyệt.
Thay quyết định cũ "agent không đụng trang bị chuyên dụng" (memory nta-agent-forge-leveling).

## Mục tiêu & ranh giới (user chốt)

| Việc | Ai quyết | Agent làm |
|---|---|---|
| (a) **Chọn** trang bị chuyên dụng khi mở ô (mốc 10 / 18) | **Người chơi** (dashboard) | nghiên cứu + rèn tạo món đã chọn |
| (b) **Dung luyện** (chọn món phụ cho từng ô, khôi phục) | **Người chơi** (dashboard, xác nhận) | gửi đúng lệnh đã chọn |
| (c) **Rèn lại** món chuyên dụng theo tiêu chí + **khoá** bằng máy cố định | agent (tự động, trong ngân sách) | như dưới |
| Đeo trang bị | **Người chơi trong game** | không làm |

## Luật game (kiểm engine 2026-09-26)

- **Danh sách hiệu ứng random của món chuyên dụng theo TỪNG TRẬN**: `game/HD_GetWorldRandomInfo` {} →
  `exclusiveMap{equipId: {arr:[effectType]}}` (+ `pawnCostMap`). `equipBase.effect` chỉ dùng ở chế độ tân thủ —
  **không** dùng cho món chuyên dụng. Món chuyên dụng ra 2 dòng từ danh sách này + `skill_intensify` cố định.
- **Ô chuyên dụng**: ô trang bị cấp 10 và 18 (`EQUIP_SLOT_EXCLUSIVE_LV`), chọn qua StudySelect (đã có luồng
  quyết định "equip" trên dashboard); món được chọn phải **rèn tạo lần đầu** (`HD_ForgeEquip{uid:"<id>_<lv>"}`).
- **Dung luyện** `HD_SmeltingEquip{mainUid, viceIds:[equipId]}` (có thời gian, `currSmeltEquip`, xong qua notify
  `SMELT_EQUIP_RET`); `HD_RestoreSmeltEquip{uid}` khôi phục. Món chính = chuyên dụng; món phụ = trang bị thường của
  mình; kết quả giữ **mọi thuộc tính món chính**, thêm **hiệu ứng** món phụ (+50% thuộc tính cơ bản món phụ);
  **2 ô** dung luyện mở theo **cấp Tiệm Rèn 14 / 20** (`getBuildLv(SMITHY) ≥ EQUIP_SMELT_NEED_LV[i]` — user nhớ
  là thành chính: sẽ đối chiếu trong game); món phụ đã dung **không dùng cho món chuyên dụng khác**. Đang dung
  luyện thì không rèn được (ecode.500237) và ngược lại. Dòng dung luyện đánh dấu trong `attrs[i][4]` (smeltId).
- **Khoá** `HD_LockEquipEffect{uid, effect}`: chỉ món chuyên dụng, **1 dòng**, không khoá lúc đang rèn. Rèn lại có
  khoá **giữ nguyên dòng đã khoá (cả giá trị, tỉ lệ)**, roll lại công/máu + dòng còn lại (`randomEquipAttr`).
- **Máy cố định mỗi lần rèn** (client `getSmeltNeedFixatorCount`) = **(1 nếu đang khoá) + số dòng dung luyện
  thuộc danh sách random của món** (trận này). Bản mô phỏng server trong client chỉ tính phần khoá → kiểm live.

## (a) Chọn & tạo trang bị chuyên dụng

- Bảng **Quyết định** (đã có) hiện thêm, với mỗi lựa chọn là món chuyên dụng: loại lính dùng được, **danh sách
  hiệu ứng random của trận này** (từ `exclusiveMap`), cường hoá kỹ năng. Người chơi chọn như hiện nay.
- Rule Forge: `craft_candidates` nhận thêm **món chuyên dụng đã được nghiên cứu mà chưa rèn tạo** → rèn tạo khi đủ
  tài nguyên (cùng luật 1 lượt rèn/lúc; không tạo khi đang dung luyện).

## (b) Dung luyện (người chơi chọn, agent gửi lệnh)

- Dashboard tab **Trang bị → Dung luyện**: chọn món chính (chuyên dụng đã rèn), món phụ cho **ô 1** (và **ô 2** nếu
  Tiệm Rèn ≥ 20) trong danh sách **trang bị thường của mình chưa dung vào món chuyên dụng khác**.
- **Xem trước** trước khi xác nhận: dòng sẽ thêm (hiệu ứng món phụ), thuộc tính cơ bản cộng thêm (50%), và **máy cố
  định mỗi lần rèn lại sau này** (dòng dung trùng danh sách random → +1 mỗi dòng), cảnh báo nếu không đổi gì.
- **Xác nhận** → lệnh `smelt` vào hàng lệnh (commands) → DecisionService gửi `HD_SmeltingEquip`; theo dõi
  `currSmeltEquip`/notify để báo xong. Nút **Khôi phục** (xác nhận) → `HD_RestoreSmeltEquip`.
- Không tự dung luyện, không tự khôi phục.

## (c) Rèn lại tự động có khoá

Mở rộng bảng rèn hiện có (tiêu chí từng dòng `"<type>.value"|"<type>.odds"` ≥ min, ngân sách sắt) cho món chuyên
dụng, thêm **ngân sách máy cố định** mỗi món; danh sách dòng để đặt mức = `exclusiveMap` của trận (không phải
`equipBase.effect`). Mỗi lượt, với một món:

1. Mọi dòng mong muốn đạt → **dừng** (giữ kết quả).
2. Có **một dòng mong muốn đã đạt** (đúng loại **và** đạt giá trị/tỉ lệ tối thiểu, không phải dòng dung luyện) mà
   chưa khoá → **khoá dòng đó** (`HD_LockEquipEffect`).
3. Chưa → **rèn lại**, tốn chi phí rèn (trừ khi lượt miễn phí) + **máy cố định = (khoá?1:0) + dòng dung luyện trùng
   danh sách random**; chỉ rèn khi đủ tài nguyên và còn **ngân sách sắt & máy cố định** của món (trừ dần như sắt).
   → Trước khi khoá, rèn lại **không tốn máy cố định** (trừ phần dung luyện); sau khi khoá mới tốn — đúng kịch bản
   user: "ra được 1 dòng thoả mãn thì khoá, rồi tốn máy cố định rèn tiếp lấy dòng còn lại".
4. Món đang **khoá sẵn một dòng không mong muốn** → **không rèn** (mỗi lượt tốn máy cố định vô ích), dashboard báo
   để người chơi đổi/bỏ khoá trong game.
5. Đang dung luyện → chờ.

**Đối chiếu live**: lần rèn chuyên dụng đầu tiên so máy cố định server thực trừ với ước tính; lệch → cảnh báo + dừng
món đó.

## Đơn vị

- `actions`: `get_world_random_info()`, `smelting_equip(main_uid, vice_ids)`, `restore_smelt_equip(uid)`
  (`lock_equip_effect` đã có).
- `execution/exclusive.py` (thuần): `effect_pool(world_info, equip_id)`, `fixator_per_recast(equip, pool)`,
  `smelt_preview(main, vices, pool, base_of)`, `lock_or_recast(equip, target, pool, ...)`.
- `execution/forge.py`: `next_recast` + `forge_view` nhận món chuyên dụng (pool, khoá, máy cố định, dòng dung luyện);
  `craft_candidates` nhận món chuyên dụng đã nghiên cứu.
- Rule `Forge`: bước khoá; `spend_fn(uid, iron, fixator)`; `forge_targets` thêm `fixator_budget`.
- State: `world_random_info` lấy khi khởi động (cache theo trận, làm mới khi trận mới), `currSmeltEquip` + notify.
- Dashboard: Quyết định (hiệu ứng trận), ForgePanel (chuyên dụng, khoá, máy cố định), tab Dung luyện (xem trước + xác
  nhận + khôi phục); server endpoints `/api/smelt/preview`, lệnh `smelt`/`restore_smelt`.

## Kiểm thử

- Pool theo trận (không dùng `equipBase.effect` cho chuyên dụng); máy cố định: khoá, dung luyện trùng/không trùng.
- Quyết định khoá/rèn/dừng; ngân sách sắt + máy cố định; khoá dòng không mong muốn → không rèn; đang dung luyện → chờ.
- Rèn tạo món chuyên dụng đã nghiên cứu; không tạo khi đang dung luyện.
- Xem trước dung luyện; lệnh chỉ đi khi xác nhận; món phụ đã dung bị loại; ô 2 chỉ khi Tiệm Rèn ≥ 20.
- Live (với sự đồng ý của user): 1 lần rèn chuyên dụng có khoá — so máy cố định thực trừ.
