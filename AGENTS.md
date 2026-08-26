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

## 開発 workflow

- `make setup`: lock 済み dependency を cache 利用で同期する。
- `make generate`: 変更の affected owner を依存順に生成する。
- `make check`: affected generator drift と静的検査を実行する。
- `make fast`: merge-base との差分に対する focused check/test を実行する。
- `make final`: 全 generator、全 local suite、DB/Storage、secret、aggregate check を実行する。
- 開発中は専用 branch へ checkpoint push し、最後に integration PR を1本作る。
  Final Integration が green なら人間承認なしで自動 merge する。
- Preflight、Story ごとの ExecPlan/worklog/debt log は必須ではない。最終 PR に関連 Story IDs、
  変更概要、検証結果、external/live 未実行事項を一度だけ記録する。
