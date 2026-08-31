# Linux Docker検証記録

実施日: 2026-08-31

環境: Ubuntu 24.04.4 LTS、Docker 29.1.3、Docker Compose 2.40.3

## 確認済み

- 通常、HTTPS、bind mount override の各 Compose 設定を解決できる。
- backend と frontend のコンテナイメージを実ビルドできる。
- PostgreSQL、FastAPI、nginx の3サービスが `healthy` になる。
- nginx 経由の SPA と `/api/health` が HTTP 200を返す。
- 自己署名証明書を使った HTTPS の SPA と `/api/health` が HTTP 200を返す。
- `.env`の`PUBLIC_IP`からCN/IP SAN付き証明書を再生成し、nginxを強制再作成して同じ証明書を配信できる。
- 同一UUIDを2回登録するとバージョンが `[2, 1]` になる。
- 編集後の表示名と説明が PostgreSQL から取得できる。
- ダウンロードしたバージョンZIPの SHA-256 が登録元と一致する。
- 論理削除後は通常一覧0件、削除込み一覧1件となり、復帰後に再表示される。
- コンテナ再起動後もプロジェクトと2つのZIPが保持される。
- DBのプロジェクト/バージョン行を消した後、`/api/admin/rebuild-index` がZIP 2件からプロジェクト1件、バージョン2件を再構築する。
- `compose.storage.example.yaml` のLinux bind mountへ実際にZIPを書き込める。
- backend pytest 6件、frontend Vitest 6件、frontend production buildが成功する。

## Windows実機での受入れ対象

- Chrome/Edgeから `%APPDATA%\gennect-space\data` を選択し、再訪後もDirectoryHandleを再利用できること。
- GENNECT Spaceが実際に作成したプロジェクトを登録・書き戻しできること。
- Linuxホストにマウントした実ネットワーク共有へbind mountできること。
- 社内CA証明書を信頼した別端末から、HTTPSとFile System Access APIが利用できること。

Linux検証では自己署名証明書を使用したため、証明書の信頼性そのものは検証対象外です。
