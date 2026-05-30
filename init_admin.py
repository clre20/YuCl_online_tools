# YuCl 新系統/init_admin.py
from app import app
from core.database import db, Admin
from werkzeug.security import generate_password_hash

def create_admin():
    with app.app_context():
        # 設定您的登入帳號與密碼
        email = "smart960710@gmail.com"  # 這是之後登入要用的 Email
        password = "123" # 這是之後登入要用的密碼
        
        # 檢查是否已存在
        existing_admin = Admin.query.filter_by(email=email).first()
        if existing_admin:
            print(f"管理員 {email} 已經存在。")
            return

        # 建立新管理員
        new_admin = Admin(
            email=email,
            password_hash=generate_password_hash(password)
        )
        db.session.add(new_admin)
        db.session.commit()
        print(f"成功建立管理員帳號！")
        print(f"帳號: {email}")
        print(f"密碼: {password}")

if __name__ == "__main__":
    create_admin()