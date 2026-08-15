import asyncio
import aiohttp
import logging
import re
import urllib.parse
from typing import List, Dict, Optional, Literal
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

# ==========================================
# 1. КОНФИГУРАЦИЯ И ЛОГИРОВАНИЕ
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger("OSINTSearchEngine")

# ==========================================
# 2. СТРОГИЕ МОДЕЛИ ДАННЫХ
# ==========================================
class WebSearchResult(BaseModel):
    engine: Literal["duckduckgo", "google", "yandex"]
    title: str
    url: str
    snippet: str
    position: int
    is_suspicious: bool = False  # Флаг, если в сниппете найдены слова "мошенник", "скам" и т.д.

class OSINTReport(BaseModel):
    query: str
    total_results: int
    results: List[WebSearchResult] = Field(default_factory=list)
    risk_score: float = 0.0  # От 0.0 до 10.0 (насколько опасен продавец/товар)

# ==========================================
# 3. DUCKDUCKGO (ПРЯМОЙ ПАРСИНГ HTML)
# ==========================================
class DuckDuckGoScraper:
    """
    Прямой парсер HTML-версии DuckDuckGo. 
    Идеален для обхода лимитов API, так как DDG лоялен к скрапингу (особенно через TOR/Прокси).
    """
    def __init__(self, proxy: Optional[str] = None):
        self.base_url = "https://html.duckduckgo.com/html/"
        self.proxy = proxy
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
        }

    async def search(self, session: aiohttp.ClientSession, query: str, limit: int = 10) -> List[WebSearchResult]:
        logger.info(f"[DuckDuckGo] Выполнение поискового запроса: '{query}'")
        payload = {"q": query, "b": ""}
        results = []

        try:
            async with session.post(self.base_url, data=payload, headers=self.headers, proxy=self.proxy, timeout=15) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'lxml')
                    
                    # Разбор специфичной верстки html.duckduckgo.com
                    for idx, result_node in enumerate(soup.find_all('div', class_='result'), start=1):
                        if idx > limit:
                            break
                            
                        title_node = result_node.find('a', class_='result__a')
                        snippet_node = result_node.find('a', class_='result__snippet')
                        url_node = result_node.find('a', class_='result__url')
                        
                        if title_node and url_node:
                            # DuckDuckGo часто оборачивает ссылки в свои редиректы, чистим их
                            raw_url = url_node.get('href', '')
                            clean_url = urllib.parse.unquote(raw_url.replace('//duckduckgo.com/l/?uddg=', '').split('&')[0])
                            
                            snippet = snippet_node.text.strip() if snippet_node else ""
                            
                            results.append(WebSearchResult(
                                engine="duckduckgo",
                                title=title_node.text.strip(),
                                url=clean_url,
                                snippet=snippet,
                                position=idx
                            ))
                else:
                    logger.warning(f"[DuckDuckGo] Блокировка или ошибка. Статус: {response.status}")
        except Exception as e:
            logger.error(f"[DuckDuckGo] Ошибка парсинга: {e}")

        return results

# ==========================================
# 4. GOOGLE (ЧЕРЕЗ SERPER.DEV API)
# ==========================================
class GoogleSerperAPI:
    """
    Интеграция с Google Search через Serper API.
    Обеспечивает самую точную выдачу и умеет пробивать отзывы.
    """
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.endpoint = "https://google.serper.dev/search"

    async def search(self, session: aiohttp.ClientSession, query: str, limit: int = 10) -> List[WebSearchResult]:
        if not self.api_key:
            logger.warning("[Google] Ключ SERPER_API_KEY не установлен. Пропуск.")
            return []

        logger.info(f"[Google] Выполнение поискового запроса: '{query}'")
        headers = {
            "X-API-KEY": self.api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "q": query,
            "gl": "ru", # Гео-локация Россия
            "hl": "ru", # Язык Русский
            "num": limit
        }

        results = []
        try:
            async with session.post(self.endpoint, headers=headers, json=payload, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    organic_results = data.get("organic", [])
                    
                    for idx, item in enumerate(organic_results, start=1):
                        results.append(WebSearchResult(
                            engine="google",
                            title=item.get("title", ""),
                            url=item.get("link", ""),
                            snippet=item.get("snippet", ""),
                            position=idx
                        ))
        except Exception as e:
            logger.error(f"[Google] Ошибка API: {e}")

        return results

# ==========================================
# 5. YANDEX (YANDEX XML API)
# ==========================================
class YandexXMLAPI:
    """
    Интеграция с Яндекс XML. Идеально для поиска информации по региональным форумам РФ.
    Вшита локальная привязка гео-запросов.
    """
    def __init__(self, user: Optional[str] = None, key: Optional[str] = None):
        self.user = user
        self.key = key
        self.endpoint = "https://yandex.ru/search/xml"
        # 242 — это внутренний ID региона для точной локальной выдачи
        self.region_id = 242 

    async def search(self, session: aiohttp.ClientSession, query: str, limit: int = 10) -> List[WebSearchResult]:
        if not self.user or not self.key:
            logger.warning("[Yandex] Учетные данные Yandex XML не установлены. Пропуск.")
            return []

        logger.info(f"[Yandex] Выполнение поискового запроса: '{query}' (Регион: {self.region_id})")
        
        params = {
            "user": self.user,
            "key": self.key,
            "query": query,
            "l10n": "ru",
            "sortby": "rlv",
            "maxpassages": 2,
            "groupby": f"attr=d.mode=deep.groups-on-page={limit}",
            "lr": self.region_id 
        }

        results = []
        try:
            async with session.get(self.endpoint, params=params, timeout=10) as response:
                if response.status == 200:
                    xml_data = await response.text()
                    soup = BeautifulSoup(xml_data, 'xml')
                    
                    for idx, group in enumerate(soup.find_all('group'), start=1):
                        doc = group.find('doc')
                        if not doc:
                            continue
                            
                        title_node = doc.find('title')
                        url_node = doc.find('url')
                        passages_node = doc.find('passages')
                        
                        title = title_node.text if title_node else ""
                        url = url_node.text if url_node else ""
                        snippet = passages_node.text if passages_node else ""
                        
                        # Очистка от XML тегов (например, выделения стронгом)
                        clean_title = re.sub(r'<[^>]+>', '', title)
                        clean_snippet = re.sub(r'<[^>]+>', '', snippet)

                        results.append(WebSearchResult(
                            engine="yandex",
                            title=clean_title,
                            url=url,
                            snippet=clean_snippet,
                            position=idx
                        ))
        except Exception as e:
            logger.error(f"[Yandex] Ошибка парсинга XML: {e}")

        return results

# ==========================================
# 6. ГЛАВНЫЙ АГРЕГАТОР OSINT РАЗВЕДКИ
# ==========================================
class OSINTOrchestrator:
    """
    Запускает все поисковики параллельно, собирает данные,
    удаляет дубликаты и анализирует риск (поиск слов "мошенник", "кидала" и т.д.).
    """
    def __init__(self, google_api_key: str = None, yandex_user: str = None, yandex_key: str = None):
        self.duckduckgo = DuckDuckGoScraper()
        self.google = GoogleSerperAPI(api_key=google_api_key)
        self.yandex = YandexXMLAPI(user=yandex_user, key=yandex_key)
        
        # Ключевые слова для анализа рисков (Красные флаги)
        self.risk_keywords = [
            "мошенник", "кидала", "обман", "скам", "scam", 
            "не советую", "осторожно", "развод", "перекуп", "скручен"
        ]

    def _analyze_risk(self, results: List[WebSearchResult]) -> float:
        """Простейший NLP анализ: чем чаще встречаются слова-маркеры, тем выше риск."""
        risk_score = 0.0
        for result in results:
            text_to_analyze = f"{result.title.lower()} {result.snippet.lower()}"
            
            for keyword in self.risk_keywords:
                if keyword in text_to_analyze:
                    result.is_suspicious = True
                    risk_score += 1.5  # Повышаем уровень угрозы
                    
        return min(risk_score, 10.0) # Максимум 10 баллов опасности

    async def run_deep_investigation(self, query: str) -> OSINTReport:
        logger.info(f"=== ЗАПУСК ГЛУБОКОГО OSINT АНАЛИЗА ДЛЯ: '{query}' ===")
        
        connector = aiohttp.TCPConnector(limit_per_host=5)
        async with aiohttp.ClientSession(connector=connector) as session:
            # Параллельный запуск всех поисковых систем
            tasks = [
                self.duckduckgo.search(session, query, limit=5),
                self.google.search(session, query, limit=5),
                self.yandex.search(session, query, limit=5)
            ]
            
            search_responses = await asyncio.gather(*tasks, return_exceptions=True)
            
            all_results: List[WebSearchResult] = []
            seen_urls = set()
            
            # Слияние результатов и удаление дубликатов ссылок
            for response in search_responses:
                if isinstance(response, list):
                    for item in response:
                        # Нормализация URL для проверки уникальности
                        clean_url = item.url.split('?')[0].lower()
                        if clean_url not in seen_urls:
                            seen_urls.add(clean_url)
                            all_results.append(item)

            # Анализ угрозы по собранным сниппетам
            risk_level = self._analyze_risk(all_results)

            report = OSINTReport(
                query=query,
                total_results=len(all_results),
                results=all_results,
                risk_score=risk_level
            )
            
            logger.info(f"=== АНАЛИЗ ЗАВЕРШЕН. Найдено уникальных ссылок: {report.total_results}. Уровень риска: {report.risk_score}/10 ===")
            return report

# ==========================================
# 7. ТЕСТОВЫЙ ПРОГОН
# ==========================================
async def run_osint_test():
    # Инициализация агрегатора (в проде ключи берутся из secrets_manager)
    osint = OSINTOrchestrator()
    
    # Симулируем поиск номера телефона продавца, чтобы выявить мошенника
    test_query = "Номер 79991234567 отзывы"
    
    report = await osint.run_deep_investigation(test_query)
    
    print("\n" + "="*50)
    print(f"🕵️  OSINT ОТЧЕТ ПО ЗАПРОСУ: {report.query}")
    print("="*50)
    print(f"Уровень угрозы (Риск): {report.risk_score}/10.0")
    print(f"Всего независимых источников: {report.total_results}\n")
    
    for item in report.results:
        warning = "🚨 ПОДОЗРИТЕЛЬНО 🚨" if item.is_suspicious else "✅ Чисто"
        print(f"[{item.engine.upper()}] {item.title}")
        print(f"Ссылка: {item.url}")
        print(f"Сниппет: {item.snippet}")
        print(f"Статус: {warning}\n")

if __name__ == "__main__":
    asyncio.run(run_osint_test())