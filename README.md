# Hioki GENNECT Space Project Data Manager

GENNECT Space のプロジェクトフォルダーを ZIP として共有保存し、版管理して必要なバージョンを元のデータディレクトリへ戻す、ログイン不要の社内向け SPA です。プロジェクト一覧を主画面に置き、履歴はサブレコード、登録・編集・設定・削除・復元はモーダルで扱います。

## 必要環境

- Linux Dockerホスト（Docker Engine、Compose v2）
- Windows 10/11 クライアント
- ディレクトリ検索/書き戻しには Chrome または Edge の現行版
- 初回選択対象: `%APPDATA%\gennect-space\data`

ブラウザーのセキュリティ制約により、アプリが上記パスを無断で開くことはできません。初回は利用者がディレクトリピッカーで選択します。アプリはディレクトリハンドルをブラウザー内に保存し、2回目以降は登録モーダルを開いた時点で権限確認と検索を行います。権限が失効した場合は再選択が必要です。

## 起動

Linux Dockerホストでリポジトリへ移動し、設定例をコピーして起動します。

```bash
cp .env.example .env
docker compose --env-file .env up -d --build
docker compose --env-file .env ps
```

ブラウザーで `http://localhost:8080` を開きます。停止は `docker compose --env-file .env down` です。データを残すため、通常運用では `down -v` を実行しないでください。`.env`を変更した場合は、上記の`up -d`またはHTTPS起動スクリプトを再実行してコンテナを再作成します。

初回起動後の流れは次のとおりです。

1. 設定または新規登録モーダルから `%APPDATA%\gennect-space\data` を選択します。
2. UUID（例: `de795586-5cdb-4ca9-a472-938a1fbfb341`）のフォルダー内にある `*.gprj` がプロジェクト名として一覧化されます。
3. 対象を登録すると UUID フォルダーの中身だけが ZIP 化され、新しいバージョンとして共有保存されます。ZIP直下には `*.gprj` とプロジェクト内のファイル/サブディレクトリが置かれ、UUIDフォルダー自体は入りません。
4. 代わりに ZIP ファイルを新規登録モーダルへ直接指定できます。正規形式は中身がZIP直下にあるflat形式です。移行互換としてUUIDフォルダーが1階層だけ付いた旧ZIPも入力できますが、保存時にflat形式へ正規化されます。
5. 履歴から復元を選ぶと、許可済みデータディレクトリ内にUUIDフォルダーを1回だけ作り、その中へZIP直下の中身を展開します。`UUID/UUID` の二重ディレクトリは作りません。同じ UUID フォルダーがあれば、上書き確認後に続行します。

削除操作は論理削除です。通常一覧からレコードは除外されますが、アーカイブ ZIP 自体は削除しません。また、認証や利用者別のアクセス制御はなく、サーバーへ到達できる利用者には全登録データが見えます。

## プロジェクトJSONの編集

保存済みバージョンを基に、ZIP直下の単一 `*.gprj` と `layout.lay` に含まれる2つのJSONを編集して新版を作成できます。編集元バージョンは上書きされず、履歴とZIPはそのまま残ります。

編集対象外のバイナリ `*.set`、画像、計測データ、サブディレクトリ内ファイル、未知拡張子は、entry pathとpayload bytesを新版へそのまま引き継ぎます。ZIPの再作成に伴う圧縮方式、entry順序、更新日時などのコンテナメタデータは変わる場合があります。

LR8450 `.set` は機種・版情報と完全性情報らしき独自ヘッダーを持ち、公開された再生成仕様を確認できないため、opaque binaryとして扱います。判断根拠は [LR8450 `.set` 公開仕様調査](docs/lr8450-set-format-research.md) にまとめています。

`*.gprj` または `layout.lay` がUTF-8 JSONとして解析できない場合や編集指定が不正な場合は、片方だけを更新せず、新しいバージョンを作成しません。

## LAN と HTTPS

HTTP は既定でLinuxホストの `0.0.0.0:8080` に公開されます。ただし File System Access API は secure context が必要なため、別端末のWindowsブラウザーからはHTTPSを使ってください。

`.env`の`PUBLIC_IP`を、Windowsから実際にアクセスするLinuxホストのIPに設定します。この値が証明書のCNとIP SANの正です。`PUBLIC_DNS_NAMES`にはカンマ区切りで追加のDNS SANを設定できます。

```dotenv
PUBLIC_IP=192.168.1.100
PUBLIC_DNS_NAMES=localhost,hioki-manager.example.local
```

証明書生成、`.env`の証明書パス設定、Compose起動、HTTPS health checkは次の1コマンドで行えます。

```bash
chmod +x scripts/enable-linux-https.sh
./scripts/enable-linux-https.sh --start
```

起動スクリプトは実行ディレクトリに関係なく、リポジトリ直下の`.env`をComposeの`--env-file`として明示的に使用します。初回だけ候補IPを検出して`.env`へ保存させる場合は`--detect`、設定値を上書きする場合は`--ip 192.168.1.100`を明示します。通常実行では自動検出せず、`.env`の`PUBLIC_IP`を使用します。

Composeは`.certs`全体をアプリへ公開せず、公開証明書と秘密鍵をnginxの`/etc/nginx/tls/`へ個別にread-only mountします。その後Windowsで`https://192.168.1.100:8443`を開きます。

自己署名証明書を信頼する場合は、Linuxから`.certs/tls.crt`だけをWindowsへコピーし、次を実行します。`tls.key`はコピーしないでください。

```powershell
.\scripts\Install-DevCertificate.ps1 -CertificatePath .\tls.crt
```

社内CAまたは正式な証明書がある場合は、`.env`の`TLS_CERT_FILE`と`TLS_KEY_FILE`にホスト上のファイルを指定し、自動生成スクリプトは使用しません。

公開範囲をLinuxホスト内だけに戻す場合は `.env` で `HTTP_BIND_ADDRESS=127.0.0.1` と `HTTPS_BIND_ADDRESS=127.0.0.1` を指定します。社内 LAN 公開では、推測しにくいパスをセキュリティ対策と考えず、Linux側ファイアウォール、VLAN、VPN等で到達元を制限してください。

## 保存先とネットワークドライブへの移行

既定の永続領域は次の named volume です。

- `project_archives`: バージョン ZIP
- `postgres_data`: 一覧、バージョン、論理削除などの索引

backend からは常に `/data/archives` として見えるため、保存先を変えてもアプリ設定は変わりません。Linuxホストにマウント済みのローカルディスク、SMB、NFS等へ変更する例:

```bash
export ARCHIVE_HOST_PATH=/mnt/hioki-project-archives
docker compose -f compose.yaml -f compose.storage.example.yaml up -d --build
```

ネットワーク共有は先にLinuxホストの`/mnt`等へマウントします。共有が常時マウントされていること、Docker daemonから読み書きできることを確認してください。切り替え前に既存`project_archives`の内容を新しい保存先へコピーし、ファイル数とチェックサムを照合します。

## バックアップと復旧

DB バックアップ（出力先はカレントディレクトリ）:

```bash
docker compose exec -T db pg_dump -U projectdata -d projectdata -Fc > projectdata.dump
```

DB 復元:

```bash
docker compose exec -T db pg_restore -U projectdata -d projectdata --clean --if-exists < projectdata.dump
```

アーカイブ volume のバックアップ例:

```bash
docker run --rm -v hioki-projectdata-manager_project_archives:/source:ro -v "$PWD:/backup" alpine tar czf /backup/project_archives.tgz -C /source .
```

bind mount 運用ではホスト/ファイルサーバー側のバックアップを利用します。アーカイブキーにはプロジェクトUUID、8桁のバージョン番号、SHA-256が入り、プロジェクト名は ZIP 内の `*.gprj` から再取得できます。DB 再索引は管理 API を呼び、完了後に件数とチェックサムを照合します。

```bash
curl --fail --request POST http://localhost:8080/api/admin/rebuild-index
```

DB を作り直す環境では `.env` の `REBUILD_INDEX_ON_STARTUP=true` により backend 起動時にも再索引できます。通常運用は `false` のままとし、意図しない全件走査を避けます。

再索引で復元するのはプロジェクト名、UUID、バージョン番号、ZIP の場所、サイズ、SHA-256 などの最低限の索引です。説明、版メモ、論理削除日時など DB だけにある運用情報は戻らないため、通常は DB dump も保管してください。

DB パスワードを `.env` で変更した場合、上記コマンドの `-U`/`-d` も対応する値へ変更します。DB dump とアーカイブは同じ時点の組として保管するのが安全です。

## 運用確認

```bash
docker compose ps
docker compose logs --tail 200 web backend db
docker compose config
```

使い捨ての検証環境では、flat ZIP、旧UUIDラッパーZIPのflat正規化、二重ラッパー拒否を独立スクリプトで確認できます。

```bash
python3 scripts/verify_zip_layout.py --base-url http://localhost:8080
```

このスクリプトが作るランダムUUIDのプロジェクトは最後に論理削除されますが、論理削除仕様によりアーカイブZIPは残ります。本番環境では実行しないでください。

アップデートはバックアップ後に `docker compose up -d --build` を実行します。構成と受入手順は [簡易要件](docs/requirements.md)、[簡易設計](docs/architecture.md)、[ロードマップ](docs/roadmap.md)、[受入チェック](docs/acceptance-checklist.md)、[Linux Docker検証記録](docs/verification.md) を参照してください。

## 注意事項

- `.env`、秘密鍵、DB dump を Git に追加しないでください。
- ZIP 展開時は `..`、絶対パス、リンク、展開容量超過を拒否します。不明な ZIP を手作業で volume へ置かないでください。
- `docker compose down -v` は DB とアーカイブの named volume を削除対象にします。データ破棄の明示的な承認がない限り実行しないでください。
- File System Access API の実装・権限保持はブラウザー依存です。Firefox/Safari はこのワークフローの対象外です。
