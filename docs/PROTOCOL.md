# NTA — Protocol (tầng API)

Kết quả mổ schema từ `proto/msg.jsc` (giải mã bằng key XXTEA, xem [RE_FINDINGS](RE_FINDINGS.md)).
Đây là bản đồ để `nta_agent/io/api/` đọc/gửi message thật.

## Transport
- Server: **`nine-hk.twomiles.cn` (43.134.159.76)**, **MQTT over TLS 1.2**, port **3653**.
  Cùng host có port 8080 & 443 (hot-update/CDN).
- Body message = **Protocol Buffers** (protobuf.js static), bọc trong envelope MQTT dạng
  `{type, messageIdentifier, version, payloadMessage:{payloadHex}}` (thấy trong localStorage
  `jsb.sqlite`). `payloadHex` = protobuf đã encode của message tương ứng.
- **Routing chưa chốt**: schema không chứa opcode số ⇒ nhiều khả năng topic MQTT = tên operation.
  Cần đọc `index.jsc`/`core/@api/*` hoặc bắt live (SSL-unpin) để xác nhận envelope + topic.

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
