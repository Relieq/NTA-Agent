# Dig tới ô đích — thiết kế

**Ngày:** 2026-09-25 · **Trạng thái:** đã chốt với user (các câu hỏi bên dưới), user uỷ quyền tự hoàn thiện.

## Mục tiêu

Người chơi bấm 1 ô trên bản đồ (tab Lãnh thổ) → agent tính **đường chiếm ô liên tiếp** từ lãnh thổ
hiện có tới ô đó sao cho **tổng thời gian nhỏ nhất**, cho xem trước (đường, số ô, thời gian, số Cứ
Điểm) → người chơi bấm **Xác nhận** → agent dig từng ô, tự điều chỉnh khi bản đồ thay đổi.

## Quyết định đã chốt với user

| Câu hỏi | Chốt |
|---|---|
| Ai dig | **Nhóm đội farm** (đội hình active) là đội dig; các đội khác làm việc như thường; nâng cấp lính vẫn chạy và bổ sung vào nhóm này. |
| Đích bị chiếm | **Tự đổi sang ô trống gần đích cũ nhất** (vẫn giữ khoảng an toàn), dig tiếp, báo lại. |
| Gần địch | **Cấm** ô cách ô địch ≤ N (mặc định N=2, chỉnh được); ngoài đó **phạt nhẹ** giảm dần theo khoảng cách; không còn đường ngoài vùng cấm → báo, không liều. |
| Ô khó (không thắng trong `max_loss`) | **Đi vòng**; chỉ khi mọi đường đều phải qua ô khó thì **chờ** (hồi máu / mạnh lên) và thử lại định kỳ, kèm báo. |
| Cứ Điểm | Cứ **>7 ô** dig kể từ nút gần nhất (thành chính / Cứ Điểm) thì xây 1 Cứ Điểm trên đường, **ưu tiên ô đất cấp 1** (loại đất tài nguyên cấp thấp nhất) để đỡ phí. |
| Bắt đầu | **Xem trước** đường + thời gian → **Xác nhận** mới chạy; có **Huỷ** bất cứ lúc nào. |

## Dữ kiện nền (đã kiểm chứng 2026-09-25)

- Chỉ chiếm được ô **kề cạnh** ô đang sở hữu; sau khi chiếm, đội **ở lại** ô đó (`autoBackType=0`)
  → đội dig tiến dần, mỗi bước hành quân 1 ô.
- **Bản đồ đất tĩnh**: APK có `tmp/json/maps/maps_{0,13,14,15}` (JsonAsset, mảng 360 000 `landId`,
  index = y·600+x). Máy chủ hiện tại dùng **maps_15** (khớp 152/152 ô sở hữu + 865/865 ô địch đều là
  đất chiếm được; maps_13/14 lệch). → Chọn bản đồ tự động bằng cách so khớp ô sở hữu.
- `land.json`: `type` 3/4/5 = đất tài nguyên có `lv` 1..5 (`occupy=1`); loại khác lv 0 / không chiếm
  được → coi là **chướng ngại**. "Đất cấp 1" = đất tài nguyên `lv == 1`.
- Quái giữ ô = `getAreaPawnConfInfo(index, landId, dist_to_main)` → sidecar mô phỏng **tự sinh** được
  khi truyền `landId` thật (đã thử: đất lv2 thắng dễ, lv5 thua) → đánh giá mọi ô không cần `get_area`.
  Quái chỉ phụ thuộc `(landId, cấp theo khoảng cách)` → **memo** theo cặp này (vài chục–trăm lần sim).
- Thời gian hành quân (engine `getMarchTime`): `floor(dis·3 600 000 / marchSpeed)·(1−cd%)` ms,
  `marchSpeed` = lính chậm nhất (`pawnBase.march_speed`, vd 62 → ~58 s/ô).

## Kiến trúc

```
Dashboard (TerritoryPanel)  --POST /api/dig/request|confirm|cancel-->  dig_request.json
        ^  GET /api/dig (dig.json: preview / active / waiting / done …)       |
        |                                                                     v
  dig.json  <----------------  DigService (agent, mỗi tick, có throttle)  <---+
                                  |  plan: WorldMap + scan_map(focus) + CellCost(sim) + dig_planner
                                  |  next_target() ------------------------> OccupyCell._dig_select
                                  |  fort chỗ >7 ô --------------------------> fort_queue (có sẵn)
```

### Đơn vị

1. **`nta_agent/execution/worldmap.py` — `WorldMap`**: nạp `maps_*.json` từ `paths.config_dir()`;
   `detect(owned)` chọn bản đồ khớp nhất; `land_id(idx)`, `land(idx)` → `{type, lv, occupy}`,
   `passable(idx)` (occupy==1), `is_lv1(idx)`. Dữ liệu trích lúc Setup bước 5 / `tools/re/extract_config.py`
   (thêm `tmp/json/maps/*` → `maps_<n>.json`, gitignore như bảng khác).
2. **`nta_agent/execution/dig_planner.py` (thuần, không I/O)**:
   - `plan_path(owned, target, step_cost, blocked, enemy, buffer=2, penalty, bbox_margin)` → Dijkstra
     4-láng giềng, nguồn = mọi ô sở hữu (chi phí 0), trong khung bao `owned∪target` + lề; ô `blocked`
     (chướng ngại / địch / thành) hoặc cách địch ≤ buffer → cấm; `step_cost(idx)` = giây hoặc `None`
     (không đi được: ô khó); phạt gần địch = `penalty_s · (buffer+3 − d)` với buffer<d≤buffer+2.
     Trả `Plan(path, total_s, reason)`; `reason ∈ {ok, no_path, blocked_by_hard}` (có đường nếu coi ô
     khó là đi được ⇒ `blocked_by_hard` → chế độ chờ).
   - `retarget(target, owned, enemy, blocked, buffer)` → ô trống, đi được, ngoài vùng cấm, gần đích cũ nhất.
   - `place_forts(path, nodes, land, every=7)` → vị trí Cứ Điểm: đi dọc đường, khi quá 7 ô kể từ nút
     gần nhất thì chọn trong cửa sổ 6..9 ô ô có `lv` thấp nhất (ưu tiên lv1), coi nó là nút mới.
3. **`nta_agent/execution/dig_cost.py` — `CellCost`**: `cost(idx)` = hành quân 1 ô (công thức engine,
   speed của nhóm dig) + thời lượng trận (sim: frames/fps) ; `None` nếu sim thua hoặc
   `loss > max_loss`. Memo theo `(landId, attrLv)`; nhóm dig coi như **đầy máu** (hồi máu có HealRouting
   + Cứ Điểm). Sim lỗi → ước lượng thô theo `lv` (không chặn cả kế hoạch).
4. **`nta_agent/runtime/dig_service.py` — `DigService`** (chạy trong vòng tick của agent):
   - Đọc `dig_request.json` (dashboard ghi), ghi `dig.json` (dashboard đọc). Trạng thái:
     `previewing → preview → active → (waiting ↔ active) → done | failed | cancelled`.
   - **Preview**: scan bản đồ (`scan_map` + `focus` = các chunk của khung bao) → plan → ghi đường,
     `total_s`, số ô, Cứ Điểm dự kiến, stamina cần. Không gửi lệnh game nào.
   - **Active**: mỗi `replan_every_s` (60 s) hoặc khi ô kế tiếp không hợp lệ: scan lại; đích bị chiếm
     (owner ≠ mình/trống) → `retarget` + sự kiện `dig_retarget`; plan lại; ô đầu tiên chưa sở hữu =
     **ô kế tiếp**. Ô Cứ Điểm đến lượt (đã sở hữu) → `fort_queue.add` một lần. Đích đã sở hữu → `done`.
     `blocked_by_hard` → `waiting` (thử lại mỗi 5 phút); `no_path` → `failed` + lý do.
   - `next_target()` cho OccupyCell (None nếu không active).
5. **`OccupyCell`**: thêm `dig_source` (callable → ô kế tiếp hoặc None). Thứ tự chọn:
   phòng thủ biên → **dig** → mở rộng → farm. `_dig_select`: chỉ xét ứng viên đúng ô kế tiếp, chỉ nhóm
   đội farm, vẫn qua mô phỏng thật (quái thật từ `get_area`) + `max_loss`; không thắng → không đánh, báo
   DigService (`dig_hard`) để plan lại coi ô đó là khó.
6. **Dashboard**: `GET /api/dig`, `POST /api/dig/request {index}`, `/api/dig/confirm`, `/api/dig/cancel`,
   cài đặt `dig_enemy_buffer`. `TerritoryPanel`: popup ô có nút **⛏ Dig tới đây**; vẽ đường (viền cam),
   ô Cứ Điểm dự kiến (🏯 mờ), đích (🎯); thẻ trạng thái: số ô, thời gian ước tính/còn lại, trạng thái,
   lý do, nút Xác nhận / Huỷ.

## Xử lý lỗi

- Agent không chạy → request nằm chờ; UI hiện "agent chưa chạy — bật agent để tính đường".
- Sidecar lỗi/timeout → `CellCost` ước lượng thô, preview ghi rõ "ước lượng thô".
- Chunk scan lỗi → giữ plan cũ, thử lại lần sau.
- Hết thể lực: OccupyCell vốn chờ thể lực; ETA chỉ tính hành quân + trận (ghi chú "chưa tính chờ thể lực/hồi máu").

## Kiểm thử

- `dig_planner`: đường ngắn nhất lưới đơn giản; đi vòng chướng ngại/ô khó; cấm vùng địch + phạt; không
  đường → `no_path`; chỉ qua ô khó → `blocked_by_hard`; `retarget`; `place_forts` (>7, ưu tiên lv1).
- `WorldMap.detect` chọn đúng bản đồ; `land/passable/is_lv1`.
- `CellCost`: memo theo (landId, attrLv), thua/`max_loss` → None, march time đúng công thức.
- `DigService`: preview không gửi lệnh; confirm → active; đích bị chiếm → retarget; ô kế tiếp bị địch
  chiếm → plan lại; fort enqueue đúng 1 lần; đích sở hữu → done; cancel.
- `OccupyCell._dig_select`: ưu tiên sau phòng thủ, trước mở rộng; chỉ nhóm farm; tôn trọng `max_loss`.
- Dashboard: endpoint + UI có nút/overlay (test tĩnh như các panel khác).
- Kiểm chứng live **chỉ ở chế độ xem trước** (không Xác nhận) — lần dig thật đầu tiên do user bấm.
