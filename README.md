<div align="center">

**Tiếng Việt** · [English](README.en.md) · [中文](README.zh.md)

# NTA-Agent

**Trợ lý tự động chơi _Ninety Thousand Acres_: xây thành, chiếm đất, rèn đồ, gom quân, có bảng điều khiển trên trình duyệt.**

[![Tải bản mới nhất](https://img.shields.io/github/v/release/Relieq/NTA-Agent?label=T%E1%BA%A3i%20v%E1%BB%81&style=for-the-badge)](https://github.com/Relieq/NTA-Agent/releases/latest)
![Windows](https://img.shields.io/badge/Windows-10%2F11-0078D6?style=for-the-badge&logo=windows)
![RAM](https://img.shields.io/badge/RAM-~0.5%20GB-2ea44f?style=for-the-badge)

<img src="docs/images/overview.png" alt="Bảng điều khiển NTA-Agent" width="900">

</div>

Agent nói chuyện **thẳng với máy chủ game** (không bấm màn hình), nên chạy nhẹ, nhanh và
không cần mở giả lập khi chạy hằng ngày. Mọi quyết định mạo hiểm đều theo giới hạn bạn đặt
(ví dụ "không tổn thất lính").

> ⚠ **Rủi ro:** dùng bot có thể vi phạm điều khoản của game và dẫn tới **khoá tài khoản**.
> Bạn tự chịu trách nhiệm khi dùng.
>
> ⚠ **Một phiên duy nhất:** khi agent chạy, game trong giả lập/điện thoại sẽ bị đăng xuất
> (và ngược lại). Muốn tự chơi thì bấm **⏹ Stop** trước.

---

## Tính năng

### 🏰 Tổng quan: tài nguyên, công trình, hàng đợi xây
Theo dõi lương thực, gỗ, đá, sắt, vàng… và tự nâng cấp công trình theo **thứ tự xây do bạn
sắp xếp** (kéo-thả, có thể bỏ qua công trình không muốn).

### ⚔ Quân đội và nhóm quân
<img src="docs/images/armies.png" alt="Quân đội" width="900">

- Chiếm ô quanh lãnh thổ bằng **mô phỏng trận đánh chính engine của game**: chỉ đánh khi
  dự đoán thắng trong giới hạn tổn thất bạn đặt. **Thể lực chỉ trả cho rương**: hết thể lực vẫn
  mở rộng được (chỉ không có rương). Bị đồng minh bao quanh cũng không kẹt: ô kề đất đồng minh
  cũng đánh được (đúng luật game).
- Mặc định mỗi đội farm đánh **riêng** khi một mình đủ thắng (dùng ít quân nhất); cả nhóm chỉ ra
  chung khi một đội không đủ sức.
- Tự chiêu mộ, hồi sinh, dồn lính cho đủ đội, nâng cấp lính bằng sách EXP.
- **Nâng lính bằng đội dư:** chọn nhóm đội + chế độ. Agent đề xuất đội dư (dùng lại đội lẻ, dồn lính,
  chiêu mộ, số sách/thời gian cần); bạn xác nhận. Đội dư nâng ở thành rồi ra **ô kề** đội chính **tráo
  lính cùng loại** — đội chính vẫn farm/dig (thiếu 1 đội thì chỉ đánh khi vẫn không mất lính).
  Mỗi lần nâng 1 cấp tốn cả **lương** (hệ số cấp × giá gốc của trận, vài trăm), nên luật chiêu mộ thường
  nhường lượng lương đó; agent chỉ nâng **đúng số lính mỗi loại mà nhóm farm đang thiếu** (đội chính
  8 cung độc + 1 thợ săn thì chỉ nâng 1 thợ săn), không nâng cả đội dư.
- Chọn **đội farm** để agent quản lý riêng. Mục **Thứ tự vào trận** (thu gọn một dòng) cho đổi thứ tự
  bằng kéo-thả hoặc ◀ ▶ rồi **Lưu**: đội đầu tiên vào trận trước (1-tile), mô phỏng dig cũng theo thứ tự đó.

### 🧠 Chat với "bộ não" (tuỳ chọn, cần OpenAI key)
<img src="docs/images/chat.png" alt="Chat tạo nhóm quân" width="760">

Ra lệnh bằng tiếng Việt, ví dụ _"Tạo nhóm 5 đội gồm 1 đội khiên lớn và 4 đội IMP, đặt tên
Đội 1 đến Đội 5"_. Bộ não đề xuất, **bạn bấm Xác nhận** thì agent mới làm: dồn lính từ các
đội hỗn hợp, chiêu mộ phần thiếu rồi tự đặt tên. Đổi tên đội, đổi chiến thuật… cũng làm qua chat.

**Tráo lính:** _"Tráo 1 lính thợ săn của Đội 3 với lính cung độc nằm cuối Đội 5"_. Có ba thao tác: **đổi
chỗ** 2 lính giữa 2 đội, **chuyển** lính sang đội khác (hoặc đội mới), **đổi thứ tự** lính trong một đội.
Agent chọn lính cấp thấp nhất (hoặc lính ở đầu/cuối đội nếu bạn nói rõ) và hiện thẻ xác nhận. Game chỉ cho
tráo khi hai đội **cùng một ô**: nếu khác ô, agent gọi chúng tới một ô trong đất của bạn (điểm gặp gần nhất,
tối đa 5 đội/ô; đội đang sắp đánh thì đứng yên, đội kia đi tới) rồi mới tráo. Nếu việc tráo làm hỏng mục
tiêu đội hình đang chạy, thẻ báo trước và xác nhận sẽ huỷ mục tiêu đó. Tên đội bạn gõ phải khớp đội có thật,
nếu không agent hỏi lại thay vì đoán.

### 🔨 Rèn lại trang bị theo tiêu chí
<img src="docs/images/forge.png" alt="Rèn lại trang bị" width="760">

Đặt **mức tối thiểu cho từng chỉ số hiệu ứng** (có hiện khoảng roll được, ví dụ 150–180%)
và **ngân sách sắt** cho mỗi món. Agent rèn lại tới khi đạt, hoặc dừng khi hết ngân sách. Món vừa **mở khoá** được chế tạo **trước** vòng
rèn lại: nếu nó còn thiếu lương/gỗ/đá/sắt thì vòng rèn lại tạm dừng (rèn lại tiêu đúng các thứ đó), và bảng
ghi rõ lý do ("đang chế tạo món mới…", "vòng rèn lại tạm dừng…").

**Trang bị chuyên dụng:** bạn chọn món ở ô 10/18 (thấy luôn danh sách hiệu ứng random **của trận này**).
Khi một dòng mong muốn đạt mức, agent **khoá** dòng đó rồi dùng **máy cố định** (ngân sách riêng) để rèn dòng còn lại.
**Dung luyện** do bạn tự chọn món phụ, xem trước rồi xác nhận — agent chỉ gửi đúng lệnh đó.

### 🗺 Lãnh thổ và Cứ Điểm
<img src="docs/images/territory.png" alt="Bản đồ lãnh thổ" width="760">

Bản đồ lãnh thổ trực tiếp: ô đã chiếm, biên giới, quân địch, vùng gợi ý xây **Cứ Điểm**
(bấm 1 ô là agent xây). Kiểu mở rộng xoắn ốc / bạch tuộc tuỳ tình hình địch.

**⛏ Dig theo đường bạn vẽ:** bấm **✏ Vẽ đường dig**, giữ chuột trái và **kéo qua từng ô** (bắt đầu từ đất của
bạn hoặc ô kề đất đồng minh; kéo ngược để xoá; Shift hoặc chuột phải để di chuyển bản đồ).
1. **📐 Đánh giá đường:** agent chấm từng ô (địa hình, đất người khác, sát địch, ô nhóm farm đánh không nổi kèm
   % tổn thất, thời gian, thể lực) và **chưa gửi lệnh nào vào game**. Bạn sửa rồi đánh giá lại tuỳ ý; các ký hiệu
   được nhớ khi huỷ hoặc xoá bản vẽ (nút **🧹 Xoá ký hiệu** để bỏ).
2. **✔ Xác nhận đường** → agent đề xuất chỗ đặt Cứ Điểm (~7 ô một cái) → bạn thêm/xoá → **✔ Xác nhận kế hoạch dig**.
3. Nhóm đội farm dig **đúng đường và đúng thứ tự đã vẽ**; gặp ô chưa đánh nổi hoặc bị chiếm thì **chờ và báo**,
   không tự đi vòng. Các đội khác vẫn farm như thường.

Nút *Gợi ý đường tới đây* (bấm một ô bất kỳ) vẫn có: agent gợi ý một đường để bạn **✏ Sửa** rồi mới xác nhận.
Mô phỏng dùng nhóm đội farm theo thứ tự đã lưu (thẻ đánh giá ghi rõ nhóm đã dùng) và mô phỏng lại ở mỗi lần đánh giá.

### 🎁 Nhiệm vụ và phần thưởng miễn phí
Agent tự nhận thưởng **nhiệm vụ hướng dẫn** khi đạt (kể cả loại game tự tính tiến độ như chọn chính sách, rèn
trang bị, cấp kiến trúc) và thử lại các nhiệm vụ còn mở mỗi 5 phút. Ngoài ra nó tự nhận, **chỉ nhận chứ không mua
gì** (không tiêu ingot, không xem quảng cáo):

- **Vòng quay may mắn:** 10 lượt miễn phí mỗi ngày (cộng các lượt thêm nếu còn), giãn cách theo thời gian game báo.
- **Vàng miễn phí** và **token chiến miễn phí** của cửa hàng, khi hết thời gian chờ.
- **Gói tân thủ:** từng ngày đến hạn (nếu bạn có gói).

Lịch nhận lưu trong `run\free_rewards.json` và hiện ở tab Tổng quan (dòng **🎁 Phần thưởng miễn phí**).

### 🧭 Cố vấn và cảnh báo
<img src="docs/images/advisor.png" alt="Cố vấn" width="760">

Cảnh báo địch áp sát, dự báo kho đầy, khuyến nghị phòng thủ. Agent **ghi lại mọi trận mất
lính**, phát lại bằng mô phỏng để rút bài học (ví dụ nên cho đội nào đánh trước).

### ⚙ Thiết lập 7 bước, tự kiểm tra
<img src="docs/images/setup.png" alt="Thiết lập" width="760">

Mỗi bước tự kiểm tra và hiện cách sửa nếu lỗi. Không cần cài Python hay Node: app đã kèm sẵn.

---

## Cài đặt (bản portable)

1. Tải **`NTA-Agent-<phiên bản>-full.zip`** từ [trang Releases](https://github.com/Relieq/NTA-Agent/releases/latest).
2. Giải nén vào một thư mục **bạn có quyền ghi**, ví dụ `D:\NTA-Agent\`
   (đừng để trong `C:\Program Files`).
3. Chạy **`NTA-Agent.exe`**. Trình duyệt sẽ mở bảng điều khiển tại `http://127.0.0.1:8787`.
   - Nếu Windows SmartScreen chặn: bấm **More info → Run anyway** (app chưa được ký số).
   - Nếu phần mềm diệt virus chặn `NTA-Agent.exe`: dùng **`NTA-Agent.bat`**, hai file làm y hệt nhau.
4. Lần đầu, bảng điều khiển mở tab **Thiết lập & Cài đặt**. Làm theo 7 bước bên dưới.
   Nút **▶ Start** bị khoá cho tới khi cả 7 bước đều ✅.

## Chuẩn bị trước

- **LDPlayer 9** (Android 9). Tải ở ldplayer.net. Chỉ cần cho lần thiết lập, xem
  [Dùng hằng ngày](#dung-hang-ngay).
- Game **Ninety Thousand Acres** đã cài trong LDPlayer, **đúng phiên bản app hỗ trợ**
  (xem bước 4).
- (Tuỳ chọn) **OpenAI API key** để bật "bộ não" chiến lược + chat.

---

## Các bước thiết lập

Ở tab **Thiết lập & Cài đặt**, bấm **▶ Chạy tất cả** hoặc chạy từng bước. Bước nào ❌ sẽ
hiện gợi ý sửa, sửa xong bấm **Chạy lại**.

<a id="buoc-1-adb"></a>
### Bước 1: Tìm ADB

App tự tìm `adb.exe` của LDPlayer (thường ở `D:\LDPlayer\LDPlayer9\adb.exe` hoặc
`C:\LDPlayer\LDPlayer9\adb.exe`). Nếu cài LDPlayer ở chỗ khác, nhập đường dẫn vào ô
**Đường dẫn adb.exe** trong phần Cài đặt rồi chạy lại.

<a id="buoc-2-gia-lap"></a>
### Bước 2: Kết nối giả lập

- Mở LDPlayer.
- Vào **Cài đặt LDPlayer → Khác → Gỡ lỗi ADB** và chọn **Mở kết nối cục bộ**.
- **LDPlayer 14** không có mục này: **tắt** giả lập, mở `LDPlayer14\vms\config\leidian0.config`,
  sửa `"basicSettings.adbDebug": 0` thành `1`, lưu rồi bật lại giả lập.
- Nếu mở nhiều máy ảo, nhập đúng thiết bị (ví dụ `emulator-5554`) vào ô **Thiết bị ADB**.

<a id="buoc-3-root"></a>
### Bước 3: Quyền root

Vào **Cài đặt LDPlayer → Khác → Quyền ROOT = Bật**, lưu lại rồi **khởi động lại LDPlayer**.
App cần root để đọc mã thiết bị và token đăng nhập của game (chỉ đọc, không sửa gì).

<a id="buoc-4-game"></a>
### Bước 4: Phiên bản game

App kiểm tra phiên bản game đang cài có khớp với bản app hỗ trợ không. Lệch phiên bản có thể
khiến agent gửi lệnh sai. Nếu game vừa cập nhật mà app chưa có bản mới, bạn có thể bấm
**Bỏ qua** (tự chịu rủi ro) hoặc chờ bản cập nhật của app.

<a id="buoc-5-du-lieu-game"></a>
### Bước 5: Dữ liệu game

App **không** kèm dữ liệu của game. Bước này lấy file cài đặt game (APK) **từ chính giả lập
của bạn**, rồi giải mã giao thức, các bảng số liệu và engine trận đánh vào thư mục dữ liệu
riêng của bạn.

- Khoá giải mã được **tự tìm trong chính bản game của bạn**, bạn không cần nhập gì.
- Mất khoảng 10–30 giây. Phải **dừng agent** trước khi chạy lại bước này.
- Khi game cập nhật phiên bản, hãy chạy lại bước này.

<a id="buoc-6-distinct-id"></a>
### Bước 6: Mã thiết bị

Đọc mã thiết bị mà game dùng khi đăng nhập. Nếu lỗi, hãy mở game một lần cho tới màn hình
chính rồi chạy lại.

<a id="buoc-7-token"></a>
### Bước 7: Token đăng nhập

1. Trong LDPlayer, mở game và **đăng nhập** (Google/Facebook…).
2. **Thoát game** (vuốt tắt hẳn).
3. Chạy lại bước này. Phải dừng agent trước.

Khi đủ 7 bước ✅, bấm **▶ Start** ở góc trên.

---

<a id="dung-hang-ngay"></a>
## Dùng hằng ngày

### Có cần bật LDPlayer không?

**Không.** Agent nói chuyện thẳng với máy chủ game, nên khi chạy bình thường bạn có thể tắt
LDPlayer (tiết kiệm khoảng 1.7 GB RAM).

Token đăng nhập của game chỉ dùng được một lần: mỗi lần agent đăng nhập, máy chủ trả token
mới và agent tự lưu lại cho lần sau. Nhờ vậy khởi động lại agent hay khởi động lại máy đều
không cần LDPlayer.

Chỉ cần LDPlayer khi:

| Trường hợp | Làm gì |
|---|---|
| Thiết lập lần đầu, hoặc game cập nhật | Chạy các bước ở tab Thiết lập (bước 5 trích lại dữ liệu game). |
| **Chuỗi token bị đứt**, thường là sau khi bạn tự vào game (giả lập hay điện thoại) | Nếu LDPlayer đang mở, agent tự lấy token mới. Nếu không, agent chuyển **CRASHED**: mở LDPlayer, đăng nhập game, thoát hẳn game, chạy lại bước 7 rồi bấm Start. |
| Bạn muốn tự chơi | Bấm **⏹ Stop** agent trước (chỉ một phiên được đăng nhập). |

### Khởi động lại

- **Khởi động lại dashboard:** agent vẫn chạy tiếp; dashboard mới tự nhận lại agent.
- **Khởi động lại máy:** không có gì tự bật lại. Chạy `NTA-Agent.exe` rồi bấm **▶ Start**.
  Agent đăng nhập bằng token đã lưu.
- Nếu agent chuyển **CRASHED**, bấm **📄 Xem lỗi** cạnh nút Start để xem nguyên nhân.

### Tốn bao nhiêu RAM?

Đo thực tế trên máy Windows 11:

| Thành phần | RAM |
|---|---|
| Mô phỏng trận (Node, chạy engine trận của game) | ~380 MB |
| Agent (Python) | ~45 MB |
| Dashboard (Python) | ~40 MB |
| **Tổng** | **~0.5 GB** |
| _(LDPlayer, khi mở)_ | _~1.7 GB, không cần khi chạy hằng ngày_ |

---

## Cài đặt (tab Thiết lập & Cài đặt)

| Mục | Ý nghĩa |
|---|---|
| OpenAI API key | Tuỳ chọn. Bật bộ não chiến lược + chat. Tính phí vào tài khoản OpenAI của bạn; nút **Kiểm tra OpenAI key** thử key miễn phí. |
| Model / Giới hạn lượt gọi | Chọn model từ danh sách lấy theo tài khoản OpenAI của bạn (mặc định `gpt-4o-mini`) và số lần gọi tối đa mỗi phiên. |
| XXTEA key | Để trống: app tự tìm khoá trong bản game của bạn. Chỉ nhập khi bước 5 báo không tìm được. |
| adb.exe / Thiết bị ADB | Chỉ cần khi app không tự dò được. |

Key được **mã hoá bằng tài khoản Windows của bạn**: copy file sang máy khác sẽ không đọc
được. Bảng điều khiển không bao giờ hiện lại key đầy đủ.

## Cập nhật

- Khi có bản mới, thanh xanh **⬆ Có bản mới** hiện trên cùng. Bấm **Cập nhật**: agent dừng,
  app tải bản mới (kiểm tra checksum), tự khởi động lại sau khoảng 1 phút.
- Nếu bản mới không khởi động được, app **tự quay về** bản cũ.
- Nếu cập nhật báo `being used by another process`: đóng cửa sổ Explorer, terminal hay trình soạn thảo đang mở
  trong thư mục NTA-Agent, bấm **⏹ Stop** agent rồi **Cập nhật** lại (từ bản 0.2.17, trình cập nhật tự dừng các
  tiến trình của NTA-Agent còn sót và ghi rõ tệp/tiến trình đang giữ khoá vào `run\updater.log`).
- Muốn quay về bản trước bằng tay: phần Cài đặt → **↩ Quay về bản trước**
  (app giữ 2 bản gần nhất).
- Cập nhật không đụng tới dữ liệu, key và cài đặt của bạn.

## Dữ liệu nằm ở đâu

Mọi thứ của riêng bạn nằm ở `%LOCALAPPDATA%\NTA-Agent\`:

- `settings.json`: cài đặt, key đã mã hoá
- `token.txt`: token đăng nhập game
- `gamedata\`: dữ liệu game trích từ APK của bạn
- `run\`: trạng thái agent, nhật ký (`agent.log`, `errors.jsonl`)
- `backups\`: các bản app cũ

**Gỡ cài đặt:** xoá thư mục app và thư mục `%LOCALAPPDATA%\NTA-Agent`.

## Xử lý sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| Trình duyệt không mở | Tự mở `http://127.0.0.1:8787`. Nếu cổng bận, app chuyển sang 8788, 8789… |
| Start báo "Chưa hoàn tất Thiết lập" | Mở tab Thiết lập, chạy các bước còn ❌. |
| Agent chuyển sang CRASHED | Bấm **📄 Xem lỗi**, hoặc xem `run\agent.log` và `run\errors.jsonl`. Lỗi token: xem [Dùng hằng ngày](#dung-hang-ngay). |
| Game trong giả lập bị đăng xuất | Bình thường: agent và game dùng chung một phiên. |
| Đổi tên đội chưa thấy tác dụng | Game chỉ cho đổi tên khi đội rảnh; agent tự thử lại khi đội về. |
| Cập nhật báo "being used by another process" | Đóng Explorer/terminal đang mở trong thư mục NTA-Agent, **Stop** agent rồi thử lại; xem `run\updater.log`. |
| Lãnh thổ không mở rộng thêm | Thể lực về 0 **không** chặn mở rộng. Thường là mọi ô kề đều vượt giới hạn tổn thất bạn đặt, hoặc các đội đang bận/đang nâng cấp; xem tab Cố vấn và nhật ký. |
| Tráo lính báo hai đội không ở cùng ô / không có đội tên đó | Nêu đúng tên đội như trong danh sách; hai đội khác ô thì agent tự gọi tới điểm gặp (cần danh sách đất đã quét). |
| Bước 5 báo "không tìm được khoá" | Game có thể đã đổi cách lưu khoá: báo người chia sẻ app, hoặc nhập XXTEA key thủ công ở Cài đặt. |

---

## Dành cho người phát triển

Mã nguồn Python 3.12 (venv `.venv`), sidecar mô phỏng trận Node ≥ 18. Kiến trúc và lộ trình
nằm trong `docs/ROADMAP.md`; ghi chú vận hành cho agent nằm trong `CLAUDE.md`.

```bash
.venv/Scripts/python.exe -m pytest -q                  # test
.venv/Scripts/python.exe -m ruff check nta_agent tests # lint
.venv/Scripts/python.exe tools/launch_detached.py dashboard   # chạy dashboard (dev)
```

Đóng gói bản phát hành (commit trước, vì chỉ file đã được git theo dõi mới được đóng gói):

```bash
.venv/Scripts/python.exe tools/package.py --version 0.1.0 --notes "..."
# -> dist/NTA-Agent-<v>-full.zip, dist/NTA-Agent-<v>-app.zip, dist/manifest.json
gh release create v0.1.0 dist/NTA-Agent-0.1.0-full.zip dist/NTA-Agent-0.1.0-app.zip dist/manifest.json
```

`tools/package.py` chỉ giữ bản build mới nhất trong `dist/` (các bản cũ đã có trên GitHub Releases).

App tự cập nhật bằng cách đọc `releases/latest` của repo này. Bản `app` (nhỏ) được dùng khi
runtime (Python/Node) không đổi, ngược lại dùng bản `full`.
