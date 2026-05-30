from flask import Blueprint, render_template, jsonify
import uuid
from core.database import db, record_tool_visit

uuidv4_bp = Blueprint("uuidv4", __name__)

@uuidv4_bp.route('/generate_uuid/<int:t>', methods=['GET'])
def generate_multiple_uuids(t):
    """
    生成指定數量的 UUID 並回傳。
    """
    if t > 50: t = 50 # 限制單次產生數量
    uuids_list = [str(uuid.uuid4()) for _ in range(t)]
    return jsonify({"uuids": uuids_list})

@uuidv4_bp.route('/uuid')
def index():
    """
    UUID 產生器主頁面。
    """
    record_tool_visit('uuidv4')
    return render_template('tool/uuidv4.html')
