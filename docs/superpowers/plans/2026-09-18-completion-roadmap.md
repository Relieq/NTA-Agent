# NTA-Agent — Lộ trình hoàn thiện sản phẩm (2026-09-18, bản v2: agent = TRỢ THỦ)

Tài liệu tổng quan cho sản phẩm hoàn chỉnh. **Tầm nhìn đã chốt (user 2026-09-18):** agent là **trợ thủ /
co-pilot**, KHÔNG phải một người chơi tự động cạnh tranh. Nó lo phần việc lặp lại nhàm chán, cung cấp thông
tin và cố vấn, và bảo vệ lãnh thổ khỏi bị lấn âm thầm — còn phần **chơi** (đánh nhau với người chơi khác,
ngoại giao, chiến lược lớn) do **người dùng tự làm**, vì "game sinh ra là để chơi".

Bổ sung cho [ROADMAP.md](../../ROADMAP.md) (kiến trúc). Mỗi hạng mục khi thực thi sẽ có spec + plan riêng.

---

## 1. Định nghĩa "hoàn thiện" (Definition of Done)

Sản phẩm hoàn thiện khi thỏa **tất cả**:

1. **Tự lo việc lặp 24/7:** thu tài nguyên, xây, tuyển, farm ô, hồi máu/hồi sinh, quản stamina — chạy nền
   nhiều ngày không cần người, tự phục hồi khi mạng/emulator/token chập chờn.
2. **Giữ đất khỏi bị lấn âm thầm:** phát hiện và **tự chặn** khi địch lặng lẽ chiếm dần ô vào phạm vi lãnh
   thổ ta (dựng tường/chiếm lại ô biên), **KHÔNG khởi chiến** — chỉ phòng thủ thụ động.
3. **Cung cấp thông tin & cố vấn chính xác:** bản đồ, mối đe dọa, cơ hội, và khuyến nghị (đặt fort, hướng
   mở rộng, ô farm, dự báo tài nguyên) hiển thị rõ ràng cho người chơi ra quyết định.
4. **An toàn tài khoản:** hành vi giống người, không pattern dễ bị phát hiện, xử lý captcha.
5. **Người chơi kiểm soát:** mọi hành động lớn/không đảo ngược và mọi việc thuộc "phần chơi" (PvP, ngoại
   giao, mở khóa binh chủng, chính sách) do người quyết; agent chỉ thực thi lệnh và giải thích.
6. **Bảo trì được:** game update chỉ cần sửa adapter/config; có regression phát hiện protocol/asset đổi.

**Ngoài phạm vi (agent KHÔNG làm — người chơi tự làm):** tấn công đất/thành người chơi khác, vây kinh đô cổ,
phối hợp quân đánh PvP, hành động liên minh (join/đóng góp/chính sách/cờ). Agent chỉ **đọc** các thứ này để
báo cáo, không tự hành động.

---

## 2. Hiện trạng (đã có)

**Nền tảng & I/O:** API-first — session MQTT/protobuf, adapter `actions.py` (~30 endpoint verify live),
catalog 134 endpoint. Chưa có vision adapter (cố ý hoãn).

**Kinh tế:** thu sản lượng thành, build-order (prereq-guarded), tuyển quân, ROI cơ bản. Chưa có giao thương,
quản trần kho, tối ưu tech dài hạn.

**Farm ô trung lập:** chiếm ô hoang thắng được (predictor sim + stats), chọn theo loot/chi phí, tối ưu đội
hình, chiến lược mở rộng spiral/octopus/hybrid. (Đây là phần "việc lặp" — hợp vai trợ thủ.)

**Duy trì:** HealRouting (điều quân thương về hồi máu), ReviveInjured (hồi sinh lính chết), nhịp stamina.

**Bản đồ/lãnh thổ:** Tier A + Tier B full-map (ô mình/địch/biên giới), fort advisor né địch (C1). Chưa có
mô hình mối-đe-dọa (bao chứa + địch chạm biên).

**Bộ não:** brain profile-editing threat/cost-aware cơ bản (thấy nearest_enemy_dist/injured, chỉnh
expansion/revive/max_loss). Chưa gọi theo sự kiện, chưa sinh khuyến nghị cho người, chưa học từ trận.

**Vận hành & tương tác:** dashboard Vue 3, event log, supervisor/pidfile, captcha solver, human-in-loop cho
mở khóa/chính sách. Chưa validate chạy nền dài, chưa auto-recover/regression.

---

## 3. Các trụ cột còn thiếu và lộ trình

Thứ tự = ưu tiên. Mỗi giai đoạn nêu **mục tiêu**, **vì sao cần**, **phạm vi**, **phụ thuộc**, **quy mô**
(S ≤1 buổi, M 1–3 buổi, L nhiều buổi/nhiều PR), **cách kiểm chứng**.

### Giai đoạn P — Bảo vệ lãnh thổ khỏi xâm nhập âm thầm — ✅ **XONG (PR#45/#46, 2026-09-18)**

P1 (threat model: convex hull + detect_incursions), P3 (fort_service ghi threats + `threat_alert` +
dashboard passthrough), P2 (OccupyCell `_defensive_select` chiếm ô biên tranh chấp trước). Giới hạn: chỉ
chặn ô occupiable; ô đệm đất trống → P3 báo người. *Nội dung thiết kế gốc giữ bên dưới để tham chiếu.*

**Mục tiêu:** agent tự phát hiện và chặn khi địch lặng lẽ lấn ô vào phạm vi lãnh thổ ta, để người chơi không
bị "gặm" đất lúc không để ý.

**Vì sao cần:** đây chính là việc một trợ thủ nên làm khi người chơi bận — canh biên và giữ đất. Nó là dạng
phòng thủ thụ động (không đánh nhau), đúng ranh giới bạn đặt ra.

**Nguyên tắc nền (user 2026-09-18):** trong **bao chứa** (bounding box / convex hull) lãnh thổ ta, **địch
chạm đường biên = đang lấn/có ý xâm nhập** (đe dọa thật, khác địch ở xa). Đối xứng chỉ dùng để **báo cơ
hội** cho người (không tự đánh).

**Phạm vi:**
- **P1 — Threat/incursion model** (M): `execution/threat.py` (thuần) tính bao chứa lãnh thổ từ owned; xác
  định ô biên; phát hiện **địch chạm biên / lấn vào trong bao chứa** kèm hướng và mức độ (số điểm tiếp xúc,
  độ sâu lấn, có thành địch gần không). Dùng dữ liệu Tier B sẵn có, không tốn request thêm.
- **P2 — Tự chặn xâm nhập** (M): rule `GuardBorder` — khi phát hiện địch lấn âm thầm, **chiếm lại/chiếm
  trước ô biên bị nhắm** để dựng tường (tận dụng 6h bảo vệ ô mới chiếm, đúng lối spiral); chỉ hành động
  phòng thủ trong phạm vi lãnh thổ, KHÔNG đuổi đánh sang đất địch. Cap số hành động/tick, best-effort.
- **P3 — Cảnh báo người chơi** (S): khi có đe dọa thật (địch mạnh áp sát / thành địch tiến vào), **đẩy cảnh
  báo lên dashboard** để người quyết đánh/thủ — agent không tự khởi chiến.

**Phụ thuộc:** Tier B (có), C1/fort advisor (có), move/occupy (có). **Kiểm chứng:** unit test hình học bao
chứa + phát hiện lấn; live khi có địch sát biên (hoặc dựng kịch bản).

### Giai đoạn I — Thông tin & Cố vấn — ✅ **XONG (PR#48, 2026-09-18)**

`execution/intel.py` `build_report` (status/threats/kinh-tế-dự-báo/cơ-hội/khuyến-nghị-kèm-lý-do) + server
`GET /api/intel` + dashboard `IntelPanel` (tab "Cố vấn"). Gộp I1/I2/I3 v1. *Thiết kế gốc giữ bên dưới.*

**Mục tiêu:** biến agent thành nguồn thông tin đáng tin để người chơi ra quyết định — "mắt và cố vấn".

**Vì sao cần:** vì agent không tự chơi PvP, giá trị lớn nhất của nó (ngoài tự động việc lặp) là **giúp
người chơi thấy và hiểu bàn cờ**: đâu là mối đe dọa, đâu là cơ hội, nên xây/mở rộng/đặt fort ở đâu.

**Phạm vi:**
- **I1 — Báo cáo tình báo bản đồ** (M): tổng hợp threat/opportunity (từ P1), cụm địch, ô giàu tài nguyên
  (lv5) gần, biên giới hở → hiển thị trực quan + danh sách ưu tiên trên dashboard.
- **I2 — Khuyến nghị hành động** (M): gợi ý đặt Cứ Điểm (đã có C1, nâng lên "vì sao"), hướng mở rộng an
  toàn/giàu tài nguyên, ô nên farm, cảnh báo sắp tràn kho — kèm lý do ngắn gọn.
- **I3 — Dự báo & tóm tắt** (S–M): dự báo thời điểm đầy kho/đủ tài nguyên cho mốc xây tiếp; tóm tắt "đã làm
  gì từ lần bạn xem" (nhật ký hành động dễ đọc).

**Phụ thuộc:** P1 (threat), Tier B, brain (I2 có thể dùng brain sinh lý do). **Kiểm chứng:** review nội dung
báo cáo với dữ liệu live; người chơi thấy đúng và hữu ích.

### Giai đoạn E — Chiều sâu kinh tế (tự động hóa việc lặp cho trọn)

**Mục tiêu:** kinh tế tự cân bằng, không lãng phí — để người chơi không phải mó tay việc vặt.

**Vì sao cần:** đây là lõi "trợ thủ lo việc lặp". Hiện thu/xây/tuyển đã có nhưng chưa cân bằng tài nguyên,
dễ tràn kho, chưa tối ưu tech dài hạn.

**Phạm vi:**
- **E1 — Giao thương Bazaar** (M): `HD_BazaarBuyRes/SellRes/SellToSys/...` — bán dư, mua thiếu phục vụ
  build/recruit; rule ROI + guard giá.
- **E2 — Quản trần kho & chống tràn** (S): theo dõi granaryCap/warehouseCap; thu/tiêu đúng nhịp để không
  tràn; cảnh báo khi sắp đầy (nối I3).
- **E3 — Tối ưu tech/mở khóa (người duyệt)** (M): agent tính thứ tự ceri/policy/binh chủng tối ưu và
  **đề xuất**; người chơi duyệt (giữ nguyên human-in-loop cho các mục taste-driven/không đảo ngược).

**Phụ thuộc:** none lớn. **Kiểm chứng:** unit ROI; live quan sát cân bằng tài nguyên nhiều tick.

### Giai đoạn B — Bộ não hỗ trợ (điều phối tự động + sinh cố vấn)

**Mục tiêu:** brain điều chỉnh chính sách tự-động (kinh tế/mở rộng/phòng thủ) theo tình thế, và **sinh
khuyến nghị** cho người — không quyết PvP.

**Vì sao cần:** để phần tự-động thích ứng (bị lấn → thế thủ; dư tài nguyên → mở rộng) và để mục I2 có lý do
chất lượng. Brain vẫn thưa, token thấp.

**Phạm vi:**
- **B1 — Gọi theo sự kiện** (S–M): trigger brain khi bị lấn (từ P), khi dư/thiếu tài nguyên mạnh, khi sắp
  tràn kho — thay vì chỉ cadence cố định; cache; ngân sách token cứng.
- **B2 — Sinh khuyến nghị cho người** (M): brain tạo phần "cố vấn" của I2 (giải thích nên làm gì và vì sao)
  dựa trên digest đã giàu (threat/territory/injured/economy). Người đọc và quyết.
- **B3 — Học từ kết quả (tùy giá trị)** (L): đối chiếu dự đoán vs kết quả trận thật (battle records có API)
  để tinh chỉnh ngưỡng farm/định giá — nâng độ chính xác cố vấn.

**Phụ thuộc:** P (sự kiện), I (kênh hiển thị khuyến nghị), battle records (có). **Kiểm chứng:** live 1 LLM
call theo kịch bản; đo độ khớp predictor sau B3.

### Giai đoạn A — Ngoại giao chỉ để BÁO (read-only)

**Mục tiêu:** đưa bối cảnh liên minh vào thông tin/cảnh báo, KHÔNG hành động.

**Vì sao cần:** liên minh chi phối an toàn (chiến tranh liên minh, kinh đô cổ). Trợ thủ nên **báo** khi liên
minh liên quan tới mối đe dọa quanh ta, để người chơi quyết. Agent không tự join/đóng góp/chính sách.

**Phạm vi:**
- **A1 — Đọc trạng thái liên minh** (M): thành viên, rank, log, cờ bản đồ (`HD_GetAlli*` đã map) → đưa vào
  báo cáo tình báo (I1) và ngữ cảnh threat (P). Chỉ đọc.

**Phụ thuộc:** I (kênh hiển thị). **Kiểm chứng:** đọc live, hiển thị đúng; không có hành động ghi.

### Giai đoạn R — Bền bỉ & Vận hành 24/7 (điều kiện để là "sản phẩm")

**Mục tiêu:** chạy nền nhiều ngày không cần người, tự phục hồi, sống sót qua game update.

**Vì sao cần:** một trợ thủ chỉ hữu ích nếu luôn bật và đáng tin. Hiện mới chạy one-off, chưa validate
long-run, chưa auto-recover.

**Phạm vi:**
- **R1 — Auto-recover** (M): reconnect khi mất MQTT/token; phát hiện emulator treo → khởi động lại qua ADB;
  backoff giống người; không spam khi lỗi kéo dài.
- **R2 — Validate chạy nền dài** (M): chạy giám sát nhiều giờ/ngày; quan sát rò rỉ tài nguyên/bộ nhớ; tick
  ổn định; sửa lỗi lộ ra.
- **R3 — Regression khi game update** (M): pin version protocol/config; test phát hiện đổi endpoint/asset;
  quy trình cập nhật catalog + template.
- **R4 — Vision fallback adapter** (L, lưới an toàn): OpenCV+OCR+ADB tap cho domain chưa crack hoặc khi API
  đổi/gãy — cho tiêu chí "bảo trì được"; chỉ đầu tư khi API tỏ ra không đủ.

**Phụ thuộc:** hành vi ở trên (chạy dài mới đáng khi agent đã đủ việc). **Kiểm chứng:** uptime nhiều ngày;
cắt mạng/tắt emulator thử recover; giả lập version đổi.

### Giai đoạn U — Trải nghiệm & An toàn (mặt tiền của trợ thủ)

**Mục tiêu:** người chơi thấy rõ agent đang làm gì, nhận thông tin/cảnh báo, duyệt việc lớn, và yên tâm về
an toàn tài khoản.

**Vì sao cần:** vì agent là trợ thủ, **giao diện tương tác chính là sản phẩm**. Đây là nơi hội tụ P/I/B.

**Phạm vi:**
- **U1 — Dashboard trung tâm chỉ huy** (M): bản đồ + threat/opportunity, khuyến nghị kèm lý do, nhật ký
  hành động, cảnh báo nổi bật; bật/tắt từng rule; chỉnh profile trực quan.
- **U2 — Hàng đợi duyệt của người** (S–M): mọi việc "phần chơi" + không đảo ngược (PvP do người, mở khóa,
  chính sách, ngoại giao) xếp vào hàng đợi chờ người duyệt; agent chỉ thực thi khi được đồng ý.
- **U3 — An toàn tài khoản** (S, xuyên suốt): rate-limit + jitter giống người, nghỉ ngẫu nhiên, tránh
  pattern; kiểm định captcha.

**Phụ thuộc:** P/I/B (sinh nội dung để hiển thị/duyệt). **Kiểm chứng:** review UI; đo nhịp request.

---

## 4. Nguyên tắc xuyên suốt

- **Agent hỗ trợ, người chơi chơi:** không PvP/ngoại giao tự động; hành động lớn/không đảo ngược cần người
  duyệt. Khi nghi ngờ ranh giới, nghiêng về "báo cho người" thay vì "tự làm".
- **Verify live có kỷ luật:** RE tĩnh chỉ là giả thuyết; chạy thật mới chốt (bài học: shape `hp`,
  `autoBackType`, cost revive đều khác dự đoán offline).
- **Tay chân vs bộ não:** LLM chỉ đọc state + sửa profile / sinh khuyến nghị, không gọi API trực tiếp;
  token thấp, chạy nền bằng rule.
- **Best-effort + TDD:** rule không làm chết vòng lặp; test trước, verify sau, PR nhỏ + merge; để server
  enforce giới hạn (policy-driven, không hardcode).
- **Hybrid là kim chỉ nam:** API-first nhưng giữ đường lui vision (R4) để bảo trì được.

## 5. Trình tự & lý do tổng

1. **P (Chặn xâm nhập)** trước — việc trợ thủ giá trị nhất khi người vắng mặt (giữ đất), và cấp dữ liệu
   threat cho mọi phần sau. Áp đúng nguyên tắc "địch chạm biên".
2. **I (Thông tin & cố vấn)** ngay sau — vai trò trung tâm của một trợ thủ; tiêu thụ threat từ P.
3. **E (Kinh tế sâu)** — hoàn tất tự-động-hóa việc lặp (song song được với I).
4. **B (Bộ não hỗ trợ)** — làm P/E thích ứng và nâng chất lượng cố vấn của I.
5. **A (Ngoại giao chỉ đọc)** — thêm bối cảnh cho I/P khi lõi đã vững.
6. **R (Vận hành 24/7)** — khi agent đã đủ việc để chạy dài mới đáng validate + auto-recover.
7. **U (Trải nghiệm/an toàn)** — mặt tiền, hoàn thiện xuyên suốt và chốt ở cuối.

## 6. Rủi ro chính & giảm thiểu

- **Chặn xâm nhập nhầm/quá tay** (chiếm ô không cần, phí quân/stamina) → ngưỡng phát hiện thận trọng +
  cap/tick + best-effort; nghiêng về cảnh báo khi không chắc.
- **Ban tài khoản** → U3 xuyên suốt (rate-limit, jitter); test bằng tài khoản phụ nếu có.
- **Game update phá protocol** → R3 regression + catalog API + tách adapter.
- **Chi phí LLM** → B1 gọi theo sự kiện + cache + ngân sách cứng.
- **API-only là điểm gãy đơn** → R4 vision fallback là lưới an toàn.

## 7. Trạng thái đã xong (tham chiếu)
Kinh tế cơ bản, farm ô trung lập + expansion presets, duy trì (heal/revive/stamina), fort advisor né địch
(C1), brain threat/cost-aware cơ bản, territory Tier A/B — đã merge (PR #11–#43). Chi tiết ở
[master-plan-remaining](2026-09-17-master-plan-remaining.md) và memory nta-agent-construction /
nta-agent-human-in-loop / nta-agent-strategy.
