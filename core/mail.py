# mail.py
import smtplib
import json
import urllib.parse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
from datetime import datetime, timedelta
from flask import render_template
from sqlalchemy import func
from core.database import db, scheduler, AccessLog, Admin, record_system_log, get_top_pages

# ================= 設定區域 =================
SMTP_CONFIG = {
    "username": "smart96071031@gmail.com",
    "password": "aqni nyuu ujou lvvi",  # 你的應用程式密碼
    "display_name": "YuCl 線上工具",
    "sender_email": "noreply@yucle.yucl.qzz.io"
}

# ================= 核心功能 1: 發送郵件 =================
def send_email(recipients, subject, html_content):
    """ 通用發送郵件函數 """
    if not recipients:
        print("[Mail] ❌ 沒有收件者，取消發送")
        return False
        
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SMTP_CONFIG["username"], SMTP_CONFIG["password"])
        
        print(f"[Mail] 準備發送郵件給 {len(recipients)} 位收件者...")

        for receiver in recipients:
            try:
                msg = MIMEMultipart()
                msg['From'] = formataddr((str(Header(SMTP_CONFIG["display_name"], 'utf-8')), SMTP_CONFIG["sender_email"]))
                msg['To'] = receiver
                msg['Subject'] = subject
                msg.attach(MIMEText(html_content, 'html'))
                server.send_message(msg)
                print(f"[Mail] ✅ 已成功發送給: {receiver}")
            except Exception as e:
                print(f"[Mail] ❌ 發送給 {receiver} 失敗: {e}")
            
        server.quit()
        return True
    except Exception as e:
        print(f"[Mail] ❌ SMTP 連線或登入失敗: {e}")
        return False

# ================= 輔助功能: 生成圖表 URL =================
def get_quickchart_url(chart_config):
    """ 將 Chart.js 設定轉為 QuickChart 圖片 URL """
    base_url = "https://quickchart.io/chart?c="
    json_config = json.dumps(chart_config)
    encoded_config = urllib.parse.quote(json_config)
    return f"{base_url}{encoded_config}"

# ================= 核心功能 2: 生成並發送週報 =================
def scheduled_weekly_report(app):
    """
    排程任務：
    1. 計算上週數據
    2. 生成圖表 URL
    3. 渲染模板並發送郵件
    """
    with app.app_context():
        print("📅 [Job] 正在執行週報生成任務...")
        
        today = datetime.utcnow().date()
        # 統計過去 7 天 (包含今天)
        start_date = datetime.combine(today - timedelta(days=7), datetime.min.time())
        end_date = datetime.combine(today, datetime.max.time())

        try:
            # --- 1. 資料庫查詢 ---
            
            # A. 歷史總數據
            total_visits_all = AccessLog.query.count()
            total_ips_all = db.session.query(func.count(func.distinct(AccessLog.ip_address))).scalar() or 0

            # B. 本週數據 (使用 timestamp 欄位)
            week_logs = AccessLog.query.filter(AccessLog.timestamp.between(start_date, end_date)).all()
            week_visits = len(week_logs)
            week_unique_ips = len(set(log.ip_address for log in week_logs))
            
            # C. 本週每日流量 (折線圖)
            daily_counts = {}
            for i in range(8):
                day_str = (today - timedelta(days=7-i)).strftime('%Y-%m-%d')
                daily_counts[day_str] = 0
            
            for log in week_logs:
                day_key = log.timestamp.strftime('%Y-%m-%d')
                if day_key in daily_counts:
                    daily_counts[day_key] += 1
                
            line_labels = list(daily_counts.keys())
            line_data = list(daily_counts.values())

            # D. 本週熱門路徑 (Top 5)
            # 使用整合後的 helper 函式，自動排除 /api/ 與 /admin/
            sorted_paths = get_top_pages(limit=5, start_date=start_date, end_date=end_date)
            
            bar_labels = [p[0] for p in sorted_paths]
            bar_data = [p[1] for p in sorted_paths]

            # E. 圓餅圖 (國家分佈 Top 5)
            country_counts = {}
            for log in week_logs:
                c = log.country or 'Unknown'
                country_counts[c] = country_counts.get(c, 0) + 1
            sorted_countries = sorted(country_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            pie_labels = [c[0] for c in sorted_countries]
            pie_data = [c[1] for c in sorted_countries]

            # --- 2. 生成 QuickChart 圖表 ---
            
            line_chart_url = get_quickchart_url({
                "type": "line",
                "data": {
                    "labels": [d[5:] for d in line_labels],
                    "datasets": [{"label": "訪問數", "data": line_data, "borderColor": "#3498db", "fill": False}]
                }
            })

            pie_chart_url = get_quickchart_url({
                "type": "doughnut",
                "data": {
                    "labels": pie_labels,
                    "datasets": [{"data": pie_data, "backgroundColor": ["#e74c3c", "#3498db", "#f1c40f", "#2ecc71", "#9b59b6"]}]
                }
            })

            bar_chart_url = get_quickchart_url({
                "type": "bar",
                "data": {
                    "labels": bar_labels,
                    "datasets": [{"label": "點擊數", "data": bar_data, "backgroundColor": "#2c3e50"}]
                },
                "options": { "indexAxis": "y" }
            })

            # --- 3. 渲染與發送 ---
            template_data = {
                'start_date': start_date.strftime('%Y-%m-%d'),
                'end_date': end_date.strftime('%Y-%m-%d'),
                'total_visits_all': total_visits_all,
                'total_ips_all': total_ips_all,
                'week_visits': week_visits,
                'week_unique_ips': week_unique_ips,
                'top_paths': sorted_paths,
                'line_chart_url': line_chart_url,
                'pie_chart_url': pie_chart_url,
                'bar_chart_url': bar_chart_url
            }

            html_content = render_template('admin/mail_weekly.html', **template_data)
            
            # 找出所有管理員
            admins = Admin.query.all()
            recipients = [admin.email for admin in admins]
            
            if recipients:
                subject = f"YuCl 系統週報表 ({start_date.strftime('%m/%d')}-{end_date.strftime('%m/%d')})"
                if send_email(recipients, subject, html_content):
                    record_system_log('SUCCESS', 'Email', f'週報表已成功發送至 {len(recipients)} 位管理員')
            else:
                record_system_log('WARNING', 'Email', '週報表發送失敗：資料庫中無管理員帳號')

        except Exception as e:
            error_msg = f"週報生成失敗: {str(e)}"
            print(f"❌ {error_msg}")
            record_system_log('ERROR', 'Email', error_msg)
