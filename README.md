# Hioki GENNECT Space Project Data Manager

GENNECT Space のプロジェクトフォルダーを ZIP として共有保存し、版管理して必要なバージョンを元のデータディレクトリへ戻す、ログイン不要の社内向け SPA です。プロジェクト一覧を主画面に置き、履歴はサブレコード、登録・編集・設定・削除・復元はモーダルで扱います。

## 必要環境

- Windows 10/11 と Docker Desktop（Compose v2）
- ディレクトリ検索/書き戻しには Chrome または Edge の現行版
- 初回選択対象: `%APPDATA%\gennect-space\data`

ブラウザーのセキュリティ制約により、アプリが上記パスを無断で開くことはできません。初回は利用者がディレクトリピッカーで選択します。アプリはディレクトリハンドルをブラウザー内に保存し、2回目以降は登録モーダルを開いた時点で権限確認と検索を行います。権限が失効した場合は再選択が必要です。

## 起動

PowerShell でリポジトリへ移動し、設定例をコピーして起動します。

```powershell
Copy-Item .env.example .env
docker compose up -d --build
docker compose ps
```

ブラウザーで `http://localhost:8080` を開きます。停止は `docker compose down` です。データを残すため、通常運用では `down -v` を実行しないでください。

初回起動後の流れは次のとおりです。

1. 設定または新規登録モーダルから `%APPDATA%\gennect-space\data` を選択します。
2. UUID（例: `de795586-5cdb-4ca9-a472-938a1fbfb341`）のフォルダー内にある `*.gprj` がプロジェクト名として一覧化されます。
3. 対象を登録すると UUID フォルダー全体が ZIP 化され、新しいバージョンとして共有保存されます。
4. 代わりに ZIP ファイルを新規登録モーダルへ直接指定できます。
5. 履歴から復元を選ぶと ZIP が展開され、許可済みデータディレクトリへ戻ります。同じ UUID フォルダーがあれば、上書き確認後に続行します。

削除操作は論理削除です。通常一覧からレコードは除外されますが、アーカイブ ZIP 自体は削除しません。また、認証や利用者別のアクセス制御はなく、サーバーへ到達できる利用者には全登録データが見えます。

## LAN と HTTPS

HTTP は既定で `0.0.0.0:8080` に公開されるため、Windows Firewall で許可すれば `http://<WindowsホストのIP>:8080` から接続できます。ただし File System Access API は secure context が必要です。`http://localhost` は利用できますが、別端末からの HTTP 接続ではディレクトリ機能が利用できないため HTTPS を使ってください。

動作確認用の自己署名証明書は Docker だけで生成できます。

```powershell
.\scripts\New-DevCertificate.ps1 -DnsName "your-hostname"
docker compose -f compose.yaml -f compose.https.yaml --profile https up -d --build
```

その後 `https://your-hostname:8443` を開きます。自己署名証明書は各クライアントで信頼設定が必要です。社内 CA または正式な証明書がある場合は `.env` の `TLS_CERT_FILE` と `TLS_KEY_FILE` にホスト上のファイルを指定します。証明書の SAN は利用するホスト名に一致させてください。

公開範囲をローカル PC のみに戻す場合は `.env` で `HTTP_BIND_ADDRESS=127.0.0.1` と `HTTPS_BIND_ADDRESS=127.0.0.1` を指定します。社内 LAN 公開では、推測しにくいパスをセキュリティ対策と考えず、Windows Firewall、VLAN、VPN 等で到達元を制限してください。

## 保存先とネットワークドライブへの移行

既定の永続領域は次の named volume です。

- `project_archives`: バージョン ZIP
- `postgres_data`: 一覧、バージョン、論理削除などの索引

backend からは常に `/data/archives` として見えるため、保存先を変えてもアプリ設定は変わりません。Windows のローカル/ネットワーク保存先へ変更する例:

```powershell
$env:ARCHIVE_HOST_PATH = "D:/HiokiProjectArchives"
docker compose -f compose.yaml -f compose.storage.example.yaml up -d --build
```

UNC パスを使う場合は Docker Desktop がその共有へアクセスできること、共有が常時マウントされていること、Docker Desktop 実行アカウントに読み書き権限があることを先に確認してください。切り替え前に既存 `project_archives` の内容を新しい保存先へコピーし、ファイル数とチェックサムを照合します。

## バックアップと復旧

DB バックアップ（出力先はカレントディレクトリ）:

```powershell
docker compose exec db pg_dump -U projectdata -d projectdata -Fc -f /tmp/projectdata.dump
docker compose cp db:/tmp/projectdata.dump ./projectdata.dump
```

DB 復元:

```powershell
docker compose cp ./projectdata.dump db:/tmp/projectdata.dump
docker compose exec db pg_restore -U projectdata -d projectdata --clean --if-exists /tmp/projectdata.dump
```

アーカイブ volume のバックアップ例:

```powershell
docker run --rm -v hioki-projectdata-manager_project_archives:/source:ro -v "${PWD}:/backup" alpine tar czf /backup/project_archives.tgz -C /source .
```

bind mount 運用ではホスト/ファイルサーバー側のバックアップを利用します。アーカイブキーにはプロジェクトUUID、8桁のバージョン番号、SHA-256が入り、プロジェクト名は ZIP 内の `*.gprj` から再取得できます。DB 再索引は管理 API を呼び、完了後に件数とチェックサムを照合します。

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8080/api/admin/rebuild-index
```

DB を作り直す環境では `.env` の `REBUILD_INDEX_ON_STARTUP=true` により backend 起動時にも再索引できます。通常運用は `false` のままとし、意図しない全件走査を避けます。

再索引で復元するのはプロジェクト名、UUID、バージョン番号、ZIP の場所、サイズ、SHA-256 などの最低限の索引です。説明、版メモ、論理削除日時など DB だけにある運用情報は戻らないため、通常は DB dump も保管してください。

DB パスワードを `.env` で変更した場合、上記コマンドの `-U`/`-d` も対応する値へ変更します。DB dump とアーカイブは同じ時点の組として保管するのが安全です。

## 運用確認

```powershell
docker compose ps
docker compose logs --tail 200 web backend db
docker compose config
```

アップデートはバックアップ後に `docker compose up -d --build` を実行します。構成と受入手順は [簡易要件](docs/requirements.md)、[簡易設計](docs/architecture.md)、[ロードマップ](docs/roadmap.md)、[受入チェック](docs/acceptance-checklist.md) を参照してください。

## 注意事項

- `.env`、秘密鍵、DB dump を Git に追加しないでください。
- ZIP 展開時は `..`、絶対パス、リンク、展開容量超過を拒否します。不明な ZIP を手作業で volume へ置かないでください。
- `docker compose down -v` は DB とアーカイブの named volume を削除対象にします。データ破棄の明示的な承認がない限り実行しないでください。
- File System Access API の実装・権限保持はブラウザー依存です。Firefox/Safari はこのワークフローの対象外です。
