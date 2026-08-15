import asyncio
import aiohttp
import logging
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ==========================================
# 1. КОНФИГУРАЦИЯ И ЛОГИРОВАНИЕ
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("PublicAPIEngine")

class PublicAPIConfig(BaseSettings):
    """
    Матрица настроек для публичных API (на базе github.com/public-apis/public-apis).
    """
    # 1. Автомобили (VIN Decoding) - NHTSA (Бесплатно, без ключа)
    NHTSA_BASE_URL: str = "https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/"
    
    # 2. Финансы и Валюты - ExchangeRate-API (Есть мощный бесплатный тир)
    EXCHANGERATE_API_KEY: Optional[str] = Field(default=None, description="Ключ для конвертации цен")
    
    # 3. OSINT и Безопасность - HaveIBeenPwned (Проверка сливов продавца)
    HIBP_API_KEY: Optional[str] = Field(default=None, description="Ключ HIBP для проверки email/телефонов")
    
    # 4. Геолокация - OpenStreetMap / Nominatim (Абсолютно бесплатно, требует User-Agent)
    NOMINATIM_USER_AGENT: str = "MarketVision_OSINT_Scanner/2.0 (contact@marketvision.local)"
    
    # 5. IP и Сеть (Определение прокси продавца)
    IPINFO_TOKEN: Optional[str] = Field(default=None)

    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

# Инициализация конфига
public_config = PublicAPIConfig()

# ==========================================
# 2. СТРОГИЕ МОДЕЛИ ДАННЫХ
# ==========================================
class VINDecodedData(BaseModel):
    vin: str
    make: str
    model: str
    year: str
    manufacturer: str
    plant_country: str
    error_code: str = ""

class OSINTLeakReport(BaseModel):
    target: str
    is_pwned: bool
    breaches: List[str] = Field(default_factory=list)
    risk_level: str = "LOW"

class CurrencyRates(BaseModel):
    base_code: str
    rates: Dict[str, float]
    last_updated: str

# ==========================================
# 3. БЕСПЛАТНЫЙ ДЕКОДЕР VIN (NHTSA)
# ==========================================
class NHTSAVinDecoder:
    """
    Декодирует VIN-код через базу Министерства транспорта США. 
    Работает для большинства мировых автомобилей. Не расходует платные лимиты ГИБДД.
    """
    def __init__(self):
        self.endpoint = public_config.NHTSA_BASE_URL

    async def decode(self, session: aiohttp.ClientSession, vin: str) -> Optional[VINDecodedData]:
        if not vin or len(vin) != 17:
            logger.error(f"[NHTSA] Некорректный VIN-код: {vin}")
            return None

        url = f"{self.endpoint}{vin}?format=json"
        logger.info(f"[NHTSA] Бесплатная расшифровка VIN: {vin}")
        
        try:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    results = data.get("Results", [])
                    if results:
                        car = results[0]
                        return VINDecodedData(
                            vin=vin,
                            make=car.get("Make", "Unknown"),
                            model=car.get("Model", "Unknown"),
                            year=car.get("ModelYear", "Unknown"),
                            manufacturer=car.get("Manufacturer", "Unknown"),
                            plant_country=car.get("PlantCountry", "Unknown"),
                            error_code=car.get("ErrorCode", "")
                        )
                else:
                    logger.warning(f"[NHTSA] Ошибка API: {response.status}")
        except Exception as e:
            logger.error(f"[NHTSA] Сбой сети при декодировании VIN: {e}")
        return None

# ==========================================
# 4. БЕСПЛАТНЫЙ ГЕОКОДЕР (NOMINATIM / OSM)
# ==========================================
class OpenStreetMapGeocoder:
    """
    Используется как fallback (запасной вариант), если платный Dadata упал или кончились лимиты.
    Позволяет определить точные координаты города для поиска по радиусу на Авито.
    """
    def __init__(self):
        self.endpoint = "https://nominatim.openstreetmap.org/search"
        self.headers = {"User-Agent": public_config.NOMINATIM_USER_AGENT}

    async def get_coordinates(self, session: aiohttp.ClientSession, city_name: str) -> Optional[Dict[str, float]]:
        params = {
            "q": city_name,
            "format": "json",
            "limit": 1
        }
        logger.info(f"[Nominatim] Поиск координат для: {city_name}")
        
        try:
            async with session.get(self.endpoint, params=params, headers=self.headers, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    if data:
                        return {
                            "lat": float(data[0]["lat"]),
                            "lon": float(data[0]["lon"]),
                            "display_name": data[0]["display_name"]
                        }
        except Exception as e:
            logger.error(f"[Nominatim] Сбой геокодирования: {e}")
        return None

# ==========================================
# 5. OSINT ПРОБИВ УТЕЧЕК (HAVE I BEEN PWNED)
# ==========================================
class HaveIBeenPwnedAPI:
    """
    Проверяет, сливался ли контакт продавца в базах данных.
    Если почта или номер продавца засветились в базах мошенников, мы повышаем риск-скор.
    """
    def __init__(self):
        self.endpoint = "https://haveibeenpwned.com/api/v3/breachedaccount/"
        self.api_key = public_config.HIBP_API_KEY

    async def check_leak(self, session: aiohttp.ClientSession, account: str) -> OSINTLeakReport:
        if not self.api_key:
            logger.warning("[HIBP] Ключ не настроен, OSINT проверка утечек пропущена.")
            return OSINTLeakReport(target=account, is_pwned=False)

        headers = {
            "hibp-api-key": self.api_key,
            "User-Agent": public_config.NOMINATIM_USER_AGENT
        }
        
        # HIBP требует задержку между запросами
        await asyncio.sleep(1.5)
        
        try:
            async with session.get(f"{self.endpoint}{account}?truncateResponse=false", headers=headers, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    breaches = [breach["Name"] for breach in data]
                    risk = "HIGH" if len(breaches) > 3 else "MEDIUM"
                    return OSINTLeakReport(target=account, is_pwned=True, breaches=breaches, risk_level=risk)
                elif response.status == 404:
                    # 404 означает, что утечек не найдено - это хороший знак
                    return OSINTLeakReport(target=account, is_pwned=False)
                elif response.status == 429:
                    logger.warning("[HIBP] Превышен лимит запросов (Rate Limit).")
        except Exception as e:
            logger.error(f"[HIBP] Ошибка при проверке {account}: {e}")
            
        return OSINTLeakReport(target=account, is_pwned=False)

# ==========================================
# 6. ВАЛЮТНЫЙ КОНВЕРТЕР (EXCHANGERATE-API)
# ==========================================
class GlobalCurrencyConverter:
    """
    Необходим для трекинга цен на зарубежных площадках (Amazon, AliExpress)
    и приведения их к рублю в реальном времени.
    """
    def __init__(self):
        self.api_key = public_config.EXCHANGERATE_API_KEY
        self.base_url = f"https://v6.exchangerate-api.com/v6/{self.api_key}/latest/"

    async def get_rates(self, session: aiohttp.ClientSession, base_currency: str = "USD") -> Optional[CurrencyRates]:
        if not self.api_key:
            logger.warning("[Currency] Ключ ExchangeRate не задан.")
            return None

        try:
            async with session.get(f"{self.base_url}{base_currency}", timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return CurrencyRates(
                        base_code=base_currency,
                        rates=data.get("conversion_rates", {}),
                        last_updated=data.get("time_last_update_utc", "")
                    )
        except Exception as e:
            logger.error(f"[Currency] Ошибка получения курсов валют: {e}")
        return None

# ==========================================
# 7. ГЛАВНЫЙ АГРЕГАТОР ПУБЛИЧНЫХ API
# ==========================================
class PublicAPIEngine:
    """
    Оркестратор, который связывает все публичные микросервисы в единый узел.
    Идеально встраивается в наш монолит как дополнительный модуль обогащения данных.
    """
    def __init__(self):
        self.vin_decoder = NHTSAVinDecoder()
        self.geocoder = OpenStreetMapGeocoder()
        self.leak_checker = HaveIBeenPwnedAPI()
        self.currency = GlobalCurrencyConverter()

    async def enrich_listing_data(self, vin: str = None, city: str = None, seller_contact: str = None) -> Dict[str, Any]:
        """
        Метод обогащения: принимает сырые данные из парсера и прогоняет их по бесплатным публичным API.
        """
        logger.info("=== Запуск обогащения данных через Public APIs ===")
        report = {}
        
        connector = aiohttp.TCPConnector(limit_per_host=5)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = []
            
            # Если есть VIN, запрашиваем детали авто
            if vin:
                tasks.append(self.vin_decoder.decode(session, vin))
            else:
                tasks.append(asyncio.sleep(0)) # Заглушка для индекса
                
            # Если есть город, ищем координаты для карты
            if city:
                tasks.append(self.geocoder.get_coordinates(session, city))
            else:
                tasks.append(asyncio.sleep(0))
                
            # Если есть контакт, проверяем на OSINT утечки
            if seller_contact:
                tasks.append(self.leak_checker.check_leak(session, seller_contact))
            else:
                tasks.append(asyncio.sleep(0))

            # Выполняем все запросы параллельно
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Парсинг результатов
            if vin and isinstance(results[0], VINDecodedData):
                report["vehicle_specs"] = results[0].model_dump()
                
            if city and isinstance(results[1], dict):
                report["geo_data"] = results[1]
                
            if seller_contact and isinstance(results[2], OSINTLeakReport):
                report["seller_osint_risk"] = results[2].model_dump()

        logger.info("=== Обогащение завершено ===")
        return report

# ==========================================
# 8. БЛОК ТЕСТИРОВАНИЯ И СИМУЛЯЦИИ
# ==========================================
async def test_public_apis():
    engine = PublicAPIEngine()
    
    # Симуляция найденного объявления на Авито
    mock_scraped_data = {
        "vin": "5UXWX7C5*BA******", # Тестовый VIN BMW
        "city": "Ульяновск",
        "seller_contact": "test_scammer@example.com"
    }
    
    print("\n" + "="*50)
    print("🚀 ИНТЕГРАЦИЯ С PUBLIC APIS")
    print("="*50)
    
    enriched_data = await engine.enrich_listing_data(
        vin=mock_scraped_data["vin"],
        city=mock_scraped_data["city"],
        seller_contact=mock_scraped_data["seller_contact"]
    )
    
    import json
    print(json.dumps(enriched_data, indent=4, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(test_public_apis())
