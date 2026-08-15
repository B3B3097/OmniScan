import asyncio
import base64
import json
import logging
import sqlite3
import os
import time
import mimetypes
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

import aiohttp
from pydantic import BaseModel, Field
from fastapi import FastAPI, HTTPException, BackgroundTasks
import uvicorn

# ==========================================
# 1. КОНФИГУРАЦИЯ И ЛОГИРОВАНИЕ
# ==========================================
os.makedirs("logs", exist_ok=True)
os.makedirs("data/db", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler("logs/ollama_engine.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("VisionChatEngine")

# ==========================================
# 2. PYDANTIC МОДЕЛИ (СТРОГАЯ ТИПИЗАЦИЯ)
# ==========================================
class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(system|user|assistant)$")
    content: str
    images: Optional[List[str]] = None  # Base64 строки
    timestamp: float = Field(default_factory=time.time)

class ChatSession(BaseModel):
    session_id: str
    item_id: str
    user_id: str
    created_at: float = Field(default_factory=time.time)
    messages: List[ChatMessage] = Field(default_factory=list)

class VisionAnalysisRequest(BaseModel):
    user_id: str
    item_id: str
    category: str  # "auto", "tech", "clothes", etc.
    description: str
    image_url: str

class ChatRequest(BaseModel):
    session_id: str
    message: str

# ==========================================
# 3. БАЗА ДАННЫХ (УПРАВЛЕНИЕ КОНТЕКСТОМ ЧАТОВ)
# ==========================================
class DatabaseManager:
    """Локальная SQLite база для хранения истории чатов с ИИ и отчетов."""
    
    def __init__(self, db_path: str = "data/db/vision_chats.sqlite"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id TEXT PRIMARY KEY,
                    item_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    has_images BOOLEAN NOT NULL,
                    timestamp REAL NOT NULL,
                    FOREIGN KEY(session_id) REFERENCES chat_sessions(session_id)
                )
            """)
            # Отдельная таблица для хранения base64 картинок, чтобы не грузить основную
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS message_images (
                    message_id INTEGER,
                    image_base64 TEXT NOT NULL,
                    FOREIGN KEY(message_id) REFERENCES messages(id)
                )
            """)
            conn.commit()
            logger.info("База данных контекста инициализирована.")

    def create_session(self, session_id: str, item_id: str, user_id: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO chat_sessions (session_id, item_id, user_id, created_at) VALUES (?, ?, ?, ?)",
                (session_id, item_id, user_id, time.time())
            )
            conn.commit()

    def add_message(self, session_id: str, message: ChatMessage):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            has_images = bool(message.images)
            cursor.execute(
                "INSERT INTO messages (session_id, role, content, has_images, timestamp) VALUES (?, ?, ?, ?, ?)",
                (session_id, message.role, message.content, has_images, message.timestamp)
            )
            message_id = cursor.lastrowid
            
            if has_images and message.images:
                for img_b64 in message.images:
                    cursor.execute(
                        "INSERT INTO message_images (message_id, image_base64) VALUES (?, ?)",
                        (message_id, img_b64)
                    )
            conn.commit()

    def get_session_history(self, session_id: str, limit: int = 10) -> List[dict]:
        """Извлекает последние N сообщений для передачи в контекст Ollama."""
        history = []
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, role, content, has_images FROM messages WHERE session_id = ? ORDER BY timestamp ASC LIMIT ?",
                (session_id, limit)
            )
            rows = cursor.fetchall()
            
            for row in rows:
                msg_id, role, content, has_images = row
                msg_dict = {"role": role, "content": content}
                
                if has_images:
                    cursor.execute("SELECT image_base64 FROM message_images WHERE message_id = ?", (msg_id,))
                    images = [img[0] for img in cursor.fetchall()]
                    if images:
                        msg_dict["images"] = images
                
                history.append(msg_dict)
        return history

# ==========================================
# 4. ДВИЖОК ОПТИМИЗАЦИИ ИЗОБРАЖЕНИЙ
# ==========================================
class ImageProcessor:
    @staticmethod
    async def download_and_encode(url: str) -> Optional[str]:
        """Асинхронное скачивание с защитой от 'битых' ссылок и таймаутов."""
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status != 200:
                        logger.error(f"Ошибка загрузки фото: {response.status} для {url}")
                        return None
                    
                    content_type = response.headers.get('Content-Type', '')
                    if not content_type.startswith('image/'):
                        logger.error(f"URL не является изображением: {content_type}")
                        return None

                    image_bytes = await response.read()
                    
                    # Защита от слишком больших файлов (Ollama может упасть по OOM)
                    if len(image_bytes) > 5 * 1024 * 1024:  # > 5 MB
                        logger.warning("Изображение слишком велико. В продакшене здесь нужен ресайз через Pillow.")
                        # TODO: Добавить интеграцию с PIL для ресайза до 1024x1024
                        
                    return base64.b64encode(image_bytes).decode('utf-8')
        except asyncio.TimeoutError:
            logger.error(f"Таймаут при скачивании {url}")
        except Exception as e:
            logger.error(f"Системная ошибка сети при загрузке фото: {e}")
        return None

# ==========================================
# 5. OLLAMA API КЛИЕНТ (ПРЯМЫЕ ЗАПРОСЫ)
# ==========================================
class OllamaClient:
    """Прямой HTTP-клиент к демону Ollama для полного контроля над запросами."""
    
    def __init__(self, host: str = "http://127.0.0.1:11434", model: str = "llava:latest"):
        self.host = host
        self.model = model

    async def _request(self, endpoint: str, payload: dict) -> dict:
        url = f"{self.host}{endpoint}"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as response:
                    response.raise_for_status()
                    return await response.json()
            except Exception as e:
                logger.error(f"Ошибка связи с Ollama демоном: {e}")
                raise

    async def ensure_model(self):
        """Проверяет локальный кэш Ollama на наличие нужной vision-модели."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.host}/api/tags") as response:
                    data = await response.json()
                    models = [m["name"] for m in data.get("models", [])]
                    
            if self.model not in models:
                logger.info(f"Модель {self.model} не найдена. Отправка команды pull...")
                # Pull-запрос может выполняться долго, запускаем стриминг
                async with aiohttp.ClientSession() as session:
                    async with session.post(f"{self.host}/api/pull", json={"name": self.model}) as resp:
                        async for chunk in resp.content.iter_any():
                            pass # Пропускаем прогресс-бар в логах
                logger.info("Модель успешно загружена.")
        except Exception as e:
            logger.error(f"Сбой инициализации модели {self.model}: {e}")

    async def chat_completion(self, messages: List[dict], json_format: bool = False) -> str:
        """Отправляет массив сообщений (с картинками) в модель и возвращает текст."""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.2, # Низкая температура для аналитики
                "top_p": 0.9
            }
        }
        if json_format:
            payload["format"] = "json"

        response_data = await self._request("/api/chat", payload)
        return response_data.get("message", {}).get("content", "")

# ==========================================
# 6. ЯДРО БИЗНЕС-ЛОГИКИ (VISION + CHAT)
# ==========================================
class VisionChatEngine:
    def __init__(self):
        self.db = DatabaseManager()
        self.ollama = OllamaClient(model="llava:latest")
        
    def _get_system_prompt(self, category: str) -> str:
        """Динамические промпты для разных категорий товаров."""
        prompts = {
            "auto": (
                "Ты профессиональный автоподборщик и эксперт-криминалист. "
                "Изучи фотографию автомобиля и описание продавца. "
                "Твоя цель - найти несоответствия, скрытые дефекты, ржавчину, зазоры, признаки ДТП. "
                "ОТВЕТЬ СТРОГО В JSON: {\"is_approved\": true/false, \"critical_defects\": [\"список\"], \"summary\": \"Вердикт\"}"
            ),
            "tech": (
                "Ты эксперт по б/у электронике. Оцени состояние устройства на фото. "
                "Ищи сколы, царапины на экранах, вздутые батареи, следы вскрытия. "
                "ОТВЕТЬ СТРОГО В JSON: {\"is_approved\": true/false, \"critical_defects\": [\"список\"], \"summary\": \"Вердикт\"}"
            )
        }
        return prompts.get(category, "Изучи фото и описание. ОТВЕТЬ В JSON: {\"is_approved\": true/false, \"summary\": \"Вердикт\"}")

    async def initial_vision_analysis(self, request: VisionAnalysisRequest) -> dict:
        """
        Первичный прогон: скачиваем фото, создаем сессию чата, 
        просим ИИ выдать JSON-отчет и сохраняем всё в БД.
        """
        base64_image = await ImageProcessor.download_and_encode(request.image_url)
        if not base64_image:
            raise HTTPException(status_code=400, detail="Не удалось загрузить или обработать изображение")

        session_id = f"session_{request.item_id}_{int(time.time())}"
        self.db.create_session(session_id, request.item_id, request.user_id)

        # 1. Системный промпт
        system_msg = ChatMessage(role="system", content=self._get_system_prompt(request.category))
        self.db.add_message(session_id, system_msg)

        # 2. Сообщение пользователя (Описание + Картинка)
        user_content = f"Описание продавца: '{request.description}'. Проанализируй прикрепленное фото."
        user_msg = ChatMessage(role="user", content=user_content, images=[base64_image])
        self.db.add_message(session_id, user_msg)

        # 3. Вызов ИИ
        history = self.db.get_session_history(session_id)
        raw_response = await self.ollama.chat_completion(history, json_format=True)

        try:
            parsed_json = json.loads(raw_response)
        except json.JSONDecodeError:
            logger.error(f"Ожидался JSON, получено: {raw_response}")
            parsed_json = {"is_approved": False, "summary": "Ошибка парсинга ответа ИИ", "critical_defects": []}

        # 4. Сохраняем ответ ИИ в контекст
        ai_msg = ChatMessage(role="assistant", content=json.dumps(parsed_json, ensure_ascii=False))
        self.db.add_message(session_id, ai_msg)

        return {
            "session_id": session_id,
            "analysis": parsed_json
        }

    async def continue_chat(self, request: ChatRequest) -> str:
        """
        Продолжение диалога. Пользователь задает вопрос по конкретному товару.
        ИИ отвечает, учитывая предыдущие сообщения и фотографию из базы.
        """
        # Проверяем существование истории
        history = self.db.get_session_history(request.session_id)
        if not history:
            raise HTTPException(status_code=404, detail="Сессия не найдена")

        # Добавляем новый вопрос
        new_user_msg = ChatMessage(role="user", content=request.message)
        self.db.add_message(request.session_id, new_user_msg)

        # Подтягиваем актуальную историю (уже с новым вопросом)
        # Если история огромная, SQLite отдаст только лимит, но первую фотку нужно сохранить в контексте
        updated_history = self.db.get_session_history(request.session_id, limit=15)
        
        logger.info(f"Запрос к ИИ в рамках сессии {request.session_id}. Вопрос: {request.message}")
        
        # Вызываем ИИ (уже без требования JSON, это обычный чат)
        ai_response_text = await self.ollama.chat_completion(updated_history, json_format=False)

        # Сохраняем ответ
        new_ai_msg = ChatMessage(role="assistant", content=ai_response_text)
        self.db.add_message(request.session_id, new_ai_msg)

        return ai_response_text

# ==========================================
# 7. FASTAPI РОУТЕР (МИКРОСЕРВИС)
# ==========================================
app = FastAPI(title="Vision AI Microservice", version="2.0")
engine = VisionChatEngine()

@app.on_event("startup")
async def startup_event():
    logger.info("Проверка локальной ИИ модели...")
    await engine.ollama.ensure_model()

@app.post("/api/v1/analyze")
async def analyze_item(request: VisionAnalysisRequest):
    """Эндпоинт для первичного жесткого анализа объявления с маркетплейса."""
    try:
        result = await engine.initial_vision_analysis(request)
        return result
    except Exception as e:
        logger.error(f"Сбой в /analyze: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/chat")
async def chat_with_ai(request: ChatRequest):
    """Эндпоинт для текстового общения с ИИ о найденном товаре."""
    try:
        reply = await engine.continue_chat(request)
        return {"session_id": request.session_id, "reply": reply}
    except Exception as e:
        logger.error(f"Сбой в /chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/history/{session_id}")
async def get_history(session_id: str):
    """Выгрузка истории переписки для отображения в мобильном приложении."""
    history = engine.db.get_session_history(session_id)
    # Вырезаем тяжелые base64 картинки перед отправкой на фронт
    for msg in history:
        msg.pop("images", None)
    return {"session_id": session_id, "messages": history}

# ==========================================
# 8. ЗАПУСК И ЭМУЛЯЦИЯ (ДЛЯ ТЕСТОВ)
# ==========================================
async def local_simulation():
    """Тестовый прогон ядра без поднятия FastAPI сервера."""
    test_engine = VisionChatEngine()
    await test_engine.ollama.ensure_model()
    
    logger.info("--- 1. ПЕРВИЧНЫЙ АНАЛИЗ (АВТО В УЛЬЯНОВСКЕ) ---")
    mock_request = VisionAnalysisRequest(
        user_id="usr_888",
        item_id="avito_777",
        category="auto",
        description="Машина в идеале. Ездил дедушка за хлебом. Без ДТП.",
        # Имитация битой машины
        image_url="https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Dodge_Charger_wrecked.jpg/800px-Dodge_Charger_wrecked.jpg"
    )
    
    analysis_result = await test_engine.initial_vision_analysis(mock_request)
    session_id = analysis_result["session_id"]
    print(f"\n[Анализ JSON]:\n{json.dumps(analysis_result['analysis'], indent=2, ensure_ascii=False)}")
    
    logger.info("--- 2. ЧАТ С ИИ ПО ЭТОЙ ЖЕ ФОТОГРАФИИ ---")
    chat_req = ChatRequest(
        session_id=session_id,
        message="Ты уверен, что с машиной проблемы? Опиши подробнее, что конкретно сломано на передней части?"
    )
    
    reply = await test_engine.continue_chat(chat_req)
    print(f"\n[Ответ ИИ в чате]:\n{reply}\n")


if __name__ == "__main__":
    import sys
    # Если запустить файл с флагом --server, поднимется полноценный FastAPI
    if len(sys.argv) > 1 and sys.argv[1] == "--server":
        uvicorn.run(app, host="0.0.0.0", port=8000)
    else:
        # Иначе просто прогоняем симуляцию
        asyncio.run(local_simulation())
