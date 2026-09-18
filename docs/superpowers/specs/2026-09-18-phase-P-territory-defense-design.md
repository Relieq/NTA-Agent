# Phase P — Bảo vệ lãnh thổ khỏi xâm nhập âm thầm — Design

**Ngày:** 2026-09-18 · **Kiểu:** deterministic, no-LLM (P1/P2), best-effort. Roadmap:
[completion-roadmap v2](../plans/2026-09-18-completion-roadmap.md) §P.

## 1. Mục tiêu & nguyên tắc
Agent (trợ thủ) tự phát hiện và **chặn** khi địch lặng lẽ lấn ô vào lãnh thổ ta, và **cảnh báo** người khi
có đe dọa thật. KHÔNG khởi chiến — phòng thủ thụ động trong phạm vi lãnh thổ.

**Nguyên tắc (user):** trong **BAO CHỨA = convex hull** lãnh thổ ta, **địch chạm biên / lọt vào trong hull =
đang xâm nhập** (đe dọa thật, khác địch ở xa). Đối xứng chỉ để **báo cơ hội** cho người, không tự đánh.

## 2. Kiến trúc
### P1 — Threat/incursion model (`execution/threat.py`, thuần)
- `convex_hull(points)` (monotone chain) → đa giác biên lãnh thổ (CCW).
- `point_in_hull(p, hull)` → điểm nằm trong/trên hull (đa giác lồi).
- `detect_incursions(owned, enemy_cells, enemy_cities, main, map_width)` → mỗi ô địch **threat** khi
  **(a)** nằm trong/trên hull owned (đã lọt vào bao chứa) HOẶC **(b)** kề (4 hướng) một ô owned (chạm biên).
  Mỗi threat: `{index,x,y, is_city, inside_hull, adjacent, dist_to_main, direction}`. Kèm `summary`
  (số threat, gần nhất, hướng, có thành địch không). Địch xa (ngoài hull + không kề) → bỏ qua.
- Dữ liệu từ Tier B sẵn có (owned/enemy), 0 request thêm.

### P2 — Tự chặn xâm nhập (`GuardBorder` rule)
- Khi có threat kề biên: **chiếm ô biên bị nhắm** (ô owned-frontier hoặc ô trung lập giữa ta và địch) để
  dựng tường (tận dụng 6h bảo vệ ô mới chiếm). Chỉ hành động **trong/ở rìa lãnh thổ**, KHÔNG đuổi sang đất
  địch. Tái dùng occupy/discover; cap/tick; best-effort; ưu tiên điểm xâm nhập sâu/nguy hiểm nhất.
- (v1 có thể chỉ chiếm ô trung lập kề địch để bịt đường; đánh trực diện ô địch = "phần chơi" → để P3 báo.)

### P3 — Cảnh báo người chơi
- Threat thật (thành địch tiến vào / cụm mạnh áp sát) → ghi vào forts.json/snapshot + event `threat_alert`
  → dashboard hiển thị nổi bật. Agent KHÔNG tự khởi chiến; người quyết đánh/thủ.

## 3. Ngoài phạm vi
Tấn công đất/thành địch, đuổi đánh, ngoại giao — người chơi tự làm (chỉ báo qua P3).

## 4. Testing
- Hull: các điểm → hull đúng; suy biến (<3 điểm/thẳng hàng) an toàn.
- point_in_hull: trong/ngoài/trên cạnh.
- detect_incursions: địch trong hull → threat(inside); địch kề owned → threat(adjacent); địch xa → bỏ;
  thành địch → is_city; summary đúng.
- GuardBorder: có threat → chiếm ô chặn đúng; không threat → im; cap/tick; best-effort ecode.
- Full suite + ruff.

## 5. Verify live
Khi có địch sát biên thật (server đông — 2288 ô địch quanh ta) → chạy detect_incursions read-only, xác nhận
phát hiện đúng địch chạm biên; GuardBorder đề xuất/chiếm ô chặn hợp lý.
