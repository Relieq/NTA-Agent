# NTA — Protocol (tầng API)

Kết quả mổ schema từ `proto/msg.jsc` (giải mã bằng key XXTEA, xem [RE_FINDINGS](RE_FINDINGS.md)).
Đây là bản đồ để `nta_agent/io/api/` đọc/gửi message thật.

## Transport & wire format (đã xác nhận từ index.jsc — code game)
- Client **Paho MQTT v3 over WebSocket** path `/mqtt`, **TLS** (`useSSL`), keepAlive 30s,
  cleanSession. Framework server: **mqant** (Go). Server: `nine-hk.twomiles.cn:3653`.
- **GỬI (request)** — hàm `net.send(route, params, cb, wait)`:
  1. `route` dạng `"module/HD_Action"` (vd `"game/HD_UpAreaBuild"`).
  2. Tên message = `route.replace("/","_").toUpperCase() + "_C2S"` → tra trong `proto` (schema).
  3. `reqId += 1`; lưu `reqMap[reqId] = {cb, msgName}`.
  4. **Publish** tới topic **`module/HD_Action/reqId`**, payload = `MSG_C2S.encode(params).finish()`, **QoS 1**.
- **NHẬN (response)** — `recvMessage` (`onMessageArrived`):
  1. Tách topic `module/action/reqId` → lấy `reqId`, tra `reqMap`.
  2. Envelope ngoài: **`S2C_RESULT { data: bytes(#1), error: string(#2) }`** = `proto.S2C_RESULT.decode(payload)`.
  3. Nếu `error` rỗng: body = `proto[msgName + "_S2C"].decode(result.data).toJSON()` → gọi `cb({err, data})`.
- **Notify/push** (server chủ động, không có reqId): xử lý qua handler `On<Event>` (vd
  `OnUpdateAllianceMembers`) — cần map riêng khi làm state store.
- **Bootstrap kết nối (đã xác định):**
  1. **HTTP gate** `https://<domain>:8080` (release) — endpoint: `/getServerInfo` (danh sách/thông tin
     server), `/getHotUpdateInfo` (hot-update), `/getNotice`, `/feedback`, `/getMaintainInfo`.
  2. **Domain**: `getServerDomain(env)` → `serverDomains[serverArea]` (data-driven config). Giá trị
     thực tế của tài khoản này: area `hk` → **`nine-hk.twomiles.cn`** (từ localStorage + pcap).
  3. **MQTT connect**: `{host: domain, port: release?3653:4653, useSSL:true}`, `clientId="t"+UUIDv4()`,
     mqttVersion 3, cleanSession, keepAlive 30. Không username/password ⇒ auth qua message login.
  4. **Login**: lần đầu `login/HD_GuestLogin{guestId, nickname, distinctId, os, lang, inviteUid}`
     → nhận accountToken (lưu `slg_account_token`). Reconnect: `lobby/HD_TryLogin{accountToken, distinctId,
     os, lang, platform}`. (Có cả google/facebook/apple/taptap/wx login.)
- **Analytics riêng** (bỏ qua): thinkingdata `ulog.dhgames.com:8180`.

## Bề mặt API: 323 request (_C2S) / 322 response (_S2C)
Quy ước tên: `MODULE_HD_ACTION_C2S` (client→server) và `_S2C` (server→client). Struct lồng dùng
hậu tố `Info/Data/Notify`. Phân bố theo module:

| Module | #req | Nội dung |
|---|---|---|
| LOBBY | 156 | login/tài khoản, hero, battle pass, shop, battle forecast, ranking |
| GAME  | 140 | in-game: build, march, army/pawn, city, battle record, alliance |
| CHAT  | 10  | chat, gallery |
| LOGIN | 8   | guest/google/facebook/apple/taptap/wx login, auth |
| MAIL  | 6   | hộp thư |
| MATCH | 3   | matchmaking |

## Ví dụ message đã decode (field-level)
```
GAME_HD_UPAREABUILD_C2S    { #1 index:int32, #2 uid:string }        # nâng cấp công trình
GAME_HD_ADDAREABUILD_C2S   { ... }                                   # xây công trình
GAME_HD_GETMARCHS_C2S      { }                                       # lấy danh sách hành quân
GAME_HD_CANCELMARCH_C2S    { ... }                                   # huỷ hành quân
LOBBY_HD_BATTLEFORECAST_C2S{ #1 sid, #2 landCount, #3 maincityLevel, # DỰ ĐOÁN trận
                             #4 landDis, #5 landlv : int32 }         #  -> dùng cho predictor
LOGIN_HD_GUESTLOGIN_C2S    { #1 guestId, #2 distinctId, #3 os,       # đăng nhập khách
                             #4 nickname, #5 inviteUid, #6 lang, #7 platform : string }
S2C_RESULT                 { #1 data:bytes, #2 error:string }        # bọc kết quả chung
```

Danh sách đầy đủ 323 op: `tools/re/decrypted/api_ops.txt` (gitignored). Schema đầy đủ (2.5MB JS):
`tools/re/decrypted/msg.js` (gitignored — là code game).

## Ánh xạ sang kiến trúc agent
- **Tay chân (heuristic)**: gọi trực tiếp các `GET*`/action lặp (thu output, march, build queue).
- **Predictor**: `LOBBY_HD_BATTLEFORECAST` cho battle outcome; các `*Info` cho ROI build.
- **Bộ não (LLM)**: đọc state chuẩn hoá từ các `S2C`/`*Info`, phát intent → tay chân dịch ra `_C2S`.

## Bước tiếp
1. Giải `index.jsc` → đọc `core/@api/*` lấy **envelope MQTT + cách routing** (topic vs opcode).
2. Decode `payloadHex` mẫu trong localStorage để kiểm chứng end-to-end.
3. Sinh Python protobuf (từ msg.js hoặc reconstruct .proto) cho `nta_agent/io/api/protocol.py`.
4. `client.py`: MQTT client (paho) qua TLS, gửi `_C2S` / nhận `_S2C`.
