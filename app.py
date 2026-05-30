from flask import Flask
import shutil
from static_ffmpeg import add_paths
from flask_migrate import Migrate
import os
import sys
#工具藍圖
from tool.tool import register_tools
#系統藍圖
from core.database import db, record_system_log, limiter, init_managed_tools, init_system_config
from routes.indexweb import indexweb_bp
from routes.admin import admin_bp
from core.middleware import setup_middleware
#掛載網站藍圖
from projects.projects import register_projects, init_projects_data
# 其他
from core.jobs import init_scheduler
from core.queue_manager import register_tool

app = Flask(__name__)
app.config['SECRET_KEY'] = '78af0dc2b88a4efe9ee1b073369863f79aba684ed36042d3a60db4e5824e49e5'

# 初始化 Limiter
limiter.init_app(app)

# 初始化 中間件 (維護模式與日誌)
setup_middleware(app)

# 配置資料庫
basedir = os.path.abspath(os.path.dirname(__file__))

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database/yucl_adb_tools_data.db')
app.config['SQLALCHEMY_BINDS'] = {
    'bdb_temp_db': 'sqlite:///' + os.path.join(basedir, 'database/yucl_bdb_tasks_data.db'), # 短及任務
    'clre_db': 'sqlite:///' + os.path.join(basedir, 'projects/clre20_website/database/clre20_data.db')
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)
migrate = Migrate(app, db)

#工具藍圖註冊
register_tools(app)
#系統藍圖註冊
app.register_blueprint(indexweb_bp)
app.register_blueprint(admin_bp)
#掛載網站藍圖註冊
register_projects(app)

def ensure_ffmpeg():
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        print(f"[V] 偵測到系統環境已有 FFmpeg: {ffmpeg_path}")
        return True
    print("[X] 系統環境未發現 FFmpeg")
    try:
        add_paths()
        new_ffmpeg_path = shutil.which("ffmpeg")
        if new_ffmpeg_path:
            print(f"[V] 已成功載入: {new_ffmpeg_path}")
            return True
        else:
            print("[X] 載入失敗，需要重新安裝套件。")
            return False
    except ImportError:
        add_paths()
        print("[V] FFmpeg 安裝並載入完成！")
        return True

if __name__ == '__main__':
    ensure_ffmpeg()          # FFmpeg初始化
    with app.app_context():
        db.create_all()      # 初始化YuCl Data
        init_projects_data() # 初始化所有子專案資料
        init_managed_tools() # 初始化工具紀錄
        init_system_config() # 初始化系統設定
        init_scheduler(app) #啟動排成器
        record_system_log('SUCCESS', 'System', 'YuCl 系統核心已成功啟動')
        
    app.run(host="0.0.0.0", port=6969, debug=True)