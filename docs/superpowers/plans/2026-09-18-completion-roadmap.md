# NTA-Agent — Lộ trình hoàn thiện sản phẩm (2026-09-18)

Tài liệu tổng quan: agent cần những gì để trở thành **sản phẩm hoàn chỉnh** — một tác nhân tự động chơi
*Ninety Thousand Acres* đủ giỏi và đủ bền để chạy 24/7 không cần người can thiệp, biết cả tấn công, phòng
thủ, kinh tế và chiến lược. Đây là bản dài hạn; mỗi hạng mục khi thực thi sẽ có spec + implementation plan
riêng. Bổ sung cho [ROADMAP.md](../../ROADMAP.md) (kiến trúc) và thay thế vai trò "phần còn lại" của
[master-plan-remaining](2026-09-17-master-plan-remaining.md).

---

## 1. Định nghĩa "hoàn thiện" (Definition of Done)

Sản phẩm được coi là hoàn thiện khi thỏa **tất cả**:

1. **Tự lập 24/7:** chạy nhiều ngày liên tục, tự phục hồi khi mạng/emulator/token chập chờn, không cần
   người khởi động lại.
2. **Đủ bốn năng lực:** kinh tế (thu/xây/tuyển), tấn công (chiếm đất, đánh địch), **phòng thủ** (phản ứng
   khi bị áp sát), và duy trì (hồi máu/hồi sinh/stamina).
3. **Chiến lược thích ứng:** bộ não LLM ra quyết định theo tình thế (bị đánh, dư/thiếu tài nguyên, cơ hội),
   không kịch bản cứng, chi phí token thấp.
4. **An toàn tài khoản:** hành vi giống người, không tạo pattern dễ bị phát hiện, xử lý captcha.
5. **Người chơi kiểm soát được:** các quyết định lớn/không đảo ngược (mở khóa binh chủng, chính sách,
   ngoại giao) do người duyệt qua dashboard; agent giải thích được vì sao nó hành động.
6. **Bảo trì được:** game update chỉ cần sửa adapter/config, không viết lại lõi; có regression phát hiện
   protocol/asset đổi.

---

## 2. Hiện trạng (đã có, trung thực)

**Nền tảng & I/O:** đã đi API-first — session MQTT/protobuf, adapter `actions.py` (~30 endpoint verify
live), catalog đầy đủ 134 endpoint. **Chưa có** vision adapter (OpenCV/OCR) — cố ý hoãn.

**Kinh tế:** thu sản lượng thành, build-order (prereq-guarded), tuyển quân, dự đoán ROI cơ bản. **Chưa
có** giao thương (Bazaar), quản trần kho, tối ưu tech dài hạn.

**Tấn công:** chiếm ô trung lập thắng được (predictor sim + stats), chọn mục tiêu theo loot/chi phí, tối
ưu đội hình (thứ tự tank), và **chiến lược mở rộng** spiral/octopus/hybrid. **Chưa có** đánh thành/đất của
người chơi khác (siege), phối hợp nhiều đạo quân.

**Duy trì:** điều quân thương về Cứ Điểm/thành hồi máu (HealRouting), hồi sinh lính chết (ReviveInjured),
nhịp stamina. Đủ để "đánh liên tục".

**Bản đồ/lãnh thổ:** mô hình Tier A (thành/fort/garrison) + Tier B full-map (ô mình/địch/biên giới), fort
advisor gợi ý Cứ Điểm **né địch** (C1). **Chưa có** mô hình mối-đe-dọa (threat).

**Bộ não:** brain kiểu profile-editing (đọc digest → sửa profile; hands thực thi; token thưa), đã
threat/cost-aware ở mức thấy `nearest_enemy_dist`/injured và chỉnh expansion/revive/max_loss. **Chưa có**
gọi theo sự kiện (bị đánh), học từ kết quả trận, quyết định ngoại giao.

**Vận hành:** dashboard Vue 3 (điều khiển agent, bản đồ, panel), event log, supervisor/pidfile, captcha
solver. **Chưa** validate chạy nền dài; **chưa có** auto-recover, regression update.

**Ngoại giao:** chưa làm (nhiều endpoint alliance đã map trong catalog nhưng chưa dùng).

---

## 3. Các trụ cột còn thiếu và lộ trình

Thứ tự = ưu tiên. Mỗi giai đoạn giải thích: **mục tiêu**, **vì sao cần cho một sản phẩm hoàn chỉnh**,
**phạm vi công việc**, **phụ thuộc**, **quy mô** (S ≤1 buổi, M 1–3 buổi, L nhiều buổi/nhiều PR),
**cách kiểm chứng**.

### Giai đoạn T — Phòng thủ & Mô hình mối đe dọa (trụ cột thiếu lớn nhất)

**Mục tiêu:** agent nhận biết khi bị áp sát và phản ứng, thay vì chỉ farm/mở rộng một chiều.

**Vì sao cần:** hiện agent chỉ biết tấn công/kinh tế; khi địch đánh tới nó không làm gì. Không có phòng
thủ thì mọi tài nguyên/đất farm được đều có thể mất trắng — đây là mảnh khiến agent "không đủ sống" trong
một server có người chơi thật.

**Nguyên tắc nền (user 2026-09-18):** trong **bao chứa** (bounding box / convex hull) lãnh thổ ta, **địch
chạm đường biên = đang có ý định tấn công** (đe dọa thật, khác địch ở xa); **đối xứng**, ô ta chạm bao chứa
địch = cơ hội/ý định tấn công của ta. Threat model phải phân biệt "địch sát biên" với "địch xa", không chỉ
dùng khoảng cách tới địch gần nhất.

**Phạm vi:**
- **T1 — Threat model** (M): `execution/threat.py` (thuần) tính bao chứa lãnh thổ từ owned, xác định ô biên
  (frontier), và phân loại **địch chạm biên → threat** kèm hướng, mức độ (số điểm tiếp xúc, khoảng cách,
  quy mô cụm địch, có thành địch gần không). Đối xứng: liệt kê **cơ hội tấn công** (ô địch ta chạm được).
  Dùng dữ liệu Tier B sẵn có, không tốn request thêm.
- **T2 — Phản ứng phòng thủ** (M): rule `DefendBorder` — khi có threat: ưu tiên **chiếm ngay ô biên bị áp
  sát để dựng tường** (tận dụng 6h bảo vệ ô mới chiếm, đúng lối spiral); **điều quân về biên bị đe dọa**
  (tái dùng move_cell_army); và **refine C1**: phân biệt *fort mở rộng* (đặt nơi an toàn) với *fort phòng
  thủ* (đặt hướng threat để tăng tốc tiếp viện + hồi máu tại chỗ).
- **T3 — Brain nhận biết threat** (S): digest thêm tóm tắt threat/opportunity (hướng, mức độ) → brain
  chuyển **thế thủ** (spiral, hạ max_loss, trú quân, tắt farm xa) khi bị áp sát, **thế công** khi có cơ hội.

**Phụ thuộc:** Tier B (có), C1 (có), move_cell_army (có). **Kiểm chứng:** unit test hình học bao chứa +
phân loại threat; live khi thực sự bị địch áp sát (hoặc dựng kịch bản sát biên).

### Giai đoạn O — Chiều sâu tấn công (đánh người chơi, không chỉ ô trung lập)

**Mục tiêu:** agent biết đánh **đất/thành của người chơi khác** và phối hợp nhiều đạo quân, không chỉ chiếm
ô trung lập.

**Vì sao cần:** một agent 4X hoàn chỉnh phải cạnh tranh với người chơi — chiếm đất địch, vây thành, cướp
tài nguyên. Hiện chỉ chiếm ô hoang.

**Phạm vi:**
- **O1 — Đánh ô/đất địch** (M): mở rộng occupy để nhắm ô địch (đã có enemy layer); dự đoán trận với quân
  phòng thủ thật của địch; chọn mục tiêu yếu/giá trị cao; tôn trọng nguyên tắc chỉ đánh ô liền kề.
- **O2 — Vây thành & landmark** (L): đánh thành người chơi và kinh đô cổ (3001–3004, 7×7) — luật riêng, cần
  RE thêm; phối hợp nhiều đạo quân, canh thời điểm.
- **O3 — Phối hợp đa quân & timing** (M): điều nhiều đạo quân đồng bộ (isSameSpeed), canh hành quân để tới
  cùng lúc; rút lui khi bất lợi.

**Phụ thuộc:** T (biết ai là địch đáng đánh), predictor (có). **Kiểm chứng:** predictor vs kết quả trận
thật; live có kiểm soát (đánh 1 mục tiêu địch yếu).

### Giai đoạn E — Chiều sâu kinh tế

**Mục tiêu:** kinh tế tự cân bằng, không lãng phí, tối ưu dài hạn.

**Vì sao cần:** hiện agent thu/xây/tuyển nhưng không cân bằng tài nguyên (thừa loại này thiếu loại kia),
dễ tràn kho, và chưa tối ưu thứ tự tech/mở khóa dài hạn.

**Phạm vi:**
- **E1 — Giao thương Bazaar** (M): `HD_BazaarBuyRes/SellRes/SellToSys/...` — bán dư, mua thiếu để phục vụ
  build/recruit; rule ROI + guard giá.
- **E2 — Quản trần kho & chống tràn** (S): theo dõi granaryCap/warehouseCap, ưu tiên tiêu/nâng cấp trước
  khi tràn (thu sản lượng đúng nhịp).
- **E3 — Tech/mở khóa dài hạn** (M): tối ưu thứ tự ceri/policy/binh chủng theo mục tiêu; các mục không đảo
  ngược vẫn để người duyệt (human-in-loop đã có khung).

**Phụ thuộc:** none lớn. **Kiểm chứng:** unit ROI; live quan sát cân bằng tài nguyên qua nhiều tick.

### Giai đoạn S — Chiều sâu bộ não (chiến lược thích ứng & học)

**Mục tiêu:** brain quyết định theo **sự kiện** và **học từ kết quả**, không chỉ theo nhịp cố định.

**Vì sao cần:** hiện brain gọi mỗi N tick; khi bị đánh đột ngột nó không phản ứng kịp. Và nó không rút kinh
nghiệm từ trận thua/thắng.

**Phạm vi:**
- **S1 — Gọi LLM theo sự kiện** (S–M, = B2 cũ): trigger khi bị áp sát (từ T), khi dư/thiếu tài nguyên mạnh,
  khi có cơ hội đánh — thay vì chỉ cadence; cache quyết định; ngân sách token cứng.
- **S2 — Thư viện chiến thuật & ghi nhớ** (M): brain lưu/đọc các "notes" chiến lược bền + preset đội hình
  theo tình huống (đã có khung notes/presets); chọn preset theo bối cảnh.
- **S3 — Học từ kết quả trận** (L): đối chiếu dự đoán vs kết quả thật (battle records đã có API), tinh chỉnh
  ngưỡng max_loss/chọn mục tiêu; phát hiện predictor lệch.

**Phụ thuộc:** T (sự kiện threat), battle records (có). **Kiểm chứng:** live 1 LLM call theo kịch bản; đo
độ khớp predictor sau S3.

### Giai đoạn D — Ngoại giao / Liên minh

**Mục tiêu:** agent tham gia liên minh ở mức tối thiểu hữu ích; quyết định lớn do người duyệt.

**Vì sao cần:** trong game này liên minh chi phối sống còn (kinh đô cổ, chiến tranh liên minh). Một sản phẩm
hoàn chỉnh ít nhất phải đọc trạng thái liên minh và phản ứng phòng thủ khi liên minh bị đánh.

**Phạm vi:**
- **D1 — Đọc trạng thái liên minh** (M): thành viên, rank, log, cờ bản đồ (nhiều `HD_GetAlli*` đã map) →
  đưa vào digest để brain/phòng thủ cân nhắc.
- **D2 — Hành động liên minh có người duyệt** (M): join/đóng góp kinh đô cổ/chính sách/cờ — surface lên
  dashboard để người quyết (theo nguyên tắc human-in-loop đã thống nhất).

**Phụ thuộc:** human-in-loop UI (có khung). **Kiểm chứng:** đọc live; hành động chỉ sau khi người duyệt.

### Giai đoạn R — Bền bỉ & Vận hành 24/7 (điều kiện để gọi là "sản phẩm")

**Mục tiêu:** chạy nền nhiều ngày không cần người, tự phục hồi, sống sót qua game update.

**Vì sao cần:** đây là điều kiện tiên quyết để agent thay người chơi thật sự. Hiện mới chạy one-off, chưa
validate long-run, chưa auto-recover.

**Phạm vi:**
- **R1 — Auto-recover** (M): tự reconnect khi mất MQTT/token; phát hiện emulator treo và khởi động lại qua
  ADB; backoff giống người; không spam khi lỗi kéo dài.
- **R2 — Validate chạy nền dài** (M): chạy giám sát nhiều giờ/ngày, quan sát rò rỉ tài nguyên/bộ nhớ, tick
  ổn định; sửa các lỗi lộ ra.
- **R3 — Regression khi game update** (M): pin version protocol/config; test phát hiện đổi endpoint/asset;
  quy trình cập nhật catalog + template.
- **R4 — Vision fallback adapter** (L, lưới an toàn): OpenCV+OCR+ADB tap cho domain chưa crack hoặc khi API
  đổi/gãy — tránh để API-only thành điểm gãy đơn. Chỉ đầu tư nếu API tỏ ra không đủ, nhưng cần cho tiêu chí
  "bảo trì được".

**Phụ thuộc:** toàn bộ hành vi ở trên (chạy dài mới có ý nghĩa khi agent đã đủ việc để làm). **Kiểm chứng:**
uptime nhiều ngày; cắt mạng/tắt emulator thử auto-recover; giả lập version đổi.

### Giai đoạn X — Hoàn thiện trải nghiệm & an toàn

**Mục tiêu:** người chơi kiểm soát, quan sát và tin tưởng agent.

**Vì sao cần:** một sản phẩm hoàn chỉnh phải để người dùng hiểu agent đang làm gì, can thiệp được, và yên
tâm về an toàn tài khoản.

**Phạm vi:**
- **X1 — Dashboard trưởng thành** (M): hiển thị threat/opportunity, quyết định brain kèm lý do, lịch sử
  hành động, cảnh báo; điều khiển chi tiết (bật/tắt từng rule, chỉnh profile trực quan).
- **X2 — Human-in-the-loop mở rộng** (S–M): mọi hành động không đảo ngược (mở khóa, ngoại giao, phá thành)
  đi qua hàng đợi duyệt; agent chờ người.
- **X3 — An toàn tài khoản** (S, xuyên suốt): rate-limit + jitter giống người, nghỉ ngẫu nhiên, tránh
  pattern; captcha đã có — kiểm định thêm.

**Phụ thuộc:** các phase trên sinh dữ liệu để hiển thị/duyệt. **Kiểm chứng:** review UI; đo nhịp request.

---

## 4. Nguyên tắc xuyên suốt (áp dụng cho mọi giai đoạn)

- **Verify live có kỷ luật:** RE tĩnh chỉ là giả thuyết; chạy thật mới chốt (bài học lặp lại: shape `hp`,
  `autoBackType`, cost revive — đều khác dự đoán offline).
- **Tay chân vs bộ não:** LLM chỉ đọc state + sửa profile/phát intent cấp cao, không gọi API trực tiếp;
  giữ token thấp, chạy nền bằng rule.
- **Best-effort + TDD:** rule không bao giờ làm chết vòng lặp; test trước, verify sau, PR nhỏ + merge; để
  server enforce giới hạn (policy-driven, không hardcode).
- **An toàn & con người quyết:** hành động lớn/không đảo ngược cần người duyệt; login API đá phiên client
  nên hạn chế login thừa.
- **Hybrid là kim chỉ nam:** API-first nhưng giữ đường lui vision (R4) để bảo trì được.

## 5. Trình tự & lý do tổng

1. **T (Phòng thủ)** trước tiên — lấp mảnh sinh tồn lớn nhất; nguyên tắc "địch chạm biên = tấn công" kích
   hoạt đúng nó, và nó làm giàu dữ liệu (threat) cho brain + tấn công.
2. **O (Tấn công sâu)** và **E (Kinh tế sâu)** song song được — cả hai nâng năng lực cạnh tranh; O dựa vào
   T để biết đánh ai.
3. **S (Bộ não sâu)** sau khi T/O/E cấp đủ tín hiệu (threat, cơ hội, kết quả trận) để brain quyết & học.
4. **D (Ngoại giao)** khi lõi công/thủ/kinh tế đã vững — liên minh khuếch đại chứ không thay thế lõi.
5. **R (Vận hành 24/7)** khi agent đã đủ hành vi để chạy dài mới đáng validate + auto-recover.
6. **X (Trải nghiệm/an toàn)** hoàn thiện xuyên suốt, chốt ở cuối để người chơi kiểm soát toàn bộ.

## 6. Rủi ro chính & giảm thiểu

- **Đánh người chơi / vây thành phức tạp & rủi ro mất quân** → RE kỹ + predictor + live có kiểm soát;
  human-in-loop cho hành động lớn.
- **Ban tài khoản** → X3 xuyên suốt; ưu tiên rate-limit, jitter; test bằng tài khoản phụ nếu có.
- **Game update phá protocol** → R3 regression + catalog API + tách adapter.
- **Chi phí LLM** → S1 gọi theo sự kiện + cache + ngân sách cứng.
- **API-only là điểm gãy đơn** → R4 vision fallback là lưới an toàn.

## 7. Trạng thái các phần đã xong (tham chiếu)
Kinh tế cơ bản, tấn công ô trung lập + expansion presets, duy trì (heal/revive/stamina), fort advisor
né địch (C1), brain threat/cost-aware cơ bản (Phase B), territory Tier A/B — đã merge (PR #11–#42). Chi
tiết ở [master-plan-remaining](2026-09-17-master-plan-remaining.md) và [nta-agent-construction] memory.
