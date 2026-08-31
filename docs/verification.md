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
- backend pytest 12件、frontend Vitest 20件、frontend production buildが成功する。

## ZIPレイアウト追加検証

追加要件 RQ-007–RQ-009 に対し、2026-08-31 に一時SQLite DB・一時アーカイブ領域でFastAPIをHTTP起動し、実際の公開APIへ `scripts/verify_zip_layout.py` を実行しました。

- flat ZIPをmultipartの `source_uuid` なし、`<uuid>.zip` ファイル名だけで登録できる。
- flat入力をdownloadすると、`*.gprj` とサブディレクトリがZIP直下から始まり、UUIDラッパーがない。
- UUIDラッパーが1階層ある旧ZIP入力を登録でき、保存/download時はflatへ正規化される。
- `<uuid>/<uuid>/*.gprj` の二重ラッパー入力は HTTP 400 で拒否される。
- verifierは作成レコードを最後に論理削除し、3ケースすべて `PASS` で終了した。

実行結果:

```text
PASS flat input -> flat download (filename UUID inference)
PASS legacy UUID wrapper input -> flat download
PASS double UUID wrapper rejected
ZIP layout contract: PASS
```

## Windows実機での受入れ対象

- Chrome/Edgeから `%APPDATA%\gennect-space\data` を選択し、再訪後もDirectoryHandleを再利用できること。
- GENNECT Spaceが実際に作成したプロジェクトを登録・書き戻しできること。
- Linuxホストにマウントした実ネットワーク共有へbind mountできること。
- 社内CA証明書を信頼した別端末から、HTTPSとFile System Access APIが利用できること。

Linux検証では自己署名証明書を使用したため、証明書の信頼性そのものは検証対象外です。

## プロジェクトJSON編集の独立E2E

追加要件 RQ-016 に対し、2026-08-31 に一時SQLite DB・一時アーカイブ領域でFastAPIをHTTP起動し、公開API経路で次を確認しました。同じ環境で2回連続実行して、どちらも成功しています。

- `.example` の3ファイルをflat ZIPとして登録し、版1の2 JSONをAPIで取得できる。
- `*.gprj` と `layout.lay` の論理値を各1箇所だけ変更する1回のPUTで版2が作られる。
- 版2では両JSONが要求した内容へ変わり、版1は全entryのpath/payload bytesが不変である。
- 版2の `.set` とその他全編集対象外entryは版1とpayload bytesが一致する。

実行結果:

```text
PASS fetched version 1 and edited one value in MKH-PDU電圧モニタ.gprj: ('formatVersion',)
PASS edited one value in layout.lay: ('paneModelList', 0, 'sheetId')
PASS created version 2 while all version 1 entry payloads remained unchanged
PASS preserved 1 opaque payload(s), including 1 .set file(s)
Configuration editing contract: PASS
```

一時環境の公開HTTP APIに対して、リポジトリルートから次を実行します。

```bash
python3 scripts/verify_configuration_edit.py --base-url http://localhost:8080
```

このverifierは `.example` の実データをflat ZIPとして登録し、APIで `*.gprj` と `layout.lay` を取得して各1つのJSON値だけを変更します。繰り返し実行できるよう、登録用コピーのgprj `id` は実行ごとの `source_uuid` に合わせますが、`.set` とその他の編集対象外ファイルは原本bytesを使います。新版のdownloadで両JSONの変更、旧版の不変性、`.set` とその他全entryのpath/payload bytes一致を検証し、最後に作成プロジェクトを論理削除します。不変アーカイブは設計どおり保存領域に残るため、使い捨て環境だけで実行してください。
