# Nâng lính bằng đội dư (buffer) — thiết kế

**Ngày:** 2026-09-25 · **Trạng thái:** bản nháp chờ user duyệt.

## Mục tiêu

Nâng cấp lính của một **nhóm đội** mà không giữ đội chính ở Thao Trường: lính được nâng trong
**đội dư**, rồi đội dư ra **ô kề** đội chính và **tráo lính cùng loại**; đội chính vẫn farm/dig.
Lâu dần đội dư thành bản song sinh của đội chính → có thể tổ chức thành nhóm 5 đội thứ hai.

## Quyết định đã chốt với user

| Câu hỏi | Chốt |
|---|---|
| Chế độ | Chọn **theo nhóm đội** muốn nâng: (1) **nâng trực tiếp** (in-place, như hiện nay) hoặc (2) **nâng bằng đội dư**. |
| Ai quyết cơ cấu | **Brain đề xuất** (đội dư nào, dồn lính từ đâu, chiêu mộ bao nhiêu, giải tán đội nào), **user xác nhận**; hands thực thi tất định. |
| Khi 1 đội đi tráo | 4 đội còn lại **đánh tiếp nếu ô kế tiếp đánh sạch** với 4 đội đó; nếu mất lính thì **chờ**. Đội tráo xong tự **tiệm cận** về hội tụ lại. |
| Sát địch | Tạm **không xét** khi chọn ô kề. |
| Sách exp | **Ước tính chính xác** theo bảng game trước khi đề xuất. |
| Hàng đợi 6 lính | Không phải nút thắt: agent **bổ sung liên tục** (xong 1 → xếp 1) tới khi đủ cấp rồi chuyển đội khác. |

## Luật game (kiểm trong engine 2026-09-25)

- `ExchangePawnArmy{index,armyUid1,uid1,armyUid2,uid2}`: hai đội **cùng một ô** (bất kỳ ô nào của mình),
  ô **không đang có trận**; lính mới chèn **đúng vị trí** lính cũ (giữ thứ tự/đội hình). Không bắt buộc
  cùng loại — hands tự ràng buộc **cùng loại** để giữ thành phần + trang bị (trang bị theo loại lính).
  *(bản mô phỏng server trong client — cần kiểm 1 lần live ngoài thành)*
- `PawnLving{index,auid,puid}`: đội phải **ở ô thành chính** (Thao Trường), không hành quân;
  hàng đợi tối đa **6/thành**; `lv_cond` = Trại Lính (2004) đạt cấp (vd lên lv3 cần 2004 ≥5, lv4 cần ≥10).
- Chi phí 1 lần nâng lv→lv+1 = `pawnAttr[id·1000+lv].lv_cost`: **sách exp** (CType 7) + lương thực
  (`PAWN_COST_LV_LIST[lv] × pawnCostMap[id]` từ server). Thời gian = `lv_time` giây (trừ policy CD).
  Vd IMP 3305: lv1→2 **1 sách**/488 s, lv2→3 **1 sách**/732 s, lv3→4 2 sách; Khiên lớn 3202: 1/2/3 sách.
- **5 đội/ô** (`DEFAULT_MAX_ARMY_COUNT`) → nhóm 5 đội đầy ô, đội dư buộc đứng **ô kề**.
- Giới hạn số đội = cơ bản + hiệu ứng `ARMY_COUNT` (công trình/chính sách). Đội mới **chỉ** tạo được khi
  chiêu mộ/hồi sinh (đặt tên); `ChangePawnArmy` chỉ chuyển lính giữa **hai đội đang có, cùng ô**.
  `DismissArmy` **mất lính** → luôn phải user xác nhận.

## Mô hình

- **Nhóm nâng** (`profile.leveling.groups[]`): `{armies:[uid…], mode:"direct"|"buffer", target_lv}`.
  Nhóm farm/dig hiện tại là trường hợp thường gặp nhất.
- **Đội dư** (`buffers[]`, agent quản, đặt tên "Nâng Cấp N"): một **kho lính theo loại** — không cố định
  "đúc" 1 đội. Mỗi lần tráo là 1 cặp `(lính yếu của đội chính, lính đạt cấp của đội dư, cùng loại)`.
- **Linh hoạt thành phần (ý user về K3 thay K2):** ở thành, đội dư có thể **đổi 1 lính lấy 1 lính khác loại**
  với **đội lẻ bất kỳ** đang ở thành (Exchange cùng ô) để khớp đúng loại mà đội chính kế tiếp cần
  → ít đội dư hơn (vd 1 đội dư phục vụ cả K2 lẫn K3). Hands tự làm khi có đội lẻ đúng loại ở thành;
  không có thì dùng đúng loại đang có.

### Ví dụ hiện tại (dữ liệu live 2026-09-25)

Nhóm: Đội 1 (8×3202 lv3 + 1×3201 lv3), Đội 2–5 (36 IMP, 34 lv1 + 2 lv2), mục tiêu lv3.
Đội lẻ: D1 (4 IMP, 4×3201, 1×3202), D5 (6 IMP, 3×3201), D6 (1 IMP, 8×3201), D7 (1 IMP, 8×3201) — 12 IMP lv1.
→ Brain có thể đề xuất: **1 đội dư IMP** = dồn 6 IMP của D5 + 3 IMP của D1 (dùng lại D5 làm đội dư, đổi tên),
sách cần ≈ IMP lv1→3 = 2 sách × (34 + 9 lính dư) + 1 × 2 = **88 sách** (đang có 49 → brain báo thiếu, đề xuất
nâng theo đợt). Đội 1 đã đạt lv3 → không cần đội dư khiên lớn.

## Luồng

```
Brain (đề xuất)  --leveling_plan (chờ duyệt)-->  Dashboard: user Xác nhận/Sửa
       |                                                  |
       v                                                  v
 BufferPlanner (thuần): nhu cầu theo loại, sách/thời gian, cơ cấu đội dư, bước sắp xếp
       |
       v
 Rule BufferLeveling (hands, mỗi tick):
   1. Sắp xếp (1 lần): gom đội lẻ về thành, ChangePawnArmy dồn lính, đổi tên "Nâng Cấp N",
      chiêu mộ thiếu, giải tán (chỉ các đội user đã duyệt).
   2. Nâng liên tục: đội dư ở thành → PawnLving lính thấp nhất chưa trong hàng đợi (lấp đầy tới 6).
   3. Chọn đích: đội dư có ≥k lính đạt cấp khớp loại lính yếu của 1 đội chính → chọn đội chính
      cải thiện nhiều nhất; (tuỳ chọn) đổi loại với đội lẻ ở thành cho khớp.
   4. Hẹn gặp: đội dư đi tới ô **của mình, kề ô đội chính, còn chỗ**; đội chính đổi ô → đích
      cập nhật, đội dư tiến dần. Tới nơi + đội chính rảnh → đội chính MoveCellArmy sang ô đó.
   5. Tráo: ExchangePawnArmy từng cặp cùng loại (yếu ↔ đạt cấp), rồi đội chính quay lại nhóm,
      đội dư về thành nâng tiếp số lính yếu vừa nhận.
   6. Xong khi mọi lính (chính + dư) đạt cấp → đội dư thành **dự bị** (giữ; sau này ghép nhóm 2).
```

### Tương tác với farm/dig (sửa luật "cả nhóm cùng đánh")

- `_dig_select`/farm: nếu có thành viên **đang đi tráo**, xét kế hoạch với **các thành viên có mặt**:
  sim **sạch** (≤ max_loss) → đánh; không → **chờ**. Ô chỉ bị báo **khó** khi **đủ cả nhóm** vẫn không sạch
  (giữ nguyên luật hiện tại). Thành viên tráo xong được gom về theo cơ chế `dig_gather` sẵn có.
- Nâng trực tiếp (mode `direct`) vẫn bị **tạm dừng cho nhóm đang dig** (như bản sửa hôm nay).

## Đơn vị

1. `execution/buffer_plan.py` (thuần): `book_cost(pawn_id, lv_from, lv_to)`, `time_s(...)` (từ pawnAttr +
   `lv_cond` check theo cấp 2004), `demand(group, target)` theo loại, `propose(group, spares, army_cap,
   exp_book)` → cơ cấu đội dư + bước sắp xếp + sách/thời gian + thiếu hụt.
2. Brain: đọc digest `leveling_needs` (từ buffer_plan) → trả `leveling_plan`; guard kiểm id đội/loại/số;
   dashboard hiển thị để **Xác nhận** (như nhóm quân).
3. `execution/heuristics.py` rule `BufferLeveling` (tách khỏi `Leveling` in-place): trạng thái mỗi đội dư
   `leveling | ready | travel | swap | home` lưu `build/run/buffers.json` (sống qua restart).
4. `OccupyCell`: luật "thành viên đi tráo" như trên; `DigService`/farm coi đội dư không thuộc nhóm.
5. Dashboard: nhóm nâng + chế độ + mục tiêu cấp; bảng đội dư (trạng thái, lính đạt cấp, đích); đề xuất
   brain chờ duyệt; ước tính sách/thời gian.

## Xử lý lỗi

- 500080/500020 (đội bận/ở Thao Trường) → coi là bận, thử lại sau; mọi lỗi di chuyển/tráo ghi `rally_error`/
  `swap_error` kèm ecode (không nuốt lỗi).
- Ô kề hết chỗ (500037) → chọn ô kề khác; không có → đội dư chờ ở ô gần nhất của mình.
- Hết sách (500012) → dừng nâng, báo ledger `res_depletion` (brain điều chỉnh đợt).
- Restart giữa chừng → khôi phục từ `buffers.json` + trạng thái thật của đội.

## Kiểm thử

- `buffer_plan`: sách/thời gian khớp bảng (IMP 1+1, 3202 1+2), `lv_cond` chặn cấp; demand theo loại;
  propose dùng lại đội lẻ + chiêu mộ khi thiếu + đề xuất giải tán khi chạm trần.
- Rule: nâng liên tục lấp 6 hàng đợi; chọn đích; hẹn gặp đổi đích khi đội chính di chuyển; tráo chỉ cặp cùng
  loại, đúng chiều (yếu ↔ đạt cấp); đổi loại với đội lẻ ở thành; kết thúc → dự bị.
- OccupyCell: thành viên đi tráo → 4 đội đánh nếu sạch, chờ nếu không; không báo khó.
- Live: **1 lần tráo ngoài thành** để xác nhận `ExchangePawnArmy` (bản mô phỏng) trước khi bật tự động.

## Giai đoạn

1. **P1**: buffer_plan + ước tính sách + đề xuất/duyệt + nâng liên tục + hẹn gặp + tráo cùng loại + luật đánh
   thiếu 1 đội.
2. **P2**: đổi loại linh hoạt với đội lẻ ở thành (K3 thay K2), tối ưu số đội dư.
3. **P3** (sau): ghép các đội dư đã đạt cấp thành **nhóm 5 đội thứ hai**.
