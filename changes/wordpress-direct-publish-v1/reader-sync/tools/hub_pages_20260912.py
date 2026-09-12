#!/usr/bin/env python3
"""Static hub pages (14) + home authoring generator for the 2026-09-12 site audit fix.

Data (copy) lives in this file; output goes to changes/wordpress-direct-publish-v1/articles/.
Run from the repository root: python3 changes/wordpress-direct-publish-v1/reader-sync/tools/hub_pages_20260912.py [--check-only]
Anchor labels are read from changes/wordpress-direct-publish-v1/articles.v1.json; re-run after title changes.
"""
from __future__ import annotations

import json
import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
ART = ROOT / 'changes/wordpress-direct-publish-v1/articles'
# Live readback evidence (rendered HTML of the published articles) is optional; the audit
# artefacts live under output/ of the owner checkout, so allow an explicit override.
EVIDENCE = Path(os.environ.get('RAOS_AUDIT_EVIDENCE_HTML')
                or next((c for c in (ROOT / 'output/site-audit-20260912/evidence/html',
                                     Path('/home/minami/rakuten/output/site-audit-20260912/evidence/html'))
                         if c.is_dir()), ROOT / 'output/site-audit-20260912/evidence/html'))
RELEASE = '20260912-audit-fix'
UPLOADS = 'https://kurashinoshirube.com/wp-content/uploads/2026/09/'
HERO_IMG = 'https://kurashinoshirube.com/wp-content/themes/kurashinoshirube-child/assets/images/magazine-hero.webp'

IMG = {
    'travel': dict(url=UPLOADS + 'ks-travel-editorial-ai-20260910.webp', alt='玄関でスーツケースと衣類を揃えた旅支度のイメージ', caption='AI生成の編集イメージ。掲載商品の実物写真ではありません。'),
    'kitchen': dict(url=UPLOADS + 'ks-kitchen-editorial-ai-20260910.webp', alt='食器と小型食洗機のあるキッチンのイメージ', caption='AI生成の編集イメージ。実物写真・収納例・設置図ではありません。'),
    'cleaning': dict(url=UPLOADS + 'ks-cleaning-editorial-ai-20260910.webp', alt='木の床と家具の間にロボット掃除機を配置した暮らしのイメージ', caption='AI生成の編集イメージ。実物写真や清掃性能の検証ではありません。'),
    'preparedness': dict(url=UPLOADS + 'ks-preparedness-editorial-ai-20260910.webp', alt='ポータブル電源とランタンを並べた備えのイメージ', caption='AI生成の編集イメージ。実物写真・配線図・動作保証ではありません。'),
}

# hub h1 = articles.v1.json title (applied to post_title on publish)
HUB_TITLE = {
    'home': 'ホーム',
    'categories': '商品カテゴリから探す', 'purposes': '悩み・目的から探す', 'guides': '選び方ガイド',
    'comparisons': '比較・条件別の候補', 'updates': '最近更新したガイド',
    'travel': 'スーツケースの選び方・比較', 'kitchen': '食洗機の選び方・比較',
    'cleaning': 'ロボット掃除機の選び方・比較', 'preparedness': 'ポータブル電源の選び方・比較',
    'small-space': '一人暮らし・省スペース', 'save-housework': '家事を短くしたい',
    'without-installation': '設置工事を避けたい', 'easy-maintenance': '手入れを続けやすいものを選びたい',
    'comfortable-travel': '旅行を快適にしたい', 'prepare-outage': '防災に備えたい',
    'comparison-policy': '比較・編集方針', 'about-ad-policy': '運営・広告方針', 'privacy-policy': 'プライバシーポリシー',
}
CAT_NAME = {'travel': 'スーツケース', 'kitchen': '食洗機', 'cleaning': 'ロボット掃除機', 'preparedness': 'ポータブル電源'}
CAT_ORDER = ['travel', 'kitchen', 'cleaning', 'preparedness']

# ---------------------------------------------------------------------------
# Articles. title = h1 (articles.v1.json). modified = live dateModified in JST.
# blurbs: compare (比較軸と候補数) / category (前提条件) / guide (何が決まるか)
#         / home (1 行紹介) / update (変更点 1 文) / purposes[slug] (この記事で決まること)
# ---------------------------------------------------------------------------
NOTE_0911 = '記事冒頭の近道と記事末の案内を追加しました。'
NOTE_GUIDE_0912 = '比較記事と共通の「実機での確認状況」の記述を更新しました。'

ARTICLES = [
    dict(id=82, slug='carry-on-suitcase-under-100-seats', cat='travel', kind='compare', pr=True,
         title='100席未満の国内線向けスーツケース4モデルを機内持ち込み規定で比較',
         published='2026-08-29', modified='2026-09-11', modified_ts='2026-09-10T22:59:14Z',
         compare='幅35×奥行20×高さ45cm・3辺100cm以内を基準に、スタリアCXR・フレスターEX・パリセイズ3-Z・INTER CITYの4モデルを外寸・重量・容量・開き方で比べます。',
         category='100席未満の国内線に乗る可能性がある方向け。運航会社・便・機材の規定を先に確かめ、拡張していない状態の外寸で照合することが前提です。',
         home='小型機の持ち込み規定を基準に、4モデルの外寸・重量・容量・開き方を比べます。',
         update='記事冒頭の近道（比較表・購入前の確認）と、記事末「利用便が違うなら、比較の入口も変える」の案内を追加しました。',
         guide=('under-100-method-title', '100cmの枠を、四つの手順で読む。', '便の規定、通常時の外寸、荷物込みの重さ、容量の順に確認する手順が決まります。'),
         purposes={'comfortable-travel': '小型機に乗る予定があるなら、幅35×奥行20×高さ45cmの枠に収まる候補と、搭乗前に確認する順番が決まります。'}),
    dict(id=83, slug='lightweight-carry-on-suitcase-under-3kg', cat='travel', kind='compare', pr=True,
         title='30L以上・3kg以下の機内持ち込みスーツケース4モデルを比較',
         published='2026-08-29', modified='2026-09-11', modified_ts='2026-09-10T22:59:21Z',
         compare='30L以上・本体3kg以下の4モデル（エアロフレックスDX2・C-Lite・APPLITE 4.0・LIEVE）を、容量・素材・ストッパー・拡張時寸法・交換車輪で比べます。',
         category='荷物込みの総重量を軽くしたい方向け。100席以上の便を前提に、本体重量だけでなく詰めた後の残り重量で考えることが前提です。',
         home='30L以上・3kg以下の候補を、容量や使い方から比較します。',
         update='記事冒頭の近道（記事一覧・ほかの条件から選ぶ）と、記事末「軽さより大切な条件が見つかったら」の案内を追加しました。',
         guide=('under-3kg-method-title', '軽量モデルは、残り重量で比べる。', '対象便の確認、通常時の外寸比較、残り重量の計算という順番で、軽さの条件の読み方が決まります。'),
         purposes={'comfortable-travel': '持ち上げる重さを減らしたいなら、本体3kg以下でも荷物込みで上限内に収まるかを、残り重量の計算で確かめられます。',
                   'easy-maintenance': '車輪を自分で交換できるLIEVE 1-250を含む4モデルで、交換部品の有無を選ぶ条件に入れるかどうかが決まります。'}),
    dict(id=84, slug='front-open-carry-on-suitcase-with-stopper', cat='travel', kind='compare', pr=True,
         title='フロントオープンとキャスターストッパーを備えた機内持ち込みスーツケース4モデル比較',
         published='2026-08-29', modified='2026-09-11', modified_ts='2026-09-10T22:59:17Z',
         compare='innovator INV50・ディフェレンス05721・フレスターEX 01551・INTER CITY II 60561の4モデルを、前面構造・容量・重量・PC収納・拡張時寸法で比べます。',
         category='移動中に荷物を取り出したい、電車やバスで転がりを抑えたい方向け。取り出す物の実寸と、開けられる場所を先に決めることが前提です。',
         home='前開きの構造とキャスターストッパーを、使う場面から4モデルで比べます。',
         update='記事冒頭の近道と、記事末「開き方と、持ち運ぶ負担を比べ直す」の案内を追加しました。',
         guide=('front-open-practical-checks', '購入前に、取り出す荷物と開ける場所を確かめる', '取り出したい荷物の実寸と開閉に必要な場所から、前開きの構造をどれにするかが決まります。'),
         purposes={'comfortable-travel': '移動の途中で充電器や小物を取り出したいなら、前面収納の構造とストッパーの有無から候補が決まります。'}),
    dict(id=19, slug='carry-on-suitcase-comparison', cat='travel', kind='compare', pr=True,
         title='エースの機内持ち込みスーツケース3モデル比較｜軽さ・容量・開き方で選ぶ',
         published='2026-08-23', modified='2026-09-11', modified_ts='2026-09-10T22:59:23Z',
         compare='エースの3モデル（クレスタ06316・ディフェレンス05721・マックスパス4 01471）を、本体重量・容量・開き方の3軸で横並びにします。',
         category='エースのブランド内で決めたい方向け。100席以上の便を使い、拡張しない状態の外寸で搭乗条件を確認できることが前提です。',
         home='ブランド内で迷う方へ。クレスタ・ディフェレンス・マックスパス4の違いを整理します。',
         update='記事冒頭の近道（比較表へ・購入前の確認へ）と、記事末「まだ迷うときは、優先する条件を変えてみる」の案内を追加しました。',
         guide=('blk-suitcase-002-title', '候補を絞ったら、条件を詳しく確認', '軽さ・開き方・容量のうち、いちばん譲れない条件をどれにするかが決まります。'),
         purposes={'comfortable-travel': 'エースの3モデルで迷っているなら、軽さ・開き方・容量のうち譲れない一つを決めるだけで候補が決まります。'}),
    dict(id=262, slug='dishwasher-installation-measurement', cat='kitchen', kind='guide', pr=False,
         title='卓上食洗機の置き場所を測る順番｜本体・扉・余白を確認する',
         published='2026-09-09', modified='2026-09-12', modified_ts='2026-09-12T03:00:05Z',
         guide_blurb='置きたい場所の幅・奥行・高さ、扉を開く空間、ホースと蒸気の余白を測る順番が決まります。対象はSOLOTA・ラクアmini color・SS-MA251・NP-TSP1です。',
         home='本体が載るだけで決めず、扉を開く空間・給排水・電源の条件を確認します。',
         update=NOTE_GUIDE_0912,
         purposes={'small-space': '置きたい場所の幅・奥行・高さに加え、扉を開いたときの奥行と周囲の余白を測り、4機種のどれが収まるかが決まります。',
                   'without-installation': '本体を載せる台、排水先、電源・アースの位置を測る順番が決まり、工事の要否を確認する相手（メーカー・施工業者）が分かります。'}),
    dict(id=263, slug='dishwasher-water-supply-methods', cat='kitchen', kind='guide', pr=False,
         title='卓上食洗機の給水・排水方法｜毎回の作業から選ぶ',
         published='2026-09-09', modified='2026-09-12', modified_ts='2026-09-12T02:59:56Z',
         guide_blurb='タンク給水は毎回何リットルをどう注ぐか、排水ホースをどこへどう固定するかが機種別に分かり、毎日続けられる置き場所かが決まります。',
         home='タンク補給と排水ホースの取り回しなど、毎回の作業から考えます。',
         update=NOTE_GUIDE_0912,
         purposes={'save-housework': 'SOLOTAはタンクを外して運び、ほか3機種はカップで注ぐ。毎回の給水と排水の手間がどれだけ残るかが決まります。',
                   'without-installation': '分岐水栓を使わないタンク給水でも、排水ホースの固定位置と高さの条件は残ります。自宅の流しで使えるかが決まります。',
                   'easy-maintenance': '毎回の給水量と排水ホースの扱いを機種別に確かめ、毎日続く作業として受け入れられるかが決まります。'}),
    dict(id=41, slug='countertop-dishwasher-for-small-households', cat='kitchen', kind='compare', pr=True,
         title='タンク式食洗機4モデルを1〜2人暮らし向けに比較',
         published='2026-08-28', modified='2026-09-12', modified_ts='2026-09-12T02:56:58Z',
         compare='タンク式のSOLOTA・ラクアmini color・SS-MA251・NP-TSP1の4機種を、本体寸法・標準食器点数・乾燥方式・扉・給水方式で比べます。',
         home='タンク式4機種を、置き場所・食器量・毎回の作業で比べます。設置条件の確認先も案内します。',
         update='導入文と比較表を判断軸ごとに再構成し、開扉時の寸法と必要な余白を設置条件の節にまとめ、5本のガイドへの導線を戻しました。',
         guide=('ps-installation-context', '設置条件の詳細と型番別の注意', '本体寸法だけでなく、開扉時の寸法と必要な余白を型番ごとに確認する条件が決まります。'),
         purposes={'small-space': '本体奥行225mmのSOLOTAから幅550mmのNP-TSP1まで、置ける寸法と扉を開く空間から4機種のどれが残るかが決まります。',
                   'save-housework': '食器の洗浄・すすぎを任せたあとに残る、並べる・取り出す・給水・手入れの作業量から、買い足す価値があるかが決まります。',
                   'without-installation': 'タンク式でも必要な電源・アース・排水経路と、開扉時の寸法を含む設置条件から、工事なしで置ける機種が決まります。',
                   'easy-maintenance': '洗浄を任せたあとに残る給水と手入れの作業を4機種で比べ、続けられる構成が決まります。'}),
    dict(id=86, slug='solota-vs-rakua-mini-plus', cat='kitchen', kind='compare', pr=False,
         title='SOLOTAとラクアmini Plusの違い｜大きさ・食器量・乾燥方式を比較',
         published='2026-08-29', modified='2026-09-11', modified_ts='2026-09-10T22:59:36Z',
         compare='SOLOTA NP-TMLK1-Kとラクアmini Plus TK-MDW22Bの2機種を、本体と開扉時の奥行・標準食器点数・使用水量・乾燥方式で比べます。広告リンクはありません。',
         home='奥行を抑えるか、食器量を増やすか。2機種の寸法・食器点数・乾燥方式を公式仕様で比べます。',
         update='記事冒頭の近道（2機種の比較表・購入前の確認）と、記事末「残っている疑問から、次の記事へ」の案内を追加しました。',
         guide=('reader-axes', '自宅に合う候補を選ぶ3つの視点', '扉を開ける空間、いつもの食器、乾燥方式の3点で、2機種のどちらを検討するかが決まります。'),
         purposes={'small-space': '本体奥行22.5cmのSOLOTAと、扉を開けると59.4cm必要なラクアmini Plusのどちらが自宅に置けるかが決まります。',
                   'without-installation': '2機種ともタンク給水ですが、扉・給排水・電源・アース・排熱の空間は必要です。自宅で確認する項目が決まります。'}),
    dict(id=266, slug='dishwasher-running-cost', cat='kitchen', kind='guide', pr=False,
         title='卓上食洗機のランニングコスト｜電気・水道・洗剤を式で確認する',
         published='2026-09-09', modified='2026-09-12', modified_ts='2026-09-12T03:00:00Z',
         guide_blurb='電気代・水道代・洗剤代を公表値と自宅の単価から計算する式が決まります。消費電力量を確認できた機種と未確認の機種を分けて扱います。',
         home='自宅の単価と運転回数で試算します。未確認の費目はゼロ円にしません。',
         update=NOTE_GUIDE_0912,
         purposes={'save-housework': '任せる家事が増えるぶん毎回かかる電気・水道・洗剤代を試算し、続けられる回数と費用の見当が決まります。',
                   'easy-maintenance': '本体価格のあとに毎回かかる電気・水道・洗剤の従量費を式で試算し、使い続ける費用の見当が決まります。'}),
    dict(id=264, slug='dishwasher-detergent-guide', cat='kitchen', kind='guide', pr=False,
         title='食洗機用洗剤の選び方｜型番ごとの量と入れてはいけないもの',
         published='2026-09-09', modified='2026-09-12', modified_ts='2026-09-12T03:00:03Z',
         guide_blurb='機種ごとの専用洗剤の種類と通常量、入れてはいけない食器・材質が分かり、いま使っている洗剤と食器のままで使えるかが決まります。',
         home='機種に合う専用洗剤と使用量、入れない食器を確認します。',
         update=NOTE_GUIDE_0912,
         purposes={'easy-maintenance': '専用洗剤の通常量（例：SOLOTAは約2g）と洗えない食器を機種別に確認し、洗剤選びで迷わない状態が決まります。'}),
    dict(id=265, slug='dishwasher-cleaning-guide', cat='kitchen', kind='guide', pr=False,
         title='卓上食洗機のお手入れ｜毎回・月1回・長く使わない時に分ける',
         published='2026-09-09', modified='2026-09-12', modified_ts='2026-09-12T02:59:52Z',
         guide_blurb='毎回・月1回・長く使わない時に分けた手入れ手順が機種別に分かり、購入後に自分に残る作業の量が決まります。',
         home='毎回の清掃と定期的な作業を分け、使い続けられる手順を確認します。',
         update=NOTE_GUIDE_0912,
         purposes={'save-housework': '残さいフィルターの毎回の水洗い、月1回のノズル清掃など、洗い物を任せた後に残る手入れの頻度が決まります。',
                   'easy-maintenance': '毎回・月1回・長期不使用時の作業を機種別に分け、続けやすい手入れの機種かどうかが決まります。'}),
    dict(id=30, slug='compact-robot-vacuum-shortlist', cat='cleaning', kind='compare', pr=True,
         title='省スペースのロボット掃除機を条件で絞る',
         published='2026-08-24', modified='2026-09-11', modified_ts='2026-09-10T22:59:01Z',
         compare='小型のRoomba Mini + AutoEmptyとSwitchBot K11+ Proを中心に、K10+ Pro Combo・Roomba Plus 515 Comboを加えた4構成を、本体とステーションの寸法・水拭き方式・自動手入れで比べます。',
         category='本体と充電台を小さくしたい方向け。家具下の高さ、帰還経路、紙パックやタンクを交換する空間を測れることが前提です。',
         home='本体と台を分け、吸引・自動ゴミ収集・モップの手入れの範囲を比べます。',
         update='記事冒頭の近道（小型2機種を詳しく比較する）と、記事末「小型2機種に絞れたら、台と構成を詳しく比較」の案内を追加しました。',
         guide=('ps-decision-steps', 'MiniとK11+ Proが残ったら、接続条件と台の周囲を比べる', 'Wi-Fiの周波数帯やアプリの接続条件と、台の周囲に必要な空間を確認する順番が決まります。'),
         purposes={'small-space': '本体幅24.5〜24.8cmの2機種とステーションの寸法を分けて確認し、家具の間と台の置き場に収まる構成が決まります。',
                   'save-housework': '床掃除を任せたあとに残る、ゴミ捨て・水拭きシートの交換・モップ手入れの作業を4構成で比べ、どこまで任せるかが決まります。',
                   'easy-maintenance': '自動ゴミ収集・使い捨てシート・モップ自動洗浄など、手入れの方式ごとに残る作業と消耗品が決まります。'}),
    dict(id=85, slug='roomba-mini-vs-switchbot-k11-pro', cat='cleaning', kind='compare', pr=True,
         title='Roomba MiniとSwitchBot K11+ Proを公式仕様で比較',
         published='2026-08-29', modified='2026-09-11', modified_ts='2026-09-10T22:59:25Z',
         compare='Roomba Mini + AutoEmpty（F155260）とSwitchBot K11+ Proの2製品を、本体・ステーション寸法・自動ゴミ収集・水拭き・Wi-Fi・消耗品で比べます。',
         category='小型2機種に絞れた方向け。自動ゴミ収集を使うか、充電台だけの別構成（Roomba Mini Slim）まで含めるかを決めてから読むと迷いません。',
         home='小型2機種を台と構成から比較。自動ゴミ収集のないMini Slimは別構成として扱います。',
         update='記事冒頭の近道（台と構成の比較表・購入前の確認）と、記事末「水拭きの手入れまで任せたいなら、比較範囲を広げる」の案内を追加しました。',
         guide=('robot-installation-title', '置き場所は、床面積だけでは決まらない。', 'ステーションの周囲に必要な空間と帰還経路まで含めて、置き場所を決める条件が分かります。'),
         purposes={'small-space': '本体は同じ高さ9.2cmでも、AutoEmptyとK11+ Proのステーション寸法は違います。台を置く場所から2機種のどちらかが決まります。',
                   'save-housework': '自動ゴミ収集で減るのはゴミ捨ての回数です。水拭きシートの交換や日常の手入れが残ることを踏まえ、任せたい範囲が決まります。',
                   'easy-maintenance': '自動収集でも残るブラシ・フィルター・シート交換の手入れと、消耗品の入手先を2機種で確かめ、続けやすい方が決まります。'}),
    dict(id=28, slug='portable-power-station-guide', cat='preparedness', kind='compare', pr=True,
         title='停電対策用ポータブル電源の選び方｜容量・定格出力・持ち運びで決める',
         published='2026-08-24', modified='2026-09-11', modified_ts='2026-09-10T22:59:27Z',
         compare='Anker Solix C300・Jackery 500 New・BLUETTI AC70・EcoFlow DELTA 3 Classicの4モデルを、容量（288〜1024Wh）・定格出力（300〜1500W）・重量・寸法で比べます。',
         category='使いたい機器の消費電力と必要時間を書き出せる方向け。容量Whと出力Wを別々に満たすことが前提で、住宅全体の電源設計は対象外です。',
         home='使う機器と時間を先に決め、容量・定格出力・運べる重量で候補を比べます。',
         update='記事冒頭の近道（Ankerの容量帯・世代差を比べる）と、記事末「容量帯が見えてきたら、シリーズ内の違いも確認」の案内を追加しました。',
         guide=('ps-decision-steps', '使いたい時間から、必要なWhとWを分けて考える', '機器ごとの消費電力Wと使いたい時間から必要なWhを計算し、容量帯を決める手順が分かります。'),
         purposes={'prepare-outage': '停電時に使う機器と時間を書き出し、必要なWhとWを計算すると、288Wh〜1024Whの4モデルのどの容量帯が要るかが決まります。'}),
    dict(id=29, slug='anker-solix-c300-c800-c1000-differences', cat='preparedness', kind='compare', pr=True,
         title='Anker Solix C300・C800 Plus・C1000・C1000 Gen 2の違い',
         published='2026-08-24', modified='2026-09-12', modified_ts='2026-09-12T02:52:36Z',
         compare='Anker Solix C300・C800 Plus・C1000・C1000 Gen 2の4型番を、容量・定格出力・重量・寸法と、C1000世代差（端子構成・拡張バッテリー対応）で比べます。',
         category='Ankerに候補を絞った方向け。使い道（小型機器中心か、大きな出力も必要か）と持ち運びの頻度を先に決めることが前提です。',
         home='C300・C800 Plus・C1000・C1000 Gen 2を別機種として比べます。',
         update='Gen 2を勧める理由から未確定だった出力差の記述を外し、公表重量とUSB-C端子数を根拠にする文へ差し替えました。',
         guide=('c1000-generation-choice', 'C1000の世代差は、使う端子と拡張の予定で選ぶ', '第1世代とGen 2のどちらにするかを、使う端子と拡張バッテリーの予定で決める条件が分かります。'),
         purposes={'prepare-outage': 'Ankerで揃えるなら、使いたい機器の出力と持ち運びから容量帯を選び、C1000は端子構成と拡張バッテリーの予定で世代が決まります。'}),
]
# The ledger title is what the publish flow applies to post_title (= article h1); it
# overrides the fallback title above so anchors always equal the destination h1.
_LEDGER = {r['slug']: r for r in json.loads((ROOT / 'changes/wordpress-direct-publish-v1/articles.v1.json').read_text(encoding='utf-8'))['articles']}
for _a in ARTICLES:
    _a['title'] = _LEDGER[_a['slug']]['title']
for _slug in list(HUB_TITLE):
    if _slug in _LEDGER:
        HUB_TITLE[_slug] = _LEDGER[_slug]['title']
BY_ID = {a['id']: a for a in ARTICLES}
BY_SLUG = {a['slug']: a for a in ARTICLES}
CAT_ARTICLES = {c: [a for a in ARTICLES if a['cat'] == c] for c in CAT_ORDER}

HEAD_STYLE = 'max-width:76rem;margin:1rem auto 3rem;padding:clamp(1rem,3vw,2.5rem);background:#faf9f6;color:#1b1b18;line-height:1.85'
PR_BADGE = '<abbr class="ks-pr-badge" title="広告リンクを含む記事" style="display:inline-block;margin-right:.4rem;padding:0 .4rem;border:1px solid #714332;color:#714332;font-size:.875rem;font-weight:700;line-height:1.6;text-decoration:none">PR</abbr>'
NOTE = ('<p class="ks-reader-note">記事内の確認日と対象機種をご確認ください。実機で検証していない性能は順位付けしていません。'
        '比較記事（PR表示あり）には販売店への広告リンクが含まれます。ガイド記事には含まれません。</p>')
POLICY_NAV = '<nav aria-label="編集方針"><a href="/comparison-policy/">比較・編集方針</a> ／ <a href="/about-ad-policy/">運営・広告方針</a></nav>'


def jp_date(iso: str) -> str:
    y, m, d = iso.split('-')
    return f'{int(y)}年{int(m)}月{int(d)}日'


def pr(a: dict) -> str:
    return PR_BADGE if a['pr'] else ''


def crumb(slug: str, parent: str | None) -> str:
    parts = ['<a href="/">ホーム</a>']
    if parent:
        parts.append(f'<a href="/{parent}/">{HUB_TITLE[parent]}</a>')
    parts.append(f'<span aria-current="page">{HUB_TITLE[slug]}</span>')
    return '<nav aria-label="このサイトの入口">' + ' ＞ '.join(parts) + '</nav>'


def wrap(slug: str, parent: str | None, body: str, extra_class: str = '') -> str:
    cls = 'ks-reader-start ks-directory' + (' ' + extra_class if extra_class else '')
    return (f'<!-- wp:html -->\n<div class="{cls}" data-reader-release="{RELEASE}" style="{HEAD_STYLE}">\n'
            f'{crumb(slug, parent)}\n{body}\n{NOTE}{POLICY_NAV}\n</div>\n<!-- /wp:html -->\n')


def card(a: dict, blurb: str, href: str | None = None, label: str | None = None, extra: str = '') -> str:
    href = href or f'/{a["slug"]}/'
    label = label or a['title']
    return f'<article><h3>{pr(a)}<a href="{href}">{label}</a></h3><p>{blurb}</p>{extra}</article>'


def grid(cards: list[str]) -> str:
    return '<div class="ks-route-grid">' + ''.join(cards) + '</div>'


# ---------------------------------------------------------------------------
# categories.html
# ---------------------------------------------------------------------------
CAT_INTRO = {
    'travel': ('利用便と荷物量を先に確認し、軽さ・開き方・容量から選ぶ。', '4記事：小型機向け、軽量、前開き、エースのモデル比較。すべて広告リンクを含む比較記事です。'),
    'kitchen': ('置き場所・いつもの食器・毎回の給水から、続けられる一台を。', '7記事：機種比較2本（うち1本は広告リンクあり）と、設置・給排水・洗剤・手入れ・費用のガイド5本。'),
    'cleaning': ('本体と台の置き場、任せたい掃除、残る手入れを分けて選ぶ。', '2記事：設置条件からの比較と、小型2機種の構成比較。どちらも広告リンクを含みます。'),
    'preparedness': ('大きさより先に、使う機器と時間、運べる重さを決める。', '2記事：停電対策の選び方と、Anker Solixの容量帯・世代差。どちらも広告リンクを含みます。'),
}


def categories_html() -> str:
    cards = []
    for i, c in enumerate(CAT_ORDER):
        img = IMG[c]
        lazy = '' if i == 0 else ' loading="lazy"'
        lead, count = CAT_INTRO[c]
        cards.append(
            f'<article><a href="/{c}/" aria-label="{HUB_TITLE[c]}" style="display:block;padding:0">'
            f'<img src="{img["url"]}" width="762" height="506" alt="{img["alt"]}"{lazy} style="display:block;width:100%;height:auto;object-fit:cover"></a>'
            f'<h3><a href="/{c}/">{HUB_TITLE[c]}</a></h3><p>{lead}</p><p>{count}</p></article>')
    body = ('<p class="ks-directory-lead">比較したい商品から、必要な条件を確かめましょう。4カテゴリとも、条件の整理、記事の比較、購入前の確認の順に進めます。</p>\n'
            '<section id="category-cards"><h2>比較したい商品から選ぶ</h2>'
            '<div class="ks-route-grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,24rem),1fr));gap:24px">' + ''.join(cards) + '</div></section>\n'
            '<section id="category-undecided"><h2>商品がまだ決まっていない方へ</h2>'
            '<p>困りごとが先にある場合は<a href="/purposes/">悩み・目的から探す</a>へ。測る・数える・確認する作業から始めるなら<a href="/guides/">選び方ガイド</a>、候補が決まっている場合は<a href="/comparisons/">比較・条件別の候補</a>から進めます。記事ごとの更新日と変更点は<a href="/updates/">最近更新したガイド</a>にまとめています。</p></section>\n'
            '<p class="ks-reader-note">画像はAI生成の編集イメージです。掲載商品の実物写真・設置例・性能の検証結果ではありません。</p>')
    return wrap('categories', None, body)


# ---------------------------------------------------------------------------
# purposes.html
# ---------------------------------------------------------------------------
PURPOSE_CARDS = [
    ('small-space', '5記事・食洗機／ロボット掃除機', '本体の寸法だけでなく、扉を開く空間や充電台の余白まで測って候補を絞ります。'),
    ('save-housework', '6記事・食洗機／ロボット掃除機', '任せられる家事と、給水・ゴミ捨て・手入れなど自分に残る作業を分けて考えます。'),
    ('without-installation', '4記事・タンク式食洗機', '「工事不要」の表示だけで決めず、置き場所・排水・電源・アースの確認順から入ります。'),
    ('easy-maintenance', '8記事・食洗機／ロボット掃除機／スーツケース', '毎回・月1回・長期不使用に分けた手入れと、消耗品・交換部品の有無を確かめます。'),
    ('comfortable-travel', '4記事・機内持ち込みスーツケース', '利用便と荷物量から、持ち上げる重さ・途中の出し入れ・小型機の枠に合う一台を選びます。'),
    ('prepare-outage', '2記事・ポータブル電源', '停電時に何を何時間使いたいかを書き出し、必要な容量と出力を分けて電源を選びます。'),
]


def purposes_html() -> str:
    cards = ''.join(
        f'<article><h3><a href="/{slug}/">{HUB_TITLE[slug]}</a></h3><p><strong>{count}</strong></p><p>{desc}</p></article>'
        for slug, count, desc in PURPOSE_CARDS)
    body = ('<p class="ks-directory-lead">商品名が決まっていなくても大丈夫です。減らしたい負担や買う前の不安から入口を選ぶと、それぞれのページで「まず読む1本」と、記事ごとに決まることを案内します。</p>\n'
            '<section id="purpose-cards"><h2>いま困っていることを選ぶ</h2>' + grid([cards]) + '</section>\n'
            '<p>商品の種類が決まっている方は<a href="/categories/">商品カテゴリから探す</a>へ。新しい記事から読みたい方は<a href="/updates/">最近更新したガイド</a>へ。</p>')
    return wrap('purposes', None, body)


# ---------------------------------------------------------------------------
# guides.html (CH-05)
# ---------------------------------------------------------------------------
def guide_fragment_card(a: dict) -> str:
    frag, heading, blurb = a['guide']
    extra = f'<p class="ks-guide-source">比較記事「{a["title"]}」内の節です。</p>'
    return card(a, blurb, href=f'/{a["slug"]}/#{frag}', label=heading, extra=extra)


def guides_html() -> str:
    sections = []
    jump = []
    for c in CAT_ORDER:
        sid = f'{c}-guides'
        jump.append(f'<a href="#{sid}">{CAT_NAME[c]}</a>')
        cards = []
        for a in CAT_ARTICLES[c]:
            if a['kind'] == 'guide':
                cards.append(card(a, a['guide_blurb']))
        for a in CAT_ARTICLES[c]:
            if a['kind'] != 'guide' and a.get('guide'):
                cards.append(guide_fragment_card(a))
        if c == 'kitchen':
            intro = ('<p>置き場所・給排水・洗剤・手入れ・費用を確かめるガイド5本（広告リンクなし）と、比較記事2本の条件整理の節です。'
                     '対象機種はSOLOTA・ラクアmini color・SS-MA251・NP-TSP1で、SOLOTAとラクアmini Plusの2機種比較は別記事です。'
                     '分岐水栓の工事を避けたい方は<a href="/without-installation/">設置工事を避けたい</a>に確認の順番をまとめています。</p>')
            h2 = '食洗機：設置から使い続ける費用まで'
        elif c == 'travel':
            intro = '<p>スーツケースにはガイド記事がありません。各比較記事の「条件を決める」節へ直接進めます。</p>'
            h2 = 'スーツケース：便・荷物・開き方を決める節'
        elif c == 'cleaning':
            intro = '<p>ロボット掃除機にはガイド記事がありません。比較記事の中で、接続条件と置き場所を確かめる節へ進めます。</p>'
            h2 = 'ロボット掃除機：接続条件と置き場所を確かめる節'
        else:
            intro = '<p>ポータブル電源にはガイド記事がありません。必要なWhとWの計算と、Anker C1000の世代の決め方の節へ進めます。</p>'
            h2 = 'ポータブル電源：必要なWhとWを決める節'
        sections.append(f'<section id="{sid}"><h2>{h2}</h2>{intro}{grid(cards)}</section>')
    body = ('<p class="ks-directory-lead">商品名を決める前に、測る・数える・確認する作業から条件を整理するページです。候補を横並びで比べたい方は<a href="/comparisons/">比較・条件別の候補</a>へ進んでください。</p>\n'
            '<nav id="ks-guide-jump" aria-label="知りたい商品の選び方へ移動" class="ks-inline-links">' + ''.join(jump) + '</nav>\n'
            + '\n'.join(sections) + '\n'
            '<p>比較記事内の節へのリンク（PR表示あり）は、販売店への広告リンクを含む記事の一部へ進みます。ガイド記事5本に広告リンクはありません。</p>')
    return wrap('guides', None, body)


# ---------------------------------------------------------------------------
# comparisons.html (CH-05 / CH-07)
# ---------------------------------------------------------------------------
def comparisons_html() -> str:
    sections = []
    jump = []
    counts = {'travel': '4本', 'kitchen': '2本', 'cleaning': '2本', 'preparedness': '2本'}
    for c in CAT_ORDER:
        sid = f'compare-{c}'
        jump.append(f'<a href="#{sid}">{CAT_NAME[c]}</a>')
        cards = [card(a, a['compare']) for a in CAT_ARTICLES[c] if a['kind'] == 'compare']
        sections.append(f'<section id="{sid}"><h2>{CAT_NAME[c]}：比較記事{counts[c]}</h2>{grid(cards)}</section>')
    jump.append('<a href="#buyer-offer-check">候補が決まったら、販売条件を同じ基準で比べる</a>')
    body = ('<p class="ks-directory-lead">候補を横並びで比べるページです。記事ごとに比較の軸と候補の数を先に示します。条件の整理から始めたい方は<a href="/guides/">選び方ガイド</a>へ。</p>\n'
            '<nav id="ks-comparison-jump" aria-label="比較したい商品へ移動" class="ks-inline-links">' + ''.join(jump) + '</nav>\n'
            + '\n'.join(sections) + '\n'
            '<section id="buyer-offer-check" aria-labelledby="buyer-offer-check-title"><h2 id="buyer-offer-check-title">候補が決まったら、販売条件を同じ基準で比べる</h2>'
            '<p>型番・世代・セット内容が同じかを先に確認し、税込の商品代に送料と必要な付属品を加えた総額を比べましょう。ポイントや条件付きクーポンは、支払額と分けて考えます。</p>'
            '<details><summary style="min-height:44px;padding:8px 0;cursor:pointer">購入前に確認する4項目</summary><ul>'
            '<li>商品名だけでなく、型番・世代・色・付属品が希望どおりか。</li>'
            '<li>新品・中古・整備済みなどの状態と、送料を含む支払総額。</li>'
            '<li>販売元、使う日までの納期、返品条件、保証の対象。</li>'
            '<li>置き場所・利用便・接続機器など、自分の使用条件を満たすか。</li></ul></details>'
            '<p>条件を満たす商品がない、または重要な点が未確認なら、今回は見送る選択もあります。商品別の確認項目はホームの<a href="/#home-purchase-check">購入前の最終確認</a>にまとめています。</p></section>')
    return wrap('comparisons', None, body)


# ---------------------------------------------------------------------------
# updates.html (CH-09)
# ---------------------------------------------------------------------------
def updates_html() -> str:
    ordered = sorted(ARTICLES, key=lambda a: a['modified_ts'], reverse=True)
    groups: dict[str, list[dict]] = {}
    for a in ordered:
        groups.setdefault(a['modified'], []).append(a)
    sections = []
    for day, rows in groups.items():
        cards = []
        for a in rows:
            pub = f'{jp_date(a["published"])}公開'
            if a['published'] == '2026-09-09':
                pub = f'<strong>{pub}</strong>'
            meta = (f'<p><time datetime="{a["modified"]}">{jp_date(a["modified"])}</time>更新 ／ {pub} ／ {CAT_NAME[a["cat"]]}</p>')
            cards.append(f'<article>{meta}<h3>{pr(a)}<a href="/{a["slug"]}/">{a["title"]}</a></h3><p>変更点：{a["update"]}</p></article>')
        n = len(rows)
        sections.append(f'<section id="updated-{day.replace("-", "")}"><h2>{jp_date(day)}に更新した{n}本</h2>{grid(cards)}</section>')
    body = ('<p class="ks-directory-lead">掲載記事15本を、公開ページで確認した更新日の新しい順に並べ、変更点を1文で記録しています。更新日は2026年9月12日時点の記録です。本文の編集日と商品仕様の確認日は別で、価格・在庫・性能を一括で再確認した更新ではありません。</p>\n'
            '<p>食洗機のガイド5本（<strong>2026年9月9日公開</strong>）が最も新しい記事です。カテゴリごとの一覧は<a href="/categories/">商品カテゴリから探す</a>へ。</p>\n'
            + '\n'.join(sections))
    return wrap('updates', None, body)


# ---------------------------------------------------------------------------
# category hubs (CH-06): travel / cleaning / preparedness
# ---------------------------------------------------------------------------
CATEGORY_HUBS = {
    'travel': dict(
        lead='利用便と荷物量を先に確認し、軽さ・開き方・容量から選ぶ。',
        intro_h2='旅の条件が決まると、選ぶ一台が見えてくる。',
        intro_p='荷物を軽くしたい。移動中に小物を取り出したい。旅で困る場面から、残す機能と妥協できることを整理しましょう。',
        axes_h2='スーツケース選びで先に確かめる4つの条件',
        axes=[('利用便と機材', '航空会社・便・機材ごとの持ち込み規定を、商品表示より先に確認します。100席未満の小型機は3辺合計100cm以内が目安です。'),
              ('通常時の外寸と重量', '拡張していない状態の外寸と、キャスター・ハンドルを含む実寸を見ます。荷物込みの総重量が上限内かも確認します。'),
              ('開き方', '中央開きか前開きか。移動中に取り出す物があるなら、前面収納の構造まで確認します。'),
              ('使い続ける条件', 'キャスターストッパーの有無、交換できる車輪、拡張時の寸法を、帰りに増える荷物と合わせて考えます。')],
        axes_note='「機内持ち込み対応」という表示だけでは、実際の便で持ち込めるとは確定しません。搭乗前に運航会社の最新規定で確認してください。',
        choose=[('本体の軽さを優先する（3kg以下）', 83, 'aeroflex-dx2-01521', 'エアロフレックスDX2 01521'),
                ('100席未満の小型機に持ち込む', 82, 'staria-cxr-02350-purchase', 'PROTECA スタリアCXR 02350'),
                ('前開きと中央開きを使い分ける', 84, 'ace-difference-05721-purchase', 'ace.TOKYO LABEL ディフェレンス 05721'),
                ('車輪を自分で交換したい', 83, 'frequenter-lieve-1-250', 'FREQUENTER LIEVE（フリクエンター リエーヴェ）1-250')],
        specs=(83, 'ps-specs', '決め手になる比較表（30L以上・3kg以下の4モデル）'),
        purposes=['comfortable-travel', 'easy-maintenance'],
        checks='通常時と拡張時の各辺・3辺合計、荷物込みの重さと個数、送料込みの総額、出発前の納期、保証を確認します。',
        hold='利用便が未定、拡張しないと荷物が収まらない、走行音や耐久性が最優先の場合は、運航会社の規定や実物・同条件の検証情報を確認してから決めましょう。',
    ),
    'cleaning': dict(
        lead='本体と台の置き場、任せたい掃除、残る手入れを分けて選ぶ。',
        intro_h2='掃除を任せて、部屋は広く使いたい。',
        intro_p='本体の小ささだけでなく、充電台の置き場と自分に残る手入れから。家に無理なく迎えられる構成を比べます。',
        axes_h2='ロボット掃除機選びで先に確かめる4つの条件',
        axes=[('本体と台の置き場', '本体寸法だけでなく、ステーションの幅・奥行・高さと周囲に必要な空間、帰還経路を測ります。'),
              ('家具下と段差', '通したい家具下の高さと、通過させたい段差の有無を確認します。'),
              ('任せたい作業', '床の片づけ・ゴミ捨て・水拭きのうち、どれを減らしたいかを決めます。自動ゴミ収集で減るのはゴミ捨ての回数です。'),
              ('通信と手入れ', 'Wi-Fiの周波数帯とアプリ、消耗品の交換頻度と入手先を確認します。')],
        axes_note='吸引力の公表単位はメーカーで異なります。Pa値だけで清掃性能の優劣は決めていません。',
        choose=[('本体と台を小さくしたい', 30, 'product-robot-roomba-mini', 'Roomba Mini（ルンバ ミニ）+ AutoEmpty F155260'),
                ('SwitchBotアプリと自動ゴミ収集で揃える', 85, 'switchbot-k11-pro-purchase', 'SwitchBot K11+ Pro'),
                ('コードレス掃除機もまとめたい', 30, 'product-robot-k10-pro-combo', 'SwitchBot（スイッチボット）ロボット掃除機 K10+ Pro Combo'),
                ('モップの洗浄・乾燥も任せたい', 30, 'product-robot-roomba-plus-515', 'Roomba Plus（ルンバ）515 Combo + AutoWash N285060'),
                ('自動ゴミ収集なしで台を小さくしたい', 85, 'roomba-mini-slim-f115060-purchase', 'Roomba Mini Slim + SlimCharge F115060')],
        specs=(30, 'ps-specs', '決め手になる比較表（4構成）'),
        purposes=['small-space', 'save-housework', 'easy-maintenance'],
        checks='本体と台の寸法に加え、帰還と部品交換の空間、床材、通信条件、セット構成、消耗品、販売元と保証を確認します。',
        hold='毛や砂の取り残し、障害物回避、段差の通過が最優先なら、寸法や公称吸引力だけでは決められません。同機種・似た住環境の比較可能な検証を確認してください。',
    ),
    'preparedness': dict(
        lead='大きさより先に、使う機器と時間、運べる重さを決める。',
        intro_h2='もしもの備えを、いつもの暮らしから考える。',
        intro_p='スマートフォン、照明、使いたい家電。必要な機器と時間を先に書き出して、容量・出力・持ち運ぶ重さを比べましょう。',
        axes_h2='ポータブル電源選びで先に確かめる4つの条件',
        axes=[('使いたい機器と時間', '機器ごとの消費電力Wと使う時間から必要なWhを計算します。容量Whと出力Wは別の条件です。'),
              ('起動時の電力と端子', '起動時に大きな電力が要る機器の有無と、使う端子（AC・USB-C・USB-A）の数を確認します。'),
              ('運ぶ重さと保管', '約4kgから約12kgまで重さが違います。保管場所と、停電時に運ぶ経路を決めます。'),
              ('拡張と世代', '拡張バッテリーを使う予定があるかで、同じシリーズでも世代の選び方が変わります。')],
        axes_note='住宅全体の電源設計や、生命維持・医療機器への給電は比較の対象外です。',
        choose=[('小型機器の充電が中心で持ち運びを優先（288Wh・300W）', 28, 'product-power-c300', 'Anker（アンカー）Solix C300 Portable Power Station'),
                ('500W級まで（512Wh）', 28, 'product-power-jackery-500-new', 'Jackery（ジャクリ）ポータブル電源 500 New'),
                ('定格1000W級まで（768Wh）', 28, 'product-power-bluetti-ac70', 'BLUETTI（ブルーティ）AC70'),
                ('定格1500W級まで（1024Wh）', 28, 'product-power-delta-3-classic', 'EcoFlow（エコフロー）DELTA 3 Classic'),
                ('AnkerのC1000で世代に迷う', 29, 'c1000-generation-choice', 'C1000の世代差は、使う端子と拡張の予定で選ぶ')],
        specs=(28, 'ps-specs', '決め手になる比較表（4モデル）'),
        purposes=['prepare-outage'],
        checks='起動時も含めた機器との対応、端子と必要付属品、使用・保管環境、重量、販売元と保証を確認。本体単体とパネルなどのセットは分けて総額を比べます。',
        hold='接続機器との対応や必要な時間を確認できない場合は推測で決めません。住宅全体の電源設計、生命維持・医療機器への給電は本比較の対象外です。',
    ),
}


def category_hub_html(slug: str) -> str:
    d = CATEGORY_HUBS[slug]
    img = IMG[slug]
    axes = ''.join(f'<li><strong>{h}</strong>：{t}</li>' for h, t in d['axes'])
    choose = ''.join(
        f'<li>{cond}：<a href="/{BY_ID[aid]["slug"]}/#{frag}">{label}</a></li>'
        for cond, aid, frag, label in d['choose'])
    sid, sfrag, slabel = d['specs']
    n = len(CAT_ARTICLES[slug])
    cards = [card(a, a['category']) for a in CAT_ARTICLES[slug]]
    others = ' '.join(f'<a href="/{c}/">{HUB_TITLE[c]}</a>' for c in CAT_ORDER if c != slug)
    purpose_links = '、'.join(f'<a href="/{p}/">{HUB_TITLE[p]}</a>' for p in d['purposes'])
    body = (f'<p class="ks-directory-lead">{d["lead"]}</p>\n'
            f'<nav aria-label="このページの読み方"><a href="#{slug}-axes">先に確かめる4つの条件</a> <a href="#choose">条件から候補を見る</a> <a href="#compare">知りたいことから記事を選ぶ</a> <a href="#purchase-checks">候補が決まったら、最後の確認</a></nav>\n'
            f'<section id="{slug}-start" class="ks-category-intro" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,22rem),1fr));gap:24px;align-items:center">'
            f'<div><h2 id="{slug}-start-title">{d["intro_h2"]}</h2><p>{d["intro_p"]}</p><p>困りごとから入るなら：{purpose_links}</p></div>'
            f'<figure class="ks-category-visual" id="ks-visual-{slug}" style="margin:0"><img src="{img["url"]}" width="762" height="506" alt="{img["alt"]}"><figcaption>{img["caption"]}</figcaption></figure></section>\n'
            f'<section id="{slug}-axes" aria-labelledby="{slug}-axes-title"><h2 id="{slug}-axes-title">{d["axes_h2"]}</h2><ol>{axes}</ol><p>{d["axes_note"]}</p></section>\n'
            f'<section id="choose"><h2>条件から候補を見る</h2><p>条件に合う機種の説明へ直接進めます。リンク先はいずれも広告リンクを含む比較記事です。</p><ul>{choose}</ul>'
            f'<p><a href="/{BY_ID[sid]["slug"]}/#{sfrag}">{slabel}</a></p></section>\n'
            f'<section id="compare"><h2>知りたいことから記事を選ぶ</h2><p>掲載記事 {n}本。順番どおりに読む必要はありません。紹介文は、その記事を読む前提条件です。</p>'
            f'<div id="{slug}-comparisons">{grid(cards)}</div></section>\n'
            f'<section id="purchase-checks"><h2>候補が決まったら、最後の確認</h2><p>{d["checks"]}</p>'
            f'<details><summary>購入を急がない方がよい場合</summary><p>{d["hold"]}</p></details></section>\n'
            f'<nav aria-label="ほかの商品カテゴリ">{others}</nav>')
    return wrap(slug, 'categories', body)


# ---------------------------------------------------------------------------
# purpose hubs (CH-01)
# ---------------------------------------------------------------------------
PURPOSE_HUBS = {
    'small-space': dict(
        lead='一人暮らしや狭い部屋で、食洗機かロボット掃除機を置きたい方へ。本体の寸法だけでなく、扉を開く空間、充電台の周囲、ホースや蒸気の余白まで含めて「置ける」を確かめます。',
        first=262, first_note='食洗機を検討しているなら、置き場所の測り方から。ロボット掃除機が先なら、下の「省スペースのロボット掃除機を条件で絞る」から読んでください。',
        axis_h2='置き場所から考える',
        axis_p='置ける寸法は、本体・扉や台・余白の3つに分けて測ると判断が早くなります。食洗機は扉を開いた奥行と蒸気の逃げ道、ロボット掃除機はステーションの周囲と帰還経路が見落としやすい点です。',
        articles=[262, 41, 86, 30, 85],
        next=[('kitchen', '食洗機'), ('cleaning', 'ロボット掃除機')],
    ),
    'save-housework': dict(
        lead='洗い物や床掃除を機械に任せて、家事の時間を短くしたい方へ。任せられる作業と、給水・ゴミ捨て・手入れのように自分に残る作業を分けて考えます。作業時間の削減量は実測していません。',
        first=41, first_note='食後の洗い物を減らしたい方は、タンク式4機種の比較から。床掃除を任せたい方は、下の「省スペースのロボット掃除機を条件で絞る」から読んでください。',
        axis_h2='減らしたい家事から選ぶ',
        axis_p='食後の洗い物なら食洗機、床のほこりならロボット掃除機が候補です。どちらも「任せた後に残る作業」を続けられるかで、買い足す価値が決まります。',
        articles=[41, 263, 265, 266, 30, 85],
        next=[('kitchen', '食洗機'), ('cleaning', 'ロボット掃除機')],
    ),
    'without-installation': dict(
        lead='分岐水栓の工事をせずに食洗機を使いたい方へ。タンク給水の機種でも、置き場所・排水先・電源・アースの確認は必要です。「工事不要」の表示だけで決めず、自宅で使える条件から確かめます。',
        first=262, first_note='置き場所を測ってから給水・排水の作業を確かめ、最後に機種を比べる順番が、買ってから置けないという不一致を避ける近道です。',
        axis_h2='購入前に確認する順番',
        axis_p='置き場所を測る、給水と排水の作業を確かめる、条件に合う機種を比べる、の順で進めます。アース端子や電気工事の要否は、メーカー・販売店または適切な施工業者へ確認してください。別機種の設置条件は流用しません。',
        articles=[262, 263, 41, 86],
        next=[('kitchen', '食洗機')],
    ),
    'easy-maintenance': dict(
        lead='買ったあとの手入れや消耗品を、無理なく続けたい方へ。食洗機は洗剤・フィルター清掃・毎回の給水、ロボット掃除機はゴミ捨てとシート交換、スーツケースは交換部品の有無を、購入前に確かめます。',
        first=265, first_note='食洗機の手入れは「毎回」「月1回」「長く使わない時」に分けると比べやすくなります。この分け方は、ほかの商品を見るときにも使えます。',
        axis_h2='残る作業・消耗品を確認する',
        axis_p='将来の部品供給や手入れの容易さを保証するものではありません。説明書や公式情報で確認できた手順と頻度だけを扱い、確認できない項目は未確認と書いています。',
        articles=[265, 264, 263, 266, 41, 85, 30, 83],
        next=[('kitchen', '食洗機'), ('cleaning', 'ロボット掃除機'), ('travel', 'スーツケース')],
    ),
    'comfortable-travel': dict(
        lead='持ち上げる重さ、移動中の出し入れ、帰りに増える荷物。旅で困る場面から機内持ち込みスーツケースを選びたい方へ。カテゴリページが商品の条件から入るのに対し、ここでは利用便と荷物量から記事を選びます。',
        first=83, first_note='100席以上の一般的な便で、荷物込みの重さを軽くしたい方に。100席未満の小型機に乗る予定があるなら、下の「100席未満の国内線向け」から読んでください。',
        axis_h2='利用便と荷物量から選ぶ',
        axis_p='まず利用便。100席未満の小型機なら3辺合計100cm以内の枠が目安、100席以上なら一般的な機内持ち込みの枠です。次に荷物量。1泊分か、帰りに増えるか。最後に、移動中に取り出す物があるかで開き方を決めます。',
        articles=[82, 83, 84, 19],
        next=[('travel', 'スーツケース')],
    ),
    'prepare-outage': dict(
        lead='停電に備えてポータブル電源を用意したい方へ。カテゴリページが商品の条件から入るのに対し、ここでは「停電時に何を、何時間使いたいか」を書き出すところから始めます。医療・生命維持機器への給電と住宅全体の電源設計は対象外です。',
        first=28, first_note='必要なWhとWの計算の手順と、容量帯ごとの候補4モデルを1本で確認できます。',
        axis_h2='使いたい機器と時間から選ぶ',
        axis_p='スマートフォンの充電や照明のような小さな機器が中心なら300W級、起動時に大きな電力が要る機器を動かすなら定格1000W級・1500W級を候補にします。必要なWhは機器ごとの消費電力Wと時間の積み上げで計算します。Whが足りることと、機器を動かせる出力があることは別の条件です。',
        articles=[28, 29],
        next=[('preparedness', 'ポータブル電源')],
    ),
}


def purpose_hub_html(slug: str) -> str:
    d = PURPOSE_HUBS[slug]
    first = BY_ID[d['first']]
    first_card = card(first, 'この記事で決まること：' + first['purposes'][slug], extra=f'<p>{d["first_note"]}</p>')
    cards = []
    for aid in d['articles']:
        if aid == d['first']:
            continue
        a = BY_ID[aid]
        cards.append(card(a, 'この記事で決まること：' + a['purposes'][slug]))
    n = len(d['articles'])
    nexts = '、'.join(f'<a href="/{c}/#purchase-checks">{label}：候補が決まったら、最後の確認</a>' for c, label in d['next'])
    body = (f'<p class="ks-directory-lead">{d["lead"]}</p>\n'
            f'<section id="first-read"><h2>まず読む1本</h2>{grid([first_card])}</section>\n'
            f'<section id="purpose-articles"><h2>{d["axis_h2"]}</h2><p>{d["axis_p"]}</p><p>掲載記事 {n}本。上の1本を含みます。</p>{grid(cards)}</section>\n'
            f'<section id="next-step"><h2>候補が決まったら</h2><p>商品ごとの購入前の確認項目へ進めます：{nexts}。</p></section>')
    return wrap(slug, 'purposes', body)


# ---------------------------------------------------------------------------
# home.html
# ---------------------------------------------------------------------------
HERO_PICKS = [('travel', 83), ('kitchen', 41), ('cleaning', 30), ('preparedness', 28)]
STEPS = [
    ('STEP 1', '/guides/', '選び方ガイド', '商品名を決める前に、置き場所・荷物量・必要な機能など、譲れない条件を整理します。', 'img:kitchen'),
    ('STEP 2', '/comparisons/', '比較・条件別の候補', '違いだけでなく、残す理由、選ばない理由、未確認事項まで同じ軸で比べます。', 'css:km-tools-photo'),
    ('STEP 3', '#home-purchase-check', '購入前の最終確認', '型番、設置・持ち込み条件、現在価格、在庫、保証を販売先で確かめます。', 'css:km-room'),
]
PURPOSE_FEATURES = [
    ('save-housework', 'img:kitchen', '洗い物と床掃除。<br>任せたい作業から選ぶ。'),
    ('small-space', 'css:km-room', '本体だけでなく、扉や台、<br>余白まで測って選ぶ。'),
    ('easy-maintenance', 'css:km-tools-photo', '手入れや消耗品も、<br>買う前に確かめておく。'),
    ('comfortable-travel', 'img:travel', '利用便と荷物量から、<br>持ち込める一台を選ぶ。'),
    ('without-installation', 'css:km-kitchen', '「工事不要」で決めず、<br>置き場所と排水から確かめる。'),
    ('prepare-outage', 'img:preparedness', '使いたい機器と時間から、<br>容量と出力を決める。'),
]
CATEGORY_CARDS = [
    ('cluster-mobility', 'travel', '荷物と移動に合わせて選ぶ →'),
    ('cluster-home', 'kitchen', '置き場所と食器量から選ぶ →'),
    (None, 'cleaning', '家の条件と残る手入れから →'),
    ('cluster-ready', 'preparedness', '使いたい機器と時間から →'),
]
EDITORIAL = [
    ('SELECTION', '商品選定の方法', '設置場所や使い方など、読者の条件を起点に比較対象を考えます。', '/comparison-policy/#production-comparison-scope', '比較の目的と対象範囲'),
    ('SOURCES', '公式情報の確かめ方', 'メーカーの仕様・説明書を確認し、対象型番と出典を示します。', '/comparison-policy/#production-comparison-evidence', '根拠の扱い'),
    ('TRANSPARENCY', '実機未確認の扱い', '実際に使っていない場合、使用感や性能の実測結果は書きません。', '/comparison-policy/#production-comparison-hands-on', '実機レビューと、実機を使っていない場合'),
    ('INDEPENDENCE', '広告と評価の分離', '報酬の有無や料率で、商品の評価・掲載順を決めません。', '/about-ad-policy/', '運営・広告方針'),
]
PURCHASE_LINKS = [
    (83, 'ps-offers', 'スーツケース：購入総額と販売先'),
    (41, 'ps-offers', '食洗機：購入総額と販売先'),
    (30, 'ps-offers', 'ロボット掃除機：購入総額と販売先'),
    (28, 'ps-offers', 'ポータブル電源：購入総額と販売先'),
]


def photo(spec: str, lazy: bool = True) -> str:
    kind, key = spec.split(':', 1)
    if kind == 'css':
        return f'<span class="km-photo {key}" aria-hidden="true"></span>'
    img = IMG[key]
    lz = ' loading="lazy"' if lazy else ''
    return (f'<img class="km-photo" src="{img["url"]}" width="762" height="506" alt="{img["alt"]}"{lz} '
            f'style="object-fit:cover" data-ks-image-purpose="ai-editorial-illustration">')


def home_html() -> str:
    hero_links = '<ul>' + ''.join(
        f'<li><span class="km-hero-cat">{CAT_NAME[c]}</span><a href="/{BY_ID[aid]["slug"]}/">{BY_ID[aid]["title"]}</a></li>'
        for c, aid in HERO_PICKS) + '</ul>'
    steps = ''.join(
        f'<a class="km-promo" href="{href}">{photo(spec, lazy=False)}<div class="km-promo-copy"><span class="km-eyebrow" aria-hidden="true">{eyebrow}</span>'
        f'<h3>{h3}</h3><p>{p}</p><span class="km-arrow" aria-hidden="true">⟶</span></div></a>'
        for eyebrow, href, h3, p, spec in STEPS)
    cat_cards = []
    for i, (ident, c, sub) in enumerate(CATEGORY_CARDS):
        img = IMG[c]
        idattr = f' id="{ident}"' if ident else ''
        lz = ' loading="lazy"' if i >= 2 else ''
        cat_cards.append(
            f'<a{idattr} href="/{c}/" style="display:block;background:#fff;color:#1b1b18;text-decoration:none;border:1px solid #d7d3cb">'
            f'<img src="{img["url"]}" width="762" height="506"{lz} alt="{img["alt"]}" style="display:block;width:100%;height:auto;aspect-ratio:762/506;object-fit:cover">'
            f'<div style="padding:16px"><strong style="display:block;font-size:20px">{CAT_NAME[c]}</strong><span style="display:block;margin-top:6px;font-size:14px">{sub}</span></div></a>')
    features = ''.join(
        f'<a class="km-feature" href="/{slug}/">{photo(spec)}<div class="km-feature-copy"><h3>{HUB_TITLE[slug]}</h3><p>{p}</p><span class="km-arrow" aria-hidden="true">⟶</span></div></a>'
        for slug, spec, p in PURPOSE_FEATURES)
    groups = []
    for c in CAT_ORDER:
        rows = CAT_ARTICLES[c]
        items = []
        for a in rows:
            badge = '<span class="km-pr">PR</span>' if a['pr'] else ''
            pub = '・2026年9月9日公開' if a['published'] == '2026-09-09' else ''
            items.append(
                f'<li>{badge}<a href="/{a["slug"]}/">{a["title"]}</a>'
                f'<span class="km-article-blurb">{a["home"]}</span>'
                f'<span class="km-article-date"><time datetime="{a["modified"]}">{jp_date(a["modified"])}</time>更新{pub}</span></li>')
        groups.append(f'<section class="km-article-group"><h3>{CAT_NAME[c]}<small>{len(rows)}記事</small></h3>{photo("img:" + c)}<ul>{"".join(items)}</ul></section>')
    editorial = ''.join(
        f'<article><span class="km-eyebrow" aria-hidden="true">{eyebrow}</span><h3>{h3}</h3><p>{p}</p><a href="{href}">{label}</a></article>'
        for eyebrow, h3, p, href, label in EDITORIAL)
    purchase = ''.join(f'<a href="/{BY_ID[aid]["slug"]}/#{frag}">{label}</a>' for aid, frag, label in PURCHASE_LINKS)

    return f'''<!-- wp:html -->
<div id="ks-magazine" data-release="{RELEASE}">
<section class="km-pick" aria-labelledby="km-hero-title"><div class="km-pick-grid"><div class="km-pick-main"><div class="km-spine" aria-hidden="true"><strong>01</strong><span>はじめに</span></div><div class="km-hero"><img class="km-hero-image" src="{HERO_IMG}" width="842" height="495" alt=""><div class="km-hero-copy"><span class="km-tag">暮らしの道具を、納得して選ぶ</span><h1 id="km-hero-title">あなたの暮らしに、<br>合うものを。</h1><p><strong>選ぶ理由も、選ばない理由も。</strong><br>置き場所、使い方、残る手間。必要な条件を整理し、自分に合う候補を比較できます。</p><nav class="km-hero-links" aria-label="商品カテゴリ別の代表記事">{hero_links}</nav></div></div></div><div class="km-promos"><h2 class="km-promos-title">選び方の3ステップ</h2>{steps}</div></div><p class="km-disclosure">当サイトの比較記事（PR表示あり）には広告・アフィリエイトリンクが含まれます。掲載順・評価は報酬条件と切り離しています。<a href="/about-ad-policy/">運営・広告方針</a></p></section>
<section class="km-section" aria-labelledby="km-categories-title"><header class="km-section-head"><span aria-hidden="true">02</span><h2 id="km-categories-title">比較したい商品から選ぶ</h2><a href="/categories/">商品カテゴリから探す <span aria-hidden="true">⟶</span></a></header><p class="km-section-lead">スーツケース・食洗機・ロボット掃除機・ポータブル電源の各ページは、先に確かめる条件、条件から候補を見る、記事を選ぶ、購入前の確認の順に進めます。</p><nav class="ks-image-categories" id="ks-visual-categories" aria-label="比較したい商品から選ぶ" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,14rem),1fr));gap:16px">{''.join(cat_cards)}</nav><p class="km-note">カテゴリ画像はAI生成の編集イメージです。掲載商品の実物写真や設置例ではありません。</p></section>
<section class="km-section" aria-labelledby="km-purposes-title"><header class="km-section-head"><span aria-hidden="true">03</span><h2 id="km-purposes-title">いま困っていることを選ぶ</h2><a href="/purposes/">悩み・目的から探す <span aria-hidden="true">⟶</span></a></header><div class="km-features">{features}</div></section>
<section class="km-section" aria-labelledby="km-articles-title"><header class="km-section-head"><span aria-hidden="true">04</span><h2 id="km-articles-title">掲載記事の一覧</h2><a href="/updates/">最近更新したガイド <span aria-hidden="true">⟶</span></a></header><p class="km-section-lead">公開中の15本すべてです。PRは販売店への広告リンクを含む比較記事、食洗機のガイド5本（2026年9月9日公開）に広告リンクはありません。更新日は2026年9月12日時点の記録です。</p><div class="km-article-groups">{''.join(groups)}</div></section>
<section class="km-section" aria-labelledby="km-editorial-title"><header class="km-section-head"><span aria-hidden="true">05</span><h2 id="km-editorial-title">編集方針</h2><a href="/comparison-policy/">比較・編集方針 <span aria-hidden="true">⟶</span></a></header><div class="km-editorial">{editorial}</div></section>
<section class="km-section" id="home-purchase-check" aria-labelledby="home-purchase-check-title"><header class="km-section-head"><span aria-hidden="true">06</span><h2 id="home-purchase-check-title">購入前の最終確認</h2></header><p>候補が決まったら、商品名・構成、送料と必要付属品を含む総額、使う日までの納期、販売元と保証を確認しましょう。用途に必要な条件が分からない間は、購入を急がずメーカーへ確認してください。</p><nav class="ks-inline-links" aria-label="商品別の購入前確認">{purchase}</nav></section><p class="km-image-note">掲載画像はAI生成のデザイン案から切り出した暮らしのイメージであり、特定商品の外観・仕様・性能を示すものではありません。掲載する判断の根拠と確認日は、それぞれの記事でご確認ください。</p>
</div>
<!-- /wp:html -->
'''


# ---------------------------------------------------------------------------
# validation helpers
# ---------------------------------------------------------------------------
class Nodes(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.text = []
        self._stack = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)


def visible_chars(html: str) -> int:
    p = Nodes()
    p.feed(html)
    return len(re.sub(r'\s+', '', ''.join(p.text)))


def ids_in(html: str) -> list[str]:
    return re.findall(r'\bid="([^"]+)"', html)


def main() -> int:
    check_only = '--check-only' in sys.argv
    outputs = {
        'categories': categories_html(), 'purposes': purposes_html(), 'guides': guides_html(),
        'comparisons': comparisons_html(), 'updates': updates_html(),
        'travel': category_hub_html('travel'), 'cleaning': category_hub_html('cleaning'),
        'preparedness': category_hub_html('preparedness'),
    }
    for slug in PURPOSE_HUBS:
        outputs[slug] = purpose_hub_html(slug)
    outputs['home'] = home_html()

    # --- style rules
    for slug, html in outputs.items():
        assert '～' not in html, slug
        assert re.search(r'。 [^<]', html) is None, (slug, '句点+半角スペース')
        assert 'STORIES' not in html and '特集' not in html and 'ヒント' not in html, slug

    # --- CH-07: no identical blurb per article across hubs
    seen: dict[tuple[str, str], str] = {}
    for slug, html in outputs.items():
        if slug == 'home':
            continue
        for m in re.finditer(r'<article>(.*?)</article>', html, re.S):
            block = m.group(1)
            href = re.search(r'href="/([a-z0-9-]+)/', block)
            ps = re.findall(r'<p>(.*?)</p>', block)
            if not href or href.group(1) not in BY_SLUG or not ps:
                continue
            key = (href.group(1), re.sub(r'<[^>]+>', '', ps[0]))
            if key in seen:
                raise SystemExit(f'CH-07 duplicate blurb: {key[0]} in {seen[key]} and {slug}')
            seen[key] = slug

    # --- ids / anchors
    known_slugs = {r['slug'] for r in json.loads((ROOT / 'changes/wordpress-direct-publish-v1/articles.v1.json').read_text())['articles']}
    live_ids: dict[str, set[str]] = {}
    for a in ARTICLES:
        gen = ART / f'{a["slug"]}.html'
        ids = set()
        if gen.exists():
            ids |= set(ids_in(gen.read_text()))
        ev = EVIDENCE / f'article-{a["slug"]}.html'
        if ev.exists():
            ids |= set(ids_in(ev.read_text()))
        live_ids[a['slug']] = ids
    policy_ids = {s: set(ids_in((ART / f'{s}.html').read_text())) for s in ('comparison-policy', 'about-ad-policy', 'kitchen')}
    link_rows = []
    for slug, html in outputs.items():
        ids = ids_in(html)
        dup = [i for i in set(ids) if ids.count(i) > 1]
        assert not dup, (slug, dup)
        for m in re.finditer(r'<a\b([^>]*)>(.*?)</a>', html, re.S):
            href = re.search(r'href="([^"]+)"', m.group(1)).group(1)
            text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            if href.startswith('#'):
                assert href[1:] in ids, (slug, href)
                continue
            mm = re.fullmatch(r'/(?:([a-z0-9-]+)/)?(?:#([A-Za-z0-9_-]+))?', href)
            assert mm, (slug, href)
            target, frag = mm.group(1), mm.group(2)
            tslug = target or 'home'
            assert tslug in known_slugs, (slug, href)
            if frag:
                if tslug in outputs:
                    tids = set(ids_in(outputs[tslug]))
                elif tslug in live_ids:
                    tids = live_ids[tslug]
                else:
                    tids = policy_ids.get(tslug, set())
                assert frag in tids, (slug, href)
            link_rows.append((slug, href, text))

    # --- CH-02 for home
    from collections import Counter, defaultdict
    # CH-02: 同一 URL (fragment 違いは別 URL 扱い) への重複は各 2 本以下、ラベルは一致
    home_links = [(h, t) for s, h, t in link_rows if s == 'home' and not h.startswith('#')]
    per_url = Counter(u for u, _ in home_links)
    labels = defaultdict(set)
    for u, t in home_links:
        labels[u].add(t)
    for u, n in per_url.items():
        assert n <= 2, (u, n)
        assert len(labels[u]) == 1, (u, labels[u])

    if not check_only:
        for slug, html in outputs.items():
            (ART / f'{slug}.html').write_text(html, encoding='utf-8')
        (ROOT / 'changes/wordpress-local-preview-v1/content/home.html').write_text(outputs['home'], encoding='utf-8')

    # --- reports
    print('== CH-01 purpose hub visible chars')
    for slug in PURPOSE_HUBS:
        print(f'  {slug}: {visible_chars(outputs[slug])}')
    print('== other hubs visible chars')
    for slug in ('categories', 'purposes', 'guides', 'comparisons', 'updates', 'travel', 'cleaning', 'preparedness'):
        print(f'  {slug}: {visible_chars(outputs[slug])}')
    print('== home images', len(re.findall(r'<img\b', outputs['home'])), 'links', len(home_links))
    print('== home per-url', dict(per_url))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
