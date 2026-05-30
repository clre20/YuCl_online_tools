from flask import render_template, request, g
import time
from datetime import datetime
from core.database import db, ManagedTool, AccessLog, SystemConfig

def setup_middleware(app):
    @app.before_request
    def check_maintenance_mode():
        # 排除靜態檔案、登入頁面與管理後台
        if request.blueprint == 'admin_console' or \
           request.path.startswith(('/static', '/login', '/api/sys/track')) or \
           request.path.endswith(('.ico', '.png', '.jpg', '.js', '.css')):
            return

        try:
            # 1. 檢查全站維護模式
            mode = SystemConfig.query.filter_by(key='maintenance_mode').first()
            if mode and mode.value == 'true':
                return render_template('maintenance.html'), 503

            # 2. 檢查特定工具/專案是否被關閉
            inactive_tools = ManagedTool.query.filter(ManagedTool.is_active == False).all()
            for t in inactive_tools:
                path_match = t.url and request.path.startswith(t.url)
                blueprint_match = t.blueprint and request.blueprint and (request.blueprint.lower() == t.blueprint.lower())

                if path_match or blueprint_match:
                    return render_template('maintenance.html', tool_name=t.name), 503

        except Exception as e:
            print(f"[Maintenance Check Error] {e}")

    @app.before_request
    def before_request_logging():
        # 紀錄開始時間與基礎資訊
        g.start_time = time.time()
        
        # 排除靜態檔案
        if request.path.startswith('/static') or request.path.endswith(('.ico', '.png', '.jpg')):
            return

    @app.after_request
    def after_request_logging(response):
        # 排除靜態檔案、日誌頁面與 API
        if request.path.startswith(('/static', '/api/sys/track', '/admin/logs')) or \
           request.path.endswith(('.ico', '.png', '.jpg', '.js', '.css')):
            return response

        try:
            # 計算處理時間 (秒)
            duration = round(time.time() - g.start_time, 4) if hasattr(g, 'start_time') else 0
            
            # 獲取真實 IP (Cloudflare 優先，否則取 remote_addr)
            ip = request.headers.get('CF-Connecting-IP', request.remote_addr) or '0.0.0.0'
            country = request.headers.get('CF-IPCountry', 'Unknown')
            
            # 建立訪問紀錄
            new_log = AccessLog(
                ip_address=ip,
                country=country,
                path=request.path,
                duration=duration,
                timestamp=datetime.utcnow()
            )
            db.session.add(new_log)
            db.session.commit()
            
        except Exception as e:
            db.session.rollback()
            print(f"[Log Sync Error] 紀錄失敗: {str(e)}")
            
        return response
