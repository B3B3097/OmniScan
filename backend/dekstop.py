import asyncio
import json
import logging
import sqlite3
import os
import time
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
import aiohttp

# ==========================================
# 1. КОНФИГУРАЦИЯ И ЛОГИРОВАНИЕ
# ==========================================
os.makedirs("data/db", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("FraudDetectorEngine")

# ==========================================
# 2. PYDANTIC МОДЕЛИ
# ==========================================
class Review(BaseModel):
    id: str
    text: str
    rating: int = Field(..., ge=1, le=5)
    date_posted: str
    author_name: str

class SellerProfile(BaseModel):
    seller_id: str
    platform: str
    name: str
    reviews: List[Review] = Field(default_factory=list)

class FraudAnalysisResult(BaseModel):
    is_fraudulent: bool
    fraud_score: float = Field(..., ge=0.0, le=100.0) # Процент уверенности ИИ в накрутке
    evidence: List[str] = Field(default_factory=list) # Доказательства (почему ИИ так решил)
    verdict: str

# ==========================================
# 3. БАЗА ДАННЫХ ЧЕРНОГО СПИСКА (BLACKLIST)
# ==========================================
class BlacklistManager:
    """Управление персональным черным списком пользователей и глобальным ЧС."""
    
    def __init__(self, db_path: str = "data/db/blacklist.sqlite"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Персональный ЧС: пользователь заблокировал продавца
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_blacklist (
                    user_id TEXT NOT NULL,
                    seller_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    added_at REAL NOT NULL,
                    PRIMARY KEY (user_id, seller_id, platform)
                )
            """)
            # Глобальный ЧС: ИИ пометил продавца как 100% накрутчика (фрод)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS global_fraud_list (
                    seller_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    fraud_score REAL NOT NULL,
                    reason TEXT,
                    detected_at REAL NOT NULL,
                    PRIMARY KEY (seller_id, platform)
                )
            """)
            conn.commit()

    def add_to_user_blacklist(self, user_id: str, seller_id: str, platform: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO user_blacklist (user_id, seller_id, platform, added_at) VALUES (?, ?, ?, ?)",
                (user_id, seller_id, platform, time.time())
            )
            conn.commit()
            logger.info(f"[Blacklist] Пользователь {user_id} заблокировал продавца {seller_id} ({platform})")

    def add_to_global_fraud(self, seller_id: str, platform: str, score: float, reason: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO global_fraud_list (seller_id, platform, fraud_score, reason, detected_at) VALUES (?, ?, ?, ?, ?)",
                (seller_id, platform, score, reason, time.time())
            )
            conn.commit()
            logger.warning(f"[Fraud DB] Продавец {seller_id} занесен в глобальный ЧС. Скор: {score}")

    def is_seller_blocked(self, user_id: str, seller_id: str, platform: str) -> bool:
        """Проверка: заблокирован ли продавец юзером ИЛИ глобальным ИИ фильтром."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Проверка персонального ЧС
            cursor.execute("SELECT 1 FROM user_blacklist WHERE user_id = ? AND seller_id = ? AND platform = ?", (user_id, seller_id, platform))
            if cursor.fetchone():
                return True
                
            # Проверка глобального ЧС (фрод > 80%)
            cursor.execute("SELECT fraud_score FROM global_fraud_list WHERE seller_id = ? AND platform = ?", (seller_id, platform))
            result = cursor.fetchone()
            if result and result[0] >= 80.0:
                return True
                
        return False

# ==========================================
# 4. ИИ-ДВИЖОК АНАЛИЗА ОТЗЫВОВ (LLM)
# ==========================================
class AIFraudDetector:
    """Анализирует текст отзывов через LLM для выявления паттернов ботоферм."""
    
    def __init__(self, use_local_ollama: bool = True):
        self.use_local = use_local_ollama
        self.endpoint = "http://127.0.0.1:11434/api/generate" # Адрес локальной Ollama

    def _build_prompt(self, seller_name: str, reviews: List[Review]) -> str:
        reviews_text = "\n".join([f"[{r.date_posted}] {r.author_name} (Оценка: {r.rating}/5): {r.text}" for r in reviews])
        
        prompt = f"""Ты эксперт по кибербезопасности и анализу данных. Твоя задача — выявить накрученные (фейковые) отзывы продавца '{seller_name}'.
Признаки накрутки:
1. Однотипные, короткие фразы ("Всё супер", "Отличный продавец", "Рекомендую").
2. Отсутствие конкретики о товаре.
3. Подозрительная кучность (много 5-звездочных отзывов за 1-2 дня).
4. Одинаковая структура предложений у разных авторов.

Вот последние отзывы продавца:
{reviews_text}

Проанализируй их. Ответь СТРОГО в формате JSON без markdown разметки:
{{
    "is_fraudulent": true/false,
    "fraud_score": 0.0-100.0,
    "evidence": ["причина 1", "причина 2"],
    "verdict": "Краткий вывод"
}}"""
        return prompt

    async def analyze_seller(self, seller: SellerProfile) -> FraudAnalysisResult:
        if len(seller.reviews) < 3:
            # Слишком мало данных для анализа
            return FraudAnalysisResult(is_fraudulent=False, fraud_score=0.0, evidence=["Мало отзывов"], verdict="Недостаточно данных")

        prompt = self._build_prompt(seller.name, seller.reviews)
        logger.info(f"Отправка {len(seller.reviews)} отзывов продавца {seller.seller_id} на ИИ-анализ...")

        # Эмуляция вызова к LLM (в проде здесь aiohttp запрос к Ollama/OpenAI)
        await asyncio.sleep(2) 
        
        # Простейшая эмуляция ответа ИИ для примера. 
        # Если в отзывах есть спам-паттерн (например все отзывы в один день и короткие)
        is_spam_likely = all(len(r.text) < 20 for r in seller.reviews) and len(seller.reviews) > 5

        if is_spam_likely:
            mock_ai_response = {
                "is_fraudulent": True,
                "fraud_score": 95.5,
                "evidence": [
                    "Все отзывы состоят из 2-3 слов.",
                    "Отсутствует описание реального опыта покупки.",
                    "Высокая плотность отзывов с оценкой 5/5."
                ],
                "verdict": "Критическая вероятность накрутки ботофермой."
            }
        else:
            mock_ai_response = {
                "is_fraudulent": False,
                "fraud_score": 15.0,
                "evidence": ["Отзывы содержат уникальные детали.", "Разное время публикации."],
                "verdict": "Отзывы выглядят органическими."
            }

        return FraudAnalysisResult(**mock_ai_response)

# ==========================================
# 5. ГЕЙТВЕЙ УВЕДОМЛЕНИЙ (ПЕРЕХВАТЧИК PUSH)
# ==========================================
class PushNotificationFilter:
    """Проверяет товары перед отправкой PUSH-уведомлений пользователю."""
    
    def __init__(self):
        self.blacklist = BlacklistManager()
        self.ai_detector = AIFraudDetector()

    async def process_and_filter(self, user_id: str, item: dict, seller: SellerProfile) -> bool:
        """
        Возвращает True, если уведомление МОЖНО отправлять.
        Возвращает False, если продавец в ЧС или накрутчик.
        """
        # 1. Быстрая проверка по базам (Персональный ЧС + Глобальный фрод)
        if self.blacklist.is_seller_blocked(user_id, seller.seller_id, seller.platform):
            logger.info(f"[PUSH FILTER] Отмена отправки. Продавец {seller.seller_id} заблокирован или в глобальном ЧС.")
            return False

        # 2. Если продавца нет в БД, натравливаем ИИ для анализа "на лету"
        analysis = await self.ai_detector.analyze_seller(seller)
        
        if analysis.is_fraudulent and analysis.fraud_score >= 80.0:
            logger.warning(f"[PUSH FILTER] ИИ обнаружил фрод! Скор: {analysis.fraud_score}. Заносим в глобальный ЧС.")
            self.blacklist.add_to_global_fraud(seller.seller_id, seller.platform, analysis.fraud_score, analysis.verdict)
            return False # Блокируем пуш

        logger.info(f"[PUSH FILTER] Проверка пройдена. Продавец чист (Фрод скор: {analysis.fraud_score}%). Пуш разрешен.")
        return True

# ==========================================
# 6. БЛОК ТЕСТИРОВАНИЯ (СИМУЛЯЦИЯ)
# ==========================================
async def test_fraud_engine():
    # Инициализируем систему
    push_filter = PushNotificationFilter()
    blacklist_mgr = push_filter.blacklist

    user = "user_999"
    
    # Ситуация 1: Пользователь сам блокирует нормального продавца, потому что он ему не нравится
    print("--- СИТУАЦИЯ 1: Ручная блокировка (Персональный ЧС) ---")
    blacklist_mgr.add_to_user_blacklist(user, seller_id="seller_123", platform="avito")
    
    mock_seller_1 = SellerProfile(
        seller_id="seller_123", platform="avito", name="Иван Иванов",
        reviews=[Review(id="1", text="Хорошая машина", rating=5, date_posted="2026-08-01", author_name="Алексей")]
    )
    
    can_send_1 = await push_filter.process_and_filter(user, item={"title": "BMW X5"}, seller=mock_seller_1)
    print(f"Пуш отправлен: {can_send_1}\n")


    # Ситуация 2: Новый продавец с явно накрученными отзывами (работа ИИ)
    print("--- СИТУАЦИЯ 2: Работа ИИ (Накрученные отзывы) ---")
    mock_seller_2 = SellerProfile(
        seller_id="scammer_777", platform="wb", name="SuperShop",
        reviews=[
            Review(id="10", text="Всё супер", rating=5, date_posted="2026-08-15", author_name="User1"),
            Review(id="11", text="Отличный продавец", rating=5, date_posted="2026-08-15", author_name="User2"),
            Review(id="12", text="Рекомендую", rating=5, date_posted="2026-08-15", author_name="User3"),
            Review(id="13", text="Супер", rating=5, date_posted="2026-08-15", author_name="User4"),
            Review(id="14", text="Круто", rating=5, date_posted="2026-08-15", author_name="User5"),
            Review(id="15", text="Всё супер", rating=5, date_posted="2026-08-15", author_name="User6"),
        ]
    )
    
    can_send_2 = await push_filter.process_and_filter(user, item={"title": "iPhone 15"}, seller=mock_seller_2)
    print(f"Пуш отправлен: {can_send_2}\n")


    # Ситуация 3: Нормальный продавец с органическими отзывами
    print("--- СИТУАЦИЯ 3: Органические отзывы (Чистый продавец) ---")
    mock_seller_3 = SellerProfile(
        seller_id="good_guy_001", platform="ozon", name="TechStore",
        reviews=[
            Review(id="20", text="Брал ноутбук для работы. Упаковка была немного помята, но сам ноут работает отлично. Положили в подарок мышку.", rating=4, date_posted="2026-08-10", author_name="Михаил"),
            Review(id="21", text="Доставка задержалась на день. Продавец отвечал на сообщения быстро. Товар соответствует описанию.", rating=5, date_posted="2026-08-12", author_name="Ольга"),
            Review(id="22", text="Отличный сервис, помогли подобрать конфигурацию.", rating=5, date_posted="2026-08-14", author_name="Сергей"),
        ]
    )
    
    can_send_3 = await push_filter.process_and_filter(user, item={"title": "MacBook Air"}, seller=mock_seller_3)
    print(f"Пуш отправлен: {can_send_3}")

if __name__ == "__main__":
    asyncio.run(test_fraud_engine())
