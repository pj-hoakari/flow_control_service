# flow_control_service

## 設計ドキュメントの参照

本リポジトリにおける開発は，別リポジトリ `KasumiMercury/pj34-poc-root` の `design/flow_control/` 配下にある設計ドキュメント群を上位仕様として参照し，それに基づいて行う

### 参照先

- リポジトリ: [`KasumiMercury/pj34-poc-root`](https://github.com/KasumiMercury/pj34-poc-root)
- ディレクトリ: `design/flow_control/`

### 設計ドキュメント一覧（v1）

上位文書から順に参照すること。各ドキュメントの冒頭に上位文書の指定がある。

1. `flow_control_requirements_v1.md` — 要件定義（最上位）
2. `flow_control_module_design_v1.md` — モジュール設計（Detection / Forecasting / DetourRouting / Optimization / FeedbackExtractor / RequestHandler の責務、I/O スキーマ、擬似コード）
3. `flow_control_extension_roadmap_v1.md` — 拡張ロードマップ（未解決事項と段階的拡張手順）
4. `flow_control_external_integration_v1.md` — 外部マイクロサービス連携仕様
5. `flow_control_math_approach_v1.md` — 数理アプローチ補助（MILP 定式化、需要予測モデル等の数理詳細）

### 開発時の遵守事項

- 新機能の実装・既存機能の変更を行う前に，該当箇所に対応する設計ドキュメントを確認すること
- 設計ドキュメントと実装に乖離が生じた場合は，独自判断で実装を進めず，設計側を更新するか，設計に合わせて実装するかを確認すること
- モジュール責務の境界（Detection / Forecasting / DetourRouting / Optimization / FeedbackExtractor）は設計書に従い，跨いだ実装を行わないこと
- 本サービスは「ステートレスな汎用最適化エンジン」であり，テナント管理・永続化・スケジューリング・データ集約は責務外であることを常に意識すること
