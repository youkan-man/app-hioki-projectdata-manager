# LR8450 `.set` 公開仕様調査

調査日: 2026-08-31

対象: `.example/de795586-5cdb-4ca9-a472-938a1fbfb341/LR8450-01_200142824.set`

## 結論

- HIOKI公式資料は、LR8450/LR8450-01の設定を本体やSD/USBメモリへ保存し、後で読み込めることを説明しています。
- 公式の保存・読込一覧では設定条件をバイナリとし、本体での読込は可能、PCでの読込は対象外としています。
- Logger Utilityや通信コマンドは本体の設定・制御に利用できます。しかし、公開資料からは任意の `.set` ファイルをbyte-levelで編集または再生成するファイル仕様/APIを確認できませんでした。
- 対象ファイルの `HIOKIWV\0MD5` は独自コンテナと完全性情報を示すように見えますが、これはローカル観察からの推測です。MD5の対象範囲、格納位置、計算方法は公開資料で確認できないため、再計算可能とは扱いません。
- 公式マニュアルは機種、ユニット構成、ファームウェア版の違いによる設定ファイル読込エラーを明記しています。したがって本ツールでは `.set` を編集せず、entry pathとpayload bytesをそのまま新版へ複製するのが安全な境界です。

## ローカルファイルの観察

先頭96 bytesには次の固定長らしき領域があります。

```text
00000000  HIOKIWV\0MD5\0....
00000020  190805\0\0LR8450\0\0
00000030  V3.00\0...
00000040  200142824\0...
00000050  CONFIG\0\0...
```

ファイルサイズは540,672 bytesです。先頭16 bytesの直後には16 bytesのバイナリ値がありますが、これだけではMD5 digestの対象や検証方法を確定できません。文字列として `LR8450`、`V3.00`、製造番号らしき `200142824`、`-01` が含まれるため、少なくとも汎用JSONではなく機種・版情報を持つバイナリ形式と判断できます。

ヘッダーには、次の3セクションを示すディレクトリらしき固定長文字列があります。数値は16進ASCIIとして読むと、実際のデータ位置と整合します。

| セクション名 | オフセット | 長さ | 観察できた内容 |
| --- | ---: | ---: | --- |
| `LR8450DTMAIN` | `0x0200` | `0x80000` | `DT` と機種名から始まる固定長の設定領域 |
| `LR8450TMPSTATUS` | `0x80200` | `0x0200` | 一時状態と思われる固定長領域 |
| `LR8450LOG` | `0x80400` | `0x3B37` | `PK\x03\x04` で始まり、`var/log/boot` を含むZIP形式の断片 |

`LR8450LOG` のZIP local headerはgeneral purpose bit flag `0x0009`を持ち、暗号化フラグが立っています。したがって一般的なZIP展開だけでログ内容を取得することはできません。これらは1サンプルの構造観察であり、設定項目とバイト位置の対応やチェック値の生成規則を確定するものではありません。

## HIOKI公式資料で確認できた範囲

- [LR8450取扱説明書「Saving Data」](https://manual.hioki.com/en/LR8450/manual/settings_operation/saving_data.html) は、測定データ、設定、画面画像などを保存できると説明しています。
- [LR8450詳細取扱説明書](https://www.hioki.com/download/30646) の「Data That Can Be Saved and Loaded」は、設定条件を `Binary`、標準ファイル名を `CONF0001.SET` とし、本体からの読込は可能、PCからの読込は対象外としています。
- [「Configuration Process」](https://manual.hioki.com/en/LR8450/manual/settings_operation/configuration_process.html) と [SD/USBメモリの説明](https://manual.hioki.com/en/LR8450/manual/connections/memory_card.html) は、測定条件を保存し、保存データを読み込んで設定を再現できることを説明しています。
- [Logger Utilityの説明](https://manual.hioki.com/en/LR8450/manual/supplement/using_logger_utility.html) はLR8450/LR8450-01の設定、監視、操作を案内しています。
- [通信コマンドによる制御](https://manual.hioki.com/en/LR8450/manual/supplement/controlling_communication_commands.html) はUSB/LAN経由の本体制御を案内し、別冊の通信コマンド取扱説明書を参照させています。[公式コマンドマニュアル/ドライバ配布ページ](https://www.hioki.com/us-en/support/download/software/versionup/detail/id_605) も本体制御とデータ収集を対象としています。これらは本体の設定手段であり、`.set` バイナリの公開オーサリングAPIであるとは記載されていません。
- [エラーメッセージ一覧](https://manual.hioki.com/en/LR8450/manual/maintenance_service/error_messages.html) は、破損、異なる機種、ユニット構成、直接接続ユニット名、版のダウングレード、LR8450-01からLR8450への読込、異なる版による設定ファイルエラーを列挙しています。
- [詳細取扱説明書PDF](https://www.hioki.com/download/30646) は `STARTUP.SET` の自動読込や、機種・版が異なる場合の扱いを説明しています。

## 実装上の判断

本ツールがJSONとして編集するのはZIP直下の単一 `*.gprj` と `layout.lay` だけです。`.set` は公式ファイル仕様と完全性情報の再生成方法が確認できないためopaque binaryとして扱い、名称、相対path、payload bytesを維持します。将来HIOKIから正式なファイルSDK/仕様が提供された場合に限り、互換性試験を別要件として追加します。
