# AGENTS.md — RAOS 開発ルール

## 目的と優先順位

- 最短で安全に実装を進める。Story ID は要求・依存・status の追跡に使うが、
  commit、branch、PR、実装 slice の境界にはしない。
- Product requirement は `docs/canonical/**` を正本とする。import 済みの canonical package
  と checksum は変更しない。Canonical の旧 Codex workflow に含まれる PR 分割、preflight、
  human-review 手順は現行の repository 開発 workflow には適用しない。
- 矛盾しない可逆的な実装詳細は、現行 contract、既存 code/test、最小変更の順で決めて進む。
  未決の実値は作らず、interface、fake/recorded adapter、disabled default まで実装する。

## 継続的な開発権限

- Repository 内の design、code、refactor、test、migration code、fixture、generator、docs、
  status 修正、および通常の GitHub 開発操作は継続承認済みである。
- edit、test、generate、stage、commit、push、PR 作成・更新、branch protection 更新、
  required CI 合格後の merge は継続承認の範囲で進め、別個の開発確認を挟まない。
- Security、migration、architecture、cross-module 変更も通常の local development とする。
  問題は automated test、diff review、最終 integration CI で検出し、修正して続ける。
- Pro は user が明示した場合だけ使える任意の助言機能であり、利用不能でも開発を止めない。

## 唯一の停止条件

次のいずれかを実際に行う必要がある場合だけ停止する。

1. GitHub 開発操作を除く live 外部作用: credential の入力・開示、規約同意、支出、
   live provider/user-facing write、publication、staging、deployment、release、Production、
   live policy または kill-switch の変更。
2. 回復不能な操作: data 削除、不可逆 migration/data transformation の適用、force push、
   default branch/history の破壊。

これらの port、migration code、rollback、fixture、simulation、test、draft artifact の local
実装は停止条件ではない。Test failure、audit finding、設計の不足、作業量、hash drift、
Pro 不在、formal/live evidence 未実行も停止条件ではなく、修正または正確な報告の対象とする。

## 実装規律

- 既存の user/他 agent の変更を保持し、無関係な dirty path を編集・stage・削除しない。
- `docs/canonical/**`、`docs/upstream/**`、`zip/**` は immutable baseline として扱う。
- Generated file は owner generator から更新する。Build input の digest 固定は canonical package、
  dependency lock、container image に限定し、通常の tracked source や開発文書には使わない。
- Runtime data integrity、generated output、release provenance の content hash は維持するが、
  approval token や開発停止条件にはしない。
- Secret、credential、personal/production data、raw prompt、prohibited provider material を読出し、
  log、commit、fixture、回答へ含めない。
- Product の auth/authz、public/internal isolation、publication、editorial/finance、disclosure、
  kill-switch invariant は code と test で維持する。Local result を formal CI、staging、release、
  Production evidence と呼ばない。

## WordPress ローカル確認ルール

- 記事・固定ページ、ホームページ、子テーマ、テンプレート、CSS、表示系プラグインの変更は、最初に `changes/wordpress-local-preview-v1/` の非本番データとローカル WordPress へ反映し、本番を試作・初回確認の場にしない。
- 本番送付・公開提案前に `make wordpress-preview-up`、必要なら `make wordpress-preview-sync`、`make wordpress-preview-check` を実行し、ローカル URL と対象 viewport のスクリーンショットを確認する。
- 未確認または失敗中は本番送付・公開提案・テーマ／プラグイン反映を行わない。合格は本番承認ではなく、MCP、別人承認、proposal、hash/precondition、kill switch、default-off gate を別途満たす。
- 最終報告には確認 URL、検査、スクリーンショット保存先、本番送付・公開の実施／未実施を記す。

## WordPress MCP 優先ルール

- `kurashinoshirube.com` の状態確認と記事・固定ページ・子テーマ・プラグイン作業は、対応能力がある限り他経路より先に project MCP の `wordpressEditor`／`wordpressDeployment` を実際に呼び、設定や過去結果だけで live 状態を推測しない。
- 状態確認、一覧・取得、下書き更新、公開提案は `wordpressEditor`、別人が wp-admin 承認済みの公開反映、追跡テーマ／固定pluginの提案・反映、通信断回復は bounded `wordpressDeployment` を使う。
- MCPで完結しない初回bootstrap、明示UI検証、障害診断だけを例外とし、先に `codex mcp list` とread-only statusを確認して利用不能理由と代替経路を報告する。
- MCP優先は権限を広げない。別人承認、未失効proposal、hash/precondition、idempotency、kill switch、用途別default-offを維持し、自己承認、credential開示、gate有効化、任意command/PHP/SQL/URL実行を行わない。

## 開発 workflow

- 通常の確認は `make fast` に集約する。変更箇所の静的検査、関連 test、affected generator
  drift を確認し、`check → fast → final` を毎回連続実行しない。
- `make setup` は環境作成・依存変更時、`make generate` は生成入力変更時に実行する。
  `make check` は静的検査のみ、`make final` は任意の全体診断であり、local 完了条件ではない。
- 差分選択は `scripts/raos_build.py --base <ref> plan --json` で確認できる。通常コードの
  import consumer、generator owner、component route、変更 test 自身を選択する。
  未対応のコード・設定、lock、共通検査基盤の変更は全件へ戻す。
- 通常 PR は影響範囲と重要回帰・secret 検査、毎日03:00 JSTと手動 CI は全件検査を行う。
  Pyright は定期・手動の全件 CI に集約し、通常の Python 型検査は mypy を使う。
- Draft PR は重い検査を省き、ready 時に実行する。専用 branch へ checkpoint push し、
  integration PR は1本にまとめる。選択された検査がすべて成功した `Final Integration`
  を条件に自動 merge する。選択外と失敗・cancel・必要な検査の未実行は区別する。
- 修正後は失敗した検査を先に実行し、次に影響範囲を確認する。失敗や変更がなければ同じ
  検査を繰り返さない。test は振る舞い・不具合再現を検証し、文書行数や総件数を固定しない。
- 新規 test は原則並列実行し、共有 checkout や外部 process state を使う場合だけ
  `serial` を明示する。DB／Storage は専用 partition で実行する。
- 通常 PR の CI 中央値10分以内を改善目標とし、新しい停止条件にはしない。定期 CI の失敗は
  修正対象として結果を残す。独自の証跡台帳、自動 revert、一律の開発停止は追加しない。
- Preflight、Story ごとの ExecPlan/worklog/debt log は必須ではない。最終 PR に関連 Story IDs、
  変更概要、検証結果、external/live 未実行事項を一度だけ記録する。
