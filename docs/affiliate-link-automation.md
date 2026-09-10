# アフィリエイトリンクの取得から記事更新候補まで

`tools.affiliate_ingestion automate`は、設定済みの公式API・feed・公式広告コードのローカル入力を取得し、
指定商品の型番・構成・JAN・リンク先を照合して、既存記事の購入導線を更新する。
6社共通の取得機構を使う。各社の専用APIが設定済みという意味ではない。
初期状態は無効で、取得権限や実値を補完しない。

## 実行する操作

通常はCodexが以下を担当する。利用者がGitやJSONを毎回編集する必要はない。

1. 登録済みサイトと提携広告主、素材の利用条件、選定済み商品を確認して所有者専用planを作る。
2. `--dry-run`で接続設定・対象記事の登録・入力条件を確認する。DNS・HTTP・書込みを行わない。
3. `automate`で公式ファイルを読み、更新候補、記事ごとの差分、HTMLを生成する。
   公式API/feedを取得する場合のみ`--fetch`を付ける。
4. `--write-drafts`を付けると、検証済みの候補をローカルの記事sourceへ反映する。
5. 既存の`direct prepare`と`direct preview`でWordPress表示を確認する。
6. 対象を指定した公開指示があれば、既存の`direct publish`で反映・照合する。

```sh
# 初回のみ。既存設定は上書きしない
.venv/bin/python -m tools.affiliate_ingestion init-config

# planと出力は所有者専用領域。planは0600、出力directoryは0700
.venv/bin/python -m tools.affiliate_ingestion automate \
  --plan ~/.config/raos/affiliate-links.json \
  --output ~/.local/share/raos/affiliate-links --dry-run

# API利用権限と接続先を確認した後の実取得 + ローカル記事更新
.venv/bin/python -m tools.affiliate_ingestion automate \
  --plan ~/.config/raos/affiliate-links.json \
  --output ~/.local/share/raos/affiliate-links --fetch --write-drafts

# 出力のarticle_keysを使う。別worktreeでは既存の認証保管先を指定する
make wordpress-production-request ARGS='direct --owner-checkout /home/minami/rakuten prepare --articles <article-key>'
make wordpress-production-request ARGS='direct --owner-checkout /home/minami/rakuten preview --candidate <candidate-id>'
```

`automate`が表示するIDはリンク更新候補のID。`direct prepare`が表示するWordPress公開候補のIDとは別。
`--dry-run`は設定検証だけで、実接続・広告の存在・商品一致の確認完了を意味しない。
定期実行の登録や自動公開はこのコマンドに含めない。

## リンクシェアの初回接続

[公式のAPI案内](https://www.linkshare.ne.jp/tool/api/)で確認した手順（2026-09-10）は、
[APIディベロッパーポータル](https://developers.linkshare.ne.jp/)へ、
アフィリエイト管理画面と同じメールアドレス・パスワードでログインし、アクセストークンを取得する流れ。
所有者は自身のブラウザでログインする。パスワードやトークンをチャット・Git・記事へ貼り付けない。

ログイン後はCodexが公式の利用ガイドと利用できるAPIを照合して接続設定を作る。
秘密値は既存の`register`の非表示入力で所有者専用設定へ保存するか、所有者の環境変数を参照する。
この時点で広告主検索・リンクロケーターによる対象サイトの提携確認、商品検索の実フィールド対応、
トークンの有効期間と更新方法を確認する。実応答を未確認のまま、URLや商品識別子を埋めない。
最初の1社・1商品・1記事で実取得と表示が確認できてから、対象を増やす。

## 所有者専用plan

[無効な初期template](../config/affiliate-link-automation.example.json)を使い、実値はリポジトリ外に保存する。
以下はすべて合成例。日時を現在時刻へ機械的に書き換えて確認済みとする運用は行わない。

```json
{
  "schema": "RAOSAffiliateAutomationPlanV1",
  "enabled": true,
  "site_url": "https://reader.example",
  "grants": [{
    "provider": "linkshare",
    "advertiser_id": "merchant-a",
    "site_url": "https://reader.example",
    "approved": true,
    "checked_at": "2026-09-10T00:00:00Z",
    "expires_at": "2026-09-11T00:00:00Z",
    "evidence_ref": "owner-confirmed-partnership",
    "format": "url",
    "allowed_hosts": ["tracking.example"]
  }],
  "placements": [{
    "slot_id": "guide-product-a",
    "article_key": "guide",
    "product_ref": "product-a",
    "anchor_id": "model-a",
    "editorial_eligible": true,
    "article_type": "shortlist",
    "provider": "linkshare",
    "resource": "products",
    "offer_id": "offer-a",
    "identity": {"model": "MODEL-A", "variant": "standard", "jan": "1234567890128"},
    "landing_url": "https://maker.example/product/a"
  }]
}
```

`grants`は広告主別・サイト別の提携と素材利用条件を確認した記録。ASP登録承認とは別で、
取得先の本文をそのままこの設定として実行しない。確認から24時間超、未来の確認時刻、
期限切れ、別サイト、重複する提携記録では処理を止める。
この版は提携状態をAPIから自動更新しないため、実運用ではCodexが公式の提携状態を確認してから更新する。

`format=url`はURL単体の利用・任意のボタン文言が許可された広告だけに使う。
`format=html`は公式コードをそのまま保持する。改変しないことと、安全なコードであることの両方を検証する。
許可するHTMLは単一のa要素とimg、span、strong、em、br。script、iframe、イベント属性、
任意style、未知の属性や送信先は受け入れない。許容範囲外の正当な公式素材も自動採用せず、対応方法を確認する。

`editorial_eligible`は既存の編集判断から設定する。ASPの料率・価格・楽天取扱有無から導かない。
`status_check`の記事への購入導線追加は既存の表示ルールに従い拒否する。
販売リンクを掲載しない旨の既存表示がある記事は、その編集方針を確認してから更新する。

## 取得レコードの接続

既存の`affiliate-networks.json`で有効化した`products`、`links`、`creatives`だけを使う。
`reports`は記事入力として拒否する。fileモードでもaccount_idは所有者の登録識別として必要だが、
リモート認証値は不要。接続URL・秘密値は既存の秘密管理経路で設定する。

各入力レコードは次の値へ対応付ける。返された商品ページを広告URLとして推測しない。

| フィールド | 内容 |
| --- | --- |
| `offer_id`, `advertiser_id` | 素材ID、広告主ID。planの対象と完全一致 |
| `site_url` | 公式素材を取得した掲載サイト。plan・提携確認のサイトとの完全一致が必須 |
| `model`, `variant`, `jan` | 型番、構成、JAN。model・variantは必須。取得素材にJANがあれば、確認済みの期待値と照合する |
| `status` | この版が採用する値は`active`。不明・終了・その他は採用しない |
| `landing_url` | 商品遷移先。選定した商品の確認済みURLとの完全一致が必要 |
| `affiliate_url` | 公式の広告URL。HTTPS、許可host、認証埋め込みなしを検証 |
| `html` | 公式素材を保持する場合のHTML。aのhrefがaffiliate_urlと一致することを検証 |

resourceに`link_fields`を指定すると、実レスポンスのフィールドへ明示的に対応付けられる。
例えば`{"offer_id":"creative.id","model":"modelCode"}`。ドット区切りでobjectの子要素を選択できる。
未指定の値は上表と同名のキーから取得する。存在しないフィールドから値を補完しない。
APIが掲載サイトをレコードに返さない場合は、認証先SIDと対象サイトの対応を確認した取得処理が別途必要。
複数サイトの素材が混ざったexportへ、一律のサイト名を付けて使うことはしない。
ASPが独自のstatus値を返す場合、契約を確認した正規化が別途必要。都合よくactiveへ置換しない。
任意のraw、Finance、秘密値は記事・候補・差分へコピーせず、必要フィールドのみ取り出す。

## 記事への挿入

記事はowner-directの`articles.v1.json`に登録し、通常sourceの`articles/`内に置く。
この版は`body_source`のHTML記事に対応する。現行の既存記事には`patch_source`で、
本番本文を読み直してから限定差分を適用するものがある。これらは`PATCH_ARTICLE_REQUIRES_LIVE_BASELINE`で停止する。
古いHTMLで置き換えず、初回接続時に最新本文を取得し、この方式へ広告候補を渡す接続を追加する必要がある。
既存記事の初回取り込みには`direct import-existing`がある。生成fixtureを直接書き換えない。
対象は、anchor_idのid属性とproduct_refのdata-raos-product-id属性を持つ、単一のarticle/section/div要素。

```html
<!-- wp:html -->
<section id="model-a" data-raos-product-id="product-a">
  <h2>対象商品の説明</h2>
  <p>本文と出典リンクは保持される。</p>
</section>
<!-- /wp:html -->
```

対象要素の末尾に広告・PR表記と専用slotを追加する。再実行時はそのslotだけを更新する。
対象がない・複数ある・商品IDが違う場合、別の場所へ勝手に挿入しない。
全placementの取得・照合が成功するまで記事は変更しない。
ローカル反映直前にも元本文を照合し、他の編集が検出された場合は上書きしない。

## 検証の境界

```sh
.venv/bin/python -m pytest -q tests/test_affiliate_link_automation.py tests/test_affiliate_ingestion.py
make fast
```

合成の6社入力、API応答のフィールド対応、広告素材保持、商品・提携・期限の不一致、
通信失敗、空結果、ページ上限、再実行、対象外パス、symlink、秘密値の出力抑止を検証する。
これらは実ASP接続・広告主提携・実商品リンク取得・本番公開の証拠ではない。
