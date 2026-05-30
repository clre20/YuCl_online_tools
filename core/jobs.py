from core.database import db, scheduler, ServerMetric, AccessLog, record_system_log
from tool.tool import cleanup_ytdl_tasks, cleanup_qrcode_tasks, cleanup_imgedit_tasks
from tool.github_stats.github_stats import update_github_data
from core.mail import scheduled_weekly_report
from datetime import datetime, timedelta
import os
import psutil

def collect_server_metrics(app):
    """ 收集伺服器資源數據 """
    with app.app_context():
        cpu = psutil.cpu_percent(interval=1)
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage('/').percent

        metric = ServerMetric(cpu_usage=cpu, ram_usage=ram, disk_usage=disk)
        db.session.add(metric)
        db.session.commit()

def cleanup_old_logs(app):
    """ 自動清理 60 天以前的系統日誌 """
    with app.app_context():
        threshold = datetime.utcnow() - timedelta(days=60)
        deleted_count = AccessLog.query.filter(AccessLog.timestamp < threshold).delete()
        db.session.commit()
        if deleted_count > 0:
            record_system_log('INFO', 'System', f'自動清理完成：已移除 {deleted_count} 筆 60 天前的過期日誌')

def init_scheduler(app):
    """ 
    中央計時器
    """
    if not scheduler.running:
        # 1. ytdl 暫存清理 (每 20 秒)
        scheduler.add_job(id='ytdl_cleanup', func=cleanup_ytdl_tasks, args=[app], trigger='interval', seconds=20, timezone='Asia/Taipei')

        # 2.5. qrcode 暫存清理 (每 30 秒)
        scheduler.add_job(id='qrcode_cleanup', func=cleanup_qrcode_tasks, args=[app], trigger='interval', seconds=30, timezone='Asia/Taipei')

        # 2.6. imgedit 暫存清理 (每 30 秒)
        scheduler.add_job(id='imgedit_cleanup', func=cleanup_imgedit_tasks, args=[app], trigger='interval', seconds=30, timezone='Asia/Taipei')

        # 3. 每週數據報表 (每週日 2:00 寄送)
        scheduler.add_job(id='weekly_report_job', func=scheduled_weekly_report, args=[app], trigger='cron', day_of_week='sun', hour=2, minute=0, replace_existing=True, timezone='Asia/Taipei')

        # 4. 資源監控 (每 5 分鐘紀錄一次)
        scheduler.add_job(id='server_monitoring', func=collect_server_metrics, args=[app], trigger='interval', minutes=5, timezone='Asia/Taipei')

        # 5. 系統日誌清理 (每天凌晨 3 點執行)
        scheduler.add_job(id='log_cleanup', func=cleanup_old_logs, args=[app], trigger='cron', hour=3, minute=0, timezone='Asia/Taipei')

        # 6. GitHub 統計卡更新 (每天凌晨 4 點執行)
        scheduler.add_job(id='github_stats_update', func=update_github_data, args=[app], trigger='cron', hour=4, minute=0, timezone='Asia/Taipei')

        scheduler.start()
        print("[Scheduler] 中央計時器已啟動，任務已就緒 (時區: Asia/Taipei)")