import asyncio
import aiohttp
import logging
import re
import json
from datetime import datetime
from typing import List, Dict, Optional, Any
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

# ==========================================
# 1. КОНФИГУРАЦИЯ И ЛОГИРОВАНИЕ
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("KompromatEngine")

# ==========================================
# 2. СТРОГИЕ МОДЕЛИ ДАННЫХ (DOSSIER)
# ==========================================
class AccidentRecord(BaseModel):
    date: str
    type: str
    region: str
    damage_points: List[str] = Field(default_factory=list)

class OwnershipPeriod(BaseModel):
    from_date: str
    to_date: Optional[str] = "Настоящее время"
    owner_type: str  # "Физическое лицо" / "Юридическое лицо"

class NomerogramPhoto(BaseModel):
    url: str
    date_posted: Optional[str] = None
    source: Optional[str] = "nomerogram.ru"
    is_accident_likely: bool = False

class DebtRecord(BaseModel):
    department: str
    bailiff: str
    amount: float
    subject: str

class CarDossier(BaseModel):
    vin: str
    license_plate: Optional[str] = None
    brand: str
    model: str
    year: int
    owners_count: int = 0
    ownership_history: List[OwnershipPeriod] = Field(default_factory=list)
    accidents: List[AccidentRecord] = Field(default_factory=list)
    is_wanted: bool = False
    has_restrictions: bool = False
    pledge_status: bool = False  # В залоге у банка
    nomerogram_photos: List[NomerogramPhoto] = Field(default_factory=list)
    seller_debts: List[DebtRecord] = Field(default_factory=list)
    
    @property
    def is_critical_risk(self) -> bool:
        """Автоматическая отбраковка машин с криминалом или тоталом."""
        return self.is_wanted or self.has_restrictions or len(self.accidents) > 2

# ==========================================
# 3. ПАРСЕР НОМЕРОГРАМА (NOMEROGRAM.RU)
# ==========================================
class NomerogramScraper:
    """Извлекает исторические фотографии автомобиля по госномеру."""
    
    def __init__(self, proxy_url: Optional[str] = None):
        self.base_url = "https://www.nomerogram.ru/api/v1/cars"
        self.proxy = proxy_url
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.nomerogram.ru",
            "Referer": "https://www.nomerogram.ru/"
        }

    def _format_plate(self, plate: str) -> str:
        """Очистка госномера от лишних символов (оставляем только буквы и цифры)."""
        return re.sub(r'[^А-Яа-яA-Za-z0-9]', '', plate).upper()

    async def fetch_photos(self, session: aiohttp.ClientSession, plate: str) -> List[NomerogramPhoto]:
        clean_plate = self._format_plate(plate)
        if not clean_plate:
            return []

        # API Номерограма обычно требует специфичных токенов или хешей,
        # в реальном бою часто парсят HTML веб-версии, если API закрыто.
        # Здесь реализован гибридный подход: стучимся в веб-морду и парсим DOM.
        url = f"https://www.nomerogram.ru/n/{clean_plate}/"
        logger.info(f"[Nomerogram] Поиск фотографий для госномера: {clean_plate}")

        photos = []
        try:
            async with session.get(url, headers=self.headers, proxy=self.proxy, timeout=15) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'lxml')
                    
                    # Ищем все теги img, которые относятся к галерее авто
                    img_tags = soup.find_all('img', class_=re.compile(r'car-photo|gallery-item'))
                    
                    for img in img_tags:
                        src = img.get('src') or img.get('data-src')
                        if src and 'nomerogram' in src:
                            # Простая эвристика: если в alt есть слова 'дтп', 'авария'
                            alt_text = img.get('alt', '').lower()
                            is_crash = any(word in alt_text for word in ['дтп', 'авария', 'разбита', 'удар'])
                            
                            photos.append(NomerogramPhoto(
                                url=src,
                                date_posted=datetime.utcnow().strftime("%Y-%m-%d"), # В реальности парсится из соседнего тега
                                is_accident_likely=is_crash
                            ))
                            
                    logger.info(f"[Nomerogram] Найдено {len(photos)} фото для {clean_plate}")
                elif response.status == 404:
                    logger.info(f"[Nomerogram] Фото для {clean_plate} не найдены (404).")
                else:
                    logger.warning(f"[Nomerogram] Ошибка доступа. Статус: {response.status}")
        except asyncio.TimeoutError:
            logger.error(f"[Nomerogram] Таймаут при запросе {clean_plate}")
        except Exception as e:
            logger.error(f"[Nomerogram] Внутренняя ошибка парсинга: {e}")

        return photos

# ==========================================
# 4. ИНТЕГРАЦИЯ С ГИБДД И АВТОТЕКОЙ
# ==========================================
class GibddAPI:
    """Интеграция с открытыми базами ГИБДД (через прокси-шлюз или напрямую)."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        # В реальности ГИБДД использует сложную систему капч, 
        # поэтому здесь эмулируется вызов к агрегатору (типа AVTOKOD или VIN01)
        self.gateway_url = "https://api.vin-checker.local/v1"

    async def get_history(self, session: aiohttp.ClientSession, vin: str) -> Dict[str, Any]:
        """Получение истории владения, ДТП, розыска и ограничений одним запросом."""
        logger.info(f"[GIBDD] Запрос полного отчета по VIN: {vin}")
        
        # Эмуляция ответа от государственного API
        await asyncio.sleep(1.5)
        
        # Мок-данные для демонстрации логики сборки компромата
        mock_response = {
            "owners": [
                {"from": "2018-05-12", "to": "2021-08-01", "type": "Юридическое лицо"},
                {"from": "2021-08-05", "to": "Настоящее время", "type": "Физическое лицо"}
            ],
            "accidents": [
                {
                    "date": "2019-11-20", 
                    "type": "Столкновение", 
                    "region": "Москва", 
                    "damage": ["Передний бампер", "Капот", "Левое крыло"]
                }
            ],
            "wanted": False,
            "restrictions": False,
            "pledge": True # Машина в залоге!
        }
        return mock_response

# ==========================================
# 5. ИНТЕГРАЦИЯ С ФССП (СУДЕБНЫЕ ПРИСТАВЫ)
# ==========================================
class FsspAPI:
    """Проверка продавца на долги (алименты, кредиты), из-за которых могут запретить регистрацию."""
    
    async def check_person(self, session: aiohttp.ClientSession, first_name: str, last_name: str, region: str) -> List[DebtRecord]:
        logger.info(f"[FSSP] Проверка продавца: {last_name} {first_name}, Регион: {region}")
        await asyncio.sleep(1.0)
        
        # Эмуляция парсинга базы судебных приставов
        # Если продавец проблемный, машина может уйти под арест
        if last_name.lower() == "перекупов":
            return [
                DebtRecord(
                    department="ОСП по ЦАО г. Москвы",
                    bailiff="Иванов И.И.",
                    amount=150000.0,
                    subject="Задолженность по кредитным платежам"
                )
            ]
        return []

# ==========================================
# 6. ГЛАВНЫЙ АГРЕГАТОР КОМПРОМАТА (ORCHESTRATOR)
# ==========================================
class KompromatOrchestrator:
    """Оркестратор, который запускает все проверки параллельно и собирает единый отчет."""
    
    def __init__(self, gibdd_key: str = "mock_key"):
        self.nomerogram = NomerogramScraper()
        self.gibdd = GibddAPI(api_key=gibdd_key)
        self.fssp = FsspAPI()

    async def generate_full_dossier(self, vin: str, plate: str, brand: str, model: str, year: int, seller_name: Optional[str] = None) -> CarDossier:
        """Главный метод: выстреливает десятки асинхронных запросов во все базы."""
        logger.info(f"=== СТАРТ СБОРА КОМПРОМАТА: {brand} {model} ({vin}) ===")
        
        dossier = CarDossier(
            vin=vin,
            license_plate=plate,
            brand=brand,
            model=model,
            year=year
        )

        connector = aiohttp.TCPConnector(limit_per_host=10)
        async with aiohttp.ClientSession(connector=connector) as session:
            # Формируем пул задач для параллельного выполнения
            tasks = [
                self.nomerogram.fetch_photos(session, plate),
                self.gibdd.get_history(session, vin)
            ]
            
            # Если знаем имя продавца из парсера Авито, проверяем его по приставам
            if seller_name and len(seller_name.split()) >= 2:
                parts = seller_name.split()
                tasks.append(self.fssp.check_person(session, first_name=parts[1], last_name=parts[0], region="77"))

            # Запускаем все проверки одновременно (экономит десятки секунд)
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # --- ПАРСИНГ РЕЗУЛЬТАТОВ ---
            
            # 1. Результаты Номерограма
            if isinstance(results[0], list):
                dossier.nomerogram_photos = results[0]

            # 2. Результаты ГИБДД
            if isinstance(results[1], dict):
                gibdd_data = results[1]
                dossier.is_wanted = gibdd_data.get("wanted", False)
                dossier.has_restrictions = gibdd_data.get("restrictions", False)
                dossier.pledge_status = gibdd_data.get("pledge", False)
                
                # Парсинг периодов владения
                for owner in gibdd_data.get("owners", []):
                    dossier.ownership_history.append(OwnershipPeriod(
                        from_date=owner["from"],
                        to_date=owner.get("to"),
                        owner_type=owner["type"]
                    ))
                dossier.owners_count = len(dossier.ownership_history)
                
                # Парсинг ДТП
                for acc in gibdd_data.get("accidents", []):
                    dossier.accidents.append(AccidentRecord(
                        date=acc["date"],
                        type=acc["type"],
                        region=acc["region"],
                        damage_points=acc.get("damage", [])
                    ))

            # 3. Результаты ФССП (если задача запускалась)
            if len(results) > 2 and isinstance(results[2], list):
                dossier.seller_debts = results[2]

        logger.info(f"=== СБОР ЗАВЕРШЕН. Найдено ДТП: {len(dossier.accidents)}, Фото: {len(dossier.nomerogram_photos)} ===")
        return dossier

# ==========================================
# 7. БЛОК ТЕСТИРОВАНИЯ
# ==========================================
async def run_kompromat_test():
    engine = KompromatOrchestrator()
    
    # Эмуляция данных, пришедших из парсера Авито
    report = await engine.generate_full_dossier(
        vin="XW8ZZZ61ZJG000000",
        plate="А777АА77",
        brand="Skoda",
        model="Octavia",
        year=2019,
        seller_name="Перекупов Иван"
    )
    
    print("\n" + "="*50)
    print(f"📄 ФИНАЛЬНОЕ ДОСЬЕ НА АВТОМОБИЛЬ")
    print("="*50)
    print(json.dumps(report.model_dump(), indent=4, ensure_ascii=False))
    
    if report.is_critical_risk:
        print("\n❌ ВНИМАНИЕ: АВТОМОБИЛЬ ОТБРАКОВАН АЛГОРИТМОМ (КРИТИЧЕСКИЙ РИСК!)")
    elif report.pledge_status:
        print("\n⚠️ ВНИМАНИЕ: МАШИНА В ЗАЛОГЕ У БАНКА!")

if __name__ == "__main__":
    asyncio.run(run_kompromat_test())
