# queue_manager.py
from datetime import datetime
import threading
from core.database import db, ManagedTool, global_queue_lock

# 用於存放所有工具的 (任務模型, 下載函數)
_tool_registry = {}

def register_tool(name, task_model, worker_func):
    """ 工具啟動時呼叫此函數註冊自己 """
    _tool_registry[name] = {
        'model': task_model,
        'worker': worker_func
    }

def global_process_queue(app):
    """ 全域排隊邏輯：打包後的中央判斷核心 """
    with global_queue_lock:
        with app.app_context():
            # 1. 蒐集全站所有正在執行的任務 (跨資料庫 BDB 查詢)
            all_active_tasks = []
            for tool_name, info in _tool_registry.items():
                active = info['model'].query.filter_by(status='processing').all()
                all_active_tasks.extend(active)
            
            current_total_count = len(all_active_tasks)
            
            # 2. 計算目前全站的「最低上限瓶頸」
            current_bottleneck = min(
                [ManagedTool.query.get(t.tool_id).max_concurrent for t in all_active_tasks], 
                default=float('inf')
            )

            # 3. 找出全站「最老」的排隊任務
            all_waiting_tasks = []
            for tool_name, info in _tool_registry.items():
                next_one = info['model'].query.filter_by(status='waiting').order_by(info['model'].created_at.asc()).first()
                if next_one:
                    all_waiting_tasks.append((next_one, info['worker']))

            if not all_waiting_tasks:
                return

            # 取得絕對最優先的一個
            next_task, worker_func = min(all_waiting_tasks, key=lambda x: x[0].created_at)
            next_tool_cfg = ManagedTool.query.get(next_task.tool_id)

            # 4. 判定是否允許進入
            if current_total_count < current_bottleneck and current_total_count < next_tool_cfg.max_concurrent:
                print(f"[Central Queue] 啟動工具任務: {next_task.id}")
                next_task.status = 'processing'
                db.session.commit()
                threading.Thread(target=worker_func, args=(app, next_task.id)).start()

def get_global_queue_position(target_created_at):
    """ 計算全站排隊名次：統計所有表單中，比目前任務更早建立且還在等待的任務數量 """
    count = 0
    # 遍歷所有已註冊的工具
    for tool_name, info in _tool_registry.items():
        model = info['model']
        # 統計該表中「狀態為 waiting」且「建立時間早於目標」的任務
        count += model.query.filter(
            model.status == 'waiting',
            model.created_at < target_created_at
        ).count()
    return count + 1 # 回傳名次 (0人領先即為第1名)