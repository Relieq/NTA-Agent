# NTA — Catalog API game (`game/HD_*`)

Danh mục endpoint request/response của game *Ninety Thousand Acres* (`twgame.global.acers`
v4.4.0). Bổ trợ cho [PROTOCOL.md](../PROTOCOL.md) (transport MQTT/protobuf) và
[RE_FINDINGS.md](../RE_FINDINGS.md) (đường RE). Đây là **tài liệu sống** — cập nhật khi crack thêm.

## Nguồn & cách đọc shape
- **Transport:** MQTT over WSS, route `"module/HD_Action"`, message `MODULE_HD_ACTION_C2S`/`_S2C`
  (protobuf). Chi tiết ở [PROTOCOL.md](../PROTOCOL.md).
- **Engine đã giải mã:** `tools/re/decrypted/index.js` (gitignored). Shape lấy từ call-site
  `netHelper.reqXxx({...})` trong engine, hoặc từ chính code ta đã chạy thật.
- **134 endpoint** `game/HD_*` tồn tại trong engine (liệt kê §Phụ lục). Tài liệu này chi tiết
  các cái đã dùng/đã RE; phần còn lại ghi mục đích + shape `TODO`.

**Ký hiệu trạng thái:**
| | Nghĩa |
|---|---|
| ✅ | Shape xác minh **live** (ta đã gửi thật, server chấp nhận) — xem `nta_agent/execution/actions.py` |
| 🔶 | Shape **đọc từ engine** (call-site), chưa gửi thật |
| ❓ | Chỉ biết mục đích, **shape chưa xác minh** |

Response: envelope `S2C_RESULT{data,error}`; `error` rỗng = OK, ngược lại là chuỗi `ecode.<n>`
(xem `nta_agent/data/config/ecode.json`). Các field response ghi khi đã biết.

---

## 1. Session / entry
| Endpoint | Trạng thái | Request | Ghi chú |
|---|---|---|---|
| `HD_Entry` | ❓ | — | Vào game, trả snapshot `player` đầy đủ (mainCityIndex, builds, resources, injuryPawns, curingQueues, fortAutoSupports, armyDists…). |
| `HD_Spectate` | ❓ | `{index}` | Xem 1 ô/thành. |
| `HD_SettleGame` | ❓ | — | Kết toán ván (mùa). |
| `HD_SyncCellInfo` | ❓ | — | Đồng bộ thông tin ô. |
| `HD_WatchArea` / `HD_UnsubscribeChunk` | ❓ | — | Đăng ký/huỷ nhận cập nhật vùng/chunk. |

## 2. Đọc map / lãnh thổ
| Endpoint | Trạng thái | Request | Ghi chú |
|---|---|---|---|
| `HD_GetAreaInfo` | ✅ | `{index, noRecord:bool}` | 1 ô: owner, cityId, landId, hp, armys[].pawns. `actions.get_area`. |
| `HD_GetMapChunk` | ✅ | `{chunkId}` | Chunk nén `cells: map<uid, PlayerCellBytesInfo{indexs1,indexs2,cities}>`. chunk=100², chunkId=cy*6+cx. `actions.get_map_chunk`. Decode ở `execution/mapchunk.py`. |
| `HD_GetMarchs` | ✅ | `{}` | Danh sách hành quân thế giới `{list:[MarchInfo]}` (engine vẽ cả march của người chơi khác: `owner`, `startIndex`, `targetIndex`, `targetUid`, `targetIsCity`, `surplusTime`). `actions.get_marches`; `AlertService` poll để cảnh báo quân địch đang tới. |
| `HD_GetSelectArmys` | ✅ | `{index, type}` | Đạo quân có thể điều từ `index`. `actions.get_select_armys`. |
| `HD_GetPlayerArmys` | ✅ | `{}` | Mọi đạo quân + pawns. `actions.get_player_armys`. **Verify live 2026-09-17:** army `{uid,name,index,state,marchSpeed,pawns}`; pawn `{uid,id,lv,attackSpeed,equip, hp}` với **`hp` = map `{0:cur, 1:max}`** (không phải list/curHp). Đội đứng ở thành → `index`=mainCityIndex. |
| `HD_GetTondenDist` | ❓ | — | Cự ly/thông tin đồn điền (Tonden). |
| `HD_GetAvoidWarDist` / `HD_GetBattleDist` | ❓ | — | Cự ly né chiến / cự ly đánh. |
| `HD_MapMarkPoint` / `HD_RemoveMapMark` | ❓ | — | Đánh dấu điểm trên map. |
| `HD_GetFallMainCityIndexs` | ❓ | — | Vị trí thành chính có thể hạ. |
| `HD_GetWorldEvent` / `HD_GetWorldRandomInfo` / `HD_GetTransits` | ❓ | — | Sự kiện thế giới / info ngẫu nhiên / trung chuyển. |
| `HD_GetPlayerLandCountByUids` / `HD_GetPlayerRankList` / `HD_GetPlayerScoreList` | ❓ | — | Bảng xếp hạng / số ô người chơi. |

## 3. Chiến đấu / hành quân
| Endpoint | Trạng thái | Request | Ghi chú |
|---|---|---|---|
| `HD_OccupyCell` | ✅ | `{indexs:[int], uids:[str], target, autoBackType, isSameSpeed:bool}` | March chiếm/đánh ô. `actions.occupy_cell`. Server chỉ cho đánh ô **kề** ô đang sở hữu. |
| `HD_MoveCellArmy` | ❓ | — | Di chuyển đạo quân giữa ô (→ dùng để đưa quân vào **Cứ Điểm hồi máu**). |
| `HD_LeaveArea` | 🔶 | `{index}` | Rút quân khỏi ô. |
| `HD_CancelMarch` | ❓ | — | Huỷ hành quân. |
| `HD_MoveAreaPawns` | ✅ | `{index, armyUid, pawns:[{uid,point{x,y}}]}` | Đặt vị trí pawn trong đội hình (thứ tự tank). `actions.move_area_pawns`. |
| `HD_ExchangePawnArmy` | ✅ | `{index, armyUid1, uid1, armyUid2, uid2}` | Đổi chỗ 2 pawn (trong/giữa đội). `actions.exchange_pawn_army`. Engine (bản mô phỏng server trong client): 2 đội **cùng ô** (bất kỳ ô của mình), ô **không đang có trận** (500036); lính mới vào đúng vị trí lính cũ. Tráo **ngoài thành** chưa kiểm live (buffer leveling). |
| `HD_SetArmySpeed` | ❓ | — | Đặt tốc độ hành quân (isSameSpeed). |
| `HD_ForceRevokeArmy` | ❓ | — | Ép thu hồi đạo quân. |
| `HD_SendCellEmoji` / `HD_BattlePlayBack` | ❓ | — | Emoji ô / phát lại trận. |
| `HD_GetBattleRecordsList` | ✅ | `{}` | Danh sách chiến báo đã lưu → `{list:[{uid,index,beginTime,endTime,...}]}`. `actions.get_battle_records_list`. |
| `HD_GetBattleRecord` | ✅ | `{uid}` | 1 chiến báo đầy đủ (frames setup + randSeed) để replay từng lượt. `actions.get_battle_record`; xem `tools/re/fetch_battle_record.py` + `tools/battlesim/replay-log.js`. |

## 4. Tonden (đồn điền — sản lượng từ ô đã chiếm)
Army có state `TONDEN` (屯田): trú trên ô để **sản xuất tài nguyên**. `getArmyTondenInfo(index,uid)`.
> ⚠️ **Chưa xác minh cơ chế đầy đủ** — cần verify live (điều kiện, sản lượng, cách thu).

| Endpoint | Trạng thái | Request | Ghi chú |
|---|---|---|---|
| `HD_CellTonden` | 🔶 | `{index, uid, target}` | Điều đội (`index`/`uid` = ô+uid đội) đồn điền ô `target`. Chặn bởi `getCellTondenCount()` (limit **policy-driven** `CELL_TONDEN`) → `CELL_TONDEN_LIMIT`. |
| `HD_CancelCellTonden` | 🔶 | `{index}` | Dừng đồn điền tại ô. |
| `HD_GetTondenDist` | 🔶 | `{}` | Thông tin/cự ly đồn điền. |

> `tonden_time` (landAttr per ô) giảm theo policy `CELL_TONDEN_CD`; `getArmyTondenInfo(index,uid)` =
> trạng thái đồn điền của đội. **Sản lượng = TREASURES** (rương): xong `tonden_time` → notify
> `UPDATE_TONDEN`/panel `TondenEnd(treasures)` → thu bằng hệ thống rương sẵn có (`ClaimTreasures`).
> Tức Tonden = đỗ quân trên ô theo thời gian lấy rương, **KHÔNG chiến đấu** (không thương vong) — đánh đổi
> với occupy (nhanh hơn nhưng có thương vong). Thời gian/sản lượng cụ thể cần thí nghiệm live (có chờ).

## 5. Rương (treasure — loot từ chiếm ô)
| Endpoint | Trạng thái | Request | Ghi chú |
|---|---|---|---|
| `HD_OpenArmyTreasure` | ✅ | `{index, auid}` | Mở rương của 1 đạo quân. `actions.open_army_treasure`. |
| `HD_ClaimArmyTreasure` | ✅ | `{index, auid}` | Nhận rương đã mở. `actions.claim_army_treasure`. |
| `HD_OpenArmysTreasure` | ✅ | `{targets:[{index,auid}]}` | Mở hàng loạt. `actions.open_armys_treasure`. |
| `HD_ClaimArmysTreasure` | ✅ | `{targets:[{index,auid}]}` | Nhận hàng loạt. `actions.claim_armys_treasure`. |
| `HD_OpenTreasure` / `HD_ClaimTreasure` | ❓ | — | Rương chung (không theo army). |

Mô hình chi phí rương/loot: `execution/treasure_model.py`, cơ chế: [treasure-mechanic.md](treasure-mechanic.md).

## 6. Hồi sinh lính chết (cure/revive — tốn SLOT)
> Đây là **hồi sinh lính CHẾT** (`deadTime`), **không phải** hồi máu lính bị thương.
> Hồi máu lính bị thương = **tự động server-side khi trú Cứ Điểm** (giới hạn `maxArmyCount`≈5 đội/ô,
> lượng hồi không giới hạn) — **không có endpoint client**. State: `injuryPawns[]`, `curingQueues[]`.

| Endpoint | Trạng thái | Request | Ghi chú |
|---|---|---|---|
| `HD_CureInjuryPawn` | 🔶 | `{index, armyUid, armyName, pawnUid}` | Hồi sinh 1 pawn chết. Vào `curingQueues` (có slot). |
| `HD_CancelCurePawn` | 🔶 | `{index, uid}` | Huỷ 1 lượt hồi sinh. |
| `HD_GiveupInjuryPawn` | ❓ | — | Bỏ hẳn lính (không hồi sinh). |
| `HD_SpeedUpCuringPawn` | ❓ | — | Tăng tốc hồi sinh (tốn tài nguyên/vật phẩm). |

## 7. Xây dựng / thành / output
| Endpoint | Trạng thái | Request | Ghi chú |
|---|---|---|---|
| `HD_ClaimCityOutput` | ✅ | `{index}` | Thu sản lượng thành. `actions.collect_city_output`. |
| `HD_AddAreaBuild` | ✅ | `{index, id}` | Xây công trình **trong thành** (type 1). `actions.add_build`. **Từ chối Cứ Điểm bằng ecode.500009** ("Kiến trúc không tồn tại"). |
| `HD_CreateCity` | ✅ | `{index, id}` | Tạo **thành/Cứ Điểm** (fort, build 2102, `ui=BuildCity`, type 2) tại ô sở hữu. `actions.create_city`; lệnh `build_fort` dùng cái này (KHÔNG phải AddAreaBuild). |
| `HD_UpAreaBuild` | ✅ | `{index, uid?}` | Nâng cấp công trình. `actions.upgrade_build`. |
| `HD_MoveAreaBuild` | ❓ | — | Di dời công trình. |
| `HD_CancelBT` / `HD_InDoneBt` | ❓ | — | Huỷ / hoàn tất tức thì hàng đợi xây (BuildTask). |
| `HD_GetBTCityQueues` | ✅ | `{}` → `{btCityQueues:[{index,id,needTime,surplusTime}]}` (ms) | Công trình kiểu thành **đang xây** (Cứ Điểm 2102). `actions.get_bt_city_queues`; FortService ghi `forts.json.building`. `HD_CreateCity` lên ô đang xây → ecode.500041 "Đang xây". |
| `HD_BuyAddOutput` | ❓ | — | Mua tăng sản lượng. |
| `HD_ReCreateMainCity` | ✅ | `{lang}` | **Tái lập thành chính sau khi bị chiếm** (verify live 2026-09-23): server tự chọn vị trí mới, trả `{playerInfo}` → bắt đầu lại (landCount=4 khối 2×2, 3 công trình lv1, tài nguyên 700, binh chủng về ô mở khoá đầu). Lỗi `NOT_CITY_INDEX` có thể xảy ra. QUYẾT ĐỊNH CỦA NGƯỜI CHƠI. |
| `HD_GetFallMainCityIndexs` | ❓ | `{}` | `{fallMainCityIndexs}` — các thành chính đã rơi (engine vẽ đổ nát). |
| `HD_DismantleCity` | ❓ | — | Phá thành. |
| `HD_ChangeCitySkin` / `HD_GetCitySkins` | ❓ | — | Skin thành. |

## 8. Pawn / army (tuyển, quản lý)
| Endpoint | Trạng thái | Request | Ghi chú |
|---|---|---|---|
| `HD_DrillPawn` | ✅ | `{index, buildUid, id, armyUid, armyName}` | Tuyển lính. `armyUid` rỗng + `armyName` → tạo đội mới. `actions.drill_pawn`. |
| `HD_ChangeConfigPawnEquip` | ✅ | `{id, equipUid, skinId, attackSpeed}` | Gắn trang bị cho pawn config. `actions.change_pawn_equip`. |
| `HD_CancelDrillPawn` / `HD_DismissPawn` / `HD_DismissArmy` | ❓ | — | Huỷ tuyển / giải tán lính / giải tán đội. |
| `HD_ChangePawnArmy` / `HD_CheckArmyName` | ❓ | — | Chuyển đội / kiểm tên (client validate). |
| `HD_ModifyAmryName` | ✅ | `{index, armyUid, name}` | Đổi tên đội (tên ≤ 12 ký tự, không newline — client chặn). `actions.rename_army`; chat tool đổi tên qua hàng đợi lệnh. |
| `HD_ChangePawnAttr` / `HD_ChangePawnPortrayal` / `HD_UsePawnSkin` | ❓ | — | Đổi thuộc tính / hoạ tượng / skin pawn. |
| `HD_PawnLving` | 🔶 | `{index, auid, puid}` | **Nâng PHỔ THÔNG** = tốn **sách exp (exp_book)**, có **hàng đợi/thời gian** (`pawnLvingQueues`), **KHÓA đội** (state LVING, không điều động). Reply: `queues`+`army`. |
| `HD_UseUpScrollUpPawnLv` | 🔶 | `{index, armyUid, uid}` | **Nâng TRỰC TIẾP** = tốn **quyển trục (up_scroll)**, **tức thì**, KHÔNG khóa đội / không chờ. |
| `HD_CancelPawnLving` | ❓ | — | Huỷ nâng phổ thông đang trong hàng đợi. |
| `HD_GetPawnDeadLvMap` | ❓ | — | Map cấp-khi-chết. |

## 9. Ceri (mở khoá binh chủng/policy/equip — người chơi quyết)
| Endpoint | Trạng thái | Request | Ghi chú |
|---|---|---|---|
| `HD_StudySelect` | ✅ | `{lv, id, tp}` | Chọn option ceri. `tp`: 1=policy,2=pawn,3=equip → cập nhật `{policy,pawn,equip}Slots`. `actions.study_select`. |
| `HD_CeriResetSelect` | ✅ | `{lv, tp}` | Reroll option (tốn vàng). Reply có `selectIds`/`resetCount`. `actions.ceri_reset`. |

## 10. Trang bị / rèn
| Endpoint | Trạng thái | Request | Ghi chú |
|---|---|---|---|
| `HD_ForgeEquip` | 🔶 | `{uid}` | Rèn/recast trang bị → attrs ngẫu nhiên mới; tốn **sắt** (`forgeCost`) trừ khi có lượt **free (CHỈ từ policy** `FREE_RECAST_COUNT`, `getfreeForgeSurplusCount`). Reply: `equip`(attrs mới), `iron`, `nextForgeFree`, `recastCount`. |
| `HD_RestoreForge` | 🔶 | `{uid}` | Hoàn lại attr trước (giữ bản tốt hơn sau recast tệ). Reply: `iron`, `equip`. |
| `HD_LockEquipEffect` | 🔶 | `{uid, effect}` | Khoá 1 dòng hiệu ứng (**loại** hiệu ứng) của món **chuyên dụng**; không khoá lúc đang rèn. Rèn lại có khoá giữ nguyên dòng đó (giá trị+tỉ lệ) và tốn thêm 1 **fixator**/lần. |
| `HD_GetWorldRandomInfo` | ✅ | `{}` → `{exclusiveMap{equipId:{arr:[effectType]}}, pawnCostMap}` | Danh sách hiệu ứng random của món chuyên dụng **theo từng trận** (không phải `equipBase.effect`). `actions.get_world_random_info`. |
| `HD_SmeltingEquip` | 🔶 | `{mainUid, viceIds:[equipId]}` → `{currSmeltEquip, fixator}` | Dung luyện: món chính chuyên dụng giữ mọi thuộc tính + thêm hiệu ứng món phụ (tối đa 2 ô, Tiệm Rèn Lv14/20); xong qua notify 64 SMELT_EQUIP_RET. Chỉ chạy khi người chơi xác nhận trên dashboard. |
| `HD_RestoreSmeltEquip` | 🔶 | `{uid}` | Khôi phục món chuyên dụng về trước khi dung luyện. Chỉ khi người chơi xác nhận. |
| `HD_InDoneForge` | ❓ | `{}` | Hoàn tất rèn tức thì. |
| `HD_SmeltingEquip` / `HD_RestoreSmeltEquip` | ❓ | — | Nung/hoàn nung trang bị. |

## 11. Nhiệm vụ
| Endpoint | Trạng thái | Request |
|---|---|---|
| `HD_ClaimTaskReward` | ✅ | `{id}` |
| `HD_ClaimOtherTaskReward` | ✅ | `{id, treasureIndex, selectIndex}` |
| `HD_ClaimTodayTaskReward` | ✅ | `{id, treasureIndex, selectIndex}` |

## 12. Bazaar / giao thương
`HD_BazaarBuyRes`, `HD_BazaarSellRes`, `HD_BazaarSellToSys`, `HD_BazaarCancelSell`,
`HD_BazaarGiveRes`, `HD_GetBazaarRecords`, `HD_GetTradingRess` — ❓ mua/bán/tặng tài nguyên. Shape TODO.

## 13. Liên minh (alliance)
Nhóm lớn (~30 endpoint) — chưa cần cho agent giai đoạn này. `HD_CreateAlliance`, `HD_GetAlliance(s)`,
`HD_ApplyJoinAlliance`, `HD_AgreeJoinAlliance`, `HD_ExitAlliance`, `HD_KickoutAlliance`,
`HD_ChangeAlliMemberJob`, `HD_VoteAlliLeader`, `HD_AlliLeaderConfirm`, `HD_AlliMapFlag`,
`HD_AlliSelectPolicy`, `HD_*AlliChatChannel`, `HD_GetAlli*` (logs/rank/battle records)… — ❓ Shape TODO.

## 14. Kinh đô cổ / prison / hero
`HD_AncientContribute`, `HD_GetAncientInfo`, `HD_GetAncientDonateAcc`, `HD_GetAncientLogs`,
`HD_GetPrisonHeroes`, `HD_ReleasePrisonHero`, `HD_WorshipHero` — ❓ Shape TODO.

## 15. Chat / mail
`HD_SendChat`, `HD_GetChats`, `HD_AddPChat`, `HD_RemovePChat`, `HD_AreaSendChat`, `HD_SendMail` — ❓.

## 16. Anti-cheat (captcha)
| Endpoint | Trạng thái | Request | Ghi chú |
|---|---|---|---|
| `HD_GetAntiCheatQuestion` | ✅ | `{}` | Lấy captcha. `actions.get_anticheat_question`. |
| `HD_AntiCheatAnswer` | ✅ | `{answer}` | Trả lời. `actions.answer_anticheat`. |

> Ecode anti-cheat làm `RuleEngine.tick` raise `CaptchaRequired` → dừng loop chờ người.

---

## Phụ lục — 134 endpoint (đã liệt kê từ engine 2026-09-17)
Nguồn: `grep game/HD_ tools/re/decrypted/index.js`. Cập nhật khi engine đổi version.

AddAreaBuild, AddPChat, AgreeJoinAlliance, AlliLeaderConfirm, AlliMapFlag, AlliSelectPolicy,
AncientContribute, AntiCheatAnswer, ApplyJoinAlliance, AreaSendChat, BattlePlayBack, BazaarBuyRes,
BazaarCancelSell, BazaarGiveRes, BazaarSellRes, BazaarSellToSys, BuyAddOutput, CancelBT,
CancelCellTonden, CancelCurePawn, CancelDrillPawn, CancelJoinAlliance, CancelMarch, CancelPawnLving,
CellTonden, CeriResetSelect, ChangeAlliApplyDesc, ChangeAlliMemberJob, ChangeAllianceNotice,
ChangeCitySkin, ChangeConfigPawnEquip, ChangePawnArmy, ChangePawnAttr, ChangePawnPortrayal,
CheckArmyName, ClaimArmyTreasure, ClaimArmysTreasure, ClaimCityOutput, ClaimOtherTaskReward,
ClaimTaskReward, ClaimTodayTaskReward, ClaimTreasure, CreateAlliChatChannel, CreateAlliance,
CreateCity, CureInjuryPawn, DelAlliChatChannel, DelAlliMapFlag, DismantleCity, DismissArmy,
DismissPawn, DrillPawn, Entry, ExchangePawnArmy, ExitAlliance, ForceRevokeArmy, ForgeEquip,
GetAllAlliBaseInfo, GetAlliBattleRecord, GetAlliLogs, GetAlliMemberBattleRecord, GetAlliRankList,
GetAlliance, GetAlliances, GetAncientDonateAcc, GetAncientInfo, GetAncientLogs, GetAntiCheatQuestion,
GetAreaInfo, GetArmyRecords, GetArmyRecordsByUids, GetAvoidWarDist, GetBTCityQueues, GetBattleDist,
GetBattleRecord, GetBattleRecordsList, GetBazaarRecords, GetChats, GetCitySkins,
GetFallMainCityIndexs, GetMapChunk, GetMarchs, GetPawnDeadLvMap, GetPlayerArmys,
GetPlayerLandCountByUids, GetPlayerRankList, GetPlayerScoreList, GetPrisonHeroes, GetSelectArmys,
GetTondenDist, GetTradingRess, GetTransits, GetWorldEvent, GetWorldRandomInfo, GiveupInjuryPawn,
InDoneBt, InDoneForge, KickoutAlliance, LeaveArea, LockEquipEffect, MapMarkPoint, ModifyAmryName,
MoveAreaBuild, MoveAreaPawns, MoveCellArmy, OccupyCell, OpenArmyTreasure, OpenArmysTreasure,
OpenTreasure, PawnLving, ReCreateMainCity, ReleasePrisonHero, RemoveMapMark, RemovePChat,
RestoreForge, RestoreSmeltEquip, SendCellEmoji, SendChat, SendMail, SetArmySpeed, SettleGame,
SmeltingEquip, Spectate, SpeedUpCuringPawn, StudySelect, SyncCellInfo, UnsubscribeChunk,
UpAreaBuild, UpdateAlliChatChannel, UsePawnSkin, UseUpScrollUpPawnLv, VoteAlliLeader, WatchArea,
WorshipHero.


## World notify `GAME_ONUPDATEWORLDINFO_NOTIFY` (push, verify RE 2026-09-23)

`{list:[OnUpdateWorldInfoNotify{type, data_<type>}]}` — `NotifyType` dùng CHUNG số với notify player
(BT_QUEUE=6…), nên `session.sync` định tuyến world riêng (`store.apply_world_notify`), không qua
`apply_player_update`. Đang xử lý: `ADD_MARCH=13` (data_13 MarchInfo) / `REMOVE_MARCH=14` →
`state.world_marches`; **`CAPTURE=29`** (data_29 `{uid, time, attacker, index, landCount}`) — nếu
`uid`=mình → `player.captureInfo={uid: attacker, time}` (giống engine `setCaptureInfo`) → Agent vào chế độ an toàn.
