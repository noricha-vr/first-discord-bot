import discord

from .. import settings
from ..infrastructure.database import (
    init_db,
    get_or_create_thread_db_id,
    save_message,
    get_chat_history_for_api,
)
from ..services.gemini_service import ask_gemini


intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
client = discord.Client(intents=intents)


@client.event
async def on_ready():
    print(f"{client.user} としてログインしました。")
    print(f"監視サーバー数: {len(client.guilds)}")
    init_db()


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user:
        return

    is_mentioned = client.user.mentioned_in(message)
    is_in_thread = isinstance(message.channel, discord.Thread) and message.channel.owner_id == client.user.id
    if not (is_mentioned or is_in_thread):
        return

    async with message.channel.typing():
        current_thread = None
        thread_db_id = None
        history = []

        if is_in_thread:
            current_thread = message.channel
            thread_db_id = await get_or_create_thread_db_id(current_thread.id, message.author.id, current_thread.parent_id)
            if thread_db_id:
                history = await get_chat_history_for_api(thread_db_id)
        elif is_mentioned:
            try:
                thread_name = f"{message.author.display_name}さんとの会話"
                if message.guild:
                    current_thread = await message.create_thread(name=thread_name, auto_archive_duration=1440)
                else:
                    await message.channel.send("DMでのスレッド作成は現在サポートされていません。サーバー内でメンションしてください。")
                    return
                if current_thread:
                    print(f"新規スレッドを作成しました: {current_thread.name} (ID: {current_thread.id})")
                    thread_db_id = await get_or_create_thread_db_id(current_thread.id, message.author.id, current_thread.parent_id)
            except discord.Forbidden:
                await message.channel.send("スレッドを作成する権限がありません。")
                return
            except discord.HTTPException as e:
                await message.channel.send(f"スレッド作成中にエラーが発生しました: {e}")
                return

        if not current_thread or not thread_db_id:
            if is_mentioned and not is_in_thread:
                await message.channel.send("申し訳ありません、会話を開始できませんでした。")
            return

        user_prompt = message.content
        if is_mentioned and not is_in_thread:
            user_prompt = message.content.replace(f'<@!{client.user.id}>', '').replace(f'<@{client.user.id}>', '').strip()
        if not user_prompt:
            if is_mentioned and not is_in_thread:
                user_prompt = "こんにちは！何かお手伝いできることはありますか？"
            else:
                return

        await save_message(thread_db_id, "user", user_prompt)
        history = await get_chat_history_for_api(thread_db_id)

        response_text = await ask_gemini(history)
        if response_text:
            await save_message(thread_db_id, "model", response_text)
            if len(response_text) > 2000:
                for i in range(0, len(response_text), 1990):
                    await current_thread.send(response_text[i:i+1990])
            else:
                await current_thread.send(response_text)
        else:
            await current_thread.send("応答を取得できませんでした。")


def run():
    if not all([
        settings.DISCORD_BOT_TOKEN,
        settings.GEMINI_API_KEY,
        settings.MYSQL_HOST,
        settings.MYSQL_USER,
        settings.MYSQL_DATABASE,
    ]):
        print("エラー: 必要な環境変数が設定されていません。 (.envファイルを確認してください)")
        print("必要な環境変数: DISCORD_BOT_TOKEN, GEMINI_API_KEY, MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE")
        return
    client.run(settings.DISCORD_BOT_TOKEN)
