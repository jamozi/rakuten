# Goal prompt: RAOS implementation-first local completion

Copy the objective below into the Goal feature without a token budget. The Goal
is intentionally broader than one interactive turn but narrower than release
or production authority.

```text
/home/minami/rakuten のRAOSを、repository owner承認済みの
docs/execplans/RAOS-IMPLEMENTATION-FIRST.md に従って、実装優先で最後まで
自律実行してください。

最終目的は、canonical backlogの全機能について、未解決の外部判断があるものは
安全なinterface/recorded fixture/fake adapter/disabled feature flagまで含めてローカル
code completeにし、その後に詳細監査、review、全local test、owner generator、
provenance closureを一括実行して、LOCAL_INTEGRATION_COMPLETEへ到達することです。
Production readiness、live provider、credential、staging、publication、release、
deployment、production writeは目的外で、実行も主張もしないでください。

開始時に必ず行うこと:

1. `pwd -P`とgit rootが正確に/home/minami/rakutenであることを確認する。
2. root AGENTS.md、docs/canonical/08_codex/AGENTS.md、
   docs/execplans/RAOS-IMPLEMENTATION-FIRST.md、
   docs/worklogs/RAOS-IMPLEMENTATION-DEBT.md、canonical backlog/status/open decisionsを読む。
3. git branch/HEAD/status/diff、外部Codexのdirty paths、local evidence、残Story、依存graphを
   live再計算する。過去の件数を無検証で使わない。
4. 既存の変更をuser/external owner/ST-0703/自分のpolicy変更に分類する。所有不明の変更を
   reset、checkout、clean、delete、stage、revertしない。
5. implementation-worker設定変更後は古いagentを再利用せず、freshなproject
   implementation_workerを使用する。root agentが唯一のintegration ownerとなる。

実行方針:

- W0からW6までcanonical dependenciesがreadyな順に進める。macro-Wave内でも依存を
  飛ばさない。
- 1 commitは1 Storyまたは明示したmechanical integration sliceにする。
- shared worktreeのwriterは常に1 agentだけにする。並列化はread-only調査、または
  rootが検証したisolated worktreeとdisjoint ownershipだけに限定する。
- reversibleな実装詳細は既存repository patternの最も近いものを採用し、provisional
  assumption/debtとして記録して続行する。routineな確認をuserへ求めない。
- Open Decisionの実値は推測しない。安全なPort、schema、fake/recorded adapter、synthetic
  fixture、validation、default-disabled activationを実装して次へ進む。
- Pro adviceや新しいhandoffを、reversible local choice、manifest hash drift、affected test
  drift、通常のreview論点ごとに要求しない。それらはWave末尾reviewへ送る。
- generated fileは手編集しない。active implementation中のtransitive driftはdebt ledgerへ
  記録し、source freeze後にowner generatorをtopological orderで一括実行する。
- focused runtime/contract failureはそのslice内で直す。unrelated suite、transitive
  provenance、formal/live/environment failureはsanitized evidence付きdebtとして継続する。
- docs/worklogs/RAOS-IMPLEMENTATION-DEBT.mdのIDは削除・再利用せず、追加またはclosure logで
  更新する。

hard stopは次だけです:

1. Secret/credential/PII/production data/raw prompt/prohibited provider materialが必要。
2. external write、publish、live provider、staging、release、deployment、production apply/writeが必要。
3. irreversible/destructive migrationまたはdata deletionが必要で、exact approval/recoveryがない。
4. auth/authz/human approval/public isolation/editorial-finance separation/disclosure/
   kill switch/security boundaryを弱める必要がある。
5. unresolved Open Decisionにsafe interface-only pathがなく、実値選択なしでは一切進めない。
6. active ownership collisionがあり、他者の変更を壊さず分離できない。

hard stop以外では停止しないでください。test failure、audit finding、manifest/provenance drift、
設計文書に列挙されていないreversible path、Pro unavailable、formal evidence未実行、時間の長さ、
作業量の多さはblocked理由ではありません。dependency-independentな次作業、実装修正、debt記録、
別Wave準備のいずれかを続けてください。同一の真のhard stopがgoal turnをまたいで3回継続し、
他に意味のある作業がない場合だけblockedを使用してください。

各sliceのminimum fast checks:

- changed sourceのparse/import/compile/type相当
- changed behaviorとcritical negative pathのfocused test
- stableなdirect owner generator check
- trust boundary変更時のsensitive-data/static check
- `git diff --check`とowned-path diff review
- skipped affected/formal/live checksの明示

各macro-Wave末尾:

- source/debt snapshotをcommitする
- feasibleなowner generationとaffected suitesを一度実行する
- introduced runtime/contract failureを修正する
- non-hard debtだけを明示carryする
- dedicated implementation branchへcheckpoint pushする
- routineな再承認を待たず次Waveへ進む

全Storyのcode completion後は新機能追加を止め、final audit/fix phaseへ移ること。そこで:

- source-to-owner dependency graphを再構築
- owner generatorを依存順に再生成しno-write check
- ST-0102 pin/ST-0301+ fan-out、ST-1203/1204、secret fixture baselineを含む全introduced debtをclosure
- canonical import/workspace drift
- isolated Story suitesとaffected integration suites
- Python/Node lint/format/type/static/security
- migration/database/runtime fixture checks（localで安全に実行できる範囲）
- UI/accessibility/visual checks（実装対象とlocal環境で可能な範囲）
- independent code review/security review
- final base-to-branch scope、generated ownership、secret、large artifact、diff clean audit

を実行し、local mandatory gateがgreenになるまで修正と再試験を繰り返してください。

Git運用:

- unrelated dirty filesをcommitへ含めない
- commitをbisectableに保つ
- 最大10 Story sliceまたはmacro-Wave末尾ごとにcheckpoint commit/push
- force push、history rewrite、merge、release、publication、deploymentはしない
- push失敗はlocal commitを保持して再診断し、実装自体を捨てない

各goal turnの短い進捗報告には、完了Story IDs、LOCAL_CODE_COMPLETE数、直近commit、
fast checks、open/closed debt、hard stop有無、次のdependency-ready sliceを含めてください。
local結果をformal CI/TST、live validation、staging、deployed、production-readyへ昇格しないでください。

Goalをcompleteにできるのは、次をすべて満たす場合だけです:

- live再計算した全残Storyがlocal implementation済み、または外部decisionのため最大安全な
  disabled/interface-only実装済み
- 全introduced debtがclosed
- 全generated artifactがowner commandで再現可能
- 全locally executable mandatory test/audit/reviewがgreen
- unrelated/user/external-Codex変更をfinal commitsへ混入していない
- branchがpush済み
- formal/live/staging/release/productionの未実行境界を最終報告に明示

大量の作業であることや残budgetを理由に完了扱いしないでください。自動継続を使い、上記の
complete条件または真のhard stopまで実行を続けてください。
```
