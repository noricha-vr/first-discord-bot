# First Discord Bot

このプロジェクトは、Discordで動作するPython製のボットです。Gemini APIと連携して、スレッド内での会話に応答します。

## 必要条件

*   Python 3.12 以降
*   [uv](https://github.com/astral-sh/uv) (Pythonパッケージインストーラおよび仮想環境マネージャ)

## セットアップ手順

1.  **リポジトリをクローンします:**
    ```bash
    git clone https://github.com/noricha-vr/first-discord-bot.git
    cd first-discord-bot
    ```

2.  **環境変数を設定します:**
    `.env.sample` ファイルをコピーして `.env` ファイルを作成し、必要な情報を設定してください。
    ```bash
    cp .env.sample .env
    ```
    最低限、以下の環境変数が必要です:
    *   `DISCORD_BOT_TOKEN`: Discordボットのトークン
    *   `GEMINI_API_KEY`: Gemini APIキー
    *   `MYSQL_HOST`: MySQLサーバーのホスト名
    *   `MYSQL_USER`: MySQLユーザー名
    *   `MYSQL_PASSWORD`: MySQLパスワード
    *   `MYSQL_DATABASE`: 使用するデータベース名

3.  **依存関係をインストールします:**
    `uv` を使用して、プロジェクトの依存関係をインストールします。
    ```bash
    uv sync
    ```
    これにより、`pyproject.toml` と `uv.lock` に基づいて仮想環境が作成され、必要なパッケージがインストールされます。

## 実行方法

以下のコマンドでDiscordボットを起動します。

```bash
uv run python -m src
```

ボットがDiscordサーバーに接続し、メンションや参加しているスレッドでのメッセージに応答を開始します。

## プロジェクト構造 (概要)

```
first-discord-bot/
├── .venv/                # uvによって管理されるPython仮想環境
├── src/                  # ソースコードディレクトリ
│   ├── __init__.py
│   ├── __main__.py       # アプリケーションのエントリーポイント
│   ├── config/           # 設定関連 (現在は未使用の可能性あり)
│   ├── domain/           # ドメインロジック、エンティティ
│   ├── infrastructure/   # データベース接続、外部API(AI)連携など
│   ├── interfaces/       # Discordボットのインターフェースロジック
│   ├── services/         # ビジネスサービス、Gemini API呼び出しなど
│   └── settings.py       # 環境変数読み込みなどの設定
├── .env                  # 環境変数ファイル (Git管理外)
├── .env.sample           # 環境変数ファイルのサンプル
├── .python-version       # Pythonバージョン指定
├── pyproject.toml        # プロジェクト設定、依存関係定義
├── README.md             # このファイル
└── uv.lock               # 依存関係のロックファイル
```
