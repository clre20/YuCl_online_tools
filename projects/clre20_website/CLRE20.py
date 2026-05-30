from flask import Blueprint, render_template, request, redirect, url_for, jsonify, session, abort
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from core.database import db
from datetime import datetime
import json
from projects.clre20_website.models import About, Skill, Experience, Project, AdminUser

CLRE20_bp = Blueprint('CLRE20', __name__, static_folder='CLRE20', template_folder='templates')

# --- 登入驗證裝飾器 (Decorator) ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'clre_user_id' not in session:
            return redirect(url_for('CLRE20.login'))
        return f(*args, **kwargs)
    return decorated_function

# --- 資料庫初始化函數 ---
def init_db_data():
    try:
        # 1. 檢查並建立預設管理員
        if not AdminUser.query.filter_by(username='admin').first():
            print("[CLRE20] 建立預設管理員帳號...")
            hashed_pw = generate_password_hash('admin123')
            admin = AdminUser(username='admin', password_hash=hashed_pw)
            db.session.add(admin)
            db.session.commit()

        # 2. 檢查 About 資料
        if not About.query.first():
            print("[CLRE20] 偵測到空資料庫，正在寫入預設網站資料...")
            
            # About
            default_about = "這是我的介紹"
            db.session.add(About(content=default_about))
            
            # Skills
            skills_data = [
                {"name": "Python", "icon_class": "fa-brands fa-python"}
            ]
            for s in skills_data:
                db.session.add(Skill(**s))

            # Experiences
            exp_data = [
                {"period": "2025-01", "title": "伺服器開發者", "description": "負責伺服器的維護。"}
            ]
            for e in exp_data:
                db.session.add(Experience(**e))

            # Projects (寫入預設範例，details 存為 JSON list)
            proj_data = [
                {
                    "title": "YuCl 線上工具", 
                    "description": "線上工具", 
                    "image_url": "/static/ico/YuCl64.png", 
                    "link_url": "https://yucle.yucl.qzz.io", 
                    "link_type": "internal",
                    "date": datetime.now().strftime('%Y-%m-%d'),
                    "last_updated": None,
                    "details": json.dumps(["# 第一頁內容\n這是 YuCl 的介紹。", "# 第二頁內容\n這是更多詳細資訊。"]),
                    "views": 0,
                    "stars": 0
                }
            ]
            for p in proj_data:
                # 這裡建議使用 try-except 或檢查資料是否存在，以免重複執行時報錯
                existing = Project.query.filter_by(title=p['title']).first()
                if not existing:
                    db.session.add(Project(**p))
                
            db.session.commit()
            print("[CLRE20] 初始化完成。")
            
    except Exception as e:
        print(f"[CLRE20] 初始化檢查/寫入失敗: {e}")


@CLRE20_bp.route('/clre20/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = AdminUser.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            session['clre_user_id'] = user.id
            return jsonify({'status': 'success', 'redirect': url_for('CLRE20.admin_dashboard')})
        else:
            return jsonify({'status': 'error', 'message': "帳號或密碼錯誤"})
            
    return render_template('clre20/login.html')

@CLRE20_bp.route('/clre20/logout')
def logout():
    session.pop('clre_user_id', None)
    return redirect(url_for('CLRE20.login'))

# --- 前台路由 (公開) ---

@CLRE20_bp.route('/clre20')
def home():
    about = About.query.first()
    skills = Skill.query.all()
    # 經歷依照日期降冪排序
    experiences = Experience.query.order_by(Experience.period.desc()).all()
    # 專案也可以依照日期排序
    projects = Project.query.order_by(Project.date.desc()).all()
    
    about_dict = {"content": about.content} if about else {"content": "Loading..."}
    return render_template('clre20/index.html', about=about_dict, skills=skills, experiences=experiences, projects=projects)

# --- Admin 後台路由 (需登入) ---

@CLRE20_bp.route('/clre20/admin')
@login_required
def admin_dashboard():
    about = About.query.first()
    skills = Skill.query.all()
    experiences = Experience.query.order_by(Experience.period.desc()).all()
    projects = Project.query.order_by(Project.date.desc()).all()
    return render_template('clre20/admin.html', about=about, skills=skills, experiences=experiences, projects=projects)

# ==================== API 路由 (需登入) ====================

# --- 1. About 管理 ---
@CLRE20_bp.route('/clre20/admin/update_about', methods=['POST'])
@login_required
def update_about():
    data = request.json
    content = data.get('content')
    
    if not content or not content.strip():
         return jsonify({'status': 'error', 'message': '內容不能為空！'})

    about = About.query.first()
    if not about:
        about = About(content=content)
        db.session.add(about)
    else:
        about.content = content
    db.session.commit()
    return jsonify({'status': 'success', 'message': '關於我已更新！'})

# --- 2. Skills 管理 ---
@CLRE20_bp.route('/clre20/admin/api/skill/<int:id>', methods=['GET'])
@login_required
def get_skill(id):
    skill = Skill.query.get_or_404(id)
    return jsonify({'id': skill.id, 'name': skill.name, 'icon_class': skill.icon_class})

@CLRE20_bp.route('/clre20/admin/skill/add', methods=['POST'])
@login_required
def add_skill():
    data = request.json
    if not data.get('name') or not data.get('icon_class'):
        return jsonify({'status': 'error', 'message': '名稱與 Icon 為必填！'})
        
    db.session.add(Skill(name=data['name'], icon_class=data['icon_class']))
    db.session.commit()
    return jsonify({'status': 'success', 'message': '技能已新增！'})

@CLRE20_bp.route('/clre20/admin/skill/update/<int:id>', methods=['POST'])
@login_required
def update_skill(id):
    data = request.json
    if not data.get('name') or not data.get('icon_class'):
        return jsonify({'status': 'error', 'message': '名稱與 Icon 為必填！'})

    skill = Skill.query.get_or_404(id)
    skill.name = data['name']
    skill.icon_class = data['icon_class']
    db.session.commit()
    return jsonify({'status': 'success', 'message': '技能已更新！'})

@CLRE20_bp.route('/clre20/admin/skill/delete/<int:id>', methods=['POST'])
@login_required
def delete_skill(id):
    skill = Skill.query.get(id)
    if skill:
        db.session.delete(skill)
        db.session.commit()
        return jsonify({'status': 'success', 'message': '技能已刪除！'})
    return jsonify({'status': 'error', 'message': '找不到該技能'}), 404

# --- 3. Experience 管理 ---
@CLRE20_bp.route('/clre20/admin/api/experience/<int:id>', methods=['GET'])
@login_required
def get_experience(id):
    exp = Experience.query.get_or_404(id)
    return jsonify({'id': exp.id, 'period': exp.period, 'title': exp.title, 'description': exp.description})

@CLRE20_bp.route('/clre20/admin/experience/add', methods=['POST'])
@login_required
def add_experience():
    data = request.json
    if not data.get('period') or not data.get('title'):
        return jsonify({'status': 'error', 'message': '錯誤：期間與職稱不能為空！'})

    db.session.add(Experience(
        period=data['period'],
        title=data['title'],
        description=data.get('description', '')
    ))
    db.session.commit()
    return jsonify({'status': 'success', 'message': '經歷已新增！'})

@CLRE20_bp.route('/clre20/admin/experience/update/<int:id>', methods=['POST'])
@login_required
def update_experience(id):
    data = request.json
    if not data.get('period') or not data.get('title'):
        return jsonify({'status': 'error', 'message': '錯誤：期間與職稱不能為空！'})

    exp = Experience.query.get_or_404(id)
    exp.period = data['period']
    exp.title = data['title']
    exp.description = data['description']
    db.session.commit()
    return jsonify({'status': 'success', 'message': '經歷已更新！'})

@CLRE20_bp.route('/clre20/admin/experience/delete/<int:id>', methods=['POST'])
@login_required
def delete_experience(id):
    exp = Experience.query.get(id)
    if exp:
        db.session.delete(exp)
        db.session.commit()
        return jsonify({'status': 'success', 'message': '經歷已刪除！'})
    return jsonify({'status': 'error', 'message': '找不到該經歷'}), 404

# --- 4. Project 管理 (分頁邏輯 + 瀏覽數控制) ---

@CLRE20_bp.route('/clre20/project/<string:title>')
@CLRE20_bp.route('/clre20/project/<string:title>/<int:page>')
def project_detail(title, page=1):
    project = Project.query.filter_by(title=title).first_or_404()
    
    # --- [修改] 瀏覽數邏輯 (30分鐘內不重複計算) ---
    current_time = datetime.now().timestamp()
    # 從 session 取得已瀏覽過的專案紀錄 (dict: project_id -> timestamp)
    viewed_projects = session.get('viewed_projects', {})
    
    # 取得上次瀏覽此專案的時間 (如果有的話)
    last_view_time = viewed_projects.get(str(project.id))
    
    # 如果沒有瀏覽過，或距離上次瀏覽超過 1800 秒 (30分鐘)
    if last_view_time is None or (current_time - last_view_time) > 1800:
        if project.views is None:
            project.views = 0
        project.views += 1
        db.session.commit()
        
        # 更新 session
        viewed_projects[str(project.id)] = current_time
        session['viewed_projects'] = viewed_projects
        session.modified = True # 確保 Flask 知道 session 已變更需要儲存

    # 嘗試解析 details (支援分頁)
    try:
        pages = json.loads(project.details)
        if not isinstance(pages, list):
            pages = [project.details]
    except (json.JSONDecodeError, TypeError):
        # 舊資料相容
        pages = [project.details]

    # 頁數防呆
    if page < 1 or page > len(pages):
        return redirect(url_for('CLRE20.project_detail', title=title, page=1))

    current_content = pages[page - 1]
    total_pages = len(pages)

    return render_template('clre20/project.html', 
                           project=project, 
                           content=current_content, 
                           current_page=page, 
                           total_pages=total_pages)

# [新增] 專案按讚 (星星) API
@CLRE20_bp.route('/clre20/api/project/star', methods=['POST'])
def toggle_project_star():
    data = request.json
    proj_id = data.get('id')
    action = data.get('action') # 'add' or 'remove'
    
    if not proj_id or not action:
        return jsonify({'status': 'error', 'message': '缺少參數'}), 400
        
    project = Project.query.get_or_404(proj_id)
    
    if project.stars is None:
        project.stars = 0
        
    if action == 'add':
        project.stars += 1
    elif action == 'remove':
        # 確保不變成負數
        project.stars = max(0, project.stars - 1)
        
    db.session.commit()
    
    return jsonify({'status': 'success', 'stars': project.stars})


@CLRE20_bp.route('/clre20/admin/api/project/<int:id>', methods=['GET'])
@login_required
def get_project(id):
    proj = Project.query.get_or_404(id)
    
    # 解析 JSON 給前端
    try:
        details_data = json.loads(proj.details)
        if not isinstance(details_data, list):
            details_data = [proj.details]
    except:
        details_data = [proj.details]

    return jsonify({
        'id': proj.id, 
        'title': proj.title, 
        'description': proj.description,
        'details': details_data,
        'image_url': proj.image_url, 
        'link_url': proj.link_url, 
        'link_type': proj.link_type,
        'date': proj.date,
        'views': proj.views if proj.views else 0, # 新增回傳
        'stars': proj.stars if proj.stars else 0  # 新增回傳
    })

@CLRE20_bp.route('/clre20/admin/project/add', methods=['POST'])
@login_required
def add_project():
    data = request.json
    if not data.get('title'): 
        return jsonify({'status': 'error', 'message': '錯誤：標題不能為空！'})

    if Project.query.filter_by(title=data['title']).first():
        return jsonify({'status': 'error', 'message': '錯誤：專案標題已存在，請使用不同名稱！'})

    current_date = datetime.now().strftime('%Y-%m-%d')
    input_date = data.get('date') if data.get('date') else current_date

    # 處理多頁內容 (前端傳來 array，這裡轉 string)
    details_content = data.get('details', '')
    if isinstance(details_content, list):
        details_content = json.dumps(details_content)

    db.session.add(Project(
        title=data['title'],
        description=data.get('description', ''),
        details=details_content,
        image_url=data.get('image_url', ''),
        link_url=data.get('link_url', ''),
        link_type=data.get('link_type', 'external'),
        date=input_date,
        last_updated=None,
        views=0, # 預設值
        stars=0  # 預設值
    ))
    db.session.commit()
    return jsonify({'status': 'success', 'message': '專案已新增！'})

@CLRE20_bp.route('/clre20/admin/project/update/<int:id>', methods=['POST'])
@login_required
def update_project(id):
    data = request.json
    if not data.get('title'):
        return jsonify({'status': 'error', 'message': '錯誤：標題不能為空！'})

    proj = Project.query.get_or_404(id)
    
    if proj.title != data['title']:
        if Project.query.filter_by(title=data['title']).first():
            return jsonify({'status': 'error', 'message': '錯誤：新標題已存在，請使用不同名稱！'})

    proj.title = data['title']
    proj.description = data['description']
    
    details_content = data.get('details', '')
    if isinstance(details_content, list):
        details_content = json.dumps(details_content)
    proj.details = details_content

    proj.image_url = data['image_url']
    proj.link_url = data.get('link_url', '')
    proj.link_type = data['link_type']
    proj.date = data.get('date')
    proj.last_updated = datetime.now()

    db.session.commit()
    return jsonify({'status': 'success', 'message': '專案已更新！'})

@CLRE20_bp.route('/clre20/admin/project/delete/<int:id>', methods=['POST'])
@login_required
def delete_project(id):
    proj = Project.query.get(id)
    if proj:
        db.session.delete(proj)
        db.session.commit()
        return jsonify({'status': 'success', 'message': '專案已刪除！'})
    return jsonify({'status': 'error', 'message': '找不到該專案'}), 404

# --- 修改帳號功能 ---
@CLRE20_bp.route('/clre20/admin/change_username', methods=['POST'])
@login_required
def change_username():
    data = request.json
    new_username = data.get('new_username')
    password = data.get('password')

    if not new_username or not password:
        return jsonify({'status': 'error', 'message': '新帳號與密碼都必須填寫！'})

    user_id = session.get('clre_user_id')
    user = AdminUser.query.get(user_id)

    if not check_password_hash(user.password_hash, password):
        return jsonify({'status': 'error', 'message': '密碼錯誤，無法修改帳號！'})

    existing = AdminUser.query.filter_by(username=new_username).first()
    if existing and existing.id != user_id:
        return jsonify({'status': 'error', 'message': '該帳號名稱已被使用！'})

    user.username = new_username
    db.session.commit()
    return jsonify({'status': 'success', 'message': f'帳號已成功修改為 {new_username}！'})

# --- 修改密碼功能 ---
@CLRE20_bp.route('/clre20/admin/change_password', methods=['POST'])
@login_required
def change_password():
    data = request.json
    old_password = data.get('old_password')
    new_password = data.get('new_password')
    confirm_password = data.get('confirm_password')

    if not old_password or not new_password or not confirm_password:
        return jsonify({'status': 'error', 'message': '所有欄位都必須填寫！'})

    if new_password != confirm_password:
        return jsonify({'status': 'error', 'message': '新密碼與確認密碼不符！'})

    user_id = session.get('clre_user_id')
    user = AdminUser.query.get(user_id)

    if not check_password_hash(user.password_hash, old_password):
        return jsonify({'status': 'error', 'message': '舊密碼錯誤！'})

    user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    return jsonify({'status': 'success', 'message': '密碼修改成功！下次登入請使用新密碼。'})