# 楽天owner-local診断の復旧（2026-09-13）

認証directoryの許可inventoryはcredentials.v1.json・results・diagnostics。追加されていたrequestsが診断を止めていた。ファイル内容を取得せず、使用中FD/cwdが0件であることを確認し、3ファイルを/home/minami/rakuten/.secrets/rakuten-owner-requestsへrenameした。inode・size・所有者・group・modeは全て保持。削除・validator緩和・認証変更なし。

生成済み計画の固定doctorをそのまま実行し、RAKUTEN_OWNER_LOCAL_DOCTOR_READY、終了0を確認。ネットワーク商品検索の成功・credentialの将来有効性を意味しない。ST1703 verifier/launcher/Makefile/READMEの参照更新はintegration worktree内。primary sourceは変更しない。復元が必要なら新旧directoryの重複や使用状況を確認して元の場所へrenameする。
