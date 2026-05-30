from flask import Blueprint, render_template

YUEYOU_bp = Blueprint('YUEYOU', __name__, template_folder='templates')


# 首頁路由
@YUEYOU_bp.route('/oneself')
def index():
    return render_template('yueyou/index.html')