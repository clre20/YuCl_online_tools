from core.database import db

BIND_KEY = 'clre_db'

# --- 新增這個 Class ---
class AdminUser(db.Model):
    __bind_key__ = BIND_KEY
    __tablename__ = 'clre_admin_users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password_hash = db.Column(db.String(200))

# --- 以下保持原樣 ---
class About(db.Model):
    __bind_key__ = BIND_KEY
    __tablename__ = 'clre_about'
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text)

class Skill(db.Model):
    __bind_key__ = BIND_KEY
    __tablename__ = 'clre_skills'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))
    icon_class = db.Column(db.String(50))

class Experience(db.Model):
    __bind_key__ = BIND_KEY
    __tablename__ = 'clre_experiences'
    id = db.Column(db.Integer, primary_key=True)
    period = db.Column(db.String(50))
    title = db.Column(db.String(100))
    description = db.Column(db.Text)

class Project(db.Model):
    __bind_key__ = BIND_KEY
    __tablename__ = 'clre_projects'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), unique=True) # [修改] 加入 unique=True 確保網址不重複
    description = db.Column(db.Text)
    details = db.Column(db.Text)
    image_url = db.Column(db.String(200))
    link_url = db.Column(db.String(200))
    link_type = db.Column(db.String(20))
    date = db.Column(db.String(20)) # 格式: YYYY-MM-DD
    last_updated = db.Column(db.DateTime, default=None) # 記錄最後修改時間
    views = db.Column(db.Integer, default=0)
    stars = db.Column(db.Integer, default=0)