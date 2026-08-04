# RAOS Codex master kickoff

このRAOS Complete Design Packageを展開し、最初に以下を読んでください。

1. `00_master/RAOS_MASTER_README_v1.0.md`
2. `08_codex/AGENTS.md`
3. `01_integration/RAOS_07_integration_design_v1.0.md`
4. `01_integration/RAOS_07_canonical_decisions_v1.0.yaml`
5. `01_integration/RAOS_07_open_decisions_v1.0.yaml`
6. `07_backlog/RAOS_13_story_backlog_v1.0.yaml`
7. `05_test/RAOS_11_test_suite_catalog_v1.0.yaml`

今回は **ST-0001: Import canonical design package** だけを実装してください。

コード変更前に、次の六点を提示してください。

1. 読み込んだ正本ファイルとVersion
2. Storyの目的と対象外
3. 検出した矛盾・不足・Open Decision
4. 変更予定ファイル
5. Test計画
6. 状態Registryをどこまで更新できるか

禁止事項:

- 他StoryのBusiness logic実装
- Proposal SQL/YAMLの直接適用
- Production credential、Cloud apply、外部公開
- 設計差分の黙示的解決
- 未実行TestのPASS扱い
- 上位設計ファイルの無断上書き

完了時は、PR本文として使用できる形で次を出してください。

- Summary
- Story/Requirement/Design IDs
- Files changed
- Tests run and exact results
- Security/privacy/a11y impact
- Implemented vs not executed
- Status registry changes
- Follow-up stories
