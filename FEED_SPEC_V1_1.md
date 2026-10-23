# Static JSON Federation Feed v1.1.0

`Markdown → JSON → GitHub Pages` で作ったサイトの記事一覧を、独立した別サイトから購読するための公開フィード仕様です。

## バージョンポリシー

- 互換キー：`schema: "static-site-feed/v1"`, `version: 1`。
- 追加キー：`schema_version: "1.1.0"`（SemVer）。v1.0では省略可。
- `1.1.x` は **旧クライアントを壊さない追加入力**のみ。必須項目の変更・削除・意味の変更は `v2` で実施。
- この受信実装は `1.0.x` と `1.1.x` のみ許可。それ以外は取り込まず、前回正常キャッシュへフォールバック。
- `schema_version` はAPI経由のJSON内容のバージョンであり、ソースコードのアプリバージョンとは別管理。

## 一覧JSON

```json
{
  "schema": "static-site-feed/v1",
  "version": 1,
  "schema_version": "1.1.0",
  "site": {"id":"partner-town", "name":"別の町だより", "kind":"media"},
  "entries": [
    {
      "id":"partner-town:sample-article", "site_id":"partner-town", "slug":"sample-article",
      "site_name":"別の町だより", "title":"秋のパンまつり", "date":"2026-10-23",
      "type":"article", "category":"イベント", "summary":"地域の催しの紹介です。",
      "url":"https://partner.example.org/posts/sample-article/",
      "cover": {"src":"data:image/webp;base64, ...", "alt":"パンの写真", "mime":"image/webp"}
    }
  ]
}
```

上記 `cover.src` の `...` は説明用の省略表記です。実際には**空白なし**の正しいBase64 WebPである必要があります。

### JSONの要件

- 最上位：`schema`,`version`,`schema_version`（v1.0は省略可）,`site`,`entries`。
- site：`id`（半角小文字、数字、`_`、`-`）、`name`、`kind`。配信先のURLは**購読側がsources.jsonで指定**する。
- entry：`id` は `site_id:slug`、`slug` は英数字等、`date` はISO日付、`url` は信頼済みHTTPS URL。
- `cover`：**WebPをBase64 data URIへ変換した小さな画像**（受信側の上限150KB）。画像の中にスクリプトを入れない。
- `i18n.en`：`title`,`summary`,`category`,`site_name`,`unit`,`stock` 等のテキストだけ。HTMLやMarkdownは受信しない。
- 本文JSON：各サイトで自由に配信可能。ただし **統合側は本文JSONを取得・表示しない**。リンクは元サイトへ送る。
- `type=product` の場合、`price_jpy`（整数）、`unit`,`stock` が必須。決済はこの規格では扱わない。

### セキュリティ制約（今回の実装）

- ソース定義20件まで、1ソースあたり記事100件、JSONファイル4MBまで。
- 画像はWebP data URIのみ。サイズ150KBまで。データURIとRIFF/WEBPのヘッダ・サイズを検証。
- 配信元のURLと記事URLはHTTPSのみ。ユーザー名・パスワード・443以外のポート・リダイレクト禁止。
- DNSの参照結果にプライベートIP・ループバック・リンクローカルなどが含まれたら拒否。
- 外部入力の巨大文字列・未知のhtml項目は取り除いて正規化し、表示用データのみ生成。
- 許可ドメインの運用者は事前に確認が必要。取得失敗時のキャッシュは真正性まで保証するものではない。

### セキュリティポリシーの変更

通信先とスキーマ検証の制約は `scripts/merge_feeds.py` に実装。検証ルールや許容データ量を変更する場合は、リポジトリ管理者がレビューしてください。
