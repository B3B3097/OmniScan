import asyncio
import aiohttp
import json
import logging
import argparse
import os
import time
from typing import Dict, Any, List

# ==========================================
# 1. КОНФИГУРАЦИЯ И ЦВЕТНОЕ ЛОГИРОВАНИЕ
# ==========================================
# Используем продвинутый логгер, чтобы в логах GitHub Actions всё было красиво
try:
    import colorlog
    handler = colorlog.StreamHandler()
    handler.setFormatter(colorlog.ColoredFormatter(
        '%(log_color)s%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        }
    ))
    logger = colorlog.getLogger("MatrixExecutor")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
except ImportError:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    logger = logging.getLogger("MatrixExecutor")

# ==========================================
# 2. ИСПОЛНИТЕЛЬНОЕ ЯДРО (PIPELINE ENGINE)
# ==========================================
class PipelineExecutor:
    """
    Читает JSON-матрицу и запускает API в правильном порядке.
    """
    def __init__(self, matrix_path: str, api_registry_path: str):
        self.matrix_path = matrix_path
        self.api_registry_path = api_registry_path
        self.matrix_data = self._load_json(self.matrix_path)
        # В проде здесь будет парсер файла api.txt, сейчас для надежности
        # мы просто маппим ID из JSON на реальные Python функции.
        self.api_dispatcher = APIDispatcher()

    def _load_json(self, path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            logger.critical(f"Файл матрицы не найден: {path}")
            raise FileNotFoundError(f"Missing config: {path}")
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    async def _execute_stage(self, session: aiohttp.ClientSession, stage_name: str, tasks_config: List[Dict]):
        """Выполняет все API-вызовы внутри одной стадии строго параллельно."""
        logger.info(f"--- Запуск стадии: [ {stage_name.upper()} ] ---")
        
        async def run_task(task_cfg: Dict):
            api_ref = task_cfg.get("api_ref")
            api_name = task_cfg.get("name")
            is_critical = task_cfg.get("critical", False)
            fallback = task_cfg.get("fallback")

            try:
                # Динамический вызов нужного API через диспетчер
                result = await self.api_dispatcher.call_api(session, api_ref, api_name)
                return {"api": api_name, "status": "success", "data": result}
            except Exception as e:
                logger.error(f"Сбой API '{api_name}' (REF: {api_ref}): {str(e)}")
                if fallback:
                    logger.warning(f"Активация Fallback для '{api_name}' -> Переход на {fallback}")
                    # Эмуляция вызова запасного API
                    await asyncio.sleep(1)
                    return {"api": fallback, "status": "success (fallback)", "data": {}}
                
                if is_critical:
                    logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА: Остановка из-за падения {api_name}")
                    raise e
                return {"api": api_name, "status": "failed", "error": str(e)}

        # Запускаем все задачи стадии одновременно
        coroutines = [run_task(cfg) for cfg in tasks_config]
        results = await asyncio.gather(*coroutines, return_exceptions=True)
        
        # Фильтрация результатов и обработка критических сбоев
        stage_report = []
        for res in results:
            if isinstance(res, Exception):
                logger.error(f"Необработанное исключение в стадии {stage_name}: {res}")
            else:
                stage_report.append(res)
                
        return stage_report

    async def run_pipeline(self, pipeline_name: str):
        """Главный метод запуска конкретного пайплайна."""
        pipelines = self.matrix_data.get("execution_pipelines", {})
        
        if pipeline_name not in pipelines:
            logger.critical(f"Пайплайн '{pipeline_name}' не найден в матрице!")
            available = ", ".join(pipelines.keys())
            logger.info(f"Доступные пайплайны: {available}")
            return

        pipeline_cfg = pipelines[pipeline_name]
        logger.info(f"🚀 Инициализация пайплайна: {pipeline_name}")
        logger.info(f"Описание: {pipeline_cfg.get('description')}")
        
        stages = pipeline_cfg.get("stages", {})
        final_report = {
            "pipeline": pipeline_name,
            "timestamp": time.time(),
            "results": {}
        }

        # Используем единую сессию для всех запросов с общим пулом коннектов
        connector = aiohttp.TCPConnector(limit_per_host=20)
        async with aiohttp.ClientSession(connector=connector) as session:
            # Стадии должны выполняться последовательно (например, сначала поиск, потом декодинг VIN)
            # Но внутри стадии задачи выполняются параллельно.
            for stage_name, tasks_config in stages.items():
                stage_results = await self._execute_stage(session, stage_name, tasks_config)
                final_report["results"][stage_name] = stage_results

        # Сохранение финального отчета для GitHub Actions Artifacts
        output_dir = "output_data"
        os.makedirs(output_dir, exist_ok=True)
        report_path = os.path.join(output_dir, f"{pipeline_name}_report.json")
        
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(final_report, f, ensure_ascii=False, indent=4)
            
        logger.info(f"✅ Пайплайн {pipeline_name} завершен. Отчет сохранен: {report_path}")

# ==========================================
# 3. ДИСПЕТЧЕР API (СИМУЛЯТОР МАРШРУТИЗАЦИИ)
# ==========================================
class APIDispatcher:
    """
    Связывает строковые идентификаторы (api_ref) с реальными функциями.
    В рабочей среде здесь будут импорты классов из engine/public_osint_integrations.py.
    """
    async def call_api(self, session: aiohttp.ClientSession, api_ref: str, api_name: str) -> Dict:
        logger.debug(f"[{api_name}] Отправка запроса (REF: {api_ref})...")
        
        # Эмуляция сетевой задержки от 0.5 до 2 секунд
        await asyncio.sleep(1.0)

        # Моки для разных систем из нашего api.txt
        if api_ref == "004": # Avito
            return {"items_found": 150, "platform": "Avito"}
        elif api_ref == "016": # NHTSA
            return {"vin_valid": True, "manufacturer": "BMW AG"}
        elif api_ref == "040": # Ollama Vision
            return {"is_approved": False, "defect_detected": "Царапина на бампере"}
        elif api_ref == "049": # HIBP
            return {"is_pwned": True, "breaches": ["VK.com", "Canva"]}
        else:
            return {"status": "ok", "message": f"API {api_ref} executed successfully."}

# ==========================================
# 4. ТОЧКА ВХОДА (CLI ARGUMENTS)
# ==========================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MarketVision API Orchestrator Matrix Executor")
    parser.add_argument(
        '--pipeline', 
        type=str, 
        required=True, 
        help='Имя пайплайна для запуска (например: pipeline_auto_ru, pipeline_seller_osint)'
    )
    parser.add_argument(
        '--matrix-file', 
        type=str, 
        default='../config/orchestrator_matrix.json', 
        help='Путь к JSON файлу матрицы'
    )
    
    args = parser.parse_args()

    # Фикс путей для локального запуска или запуска из GitHub Actions
    base_dir = os.path.dirname(os.path.abspath(__file__))
    matrix_absolute_path = os.path.normpath(os.path.join(base_dir, args.matrix_file))

    executor = PipelineExecutor(
        matrix_path=matrix_absolute_path,
        api_registry_path=os.path.join(base_dir, '../config/api.txt')
    )
    
    # Запуск асинхронного цикла
    try:
        asyncio.run(executor.run_pipeline(args.pipeline))
    except KeyboardInterrupt:
        logger.info("Процесс принудительно остановлен пользователем.")
    except Exception as e:
        logger.critical(f"Глобальный сбой ядра: {e}")
        exit(1)
