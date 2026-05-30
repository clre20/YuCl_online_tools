from flask import Blueprint, render_template

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