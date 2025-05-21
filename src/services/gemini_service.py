import asyncio
import traceback
from google import genai
from google.genai import types

from .. import settings

GEMINI_MODEL_NAME = "gemini-2.5-flash-preview-05-20"

gemini_client = None
if settings.GEMINI_API_KEY:
    try:
        gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
    except Exception as e:
        print(f"Gemini APIクライアントの初期化中にエラーが発生しました: {e}")
        print(traceback.format_exc())


async def ask_gemini(chat_history_contents: list[types.Content]) -> str | None:
    """Query Gemini API and return the response text."""
    if not gemini_client:
        return "Gemini APIクライアントが設定されていません。"
    if not chat_history_contents:
        return "履歴が空のため、問い合わせできません。"
    try:
        print(
            f"Geminiに問い合わせ中... モデル: {GEMINI_MODEL_NAME}, 履歴の要素数: {len(chat_history_contents)}"
        )
        gemini_tools = [types.Tool(google_search=types.GoogleSearch())]
        gen_config = types.GenerateContentConfig(tools=gemini_tools)
        response = await asyncio.to_thread(
            gemini_client.models.generate_content,
            model=f"models/{GEMINI_MODEL_NAME}",
            contents=chat_history_contents,
            config=gen_config,
        )
        if (
            response
            and response.candidates
            and response.candidates[0].content
            and response.candidates[0].content.parts
        ):
            part = response.candidates[0].content.parts[0]
            if part.text:
                return part.text
            else:
                print(
                    f"Geminiからの応答にテキストパートが含まれていません: {part}"
                )
                return "AIからの応答を正しく解析できませんでした。(テキスト不在)"
        else:
            print(f"Geminiからの予期しない応答形式です: {response}")
            return "AIからの応答を正しく解析できませんでした。"
    except Exception as e:
        print(f"Gemini APIエラー: {e}")
        print(traceback.format_exc())
        return f"申し訳ありません、AIとの通信でエラーが発生しました。(詳細: {type(e).__name__})"
