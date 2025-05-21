# main.py
import discord
import os
import asyncio
from dotenv import load_dotenv
import mysql.connector
from google import genai
from google.genai import types  # Ensure types is imported
from datetime import datetime
import traceback # For detailed error logging
from pathlib import Path # Pathを追加

# --- 環境変数の読み込み ---
# .envファイルへのパスを明示的に指定
# このスクリプト(main.py)の親ディレクトリ(src/)の親ディレクトリ(プロジェクトルート)にある .env ファイルを指す
dotenv_path = Path(__file__).resolve().parent.parent / '.env'
print(f"{dotenv_path=}")

try:
    dotenv_loaded = load_dotenv(dotenv_path=dotenv_path)
    if dotenv_loaded:
        print(f".envファイルが読み込まれました: {dotenv_path}")
    else:
        print(f"警告: .envファイルが見つからないか、空です: {dotenv_path}")
except Exception as e:
    print(f"環境変数の読み込みエラー: {e}")

DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
MYSQL_HOST = os.getenv('MYSQL_HOST')
MYSQL_USER = os.getenv('MYSQL_USER')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DATABASE = os.getenv('MYSQL_DATABASE')
# MYSQL_PORT を文字列として取得し、コメントを除去してから整数に変換
raw_mysql_port = os.getenv('MYSQL_PORT', '3306')
MYSQL_PORT = raw_mysql_port.split('#')[0].strip().strip('"').strip("'")

# --- Gemini APIの初期設定 ---
GEMINI_MODEL_NAME = "gemini-2.5-flash-preview-05-20"  # 使用するモデルを指定(変更禁止)
gemini_client = None
try:
    if not GEMINI_API_KEY:
        print("エラー: GEMINI_API_KEYが設定されていません。")
    else:
        gemini_client = genai.Client(
            api_key=GEMINI_API_KEY,
            # http_options={'api_version': 'v1alpha'} # v1alpha may not be needed for basic models
        )
        print(f"Gemini APIクライアントの設定が完了しました。モデル: {GEMINI_MODEL_NAME}")

except Exception as e:
    print(f"Gemini APIクライアントの初期化中にエラーが発生しました: {e}")
    print(traceback.format_exc())
    gemini_client = None

# --- Discordボットのクライアント設定 ---
intents = discord.Intents.default()
intents.message_content = True  # メッセージ内容の取得を有効化
intents.guilds = True  # サーバー関連のイベント取得を有効化
client = discord.Client(intents=intents)

# --- データベース関連 ---


def get_db_connection():
    """MySQLデータベースへの接続を取得します。"""
    try:
        conn = mysql.connector.connect(
            host=MYSQL_HOST,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE,
            port=int(MYSQL_PORT)  # ここで整数に変換
        )
        # print("MySQLデータベースへの接続に成功しました。")
        return conn
    except mysql.connector.Error as err:
        print(f"MySQL接続エラー: {err}")
        return None


def init_db():
    """データベースの初期化処理。テーブルが存在しない場合は作成します。"""
    conn = get_db_connection()
    if not conn:
        print("データベースに接続できないため、初期化をスキップします。")
        return

    cursor = conn.cursor()
    try:
        # active_threads テーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS active_threads (
                id INT AUTO_INCREMENT PRIMARY KEY,
                discord_thread_id BIGINT UNIQUE NOT NULL,
                user_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_activity_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        print("テーブル 'active_threads' の準備ができました。")

        # messages テーブル
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INT AUTO_INCREMENT PRIMARY KEY,
                thread_db_id INT NOT NULL,
                role VARCHAR(10) NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (thread_db_id) REFERENCES active_threads(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        print("テーブル 'messages' の準備ができました。")
        conn.commit()
    except mysql.connector.Error as err:
        print(f"テーブル作成エラー: {err}")
    finally:
        cursor.close()
        conn.close()


async def get_or_create_thread_db_id(discord_thread_id: int, user_id: int, channel_id: int) -> int | None:
    """
    DiscordのスレッドIDを元に、DB内のスレッド管理用IDを取得または新規作成します。
    """
    conn = get_db_connection()
    if not conn:
        return None
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id FROM active_threads WHERE discord_thread_id = %s", (discord_thread_id,))
        result = cursor.fetchone()
        if result:
            return result[0]
        else:
            cursor.execute(
                "INSERT INTO active_threads (discord_thread_id, user_id, channel_id) VALUES (%s, %s, %s)",
                (discord_thread_id, user_id, channel_id)
            )
            conn.commit()
            return cursor.lastrowid
    except mysql.connector.Error as err:
        print(f"スレッドDB IDの取得/作成エラー: {err}")
        return None
    finally:
        cursor.close()
        conn.close()


async def save_message(thread_db_id: int, role: str, content: str):
    """メッセージをデータベースに保存します。"""
    conn = get_db_connection()
    if not conn:
        return
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO messages (thread_db_id, role, content) VALUES (%s, %s, %s)",
            (thread_db_id, role, content)
        )
        conn.commit()
    except mysql.connector.Error as err:
        print(f"メッセージ保存エラー: {err}")
    finally:
        cursor.close()
        conn.close()


async def get_chat_history_for_api(thread_db_id: int, limit: int = 20) -> list:
    """
    指定されたスレッドのチャット履歴をDBから取得し、Gemini APIの形式に整形します。
    履歴は新しいものからlimit件取得し、API用に古い順に並べ替えます。
    """
    conn = get_db_connection()
    if not conn:
        return []
    cursor = conn.cursor(dictionary=True)  # カラム名をキーとする辞書形式で取得
    history_for_api = []
    try:
        # 履歴は最新のものを取得し、Geminiには古い順で渡す
        cursor.execute(
            "SELECT role, content FROM messages WHERE thread_db_id = %s ORDER BY timestamp DESC LIMIT %s",
            (thread_db_id, limit)
        )
        # DBからは新しい順で取得されるので、API用に逆順（古い順）にする
        db_messages = cursor.fetchall()[::-1]

        for msg in db_messages:
            # Gemini APIの 'user' と 'model' の役割に合わせて変換
            # DBには 'user' (ユーザー) と 'model' (AI) で保存されている
            history_for_api.append(
                types.Content(
                    role=msg["role"], # 'user' or 'model'
                    parts=[types.Part(text=msg["content"])]
                )
            )
        return history_for_api
    except mysql.connector.Error as err:
        print(f"チャット履歴取得エラー: {err}")
        return []
    finally:
        cursor.close()
        conn.close()

# --- Gemini API 関連 ---


async def ask_gemini(chat_history_contents: list[types.Content]) -> str | None:
    """Gemini APIに問い合わせて応答を取得します。chat_history_contentsには最新のプロンプトも含まれます。"""
    if not gemini_client:
        return "Gemini APIクライアントが設定されていません。"
    if not chat_history_contents:
        return "履歴が空のため、問い合わせできません。"

    try:
        print(f"Geminiに問い合わせ中... モデル: {GEMINI_MODEL_NAME}, 履歴の要素数: {len(chat_history_contents)}")

        # Google検索ツールの設定
        gemini_tools = [
            types.Tool(google_search=types.GoogleSearch()),
        ]
        
        # GenerateContentConfig オブジェクトを作成し、tools を含める
        # クラス名を GenerationConfig から GenerateContentConfig に修正
        gen_config = types.GenerateContentConfig(tools=gemini_tools)

        # generate_contentは同期的なので、asyncio.to_threadで実行
        response = await asyncio.to_thread(
            gemini_client.models.generate_content,
            model=f"models/{GEMINI_MODEL_NAME}",
            contents=chat_history_contents,
            config=gen_config  # tools を含んだ config オブジェクトを渡す
            # ここに直接 tools=gemini_tools は不要
        )

        if response and response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            part = response.candidates[0].content.parts[0]
            if part.text:
                return part.text
            # TODO: もし part.function_call が返ってきた場合の処理を追加検討
            # elif part.function_call:
            #     print(f"Gemini API returned a function call: {part.function_call}")
            #     return "AIがツールの使用を試みましたが、結果の処理は未実装です。"
            else:
                print(f"Geminiからの応答にテキストパートが含まれていません: {part}")
                return "AIからの応答を正しく解析できませんでした。(テキスト不在)"
        else:
            print(f"Geminiからの予期しない応答形式です: {response}")
            return "AIからの応答を正しく解析できませんでした。"

    except Exception as e:
        print(f"Gemini APIエラー: {e}")
        print(traceback.format_exc())
        return f"申し訳ありません、AIとの通信でエラーが発生しました。(詳細: {type(e).__name__})"


# --- Discord イベントハンドラ ---
@client.event
async def on_ready():
    """ボット起動時に呼び出されるイベントハンドラ。"""
    print(f'{client.user} としてログインしました。')
    print(f"監視サーバー数: {len(client.guilds)}")
    init_db()  # データベースの初期化


@client.event
async def on_message(message: discord.Message):
    """メッセージ受信時に呼び出されるイベントハンドラ。"""
    # ボット自身のメッセージは無視
    if message.author == client.user:
        return

    # メンションされた場合、またはボットが参加しているスレッド内での発言の場合
    is_mentioned = client.user.mentioned_in(message)
    is_in_thread_with_bot = isinstance(
        message.channel, discord.Thread) and message.channel.owner_id == client.user.id

    if not (is_mentioned or is_in_thread_with_bot):
        return

    # 処理中であることをユーザーに伝える (UX向上)
    async with message.channel.typing():
        current_thread = None
        thread_db_id = None
        chat_history_for_gemini_api = []

        if is_in_thread_with_bot:
            # 既にボットが作成したスレッド内での会話
            current_thread = message.channel
            thread_db_id = await get_or_create_thread_db_id(current_thread.id, message.author.id, current_thread.parent_id)
            if thread_db_id:
                chat_history_for_gemini_api = await get_chat_history_for_api(thread_db_id)
        elif is_mentioned:
            # 新規メンションの場合、スレッドを作成
            try:
                # スレッド名はユーザー名を含めると分かりやすい
                thread_name = f"{message.author.display_name}さんとの会話"
                # スレッドのメッセージタイプに応じて starter_message を指定
                if message.guild:  # サーバー内メッセージの場合
                    # 24時間でアーカイブ
                    current_thread = await message.create_thread(name=thread_name, auto_archive_duration=1440)
                else:  # DMの場合 (スレッド作成はサーバー内のみ)
                    await message.channel.send("DMでのスレッド作成は現在サポートされていません。サーバー内でメンションしてください。")
                    return

                if current_thread:
                    print(
                        f"新規スレッドを作成しました: {current_thread.name} (ID: {current_thread.id})")
                    thread_db_id = await get_or_create_thread_db_id(current_thread.id, message.author.id, current_thread.parent_id)
                    # 最初のメッセージなので履歴は空
                    chat_history_for_gemini_api = []

            except discord.Forbidden:
                await message.channel.send("スレッドを作成する権限がありません。")
                return
            except discord.HTTPException as e:
                await message.channel.send(f"スレッド作成中にエラーが発生しました: {e}")
                return
            except Exception as e:
                print(f"スレッド作成中の予期せぬエラー: {e}")
                await message.channel.send("スレッド作成中に予期せぬエラーが発生しました。")
                return

        if not current_thread or not thread_db_id:
            # スレッドがうまく作成/取得できなかった場合
            if is_mentioned and not is_in_thread_with_bot:  # 新規メンションでスレッド作成失敗時のみエラー通知
                await message.channel.send("申し訳ありません、会話を開始できませんでした。")
            return

        # ユーザーのメッセージ内容を取得 (メンション部分は除去)
        user_prompt = message.content
        if is_mentioned and not is_in_thread_with_bot:  # 最初のメンション時のみ除去
            user_prompt = message.content.replace(
                f'<@!{client.user.id}>', '').replace(f'<@{client.user.id}>', '').strip()

        if not user_prompt:
            if is_mentioned and not is_in_thread_with_bot:
                # 以前はここで返信していたが、履歴に追加してGeminiに判断させることもできる
                # await current_thread.send("こんにちは！何かお手伝いできることはありますか？")
                # メンションのみの場合も履歴に追加してAIにコンテキストを与える
                user_prompt = "こんにちは！何かお手伝いできることはありますか？" # デフォルトの応答を促すプロンプト
            else: # スレッド内で空メッセージの場合は何もしない
                return

        # ユーザーのメッセージをDBに保存
        await save_message(thread_db_id, "user", user_prompt)
        
        # 更新されたチャット履歴をAPI用に取得
        # save_message の後、get_chat_history_for_api を呼び出すことで、
        # 最新のユーザーメッセージが履歴に含まれるようになる
        chat_history_for_gemini_api = await get_chat_history_for_api(thread_db_id)


        # Geminiに問い合わせ
        # chat_history_for_gemini_api には既に最新の user_prompt が含まれている
        print(
            f"Geminiに問い合わせ準備完了... スレッドID: {current_thread.id}, 履歴要素数: {len(chat_history_for_gemini_api)}")
        gemini_response_text = await ask_gemini(chat_history_for_gemini_api)

        if gemini_response_text:
            # ボットの応答をDBに保存
            # Gemini APIの役割は 'model'
            await save_message(thread_db_id, "model", gemini_response_text)

            # Discordに返信 (長文の場合は分割して送信することも検討)
            if len(gemini_response_text) > 2000:
                # Discordのメッセージ上限は2000文字
                for i in range(0, len(gemini_response_text), 1990):  # 余裕をもって分割
                    await current_thread.send(gemini_response_text[i:i+1990])
            else:
                await current_thread.send(gemini_response_text)
        else:
            await current_thread.send("応答を取得できませんでした。")


# --- ボットの実行 ---
if __name__ == '__main__':
    if not all([DISCORD_BOT_TOKEN, GEMINI_API_KEY, MYSQL_HOST, MYSQL_USER, MYSQL_DATABASE]):
        print("エラー: 必要な環境変数が設定されていません。 (.envファイルを確認してください)")
        print("必要な環境変数: DISCORD_BOT_TOKEN, GEMINI_API_KEY, MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE")
    else:
        try:
            client.run(DISCORD_BOT_TOKEN)
        except discord.LoginFailure:
            print("エラー: Discordボットトークンが無効です。" + DISCORD_BOT_TOKEN[:10] + "...")
        except Exception as e:
            print(f"ボット実行中に予期せぬエラーが発生しました: {e}")
