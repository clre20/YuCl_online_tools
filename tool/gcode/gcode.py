import hashlib
import json
import base64
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify
from core.database import db, ManagedTool, record_tool_visit

gcode_bp = Blueprint("gcode", __name__)

# 設定與前端一致的參數
CURRENT_VERSION = "v0.14.1"
#這是一個只有你我知道的密鑰，用來混淆雜湊，讓別人無法猜出規律
SECRET_KEY = "YuCl_Gcode_Simulation_2025_Secure_Key" 

@gcode_bp.route("/gcode")
def manage_urls():
    tool = ManagedTool.query.filter_by(name='gcode').first()
    if not tool:
        tool = ManagedTool(name='gcode', url='/gcode', max_concurrent=1)
        db.session.add(tool)
        db.session.commit()
    
    record_tool_visit('gcode')
    # 不再傳遞 version 給前端，防止直接從原始碼看到變數
    return render_template("tool/gcode.html")

@gcode_bp.route("/gcode_verify_access", methods=["POST"])
def verify_access():
    try:
        # 1. 獲取加密的 payload
        req_data = request.get_json()
        encrypted_payload = req_data.get('payload')

        if not encrypted_payload:
            return jsonify({"success": False, "msg": "No payload"}), 400

        # 2. 解碼 Base64 (看起來像加密，其實只是編碼)
        try:
            decoded_bytes = base64.b64decode(encrypted_payload)
            decoded_str = decoded_bytes.decode('utf-8')
            data = json.loads(decoded_str)
        except:
            return jsonify({"success": False, "msg": "Invalid format"}), 400

        client_timestamp = str(data.get('ts')) # 取出前端的時間戳
        client_signature = data.get('sign')    # 取出前端的雜湊簽名

        # 3. 後端自行計算預期的簽名 (Hash)
        # 邏輯：sha256( 版本 + 月份 + 時間戳 + 密鑰 )
        current_month = datetime.now().strftime("%m")
        
        # 組合字串 (順序必須與前端完全一致)
        raw_string = f"{CURRENT_VERSION}{current_month}{client_timestamp}{SECRET_KEY}"
        
        # 進行 SHA-256 雜湊
        expected_signature = hashlib.sha256(raw_string.encode('utf-8')).hexdigest()

        # 4. 比對簽名 (不檢查時間是否過期，只檢查算出來的 Hash 對不對)
        if client_signature == expected_signature:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "msg": "Access Denied"}), 403

    except Exception as e:
        return jsonify({"success": False, "msg": str(e)}), 500