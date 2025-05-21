from __future__ import annotations
import mysql.connector
from google.genai import types
from typing import List, Optional

from .. import settings


def get_db_connection():
    """Get a MySQL database connection."""
    try:
        conn = mysql.connector.connect(
            host=settings.MYSQL_HOST,
            user=settings.MYSQL_USER,
            password=settings.MYSQL_PASSWORD,
            database=settings.MYSQL_DATABASE,
            port=settings.MYSQL_PORT,
        )
        return conn
    except mysql.connector.Error as err:
        print(f"MySQL connection error: {err}")
        return None


def init_db() -> None:
    """Initialize database tables if they do not exist."""
    conn = get_db_connection()
    if not conn:
        print("データベースに接続できないため、初期化をスキップします。")
        return

    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS active_threads (
                id INT AUTO_INCREMENT PRIMARY KEY,
                discord_thread_id BIGINT UNIQUE NOT NULL,
                user_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_activity_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INT AUTO_INCREMENT PRIMARY KEY,
                thread_db_id INT NOT NULL,
                role VARCHAR(10) NOT NULL,
                content TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (thread_db_id) REFERENCES active_threads(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """
        )
        conn.commit()
    except mysql.connector.Error as err:
        print(f"テーブル作成エラー: {err}")
    finally:
        cursor.close()
        conn.close()


async def get_or_create_thread_db_id(discord_thread_id: int, user_id: int, channel_id: int) -> Optional[int]:
    conn = get_db_connection()
    if not conn:
        return None
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id FROM active_threads WHERE discord_thread_id = %s",
            (discord_thread_id,),
        )
        result = cursor.fetchone()
        if result:
            return result[0]
        cursor.execute(
            "INSERT INTO active_threads (discord_thread_id, user_id, channel_id) VALUES (%s, %s, %s)",
            (discord_thread_id, user_id, channel_id),
        )
        conn.commit()
        return cursor.lastrowid
    except mysql.connector.Error as err:
        print(f"スレッドDB IDの取得/作成エラー: {err}")
        return None
    finally:
        cursor.close()
        conn.close()


async def save_message(thread_db_id: int, role: str, content: str) -> None:
    conn = get_db_connection()
    if not conn:
        return
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO messages (thread_db_id, role, content) VALUES (%s, %s, %s)",
            (thread_db_id, role, content),
        )
        conn.commit()
    except mysql.connector.Error as err:
        print(f"メッセージ保存エラー: {err}")
    finally:
        cursor.close()
        conn.close()


async def get_chat_history_for_api(thread_db_id: int, limit: int = 20) -> List[types.Content]:
    conn = get_db_connection()
    if not conn:
        return []
    cursor = conn.cursor(dictionary=True)
    history_for_api: List[types.Content] = []
    try:
        cursor.execute(
            "SELECT role, content FROM messages WHERE thread_db_id = %s ORDER BY timestamp DESC LIMIT %s",
            (thread_db_id, limit),
        )
        db_messages = cursor.fetchall()[::-1]
        for msg in db_messages:
            history_for_api.append(
                types.Content(role=msg["role"], parts=[types.Part(text=msg["content"])])
            )
        return history_for_api
    except mysql.connector.Error as err:
        print(f"チャット履歴取得エラー: {err}")
        return []
    finally:
        cursor.close()
        conn.close()
