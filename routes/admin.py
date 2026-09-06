# YuCl 新系統/admin.py
from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify, flash, current_app
from core.database import db, Admin, ManagedTool, ToolDailyStat, SystemLog, AccessLog, ServerMetric, SystemConfig, Announcement, record_system_log, limiter, get_top_pages
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from datetime import datetime

admin_bp = Blueprint('admin_console', __name__)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            return redirect(url_for('admin_console.login'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/admin/logs')
@login_required
def logs_view():
    """ 系統與訪問日誌檢視頁面 - 支援搜尋與篩選 """
    # 獲取搜尋參數
    ip_search = request.args.get('ip', '').strip()
    path_search = request.args.get('path', '').strip()
    module_search = request.args.get('module', '').strip()
    level_filter = request.args.get('level', '').strip()
    active_tab = request.args.get('tab', 'system') # [新增] 紀錄目前標籤

    # 1. 處理訪問日誌 (AccessLog)
    access_query = AccessLog.query
    if ip_search:
        access_query = access_query.filter(AccessLog.ip_address.contains(ip_search))
    if path_search:
        access_query = access_query.filter(AccessLog.path.contains(path_search))
    access_logs = access_query.order_by(AccessLog.timestamp.desc()).limit(100).all()

    # 2. 處理系統日誌 (SystemLog)
    system_query = SystemLog.query
    if module_search:
        system_query = system_query.filter(SystemLog.module.contains(module_search))
    if level_filter:
        system_query = system_query.filter(SystemLog.level == level_filter)
    system_logs = system_query.order_by(SystemLog.timestamp.desc()).limit(100).all()
    
    return render_template('admin/logs.html', 
                           system_logs=system_logs, 
                           access_logs=access_logs,
                           ip_search=ip_search,
                           path_search=path_search,
                           module_search=module_search,
                           level_filter=level_filter,
                           active_tab=active_tab)

@admin_bp.route('/admin')
@login_required
def index():
    """ 管理後台總覽首頁 - 包含分析數據與維護模式狀態 """
    tools = ManagedTool.query.all()
    today = datetime.utcnow().date()
    
    # 維護模式狀態
    maintenance_config = SystemConfig.query.filter_by(key='maintenance_mode').first()
    is_maintenance = maintenance_config.value == 'true' if maintenance_config else False

    # 公告列表
    announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()

    # 伺服器即時資源
    latest_metric = ServerMetric.query.order_by(ServerMetric.timestamp.desc()).first()

    # 統計全站總數據
    from datetime import timedelta
    seven_days_ago = today - timedelta(days=6)

    total_stats = {
        'visits': db.session.query(db.func.sum(ManagedTool.visit_count_total)).scalar() or 0,
        'usage': db.session.query(db.func.sum(ManagedTool.usage_count_total)).scalar() or 0,
        'daily_visits': db.session.query(db.func.sum(ToolDailyStat.visit_count)).filter(ToolDailyStat.date == today).scalar() or 0,
        'daily_usage': db.session.query(db.func.sum(ToolDailyStat.usage_count)).filter(ToolDailyStat.date == today).scalar() or 0,
        'tool_count': len(tools),
        # 訪客 IP 統計 (歷史總計與本週新增)
        'total_unique_ips': db.session.query(db.func.count(db.func.distinct(AccessLog.ip_address))).scalar() or 0,
        'weekly_unique_ips': db.session.query(db.func.count(db.func.distinct(AccessLog.ip_address)))\
                                      .filter(AccessLog.timestamp >= seven_days_ago).scalar() or 0
    }

    # 2. 趨勢圖數據: 過去 7 天全站訪問量
    seven_days_ago = today - timedelta(days=6)
    daily_trend_raw = db.session.query(
        db.func.date(AccessLog.timestamp).label('date'),
        db.func.count(AccessLog.id)
    ).filter(AccessLog.timestamp >= seven_days_ago)\
     .group_by('date').all()
    
    trend_labels = []
    trend_values = []
    trend_dict = {str(r[0]): r[1] for r in daily_trend_raw}
    for i in range(7):
        d = seven_days_ago + timedelta(days=i)
        d_str = d.strftime('%Y-%m-%d')
        trend_labels.append(d.strftime('%m/%d'))
        trend_values.append(trend_dict.get(d_str, 0))

    # 3. 工具佔比圖
    tool_share_labels = [t.name for t in tools]
    tool_share_values = [t.usage_count_total for t in tools]

    # 4. 國家分佈圖
    country_stats_raw = db.session.query(
        AccessLog.country, db.func.count(AccessLog.id)
    ).group_by(AccessLog.country).order_by(db.desc(db.func.count(AccessLog.id))).all()
    
    # 5. 熱門頁面排行 (Top 10)
    hide_api = request.args.get('hide_api', 'true') == 'true'
    top_pages = get_top_pages(limit=10, hide_internal=hide_api)

    map_data = []
    full_country_list = []
    unknown_count = 0
    
    for c_code, count in country_stats_raw:
        if c_code and c_code != 'Unknown' and c_code != 'Local':
            map_data.append([c_code, count])
            full_country_list.append({'code': c_code, 'count': count})
        else:
            unknown_count += count

    chart_data = {
        'trend': {'labels': trend_labels, 'values': trend_values},
        'tool_share': {'labels': tool_share_labels, 'values': tool_share_values},
        'map_data': map_data,
        'full_country_list': full_country_list,
        'unknown_count': unknown_count
    }
    
    for tool in tools:
        daily = ToolDailyStat.query.filter_by(tool_id=tool.id, date=today).first()
        tool.daily_visit = daily.visit_count if daily else 0
        tool.daily_usage = daily.usage_count if daily else 0
            
    return render_template('admin/admin.html', 
                           tools=tools, 
                           total_stats=total_stats, 
                           chart_data=chart_data,
                           top_pages=top_pages,
                           hide_api=hide_api,
                           is_maintenance=is_maintenance,
                           latest_metric=latest_metric,
                           announcements=announcements)

@admin_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        admin = Admin.query.filter_by(email=email).first()
        if admin and check_password_hash(admin.password_hash, password):
            session['admin_logged_in'] = True
            session['admin_id'] = admin.id
            return jsonify({"status": "success", "message": "登入成功，正在跳轉..."})
        return jsonify({"status": "error", "message": "帳號或密碼錯誤"}), 401
    return render_template('admin/login.html')

@admin_bp.route('/api/sys/maintenance/toggle', methods=['POST'])
@login_required
def toggle_maintenance():
    """ 切換全站維護模式 """
    mode = SystemConfig.query.filter_by(key='maintenance_mode').first()
    if not mode:
        mode = SystemConfig(key='maintenance_mode', value='false')
        db.session.add(mode)
    
    # 切換狀態
    new_status = 'true' if mode.value == 'false' else 'false'
    mode.value = new_status
    db.session.commit()
    
    log_msg = f"管理員已{'開啟' if new_status == 'true' else '關閉'}全站維護模式"
    record_system_log('WARNING', 'Admin', log_msg)
    
    return jsonify({"status": "success", "new_status": new_status})

@admin_bp.route('/api/sys/announcement/add', methods=['POST'])
@login_required
def add_announcement():
    """ 新增系統公告 """
    data = request.json or {}
    content = data.get('content', '').strip()
    ann_type = data.get('type', 'info').strip()
    expires_at_str = data.get('expires_at', '').strip()
    
    if not content:
        return jsonify({"status": "error", "message": "公告內容不能為空"}), 400
        
    display_duration = 5
    try:
        display_duration = int(data.get('display_duration', 5))
        if display_duration <= 0:
            display_duration = 5
    except (ValueError, TypeError):
        display_duration = 5
        
    try:
        expires_at = None
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str)
            except ValueError:
                expires_at = datetime.strptime(expires_at_str, "%Y-%m-%d %H:%M:%S")
        
        new_ann = Announcement(
            content=content,
            type=ann_type,
            is_active=True,
            expires_at=expires_at,
            display_duration=display_duration
        )
        db.session.add(new_ann)
        db.session.commit()
        
        record_system_log('WARNING', 'Admin', f'管理員新增全站公告: {content} (類型: {ann_type})')
        return jsonify({"status": "success", "message": "公告新增成功"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@admin_bp.route('/api/sys/announcement/toggle/<int:id>', methods=['POST'])
@login_required
def toggle_announcement(id):
    """ 切換公告啟用狀態 """
    ann = Announcement.query.get_or_404(id)
    try:
        ann.is_active = not ann.is_active
        db.session.commit()
        
        status_str = "啟用" if ann.is_active else "停用"
        record_system_log('WARNING', 'Admin', f'管理員{status_str}公告 (ID: {id}): {ann.content[:30]}...')
        return jsonify({"status": "success", "is_active": ann.is_active})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@admin_bp.route('/api/sys/announcement/delete/<int:id>', methods=['POST'])
@login_required
def delete_announcement(id):
    """ 刪除公告 """
    ann = Announcement.query.get_or_404(id)
    try:
        content_preview = ann.content[:30]
        db.session.delete(ann)
        db.session.commit()
        
        record_system_log('WARNING', 'Admin', f'管理員刪除了公告 (ID: {id}): {content_preview}...')
        return jsonify({"status": "success", "message": "公告已成功刪除"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@admin_bp.route('/api/tool/toggle_status/<int:id>', methods=['POST'])
@login_required
def toggle_tool_status(id):
    """ 切換單一工具的啟用狀態 """
    tool = ManagedTool.query.get_or_404(id)
    tool.is_active = not tool.is_active
    db.session.commit()
    
    status_str = "開啟" if tool.is_active else "關閉"
    record_system_log('WARNING', 'Admin', f'管理員已{status_str}工具: {tool.name}')
    
    return jsonify({"status": "success", "is_active": tool.is_active})

@admin_bp.route('/admin/tool/<int:id>')
@login_required
def tool_detail(id):
    """ 單一工具的獨立控制台 """
    tool = ManagedTool.query.get_or_404(id)
    today = datetime.utcnow().date()
    
    # 1. 取得今日數據
    daily_stat = ToolDailyStat.query.filter_by(tool_id=id, date=today).first()
    stats = {
        'daily_visit': daily_stat.visit_count if daily_stat else 0,
        'daily_usage': daily_stat.usage_count if daily_stat else 0
    }
    
    # 2. 取得過去 7 天的數據 (用於圖表)
    from datetime import timedelta
    seven_days_ago = today - timedelta(days=6)
    
    history_stats = ToolDailyStat.query.filter(
        ToolDailyStat.tool_id == id,
        ToolDailyStat.date >= seven_days_ago
    ).order_by(ToolDailyStat.date.asc()).all()
    
    # 格式化圖表數據
    labels = []
    usage_data = []
    history_dict = {str(s.date): s.usage_count for s in history_stats}
    
    for i in range(7):
        d = seven_days_ago + timedelta(days=i)
        d_str = str(d)
        labels.append(d.strftime('%m/%d'))
        usage_data.append(history_dict.get(d_str, 0))
        
    tool_chart = {
        'labels': labels,
        'usage': usage_data
    }
    
    return render_template('admin/tool_detail.html', 
                           tool=tool, 
                           stats=stats, 
                           tool_chart=tool_chart)

@admin_bp.route('/logout')
def logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_console.login'))

@admin_bp.route('/api/tool/update_concurrency/<int:id>', methods=['POST'])
@login_required
def update_concurrency(id):
    # ... 原有邏輯
    data = request.json
    tool = ManagedTool.query.get_or_404(id)
    try:
        new_val = int(data.get('max_concurrent', 1))
        tool.max_concurrent = new_val
        db.session.commit()
        return jsonify({"status": "success"})
    except ValueError:
        return jsonify({"status": "error", "message": "無效的數值"}), 400

@admin_bp.route('/api/sys/track', methods=['POST'])
def track_page_visit():
    """ 接收前端傳回的訪問統計數據 (強化解析版) """
    try:
        # 1. 嘗試多種方式獲取數據
        data = None
        
        # 優先嘗試標準 JSON
        if request.is_json:
            data = request.get_json()
        
        # 如果不是標準 JSON (例如 sendBeacon 發送的 text/plain)，手動解析原始數據
        if not data:
            raw_data = request.data.decode('utf-8')
            if raw_data:
                import json
                try:
                    data = json.loads(raw_data)
                except Exception as je:
                    print(f"[Track Debug] JSON 解析失敗: {je}, 原始數據: {raw_data}")
        
        if not data:
            return jsonify({"status": "no_data_received"}), 200

        # 2. 獲取真實 IP 與國家 (Cloudflare)
        ip = request.headers.get('CF-Connecting-IP', request.remote_addr)
        country = request.headers.get('CF-IPCountry', 'Unknown')

        # 3. 建立紀錄 (對應 AccessLog 模型)
        # 欄位：ip_address, country, path, duration, timestamp
        log = AccessLog(
            ip_address=ip,
            country=country,
            path=data.get('path', 'Unknown'),
            duration=round(float(data.get('duration', 0)), 4),
            timestamp=datetime.utcnow()
        )
        
        db.session.add(log)
        db.session.commit()
        return jsonify({"status": "success"})
        
    except Exception as e:
        db.session.rollback()
        print(f"[Critical Track Error] {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@admin_bp.route('/api/sys/logs/clear/<string:log_type>', methods=['POST'])
@login_required
def clear_logs(log_type):
    # ... 原有邏輯
    try:
        if log_type == 'system':
            db.session.query(SystemLog).delete()
            record_system_log('WARNING', 'Admin', '管理員已清空所有系統日誌')
        elif log_type == 'access':
            db.session.query(AccessLog).delete()
            record_system_log('WARNING', 'Admin', '管理員已清空所有訪問紀錄')
        else:
            return jsonify({"status": "error", "message": "無效的日誌類型"}), 400

        db.session.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500

@admin_bp.route('/api/sys/report/test', methods=['POST'])
@login_required
def test_weekly_report():
    """ 手動觸發週報寄送測試 """
    from core.mail import scheduled_weekly_report
    from flask import current_app
    try:
        # 非同步執行以避免前端逾時
        import threading
        threading.Thread(target=scheduled_weekly_report, args=(current_app._get_current_object(),)).start()
        return jsonify({"status": "success", "message": "週報生成任務已啟動，請稍候查收郵件"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500