from core.database import Announcement
from datetime import datetime

from flask import Blueprint, render_template, jsonify

indexweb_bp = Blueprint("indexweb", __name__)

# 首頁
@indexweb_bp.route('/')
def indexweb():
    return render_template('index.html')
# 服務條款
@indexweb_bp.route('/terms')
def terms():
    return render_template('terms.html')
# 隱私政策
@indexweb_bp.route('/privacy')
def privacy():
    return render_template('privacy.html')
# 統歷史記錄
@indexweb_bp.route('/history')
def history():
    return render_template('history.html')

# 獲取全站公告設定 (公開 API - 支援多重公告與過期)
@indexweb_bp.route('/api/sys/announcement', methods=['GET'])
def get_announcements():
    try:
        now = datetime.utcnow()
        active_announcements = Announcement.query.filter(
            Announcement.is_active == True,
            (Announcement.expires_at == None) | (Announcement.expires_at > now)
        ).order_by(Announcement.created_at.desc()).all()
        
        list_data = []
        for ann in active_announcements:
            list_data.append({
                "id": ann.id,
                "content": ann.content,
                "type": ann.type,
                "display_duration": ann.display_duration or 5
            })
            
        return jsonify({
            "status": "success",
            "announcements": list_data
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500