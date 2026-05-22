# Roomba Agent

ルンバを自然言語で操作する Streamlit アプリです。  
MCP 経由でロボット制御ツールを呼び出し、Ollama のローカル LLM で指示を解釈します。

## 主な機能

- MCP（stdio）経由でルンバ操作
- 日本語チャットでの指示入力
- サイドバーに質問候補を表示
- サイドバーに利用中 LLM（Provider / Model）を表示
- 応答のストリーミング表示
- メッセージ本文中にツール呼び出しタイミングを表示（🔧 付き）

## 技術スタック

- Python 3.12+
- Streamlit
- strands-agents（ollama extra）
- MCP Python SDK
- Ollama

## 事前準備

### 1. 依存関係のインストール

```bash
uv sync
```

### 2. Ollama を起動し、モデルを取得

このアプリは `gemma4:e2b` を使用します。

```bash
ollama pull gemma4:e2b
```

Ollama が `http://127.0.0.1:11434` で利用可能であることを確認してください。

### 3. MCP エンドポイントを起動

アプリ側は以下の stdio 接続設定で MCP に接続します。

- command: `uvx`
- args: `mcp-proxy http://localhost:8000/mcp`

`http://localhost:8000/mcp` で応答する MCP サーバーを事前に起動してください。

## 起動方法

```bash
streamlit run main.py
```

起動後、ブラウザで表示された URL を開いて利用します。

## 使い方

1. サイドバーの質問候補をクリック、またはチャットに自由入力します。
2. 例: `0.2m/sで3秒前進して`
3. アシスタントの返答中に、ツール呼び出し行が本文内に表示されます。
4. 必要に応じて「利用可能なMCPツール」からツール一覧を確認できます。

## move ツールの取り扱いルール

- `velocity`: m/s（小数可）
- `yaw_rate`: deg/s
- `duration`: 秒（指定なしの場合は 1）

挙動ルール:

- 前進/後進: `yaw_rate = 0`、`velocity` の符号で方向を表現
- 旋回: `velocity = 0`、`yaw_rate` の符号で左右を表現

## よくあるトラブル

### MCP 接続の初期化に失敗する

- `http://localhost:8000/mcp` 側のサーバーが起動しているか確認
- `uvx` コマンドが実行可能か確認

### モデル呼び出しに失敗する

- Ollama が起動しているか確認
- `ollama pull gemma4:e2b` が完了しているか確認

### ツール一覧が表示できない

- MCP サーバーがツールを公開しているか確認
- 接続 URL が `main.py` の設定と一致しているか確認

## プロジェクト構成

- `main.py`: アプリ本体
- `pyproject.toml`: 依存関係定義
- `README.md`: このファイル
