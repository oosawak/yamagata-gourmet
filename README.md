# 山形グルメ案内 — 独立JSONサイト

このリポジトリは独立したGitHub Pagesサイトです。**ほかの店舗のソースコードや記事は含まれていません**。Markdownから日本語＋英語の静的JSONを生成し、共有用 `data/sites/gourmet.json` を公開します。

## 最初の公開手順

1. GitHubで**空のPublicリポジトリ**を作成してください（READMEの自動作成は選ばない）。
2. このZIPを解凍し、**解凍フォルダの中身**をそのリポジトリの直下に配置します。
3. `main` ブランチへpushします。
4. GitHubの **Settings → Pages → Build and deployment → Source = GitHub Actions** を選択します。
5. **Actions → Build and publish... / Merge feeds...** が成功したらPagesのURLを確認します。

```bash
git init
git add .
git commit -m "Initial independent JSON site"
git branch -M main
git remote add origin https://github.com/<OWNER>/<REPOSITORY>.git
git push -u origin main
```

> `<OWNER>` と `<REPOSITORY>` は自分のGitHub情報へ置換します。標準の公開URLは `https://OWNER.github.io/REPOSITORY/` です。個人トップの `OWNER.github.io` リポジトリでは末尾パスを付けません。非公開リポジトリでのPages公開可否はプランに依存します。

## 記事を更新する

- 編集場所: `content/posts/gourmet/YYYY-MM-DD-slug.md`
- 画像: `content/images/gourmet/` にWebP/JPG/PNGを保存し、Markdownの `cover: gourmet/image.webp` に指定
- `git add . && git commit -m "Update article" && git push` でActionsが再生成・公開します。
- 日本語が原本です。既存の18記事相当の英語訳から**このサイトの4記事分だけ**同梱しています。
- 新しい記事を英語に自動翻訳したい場合は `Settings → Secrets and variables → Actions → Secrets` に `DEEPL_AUTH_KEY` を登録します。
- 自動翻訳のキャッシュはActions Cacheで保持します。外部API不調時には未翻訳箇所は日本語のままです。

## 公開URL・統合ポータルとの接続

- Actionsで自動的に `GITHUB_REPOSITORY` からPagesのURLを組み立て、記事 `url` に **完全なHTTPS URL** を埋め込みます。
- カスタムドメインの場合は `Settings → Secrets and variables → Actions → Variables` に `SITE_URL=https://example.com/` を指定し、**Actions → Run workflow** で再ビルドしてください。
- 統合ポータルへのリンクをヘッダーに表示したい場合は同じVariablesに `PORTAL_URL=https://OWNER.github.io/community-portal/` を設定します（任意）。設定したあとに **Actions → Run workflow** で再ビルドしてください。
- 公開フィード：`https://OWNER.github.io/REPOSITORY/data/sites/gourmet.json`
- 記事詳細JSON：`https://OWNER.github.io/REPOSITORY/data/posts/gourmet/<slug>.json`
- 公開フィードには記事の**タイトル・本文要約・Base64サムネイル・英語テキスト・正規URL**を含み、本文自体は含みません。
- 別サイトの記事は、独立サイト側で全件を複製せず、`PORTAL_URL` のリンクから確認できます。
- **統合ポータルは記事公開を即時通知では受けません**。標準では毎日の再取得か、ポータルActionsの手動実行で同期します。

## ローカル確認

```bash
python -m pip install -r requirements.txt
python scripts/build.py
python -m unittest discover -s scripts -p 'test_*.py' -v
python scripts/export_preview.py
python -m http.server 8000 --directory dist
```

`http://localhost:8000/` で動作確認します。単体HTMLの確認には `dist/preview.html` を開いてください。

## データとセキュリティ

- PHP、DB、サーバー管理画面は不要。記事更新はGitの書き込み権限で管理。
- バイナリ画像はビルド時にWebP/Base64変換。公開サイトではデータベースを使用しません。
- `scripts/build.py` はMarkdown由来HTMLをサニタイズします。PRはSecretsなしの読み取り専用テスト。
- 商品データとカートはデモです。実決済はできません。
- 共通JSON仕様は `docs/FEED_SPEC_V1_1.md` を参照してください。
