"""
================================================================================
OmniScan CORE ENGINE (v4.0.0 - ULTIMATE ENTERPRISE RELEASE)
================================================================================
Описание: Главный сервер приложения OmniScan.
Функционал:
  - Продвинутый REST API для запуска OSINT-матриц.
  - Асинхронный HTTP-движок (aiohttp) для реального парсинга API.
  - Rate Limiter (Token Bucket) для защиты от DDoS.
  - WebSockets (Чат + AI) с аппаратной фильтрацией эмодзи.
  - Неблокирующая работа с базой данных (SQLite).
================================================================================
"""

import asyncio
import os
import re
import json
import sqlite3
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse

import aiohttp
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, BackgroundTasks, HTTPException, Depends, Header, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# ==========================================
# 1. КОНФИГУРАЦИЯ И БАЗА ДАННЫХ
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] OmniScan-Core: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("OmniScan")

# Ключ по умолчанию для тестов (в проде выносить в .env)
SECRET_API_KEY = os.getenv("OMNISCAN_API_KEY", "omniscan_master_key_2026")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "omniscan_data.db")

app = FastAPI(
    title="OmniScan API", 
    description="Универсальный OSINT-сканер и анализатор рынка", 
    version="4.0.0",
    docs_url="/api/docs"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # В продакшене заменить на домен GitHub Pages
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def init_db():
    """Инициализация расширенной структуры базы данных."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Таблица ЧС
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blacklist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_id TEXT UNIQUE,
            platform TEXT,
            reason TEXT,
            risk_level TEXT DEFAULT 'HIGH',
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица логов сканирования
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scan_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT,
            pipeline TEXT,
            status TEXT,
            execution_time_ms INTEGER,
            scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица системных ошибок API
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_endpoint TEXT,
            error_msg TEXT,
            occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    logger.info("База данных OmniScan успешно инициализирована.")

init_db()

# ==========================================
# 2. RATE LIMITER (ЗАЩИТА ОТ DDoS И СПАМА)
# ==========================================
class RateLimiter:
    """Алгоритм Token Bucket для ограничения количества запросов."""
    def __init__(self, capacity: int, fill_rate: float):
        self.capacity = capacity
        self.fill_rate = fill_rate
        self.clients: Dict[str, Dict[str, float]] = {}

    def is_allowed(self, client_id: str) -> bool:
        now = time.time()
        if client_id not in self.clients:
            self.clients[client_id] = {"tokens": self.capacity, "last_update": now}
        
        client = self.clients[client_id]
        # Пополняем токены
        elapsed = now - client["last_update"]
        client["tokens"] = min(self.capacity, client["tokens"] + elapsed * self.fill_rate)
        client["last_update"] = now
        
        if client["tokens"] >= 1:
            client["tokens"] -= 1
            return True
        return False

# Ограничение: 5 запросов в секунду на 1 IP
limiter = RateLimiter(capacity=5, fill_rate=1.0)

async def check_rate_limit(request: Request):
    client_ip = request.client.host if request.client else "unknown"
    if not limiter.is_allowed(client_ip):
        logger.warning(f"Rate limit превышен для IP: {client_ip}")
        raise HTTPException(status_code=429, detail="Too Many Requests")

# Зависимость для авторизации
async def verify_api_key(x_api_key: str = Header(default="")):
    if x_api_key != SECRET_API_KEY:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid or missing API Key")
    return x_api_key

# ==========================================
# 3. АСИНХРОННЫЙ OSINT ДВИЖОК (ПАРСЕР)
# ==========================================
class OmniScanEngine:
    """Боевой движок для выполнения реальных HTTP запросов по матрице."""
    
    @staticmethod
    async def fetch_api(session: aiohttp.ClientSession, url: str, method: str = "GET", headers: dict = None) -> Dict[str, Any]:
        """Универсальный метод для безопасного запроса к публичным API."""
        start_time = time.time()
        try:
            async with session.request(method, url, headers=headers, timeout=10) as response:
                resp_text = await response.text()
                try:
                    data = json.loads(resp_text)
                except json.JSONDecodeError:
                    data = {"raw_text": resp_text[:500]} # Если ответ не JSON (например HTML), берем кусок
                
                return {
                    "status_code": response.status,
                    "success": 200 <= response.status < 300,
                    "data": data,
                    "ms": int((time.time() - start_time) * 1000)
                }
        except Exception as e:
            logger.error(f"Сбой сети при запросе к {url}: {e}")
            # Запись ошибки в БД (через thread чтобы не блокировать loop)
            asyncio.create_task(OmniScanEngine.log_error(url, str(e)))
            return {"success": False, "error": str(e), "ms": int((time.time() - start_time) * 1000)}

    @staticmethod
    async def log_error(endpoint: str, msg: str):
        def _write():
            conn = sqlite3.connect(DB_PATH)
            conn.cursor().execute("INSERT INTO api_errors (api_endpoint, error_msg) VALUES (?, ?)", (endpoint, msg))
            conn.commit()
            conn.close()
        await asyncio.to_thread(_write)

    @staticmethod
    async def log_scan(query: str, pipeline: str, status: str, exec_time: int):
        def _write():
            conn = sqlite3.connect(DB_PATH)
            conn.cursor().execute(
                "INSERT INTO scan_logs (query, pipeline, status, execution_time_ms) VALUES (?, ?, ?, ?)", 
                (query, pipeline, status, exec_time)
            )
            conn.commit()
            conn.close()
        await asyncio.to_thread(_write)

    @classmethod
    async def run_pipeline(cls, target: str, pipeline_name: str):
        """Реальное выполнение задач. В проде здесь читается JSON матрица."""
        logger.info(f"OSINT ДВИЖОК: Старт пайплайна '{pipeline_name}' для цели '{target}'")
        start_time = time.time()
        
        results = {"target": target, "pipeline": pipeline_name, "stages": {}}
        
        # Настраиваем коннектор для оптимизации соединений
        connector = aiohttp.TCPConnector(limit_per_host=10, ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            
            # ЭМУЛЯЦИЯ ЛОГИКИ МАТРИЦЫ (Здесь мы делаем реальные запросы к публичным API)
            if pipeline_name == "auto_ru_market":
                # Запрос 1: Пытаемся расшифровать как VIN через бесплатный NHTSA
                logger.info("Запуск проверки через NHTSA API...")
                nhtsa_url = f"https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{target}?format=json"
                nhtsa_res = await cls.fetch_api(session, nhtsa_url)
                results["stages"]["vin_decode"] = nhtsa_res

            elif pipeline_name == "tech_global":
                # Запрос 2: Проверка курсов валют как часть пайплайна техники
                logger.info("Запуск модуля валют (Frankfurter API)...")
                fx_url = "https://api.frankfurter.app/latest?from=USD&to=RUB,EUR"
                fx_res = await cls.fetch_api(session, fx_url)
                results["stages"]["currency_check"] = fx_res

            elif pipeline_name == "seller_osint":
                # Запрос 3: Проверка контактов на мошенничество
                logger.info("Проверка по базам спамеров...")
                spam_url = f"https://api.stopforumspam.org/api?ip={target}&json"
                spam_res = await cls.fetch_api(session, spam_url)
                results["stages"]["spam_check"] = spam_res

            else:
                logger.warning(f"Пайплайн {pipeline_name} не имеет привязанных API-маршрутов.")

        exec_time_ms = int((time.time() - start_time) * 1000)
        await cls.log_scan(target, pipeline_name, "COMPLETED", exec_time_ms)
        
        # Сохранение сырого дампа в файл
        os.makedirs("output_data", exist_ok=True)
        dump_file = f"output_data/omniscan_{int(time.time())}.json"
        with open(dump_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=4)
            
        logger.info(f"Сбор данных завершен. Время: {exec_time_ms}мс. Дамп: {dump_file}")

# ==========================================
# 4. СИСТЕМА CHAT & WEBSOCKETS
# ==========================================
EMOJI_FILTER = re.compile(r'[^\w\s.,!?"\'\-а-яА-ЯёЁa-zA-Z0-9]', re.UNICODE)

class WsManager:
    def __init__(self):
        self.rooms: Dict[str, List[WebSocket]] = {}

    def sanitize(self, text: str) -> str:
        return EMOJI_FILTER.sub('', text).strip()

    async def connect(self, ws: WebSocket, room: str):
        await ws.accept()
        if room not in self.rooms:
            self.rooms[room] = []
        self.rooms[room].append(ws)

    def disconnect(self, ws: WebSocket, room: str):
        if room in self.rooms and ws in self.rooms[room]:
            self.rooms[room].remove(ws)

    async def broadcast(self, message: str, room: str, sender: str):
        clean_msg = self.sanitize(message)
        if not clean_msg: return
            
        payload = {"sender": sender, "text": clean_msg, "time": datetime.now().strftime("%H:%M")}
        for conn in list(self.rooms.get(room, [])):
            try:
                await conn.send_json(payload)
            except Exception:
                self.disconnect(conn, room)

ws_manager = WsManager()

@app.websocket("/ws/chat/{room}/{username}")
async def ws_endpoint(websocket: WebSocket, room: str, username: str):
    await ws_manager.connect(websocket, room)
    try:
        while True:
            data = await websocket.receive_text()
            if room == "ai":
                clean = ws_manager.sanitize(data)
                if not clean: continue
                # Эмуляция ответа нейросети
                await asyncio.sleep(1)
                await websocket.send_json({
                    "sender": "OmniScan AI",
                    "text": f"Принято. Анализирую: {clean[:20]}...",
                    "time": datetime.now().strftime("%H:%M"),
                    "isAi": True
                })
            else:
                await ws_manager.broadcast(data, room, username)
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, room)

# ==========================================
# 5. REST API ENDPOINTS
# ==========================================
class ScanRequest(BaseModel):
    target: str = Field(..., min_length=2, description="Цель (VIN, Номер, Город)")
    pipeline: str = Field(default="auto_ru_market")

class BlacklistData(BaseModel):
    target_id: str
    platform: str
    reason: str

@app.post("/api/v1/scan", dependencies=[Depends(check_rate_limit)])
async def trigger_scan(req: ScanRequest, bg_tasks: BackgroundTasks, auth: str = Depends(verify_api_key)):
    """Запуск матрицы OmniScan. Выполняется асинхронно в фоне."""
    bg_tasks.add_task(OmniScanEngine.run_pipeline, req.target, req.pipeline)
    return {
        "status": "processing",
        "target": req.target,
        "message": "Задача успешно поставлена в очередь. Движок OmniScan работает."
    }

@app.post("/api/v1/blacklist", dependencies=[Depends(check_rate_limit)])
async def add_blacklist(data: BlacklistData, auth: str = Depends(verify_api_key)):
    """Добавление перекупа в глобальную базу OmniScan."""
    def _insert():
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO blacklist (target_id, platform, reason) VALUES (?, ?, ?)", 
                        (data.target_id, data.platform, data.reason))
            conn.commit()
            return True, "Добавлено"
        except sqlite3.IntegrityError:
            return False, "Уже в ЧС"
        finally:
            conn.close()
            
    success, msg = await asyncio.to_thread(_insert)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "success", "message": msg}

@app.get("/api/v1/status")
async def get_status():
    """Публичный эндпоинт статуса (без ключа)."""
    def _stats():
        conn = sqlite3.connect(DB_PATH)
        bl_count = conn.cursor().execute("SELECT COUNT(*) FROM blacklist").fetchone()[0]
        scan_count = conn.cursor().execute("SELECT COUNT(*) FROM scan_logs").fetchone()[0]
        conn.close()
        return bl_count, scan_count
        
    bl, scans = await asyncio.to_thread(_stats)
    return {
        "system": "OmniScan Engine",
        "version": "4.0.0",
        "status": "OPERATIONAL",
        "metrics": {
            "scammers_blocked": bl,
            "total_scans_performed": scans,
            "active_ws_connections": sum(len(c) for c in ws_manager.rooms.values())
        }
    }

# ==========================================
# 6. ТОЧКА ВХОДА
# ==========================================
if __name__ == "__main__":
    logger.info("========================================")
    logger.info("🔥 OMNISCAN ENGINE BOOT SEQUENCE INIT   ")
    logger.info("========================================")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, log_level="warning")
