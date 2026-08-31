# 受入チェックリスト

実行日、実行者、対象コミット、結果をリリース記録または Git の変更履歴に残します。

| ID | 関連要件 | 確認内容 | 合格条件 |
| --- | --- | --- | --- |
| AC-001 | RQ-001–RQ-004 | SPA の一覧、履歴展開、メモ、各モーダル | ページ遷移なしで主要操作ができ、履歴が親行のサブレコードとして見える。プロジェクトメモとバージョンメモは、それぞれの情報行から分離された専用2行目で確認できる。 |
| AC-002 | RQ-005、RQ-006 | 初回選択と2回目の自動検索 | 初回は選択を要求し、再訪後は権限があればモーダル表示時に検索する。拒否/失効時は再選択できる。 |
| AC-003 | RQ-007、RQ-008 | ディレクトリ登録と ZIP 登録 | flat ZIPを登録できる。UUIDラッパーが1階層ある旧ZIPも入力できるが、保存・download結果はどちらも中身だけがZIP直下にあるflat形式になる。 |
| AC-004 | RQ-009 | 復元と上書き確認 | 空き先へUUIDフォルダーを1回だけ作って復元でき、二重UUIDラッパー入力は拒否され、同名フォルダーがある場合は確認なしに上書きしない。 |
| AC-005 | RQ-010 | 共有表示と論理削除 | 別ブラウザーから同じ一覧が見え、削除後も ZIP 実体が残る。 |
| AC-006 | RQ-011 | 再起動と再索引 | コンテナ再作成後も一覧/ZIPが残り、DB 初期化後にアーカイブから索引を再構築できる。 |
| AC-007 | RQ-012 | bind mount 差し替え | `compose.storage.example.yaml` でLinuxホスト上のマウント済み保存先へ切り替えて登録/取得できる。 |
| AC-008 | RQ-013 | LAN 公開 | Windows端末からLinuxホストの許可済みポートへ接続できる。 |
| AC-009 | RQ-014 | HTTPS とブラウザー API | 信頼済み証明書の HTTPS URL でディレクトリ選択、再権限確認、書き戻しが動く。 |
| AC-010 | RQ-015 | 悪意ある ZIP | `../`、絶対パス、リンク、過大展開を含む ZIP が拒否され、保存領域外へ書き込まれない。 |
| AC-011 | RQ-011 | バックアップ/復元 | DB dump とアーカイブバックアップから別環境へ復元し、チェックサムが一致する。 |
| AC-012 | RQ-016 | 2 JSON編集と新版作成 | 対象版を取得し、root-level `*.gprj` と `layout.lay` の各1箇所を編集するとバージョンが1つ増える。新版downloadでは両JSONの指定値が変わり、`*.set`、サブディレクトリを含む他entryのpathとpayload bytesが旧版と完全一致する。旧版downloadも編集前のまま残る。 |
| AC-013 | RQ-016 | 編集境界と失敗時の不変性 | `*.gprj`/`layout.lay` が不正JSON、JSON object以外、または上限超過の場合は、片方だけを変更したZIPや新版レコードを作成しない。 |

## 構成チェック

```powershell
docker compose config
docker compose build
docker compose up -d
docker compose ps
docker compose logs --tail 100 backend web db
```

HTTPS 構成は次でも検証します。

```powershell
docker compose -f compose.yaml -f compose.https.yaml --profile https config
docker compose -f compose.yaml -f compose.https.yaml --profile https up -d --build
```

ZIPレイアウトのAPI統合確認は、使い捨ての検証環境に対して実行します。ランダムUUIDのレコードは論理削除されますが、仕様どおりZIP実体は残ります。

```bash
python3 scripts/verify_zip_layout.py --base-url http://localhost:8080
```
