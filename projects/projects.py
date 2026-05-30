# projects/projects.py
from projects.clre20_website.CLRE20 import CLRE20_bp, init_db_data
from projects.yueyou_website.YUEYOU import YUEYOU_bp

def register_projects(app):
    """
    將所有獨立的專案藍圖註冊到主要的 Flask app 中
    """
    # 註冊 CLRE20 個人網站
    app.register_blueprint(CLRE20_bp)
    
    # 註冊 YUEYOU 個人網站
    app.register_blueprint(YUEYOU_bp)

def init_projects_data():
    """
    初始化所有專案所需的資料庫數據
    """
    init_db_data() # CLRE20 的初始化
