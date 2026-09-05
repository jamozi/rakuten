# 既存記事の段階公開

`verified-incremental` は既存記事の一部と、明示した共通変更だけを扱う公開方式です。
通常 API リンクの `standard-api` を指定し、計測は OFF のままにします。
方式未指定の従来呼び出しは全件公開のままです。自動切替はありません。

## 対象と証跡

- 既存記事 ID・slug・URL を維持します。新規投稿・固定ページは作成しません。
- 比較に残す商品と、写真・購入リンクを掲載する商品は別集合です。
  未確認の商用要素はブロックごと除外し、理由を manifest に残します。
  写真の空枠やメーカーリンクへの購入ボタン代替は使いません。
- 購入リンクがない記事の収益機能は `NOT_INCLUDED` です。検証済みの件数へ
  加算しません。同一商品の API URL を複数箇所に使うことはできます。
- 本文・公式出典・対象商品・掲載位置・共通成果物の正確な集合とハッシュを、
  生成、監査、提案、再開、適用、本番照合で再検証します。

公式情報は実際に再取得して locator と本文を照合します。日付やハッシュだけを
更新して確認済みにはしません。楽天の資格情報、API 応答、画像、公開バックアップは
保存済み checkout `/home/minami/rakuten` の private 保存先に置きます。
実行するコードと商品契約は現在の作業 checkout を使い、秘密情報をコピーしません。

## 準備とローカル確認

1. bounded WordPress MCP から実際の公開内容を取得します。
   `scripts/raos_wordpress_incremental_snapshot.py` は固定の既存14ページを対象とし、
   公開日時・分類は公開 REST 応答との照合結果も区別して保存します。
2. `scripts/raos_wordpress_incremental_preview.py` で改稿対象を明示します。
   `--articles`、`--update-policies`、`--home-mode` を省略しません。
   未選択の記事は MCP の保存内容を使い、共通テーマを旧稿でも確認します。
   ホームの保存本文を取得したことと、表示中の共通テンプレートを検査したことは別です。
3. ローカル起動・同期・表示検査を実施します。環境には
   `RAOS_WORDPRESS_PUBLICATION_PROFILE=verified-incremental`、
   `RAOS_WORDPRESS_LINK_MODE=standard-api` と、生成された正確な
   `RAOS_WORDPRESS_PREVIEW_FIXTURE_ROOT` を渡します。
4. 130画面、キーボード、200%ズーム、画像・リンク、SEO、計測 OFF、axe、
   3回以上のモバイル性能を確認します。正式なローカル検査レポートは
   `output/playwright/local-preview.audit.v1.json` に出ます。前回の成功を
   今回の実行結果として使わず、入力・画面・測定結果のハッシュを再検証します。
5. `make generate`、`make check`、focused tests、`make fast`、`make final` と
   テーマ／プラグイン検査を通します。バックアップは実際にローカル復元して照合します。

## 監査対象と短命の公開証跡を分ける

`scripts/raos_wordpress_incremental_candidate.py` の現在の準備経路は、商用要素を
除いた候補を作成します。この候補を作っただけでは監査・収益検証・公開は未完了です。

候補 manifest は同じ成果物を2巡監査するための不変の対象です。有効期間は最長24時間、
かつ選定出典の最短有効期限までです。これは公開権限や15分の反映用証跡ではありません。
実装担当とは別の Codex による実際の監査を2巡行い、修正があれば影響する検査と監査を
やり直します。過去の検査出力を点検したことと、その場で検査を再実行したことを区別します。

実読者調査は未実施の後日確認項目です。Codex による評価で代用しません。
連絡先の所有者確認と実送受信試験も区別します。監査報告の詳細な形式は
[監査インターフェース](../verified-incremental-audit-v1.md) を参照してください。

公開直前は、現在の出典・商品・成果物・ローカル検査・本番保存内容を再検証したうえで、
最長15分の activation を作ります。商品／出典は24時間の期限を維持し、最短の期限を
採用します。再開で期限を自動延長しません。失効した対象に新しい適用を行いません。

## 提案、所有者承認、照合

実行入口は `scripts/raos_wordpress_publication_request.py` です。
`--publication-profile verified-incremental`、`--link-mode standard-api`、
`--quality-audit-mode codex-owner`、正確な private candidate と preview fixture、
実装 execution ID、明示した `--incremental-stage propose|apply|readback` を使います。
全件公開用の証跡を混ぜたり、別方式へ戻したりしません。

ローカル検査と必須 CI 合格後のコードから提案を作り、対象ハッシュを所有者へ示します。
本番連携プラグイン初回更新は既存の wp-admin 手順で所有者が実施します。
所有者の具体的な wp-admin 承認と単回リースがなければ適用しません。
Codex の監査結果や会話上の包括的な依頼を、この承認の代わりにはしません。

通信断時は既存 operation の状態を確認します。`operation-status` は指定1件の状態を
取得し、公開・適用・復旧・後処理を起動しません。ただし既存サーバーの期限整合処理で
失効状態と失効リースが更新される場合があります。無条件の再送は行いません。

適用後は対象本文・URL・SEO・画像・リンク・テーマを照合し、未更新ページと対象外の
公開内容が維持されたことも確認します。本番照合が成功した batch だけを公開済みとし、
改善中・保留・収益機能未導入の範囲を分けて報告します。PR のマージやローカル成功を
本番公開と呼びません。収益、検索順位、実読者評価、法令適合そのものは保証しません。
