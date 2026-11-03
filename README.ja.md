# hyperresearch（日本語版 README）

> [!IMPORTANT]
> このリポジトリは [jordan-gibbs/hyperresearch](https://github.com/jordan-gibbs/hyperresearch)（MIT ライセンス）のフォークです。本体の設計・実装の大部分は原作者とそのコントリビューターによるものです。
> このフォークで独自に加えた変更は「[このフォークでの変更](#このフォークでの変更)」にまとめています。英語の README（[README.md](README.md)）は原作者のものをそのまま残しています。

## 目的

Claude Code や OpenAI Codex の上で「深い調査（deep research）」を手順どおりに走らせるための道具です。

- 1つの問いを 16 段階の手順（分解 → 幅広い収集 → 深掘り → 草稿 → 批評 → 修正 → 引用検証）で処理し、出典つきの報告書を作ります。
- 読んだ出典はすべて、Markdown ファイルと SQLite（全文検索 FTS5）でできた「ボールト」に保存され、次回の調査で再利用されます。
- 取ってきた Web ページは信用できない入力として扱います（SSRF 対策、TLS 検証、閲覧画面での XSS 対策など）。

LLM を使う調査そのものには Claude Code か Codex の実行環境と API 利用料が必要です。ボールト（保存・検索・閲覧）の部分は、ネット接続も API キーもなしで動きます。

## 使い方

### インストール

```bash
pip install hyperresearch
```

開発版（このリポジトリ）を使う場合:

```bash
pip install -e ".[dev]"
```

### 調査を走らせる（Claude Code / Codex が必要）

```bash
cd your-project
hyperresearch install                    # Claude Code 用。セッション内で /hyperresearch <問い>
hyperresearch install . --target codex   # Codex 用。セッション内で $hyperresearch <問い>
```

### ボールトだけを使う（ネット・API キー不要）

```bash
hyperresearch init
```

```bash
hyperresearch note new "メモの題名" --body "本文"
```

```bash
hyperresearch search "検索語"
```

```bash
hyperresearch serve --open   # http://127.0.0.1:8080 でメモ・タグ・リンクグラフを閲覧
```

### テスト・検証

```bash
ruff check src/ tests/ scripts/
```

```bash
pytest tests/
```

```bash
python scripts/bench_vault.py   # ボールトの書き込み・索引・検索の速さを測る（オフライン）
```

## 実測結果

以下はすべて、この PR の作業中に実際にコマンドを実行して得た数字です。

**計測環境:** Linux コンテナ（4 コア）、Python 3.13.18、SQLite 3.53.1、Crawl4AI 0.9.5。

### テスト

| 対象 | 結果 | 所要時間 |
|---|---|---|
| 変更前（`9c16854`、元のコードとテスト） | 1715 件成功 / **4 件失敗** | 201 秒 |
| 変更後（この PR） | **1745 件成功 / 0 件失敗** | 226 秒（カバレッジ計測込み） |

- 変更前に落ちていた 4 件の内訳: Crawl4AI 0.9 系で挙動が変わったことによる TLS テスト 2 件、DNS が引けない環境で実際に `example.com` を名前解決しようとしていたテスト 2 件（詳細は下記）。
- 行カバレッジ（`pytest --cov=hyperresearch`）: 71%（11,677 行中 3,443 行が未実行）
- `ruff check src/ tests/ scripts/`: 指摘 0 件。

### ボールトの性能（`python scripts/bench_vault.py`、既定値で 3 回実行）

条件: 300 語のメモ 1,000 件を書き込み、索引を作り直し、2 語の全文検索を 200 回。

| 項目 | 1 回目 | 2 回目 | 3 回目 |
|---|---|---|---|
| 書き込み | 0.81 秒 | 0.81 秒 | 0.56 秒 |
| 索引（sync） | 2.07 秒 | 1.96 秒 | 1.92 秒 |
| 検索の中央値 | 12.75 ms | 9.82 ms | 12.81 ms |
| 検索の p95 | 14.33 ms | 13.91 ms | 14.67 ms |

3 回とも 1,000 件すべてが索引に入り、200 回の検索すべてで 1 件以上ヒットしました。

### `hyperresearch serve` の Host 検証（実機で確認）

`hyperresearch serve --port 8765` を起動し、`curl -H "Host: ..." http://127.0.0.1:8765/api/graph` の応答コードを確認しました。

| Host ヘッダ | 応答 |
|---|---|
| `127.0.0.1:8765` | 200 |
| `localhost:8765` | 200 |
| `evil.example:8765` | 421（ボールトの中身は返さない） |

### 測っていないもの

英語 README にある DRACO ベンチマークの順位・得点は原作者が公表している数字で、このフォークでは再現していません（LLM の実行費用がかかるため）。

## このフォークでの変更

### 1. 閲覧サーバーの DNS リバインディング対策（セキュリティ）

`hyperresearch serve` は 127.0.0.1 だけで待ち受けますが、利用者が開いている悪意のある Web ページは「自分のドメインの名前解決先を途中で 127.0.0.1 に切り替える」手口（DNS リバインディング）で、ボールトの中身（`/api/graph` や `/note/...`）を読み出せました。ブラウザはその間も `Host: 攻撃者のドメイン` を送り続けるので、Host ヘッダが `127.0.0.1` / `localhost` / `[::1]`（かつ待ち受け中のポート）でない要求は `421` で断るようにしました。あわせて `X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy: no-referrer` を付けています。

- 変更: `src/hyperresearch/serve/server.py`
- テスト: `tests/test_serve/test_host_header.py`（修正前のコードでは失敗、修正後は成功することを確認）

### 2. 落ちていたテストの修正（壊れていた所）

- **Crawl4AI 0.9 系との不一致:** Crawl4AI 0.8 系は Chromium を常に `--ignore-certificate-errors` 付きで起動していたため、本体はそのフラグを取り除いて TLS を検証しています。0.9 系はこのフラグを「検証しない設定のときだけ」付けるようになり、本体の安全性は保たれたまま、旧挙動を前提にした 2 件のテストが落ちていました。テストを「上書きはインスタンス単位でクラスに漏れない」「検証しない設定では Crawl4AI の引数をそのまま使う」という本来の意図で確かめる形に直し、フラグを常に付ける版を模した偽物で除去処理そのものも確かめるテストを足しました。
- **ネット依存:** 2 件のテストが SSRF 対策の名前解決で本物の DNS を引いており、DNS のない CI やサンドボックスで落ちていました。名前解決だけを差し替えてオフラインで動くようにしました（SSRF 判定そのものは本物を通ります）。

### 3. CI（GitHub Actions）の強化

既存の `.github/workflows/ci.yml`（Python 3.11〜3.14 と Windows で ruff・pytest・パッケージ作成）に以下を加えました。

- `permissions: contents: read`（トークンの権限を読み取りだけに）
- 同じブランチへの新しい push で古い実行を止める `concurrency`
- 30 分のタイムアウト、pip のキャッシュ
- カバレッジの表示、`scripts/` も ruff の対象に

### 4. 計測スクリプト

`scripts/bench_vault.py`: ネットも API キーも使わず、ボールトの書き込み・索引・全文検索の時間を測ります。上の数字はこのスクリプトの出力です。壊れないよう `tests/test_core/test_bench_script.py` で動作確認しています。

## 既知の課題（この PR では直していないもの）

- `pyproject.toml` は mypy の strict を指定していますが、CI では実行されておらず、`mypy src` を実行すると 421 件のエラーが出ます（114 ファイル中 59 ファイル）。
- Crawl4AI 0.9.5 で `PruningContentFilter` の非推奨警告が出ます。

## ライセンス

[MIT](LICENSE)（原作者 Jordan Gibbs）
