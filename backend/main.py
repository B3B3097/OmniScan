import asyncio
import aiohttp
import random
import logging
import json
import hashlib
import os
from typing import List, Dict, Optional, Literal, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from urllib.parse import urlencode, quote
from pydantic import BaseModel, HttpUrl, Field, model_validator

# ==========================================
# 1. КОНФИГУРАЦИЯ И ЛОГИРОВАНИЕ
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.FileHandler("monolith_core.log"), logging.StreamHandler()]
)
logger = logging.getLogger("MonolithCore")

# Сотни ключей для API (матрица)
class APIConfig:
    WB_API_TOKEN = os.getenv("WB_API_TOKEN", "mock_wb_token")
    OZON_CLIENT_ID = os.getenv("OZON_CLIENT_ID", "mock_ozon_id")
    AVITO_CLIENT_ID = os.getenv("AVITO_CLIENT_ID", "mock_avito_id")
    OPENAI_VISION_KEY = os.getenv("OPENAI_VISION_KEY", "mock_openai_key")
    FIREBASE_SERVER_KEY = os.getenv("FIREBASE_SERVER_KEY", "mock_fcm_key")
    DADATA_API_KEY = os.getenv("DADATA_API_KEY", "mock_dadata_key")
    AVTOKOD_API_KEY = os.getenv("AVTOKOD_API_KEY", "mock_avtokod_key")
    VIN01_API_KEY = os.getenv("VIN01_API_KEY", "mock_vin01_key")
    NOMEROGRAM_TOKEN = os.getenv("NOMEROGRAM_TOKEN", "mock_nomerogram")

# ==========================================
# 2. СТРОГИЕ МОДЕЛИ ДАННЫХ (PYDANTIC)
# ==========================================
class UserProfile(BaseModel):
    user_id: str
    referral_code: str
    referred_by: Optional[str] = None
    is_pro: bool = False
    pro_expires_at: Optional[datetime] = None
    device_token: str

class SearchFilter(BaseModel):
    target_city: str
    query: str
    categories: List[str]
    brands: List[str] = Field(default_factory=list)
    min_price: float = Field(default=0.0, ge=0)
    max_price: float = Field(default=float('inf'), gt=0)
    is_auto_podbor: bool = False

    @model_validator(mode='after')
    def check_budget_range(self):
        if self.min_price >= self.max_price:
            raise ValueError("Бюджет 'от' не может быть больше 'до'")
        return self

class BaseItem(BaseModel):
    platform_id: str
    platform: str
    title: str
    brand: str
    city: str
    description: str
    price: float
    url: str
    image_url: str

class AutoItem(BaseItem):
    vin: str
    seller_phone: str
    owners_count: int = 1
    accidents_count: int = 0
    is_perekup: bool = False
    vision_report: Optional[str] = None
    is_vision_approved: bool = False

# ==========================================
# 3. ПОЛЬЗОВАТЕЛЬСКАЯ БАЗА И РЕФЕРАЛЫ
# ==========================================
class UserManager:
    def __init__(self):
        # Имитация базы данных пользователей
        self.db: Dict[str, UserProfile] = {
            "user_1": UserProfile(
                user_id="user_1",
                referral_code="REF123",
                device_token="device_abc"
            ),
            "user_2": UserProfile(
                user_id="user_2",
                referral_code="FRIEND777",
                device_token="device_xyz",
                is_pro=True,
                pro_expires_at=datetime.utcnow() + timedelta(days=2)
            )
        }

    def apply_referral(self, current_user_id: str, friend_code: str) -> str:
        """
        Получение PRO подписки на 7 дней за друга по реферальному коду.
        """
        user = self.db.get(current_user_id)
        if not user:
            return "Пользователь не найден."
        if user.referred_by:
            return "Вы уже вводили реф. код."
        
        friend = next((u for u in self.db.values() if u.referral_code == friend_code), None)
        if not friend:
            return "Код друга не найден."

        # Начисляем 7 дней текущему юзеру
        now = datetime.utcnow()
        if user.pro_expires_at and user.pro_expires_at > now:
            user.pro_expires_at += timedelta(days=7)
        else:
            user.pro_expires_at = now + timedelta(days=7)
        user.is_pro = True
        user.referred_by = friend_code

        # Начисляем 7 дней другу
        if friend.pro_expires_at and friend.pro_expires_at > now:
            friend.pro_expires_at += timedelta(days=7)
        else:
            friend.pro_expires_at = now + timedelta(days=7)
        friend.is_pro = True

        logger.info(f"Реферальный код {friend_code} применен. Пользователь {current_user_id} получил 7 дней PRO.")
        return "Успех! PRO активировано на 7 дней."

# ==========================================
# 4. МЕНЕДЖЕР АНТИ-БОТ И СЕТЬ
# ==========================================
class NetworkEngine:
    def __init__(self):
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15"
        ]

    def get_headers(self) -> dict:
        return {
            "User-Agent": random.choice(self.user_agents),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive"
        }

    async def fetch(self, session: aiohttp.ClientSession, url: str) -> dict:
        try:
            async with session.get(url, headers=self.get_headers(), timeout=15) as response:
                if response.status == 200:
                    return await response.json()
                logger.warning(f"Ошибка HTTP {response.status} на {url}")
        except Exception as e:
            logger.error(f"Сетевая ошибка: {e}")
        return {}

# ==========================================
# 5. ПАРСЕРЫ ПЛАТФОРМ (МАРКЕТПЛЕЙСЫ И Б/У)
# ==========================================
class ScraperSubsystem:
    def __init__(self, network: NetworkEngine):
        self.network = network

    async def analyze_platforms_by_city(self, city: str) -> List[str]:
        """Анализ доступных платформ в зависимости от запрошенного города."""
        logger.info(f"Анализ доступности платформ для города: {city}...")
        await asyncio.sleep(1) # Имитация гео-проверки
        # Если город маленький, отключаем локальный DNS, оставляем маркетплейсы
        if city.lower() in ["москва", "санкт-петербург", "ульяновск"]:
            return ["wb", "ozon", "avito", "dns", "mvideo"]
        return ["wb", "ozon", "avito"]

    async def scrape_wildberries(self, session: aiohttp.ClientSession, query: str, min_price: float, max_price: float, brands: List[str]) -> List[BaseItem]:
        logger.info(f"Парсинг WB. Запрос: {query}, Бюджет: {min_price}-{max_price}")
        # Эмуляция ответа Wildberries
        await asyncio.sleep(1.5)
        raw_data = [
            {"id": "111", "name": "Кроссовки Nike", "brand": "Nike", "price": 8000},
            {"id": "222", "name": "Кроссовки Adidas", "brand": "Adidas", "price": 9500},
            {"id": "333", "name": "Кроссовки Noname", "brand": "Noname", "price": 2000}
        ]
        
        results = []
        for item in raw_data:
            # Жесткие фильтры по бюджету и бренду
            if item["price"] < min_price or item["price"] > max_price:
                continue
            if brands and item["brand"] not in brands:
                continue
                
            results.append(BaseItem(
                platform_id=f"wb_{item['id']}",
                platform="WB",
                title=item["name"],
                brand=item["brand"],
                city="РФ",
                description="Описание из карточки WB",
                price=item["price"],
                url=f"https://wildberries.ru/catalog/{item['id']}",
                image_url="https://wb.ru/image.jpg"
            ))
        return results

    async def scrape_avito_cars(self, session: aiohttp.ClientSession, query: str, city: str, min_price: float, max_price: float, brands: List[str]) -> List[AutoItem]:
        logger.info(f"Парсинг Авито (Авто). Город: {city}. Запрос: {query}")
        await asyncio.sleep(2)
        # Эмуляция сырой выдачи б/у авто
        raw_data = [
            {
                "id": "A1", "title": "Toyota Camry 2020", "brand": "Toyota", 
                "price": 2500000, "description": "Не бита, ездила жена, идеальное состояние.",
                "vin": "JTNB52K103012345", "seller_phone": "79990001122"
            },
            {
                "id": "A2", "title": "BMW 3 2018", "brand": "BMW", 
                "price": 2200000, "description": "Срочно, торг у капота.",
                "vin": "WBA320I000111222", "seller_phone": "78889990011"
            }
        ]

        results = []
        for item in raw_data:
            if item["price"] < min_price or item["price"] > max_price:
                continue
            if brands and item["brand"] not in brands:
                continue
                
            results.append(AutoItem(
                platform_id=f"avito_{item['id']}",
                platform="Avito",
                title=item["title"],
                brand=item["brand"],
                city=city,
                description=item["description"],
                price=item["price"],
                url=f"https://avito.ru/{item['id']}",
                image_url="https://avito.ru/photo.jpg",
                vin=item["vin"],
                seller_phone=item["seller_phone"]
            ))
        return results

# ==========================================
# 6. ДВИЖОК КОМПРОМАТА И АНАЛИЗА ПРОДАВЦОВ
# ==========================================
class KompromatEngine:
    def __init__(self):
        self.api_key = APIConfig.AVTOKOD_API_KEY

    async def gather_dossier(self, item: AutoItem) -> AutoItem:
        """Сбор компромата: кол-во владельцев и проверка на перекупа."""
        logger.info(f"Сбор компромата на авто {item.title} (VIN: {item.vin})...")
        await asyncio.sleep(1) # Имитация запроса к базам

        # Эмуляция проверки истории VIN
        if item.brand == "BMW":
            item.owners_count = 5
            item.accidents_count = 2 # Битая машина
        else:
            item.owners_count = 1
            item.accidents_count = 0

        # Эмуляция проверки продавца по номеру телефона
        historical_sales = 6 if item.brand == "BMW" else 1
        if historical_sales > 3:
            item.is_perekup = True
            logger.warning(f"Продавец {item.seller_phone} помечен как ПЕРЕКУП.")

        return item

# ==========================================
# 7. AI VISION: ОЦЕНКА СОСТОЯНИЯ
# ==========================================
class VisionAIEngine:
    def __init__(self):
        self.api_key = APIConfig.OPENAI_VISION_KEY

    async def evaluate_condition(self, description: str, image_url: str) -> dict:
        """
        Прогон фото через ИИ Vision для сопоставления описания и реального состояния.
        """
        logger.info("ИИ Vision анализирует состояние на фото...")
        await asyncio.sleep(2) # Имитация запроса к OpenAI
        
        # Анализ
        if "идеальное состояние" in description.lower():
            return {
                "approved": True,
                "report": "Фото подтверждает описание. Дефектов кузова не обнаружено. Состояние соответствует заявленному."
            }
        else:
            return {
                "approved": False,
                "report": "На фото видны царапины на бампере и зазоры. Состояние не соответствует цене."
            }

# ==========================================
# 8. СИСТЕМА УВЕДОМЛЕНИЙ (PUSH)
# ==========================================
class NotificationSystem:
    @staticmethod
    def send_push(device_token: str, title: str, body: str):
        """Отправка Push-уведомления пользователю, если объявление подошло."""
        logger.info(f"[PUSH SENT to {device_token}]: {title} - {body}")

# ==========================================
# 9. ГЛАВНЫЙ ОРКЕСТРАТОР (MAIN PIPELINE)
# ==========================================
class MainOrchestrator:
    def __init__(self):
        self.users = UserManager()
        self.network = NetworkEngine()
        self.scraper = ScraperSubsystem(self.network)
        self.kompromat = KompromatEngine()
        self.vision = VisionAIEngine()

    async def execute_search_24_7(self, current_user_id: str, search_filter: SearchFilter):
        logger.info(f"Запуск умного трекера 24/7 для пользователя: {current_user_id}")
        user = self.users.db.get(current_user_id)
        if not user:
            logger.error("Пользователь не авторизован.")
            return

        # 1. Запрос названия города и анализ доступных платформ
        available_platforms = await self.scraper.analyze_platforms_by_city(search_filter.target_city)
        logger.info(f"Доступные платформы для поиска: {available_platforms}")

        async with aiohttp.ClientSession() as session:
            # 2. Параллельный парсинг площадок
            tasks = []
            if "wb" in available_platforms and not search_filter.is_auto_podbor:
                tasks.append(self.scraper.scrape_wildberries(
                    session, search_filter.query, search_filter.min_price, search_filter.max_price, search_filter.brands
                ))
            if "avito" in available_platforms and search_filter.is_auto_podbor:
                tasks.append(self.scraper.scrape_avito_cars(
                    session, search_filter.query, search_filter.target_city, search_filter.min_price, search_filter.max_price, search_filter.brands
                ))

            gathered_results = await asyncio.gather(*tasks)
            all_found_items = [item for sublist in gathered_results for item in sublist]

            # 3. Анализ и фильтрация результатов
            for item in all_found_items:
                if isinstance(item, AutoItem) and search_filter.is_auto_podbor:
                    # Собираем компромат
                    item = await self.kompromat.gather_dossier(item)

                    # Автоподбор: отфильтровываем машины, чтобы особо не было аварий
                    if item.accidents_count > 0:
                        logger.info(f"Объявление {item.title} отбраковано. Причина: найдено {item.accidents_count} ДТП.")
                        continue

                    # 4. Проверка состояния через ИИ Vision (Только для PRO)
                    if user.is_pro:
                        vision_result = await self.vision.evaluate_condition(item.description, item.image_url)
                        item.vision_report = vision_result["report"]
                        item.is_vision_approved = vision_result["approved"]

                        # Если все как надо, отправляем PUSH
                        if item.is_vision_approved:
                            push_body = f"Владельцев: {item.owners_count}. Перекуп: {'Да' if item.is_perekup else 'Нет'}. ИИ: {item.vision_report}"
                            NotificationSystem.send_push(
                                user.device_token,
                                title=f"Найден идеальный вариант: {item.title}",
                                body=push_body
                            )
                    else:
                        logger.info(f"Найден {item.title}, но ИИ Vision доступен только по PRO подписке.")

# ==========================================
# 10. ТОЧКА ВХОДА
# ==========================================
async def main():
    orchestrator = MainOrchestrator()

    # Сценарий: Пользователь 1 вводит код Друга 777 для получения PRO
    logger.info("--- Активация реферальной системы ---")
    res = orchestrator.users.apply_referral("user_1", "FRIEND777")
    print(res)

    # Создаем жесткие фильтры для Автоподбора
    filters = SearchFilter(
        target_city="Ульяновск",
        query="Toyota",
        categories=["avito"],
        brands=["Toyota"],
        min_price=1000000,
        max_price=3000000,
        is_auto_podbor=True
    )

    # Запуск бесконечного цикла (эмуляция 24/7)
    logger.info("--- Запуск ядра поиска ---")
    while True:
        await orchestrator.execute_search_24_7("user_1", filters)
        logger.info("Цикл завершен. Пауза перед следующим сканированием...")
        break # Break установлен только для демонстрации, в продакшене тут await asyncio.sleep(300)

if __name__ == "__main__":
    asyncio.run(main())
