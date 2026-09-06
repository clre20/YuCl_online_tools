from flask_sqlalchemy import SQLAlchemy
from flask_apscheduler import APScheduler
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import datetime
import threading

db = SQLAlchemy()
scheduler = APScheduler()
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")
global_queue_lock = threading.Lock()

# --- 工具統計輔助函數 ---

def record_tool_visit(tool_name):
    """ 紀錄工具訪問次數 (總計與每日) """
    from datetime import datetime
    tool = ManagedTool.query.filter_by(name=tool_name).first()
    if not tool:
        return
    
    # 更新總計
    tool.visit_count_total += 1
    
    # 更新每日
    today = datetime.utcnow().date()
    stat = ToolDailyStat.query.filter_by(tool_id=tool.id, date=today).first()
    if not stat:
        stat = ToolDailyStat(tool_id=tool.id, date=today, visit_count=1)
        db.session.add(stat)
    else:
        stat.visit_count += 1
    
    db.session.commit()

def record_tool_usage(tool_name):
    """ 紀錄工具使用次數 (總計與每日) """
    from datetime import datetime
    tool = ManagedTool.query.filter_by(name=tool_name).first()
    if not tool:
        return
    
    # 更新總計
    tool.usage_count_total += 1
    
    # 更新每日
    today = datetime.utcnow().date()
    stat = ToolDailyStat.query.filter_by(tool_id=tool.id, date=today).first()
    if not stat:
        stat = ToolDailyStat(tool_id=tool.id, date=today, usage_count=1)
        db.session.add(stat)
    else:
        stat.usage_count += 1
    
    db.session.commit()

# --- 資料庫模型定義  ---

class Admin(db.Model):
    """管理員帳號"""
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AccessLog(db.Model):
    """全站流量紀錄"""
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), nullable=False)
    country = db.Column(db.String(10), nullable=True) 
    path = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    duration = db.Column(db.Float, nullable=True) # 允許為空，待結束後更新

class SystemLog(db.Model):
    """ 系統運作與數值日誌 """
    id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.String(20), default='INFO') # INFO, WARNING, ERROR, SUCCESS
    module = db.Column(db.String(50)) # 模組名稱
    message = db.Column(db.Text)      # 訊息內容
    value = db.Column(db.Float, nullable=True) # 各種數值紀錄 (選填)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class ServerMetric(db.Model):
    """ 伺服器資源監控紀錄 """
    id = db.Column(db.Integer, primary_key=True)
    cpu_usage = db.Column(db.Float)
    ram_usage = db.Column(db.Float)
    disk_usage = db.Column(db.Float)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class SystemConfig(db.Model):
    """ 系統全域設定 """
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False) # e.g., 'maintenance_mode'
    value = db.Column(db.String(255))
    description = db.Column(db.String(255))

class Announcement(db.Model):
    """ 系統公告 """
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(20), default='info') # info, warning, danger, success
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True) # 過期時間 (UTC)
    display_duration = db.Column(db.Integer, default=5) # 顯示時間 (秒)

def record_system_log(level, module, message, value=None):
    """ 輔助函數：紀錄系統日誌 """
    log = SystemLog(level=level, module=module, message=message, value=value)
    db.session.add(log)
    db.session.commit()

def get_top_pages(limit=10, start_date=None, end_date=None, hide_internal=True):
    """ 
    輔助函數：獲取熱門頁面排行
    預設會排除 /api/ 與 /admin/ 開頭的內部路徑
    """
    from sqlalchemy import desc, func
    query = db.session.query(
        AccessLog.path, func.count(AccessLog.id).label('count')
    )
    
    # 時間篩選
    if start_date:
        query = query.filter(AccessLog.timestamp >= start_date)
    if end_date:
        query = query.filter(AccessLog.timestamp <= end_date)
        
    # 排除管理與 API 路徑
    if hide_internal:
        query = query.filter(
            ~AccessLog.path.startswith('/api/'),
            ~AccessLog.path.startswith('/admin/')
        )
        
    return query.group_by(AccessLog.path).order_by(desc('count')).limit(limit).all()

    
# 工具定義
class ManagedTool(db.Model):
    """ 工具定義與排隊上限 """
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True) # 如 'ytmp3'
    blueprint = db.Column(db.String(100), nullable=True)         # 對應的藍圖名稱
    max_concurrent = db.Column(db.Integer, default=1)           # 此工具的同時執行上限
    url = db.Column(db.String(500), nullable=False)
    is_active = db.Column(db.Boolean, default=True)            # 工具是否啟用
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 統計欄位
    visit_count_total = db.Column(db.Integer, default=0)
    usage_count_total = db.Column(db.Integer, default=0)

class ToolDailyStat(db.Model):
    """ 每日工具統計 """
    id = db.Column(db.Integer, primary_key=True)
    tool_id = db.Column(db.Integer, db.ForeignKey('managed_tool.id', ondelete='CASCADE'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    visit_count = db.Column(db.Integer, default=0)
    usage_count = db.Column(db.Integer, default=0)

    __table_args__ = (db.UniqueConstraint('tool_id', 'date', name='_tool_date_uc'),)

# Ytdl
class YtdlTask(db.Model):
    """ytdl 暫存任務表"""
    __bind_key__ = 'bdb_temp_db'
    id = db.Column(db.String(50), primary_key=True) # UUID
    tool_id = db.Column(db.Integer)
    status = db.Column(db.String(20), default='waiting') # waiting, processing, finished, error
    video_url = db.Column(db.String(500))
    download_type = db.Column(db.String(10))        # mp3, mp4
    quality = db.Column(db.String(50))              # mp3-320, etc.
    file_name = db.Column(db.String(255))           # 存放最終產出的檔名
    progress = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow) # 用於排隊順序
    last_polled = db.Column(db.DateTime, default=datetime.utcnow)

class YtdlUsageLog(db.Model):
    """ytdl 數據統計"""
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    action = db.Column(db.String(20)) # 'browse', 'convert_request', 'convert_success'

class QrCodeTask(db.Model):
    """qrcode暫存任務表"""
    __bind_key__ = 'bdb_temp_db'
    id = db.Column(db.String(50), primary_key=True) # UUID
    tool_id = db.Column(db.Integer)
    status = db.Column(db.String(20), default='waiting') # waiting, processing, finished, error
    
    # Form data params
    data_type = db.Column(db.String(20)) # text, wifi, email
    qr_data = db.Column(db.Text)
    style_type = db.Column(db.String(20)) # basic, styled
    version = db.Column(db.Integer)
    error_correction = db.Column(db.String(5))
    box_size = db.Column(db.Integer)
    fill_color = db.Column(db.String(50))
    back_color = db.Column(db.String(50))
    
    # Styled options
    module_drawer = db.Column(db.String(50))
    color_mask = db.Column(db.String(50))
    center_color = db.Column(db.String(50))
    edge_color = db.Column(db.String(50))
    left_color = db.Column(db.String(50))
    right_color = db.Column(db.String(50))
    top_color = db.Column(db.String(50))
    bottom_color = db.Column(db.String(50))
    embed_image_name = db.Column(db.String(255))
    
    file_name = db.Column(db.String(255))
    progress = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_polled = db.Column(db.DateTime, default=datetime.utcnow)

class ImgeditTask(db.Model):
    """imgedit暫存任務表"""
    __bind_key__ = 'bdb_temp_db'
    id = db.Column(db.String(50), primary_key=True) # UUID
    tool_id = db.Column(db.Integer)
    status = db.Column(db.String(20), default='waiting') # waiting, processing, finished, error
    
    # Form data params
    width = db.Column(db.Integer, nullable=True)
    height = db.Column(db.Integer, nullable=True)
    keep_aspect = db.Column(db.Boolean, default=True)
    
    filter_type = db.Column(db.String(50), default='none')
    brightness = db.Column(db.Float, default=1.0)
    contrast = db.Column(db.Float, default=1.0)
    saturation = db.Column(db.Float, default=1.0)
    
    cyan_red = db.Column(db.Integer, default=0)
    magenta_green = db.Column(db.Integer, default=0)
    yellow_blue = db.Column(db.Integer, default=0)
    
    output_format = db.Column(db.String(20), default='original')
    
    input_file_name = db.Column(db.String(255))
    file_name = db.Column(db.String(255))
    progress = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_polled = db.Column(db.DateTime, default=datetime.utcnow)

def init_managed_tools():
    """ 初始化常用工具至資料庫，確保重置後依然存在 """
    tools_data = [
        {'name': 'ytdl', 'url': '/ytdl', 'blueprint': 'ytdl_bp', 'max_concurrent': 1},
        {'name': 'gcode', 'url': '/gcode', 'blueprint': 'gcode', 'max_concurrent': 1},
        {'name': 'qrcode', 'url': '/qrcode', 'blueprint': 'qrcode_bp', 'max_concurrent': 1},
        {'name': 'imgedit', 'url': '/imgedit', 'blueprint': 'imgedit_bp', 'max_concurrent': 1},
        {'name': 'clre20', 'url': '/clre20', 'blueprint': 'CLRE20', 'max_concurrent': 1},
        {'name': 'yueyou_website', 'url': '/oneself', 'blueprint': 'YUEYOU', 'max_concurrent': 1},
        {'name': 'shorturl', 'url': '/shorturl', 'blueprint': 'shorturl_bp', 'max_concurrent': 5},
    ]
    for t_data in tools_data:
        existing = ManagedTool.query.filter_by(name=t_data['name']).first()
        if not existing:
            print(f"[Init] 建立預設工具紀錄: {t_data['name']}")
            new_tool = ManagedTool(**t_data)
            db.session.add(new_tool)
            
    # 清理廢棄的舊工具紀錄
    existing_names = [t['name'] for t in tools_data]
    obsolete = ManagedTool.query.filter(~ManagedTool.name.in_(existing_names)).all()
    for obs in obsolete:
        print(f"[Init] 移除過期工具紀錄: {obs.name}")
        db.session.delete(obs)
        
    db.session.commit()

def init_system_config():
    """ 初始化系統全域設定 """
    configs = [
        {'key': 'maintenance_mode', 'value': 'false', 'description': '全站維護模式 (true/false)'}
    ]
    for cfg_data in configs:
        existing = SystemConfig.query.filter_by(key=cfg_data['key']).first()
        if not existing:
            new_cfg = SystemConfig(**cfg_data)
            db.session.add(new_cfg)
    db.session.commit()

def init_default_announcements():
    """ 初始化預設公告 """
    try:
        # 確保舊資料庫升級，添加 display_duration 欄位
        try:
            db.session.execute(db.text("ALTER TABLE announcement ADD COLUMN display_duration INTEGER DEFAULT 5"))
            db.session.commit()
            print("[Upgrade] 公告資料表已成功升級新增 display_duration 欄位")
        except Exception:
            db.session.rollback()

        existing = Announcement.query.first()
        if not existing:
            default_ann = Announcement(
                content="歡迎來到 YuCl 線上工具系統！本站已支援全新的公告小卡功能。",
                type="info",
                is_active=True,
                display_duration=5
            )
            db.session.add(default_ann)
            db.session.commit()
            print("[Init] 已建立預設系統公告")
    except Exception as e:
        print(f"[Init Error] 初始化公告失敗: {e}")