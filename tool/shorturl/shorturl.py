# tool/shorturl/shorturl.py
import os
import requests
from flask import Blueprint, render_template, request, jsonify

shorturl_bp = Blueprint("shorturl", __name__)

EXTERNAL_API_URL = "https://url.yucl.qzz.io/api/link/create"

@shorturl_bp.route("/shorturl")
def shorturl_index():
    """ 短網址產生器主頁面 """
    return render_template("tool/shorturl.html")

@shorturl_bp.route("/api/link/create", methods=["POST"])
def create_link():
    """
    短連結建立 Proxy API：轉發請求至外部短網址服務 (支援 Sink API Bearer 驗證)
    """
    try:
        # 1. 取得前端傳入的參數
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "無效的 JSON 請求"}), 400

        # 2. 準備轉發給外部 API 的 Payload
        payload = {}
        if "url" in data:
            payload["url"] = data["url"]
        if "slug" in data:
            payload["slug"] = data["slug"]

        # 強制設定過期時間為 1 年 (即現在時間 + 31,536,000 秒)
        import time
        current_time = int(time.time())
        one_year_seconds = 365 * 24 * 60 * 60
        payload["expiration"] = current_time + one_year_seconds

        # 3. 取得 Cloudflare Sink 授權金鑰 (優先自環境變數載入)
        token = "@Smart96071031"

        # 4. 準備與轉發 Header
        headers = {"Content-Type": "application/json"}
        
        # 加入授權 Bearer Token (若環境中有配置)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif "Authorization" in request.headers:
            # 備份：若本機未配置環境變數，則轉發前端傳入的 Auth 標頭
            headers["Authorization"] = request.headers["Authorization"]

        # 轉發其他可能的標頭
        forward_headers = ["Cookie", "X-API-Key", "X-App-Id"]
        for header_name in forward_headers:
            if header_name in request.headers:
                headers[header_name] = request.headers[header_name]

        # 5. 發送請求至外部短網址 API
        response = requests.post(EXTERNAL_API_URL, json=payload, headers=headers, timeout=10)

        # 6. 解析回應
        try:
            response_json = response.json()
        except ValueError:
            return jsonify({
                "status": "error", 
                "message": f"外部服務回傳非 JSON 格式：{response.text[:200]}"
            }), 502

        return jsonify(response_json), response.status_code

    except requests.exceptions.Timeout:
        return jsonify({"status": "error", "message": "連線至外部短網址服務逾時，請稍後再試"}), 504
    except requests.exceptions.RequestException as re:
        return jsonify({"status": "error", "message": f"無法連線至外部服務: {str(re)}"}), 502
    except Exception as e:
        return jsonify({"status": "error", "message": f"伺服器內部錯誤: {str(e)}"}), 500
