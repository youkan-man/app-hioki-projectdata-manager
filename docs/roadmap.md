# 簡易ロードマップ

厳格な Baseline、独立レビュー記録、文書ごとのリビジョン固定は省略します。状態、担当境界、要件ID、受入確認だけを Git で追跡します。

| Locator | 作業 | 対象 | 依存 | 状態 | 備考 |
| --- | --- | --- | --- | --- | --- |
| RM-001#S-01 | FastAPI、PostgreSQL モデル、ZIP 保存・再索引 API | RQ-008–RQ-012、RQ-015 | なし | 完了 | pytest 6件、compileall 成功 |
| RM-001#S-02 | React SPA、一覧/履歴、モーダル、ディレクトリ検索/復元 | RQ-001–RQ-010、RQ-014 | API 契約 | 完了 | Vitest 6件、production build、preview HTTP 200 成功 |
| RM-001#S-03 | Docker、nginx、永続 volume、HTTPS、Windows 運用手順 | RQ-011–RQ-014 | frontend/backend の起動契約 | 待機 | YAML 構文確認済み。実行環境に Docker CLI がなく実ビルド待ち |
| RM-001#S-04 | 統合ビルドと受入確認 | 全要件 | S-01、S-02、S-03 | 待機 | アプリ単体検証済み。Docker/Windows/Chromium の実機受入れ待ち |

## 完了条件

- Docker Compose で全サービスが起動し、SPA と `/api` が同一 origin で利用できる。
- 通常系に加え、不正 ZIP、権限喪失、重複復元、DB 再構築の失敗経路を確認する。
- [受入チェック](acceptance-checklist.md) の必須項目を実行し、未確認項目をリリース時に残さない。
- 意味のある仕様変更では該当 RQ/D と受入項目を同じ変更で更新する。
