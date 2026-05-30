import io
import os
import uuid
import threading
import logging
import time
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, send_from_directory, jsonify, current_app

import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import (
    SquareModuleDrawer,
    GappedSquareModuleDrawer,
    CircleModuleDrawer,
    RoundedModuleDrawer,
    VerticalBarsDrawer,
    HorizontalBarsDrawer,
)
from qrcode.image.styles.colormasks import (
    SolidFillColorMask,
    RadialGradiantColorMask,
    SquareGradiantColorMask,
    HorizontalGradiantColorMask,
    VerticalGradiantColorMask,
)
from qrcode.constants import ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q, ERROR_CORRECT_H
from PIL import Image, ImageColor

from core.database import db, ManagedTool, record_tool_visit, record_tool_usage, QrCodeTask, record_system_log
from core.queue_manager import register_tool, global_process_queue, get_global_queue_position

# Max embedded image size (1MB)
MAX_IMAGE_SIZE = 1 * 1024 * 1024  # 1MB
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}
OUTPUT_DIR = 'Downloads'

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

qrcode_bp = Blueprint('qrcode_bp', __name__)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def actual_qrcode_worker(app, task_id):
    """
    非同步 QR Code 產生背景工作
    """
    start_time = time.time()
    with app.app_context():
        task = QrCodeTask.query.get(task_id)
        if not task:
            return

        try:
            # 1. 取得糾錯率對照
            error_correction_map = {
                "L": ERROR_CORRECT_L, "M": ERROR_CORRECT_M,
                "Q": ERROR_CORRECT_Q, "H": ERROR_CORRECT_H
            }
            error_correction = error_correction_map.get(task.error_correction, ERROR_CORRECT_L)
            
            # 如果有嵌入圖片，強制使用高糾錯率
            embed_image_path = None
            if task.embed_image_name:
                embed_image_path = os.path.join(OUTPUT_DIR, task.embed_image_name)
                if os.path.exists(embed_image_path):
                    error_correction = ERROR_CORRECT_H
            
            # 2. 初始化 QRCode 物件
            qr = qrcode.QRCode(
                version=task.version,
                error_correction=error_correction,
                box_size=task.box_size,
                border=4,
            )
            qr.add_data(task.qr_data)
            qr.make(fit=True)

            # 3. 處理顏色設定
            fill_color_tuple = ImageColor.getrgb(task.fill_color)
            back_color_tuple = ImageColor.getrgb(task.back_color)

            # 4. 生成圖像 (基本型或樣式化)
            if task.style_type == "styled":
                module_drawer_map = {
                    "square": SquareModuleDrawer(), "gapped": GappedSquareModuleDrawer(),
                    "circle": CircleModuleDrawer(), "rounded": RoundedModuleDrawer(),
                    "vertical": VerticalBarsDrawer(), "horizontal": HorizontalBarsDrawer(),
                }
                module_drawer_instance = module_drawer_map.get(task.module_drawer, SquareModuleDrawer())

                color_mask_instance = None
                if task.color_mask == "solid":
                    color_mask_instance = SolidFillColorMask(
                        back_color=back_color_tuple, front_color=fill_color_tuple
                    )
                elif task.color_mask == "radial_gradient":
                    center_color_tuple = ImageColor.getrgb(task.center_color)
                    edge_color_tuple = ImageColor.getrgb(task.edge_color)
                    color_mask_instance = RadialGradiantColorMask(
                        back_color=back_color_tuple,
                        center_color=center_color_tuple,
                        edge_color=edge_color_tuple
                    )
                elif task.color_mask == "square_gradient":
                    square_center_color_tuple = ImageColor.getrgb(task.edge_color)
                    color_mask_instance = SquareGradiantColorMask(
                        back_color=back_color_tuple,
                        center_color=square_center_color_tuple,
                        edge_color=fill_color_tuple
                    )
                elif task.color_mask == "horizontal_gradient":
                    left_color_tuple = ImageColor.getrgb(task.left_color)
                    right_color_tuple = ImageColor.getrgb(task.right_color)
                    color_mask_instance = HorizontalGradiantColorMask(
                        back_color=back_color_tuple,
                        left_color=left_color_tuple,
                        right_color=right_color_tuple
                    )
                elif task.color_mask == "vertical_gradient":
                    top_color_tuple = ImageColor.getrgb(task.top_color)
                    bottom_color_tuple = ImageColor.getrgb(task.bottom_color)
                    color_mask_instance = VerticalGradiantColorMask(
                        back_color=back_color_tuple,
                        top_color=top_color_tuple,
                        bottom_color=bottom_color_tuple
                    )
                else:
                    color_mask_instance = SolidFillColorMask(
                        back_color=back_color_tuple, front_color=fill_color_tuple
                    )

                img = qr.make_image(
                    image_factory=StyledPilImage,
                    module_drawer=module_drawer_instance,
                    color_mask=color_mask_instance,
                    embeded_image_path=embed_image_path
                )
            else:
                img = qr.make_image(fill_color=fill_color_tuple, back_color=back_color_tuple)

            # 5. 儲存成品檔案
            final_filename = f"qrcode_{task.id}.png"
            final_path = os.path.join(OUTPUT_DIR, final_filename)
            img.save(final_path, "PNG")

            # 6. 清理嵌入的暫存圖檔
            if embed_image_path and os.path.exists(embed_image_path):
                try:
                    os.remove(embed_image_path)
                except Exception as ex:
                    logging.warning(f"Failed to delete temp embed image: {ex}")

            # 7. 更新任務狀態
            duration = round(time.time() - start_time, 2)
            record_system_log('SUCCESS', 'qrcode', f'QR Code 產生成功: {final_filename}', value=duration)

            task.status = 'finished'
            task.file_name = final_filename
            db.session.commit()

        except Exception as e:
            record_system_log('ERROR', 'qrcode', f'QR Code 產生失敗: {str(e)}')
            logging.error(f"Generate QR Code Error: {str(e)}", exc_info=True)
            task.status = 'error'
            db.session.commit()
        finally:
            global_process_queue(app)

@qrcode_bp.route("/qrcode")
def show_qrcode_page():
    tool = ManagedTool.query.filter_by(name='qrcode').first()
    if not tool:
        tool = ManagedTool(name='qrcode', url='/qrcode', blueprint='qrcode_bp', max_concurrent=1)
        db.session.add(tool)
        db.session.commit()
    record_tool_visit('qrcode')
    return render_template("tool/qrcode.html")

@qrcode_bp.route("/generate_qrcode", methods=["POST"])
def generate_qrcode_route():
    task_id = str(uuid.uuid4())
    form_data = request.form

    # 1. 確保載入工具紀錄
    tool = ManagedTool.query.filter_by(name='qrcode').first()
    if not tool:
        tool = ManagedTool(name='qrcode', url='/qrcode', blueprint='qrcode_bp', max_concurrent=1)
        db.session.add(tool)
        db.session.commit()
    
    record_tool_usage('qrcode')

    try:
        # 2. 解析 QR Code 實際內容
        data_type = form_data.get("data_type", "text")
        qr_data_string = ""

        if data_type == "text":
            qr_data_string = form_data.get("data", "")
            if not qr_data_string:
                return jsonify({"error": "請輸入文字或網址。"}), 400
        elif data_type == "wifi":
            ssid = form_data.get("wifi_ssid", "")
            password = form_data.get("wifi_password", "")
            encryption = form_data.get("wifi_encryption", "WPA")
            hidden = "true" if form_data.get("wifi_hidden") else "false"
            if not ssid:
                return jsonify({"error": "請輸入 Wi-Fi SSID。"}), 400
            qr_data_string = f"WIFI:T:{encryption};S:{ssid};P:{password};H:{hidden};;"
        elif data_type == "email":
            to_email = form_data.get("email_to", "")
            subject = form_data.get("email_subject", "")
            body = form_data.get("email_body", "")
            if not to_email:
                return jsonify({"error": "請輸入收件人 Email。"}), 400
            qr_data_string = f"mailto:{to_email}?subject={subject}&body={body}"
        else:
            return jsonify({"error": "不支援的資料格式類型。"}), 400

        # 3. 取得樣式與基礎設定
        style_type = form_data.get("style_type", "basic")
        version = int(form_data.get("version", 5)) if style_type == "styled" else 5
        error_correction = form_data.get("error_correction", "L")
        box_size = int(form_data.get("box_size", 10))

        # 4. 取得並驗證顏色設定
        fill_color = form_data.get("fill_color", "black")
        back_color = form_data.get("back_color", "white")

        try:
            ImageColor.getrgb(fill_color)
            ImageColor.getrgb(back_color)
        except ValueError as e:
            return jsonify({"error": f"填充或背景顏色代碼無效: {e}"}), 400

        # 5. 取得樣式化參數
        module_drawer = form_data.get("module_drawer", "square")
        color_mask = form_data.get("color_mask", "solid")
        
        center_color = form_data.get("center_color", "#0000FF")
        edge_color = form_data.get("edge_color", "#ADD8E6")
        left_color = form_data.get("left_color", "#FF0000")
        right_color = form_data.get("right_color", "#FFFF00")
        top_color = form_data.get("top_color", "#008000")
        bottom_color = form_data.get("bottom_color", "#FFA500")

        # 驗證漸層顏色
        if style_type == "styled":
            try:
                if color_mask == "radial_gradient":
                    ImageColor.getrgb(center_color)
                    ImageColor.getrgb(edge_color)
                elif color_mask == "square_gradient":
                    ImageColor.getrgb(edge_color)
                elif color_mask == "horizontal_gradient":
                    ImageColor.getrgb(left_color)
                    ImageColor.getrgb(right_color)
                elif color_mask == "vertical_gradient":
                    ImageColor.getrgb(top_color)
                    ImageColor.getrgb(bottom_color)
            except ValueError as e:
                return jsonify({"error": f"漸層顏色代碼無效: {e}"}), 400

        # 6. 處理嵌入圖片
        embed_image_name = None
        embed_image_file = request.files.get("embed_image")
        if embed_image_file and embed_image_file.filename != '':
            if not allowed_file(embed_image_file.filename):
                return jsonify({"error": "不支援的圖片格式！只支援 png, jpg, gif, bmp"}), 400
            
            image_data = embed_image_file.read()
            embed_image_file.seek(0)
            if len(image_data) > MAX_IMAGE_SIZE:
                return jsonify({"error": "上傳的嵌入圖片大小不得超過 1MB"}), 400
            
            ext = embed_image_file.filename.rsplit('.', 1)[1].lower()
            embed_image_name = f"embed_{task_id}.{ext}"
            temp_path = os.path.join(OUTPUT_DIR, embed_image_name)
            with open(temp_path, "wb") as f:
                f.write(image_data)

        # 7. 建立非同步任務紀錄
        new_task = QrCodeTask(
            id=task_id,
            tool_id=tool.id,
            status='waiting',
            data_type=data_type,
            qr_data=qr_data_string,
            style_type=style_type,
            version=version,
            error_correction=error_correction,
            box_size=box_size,
            fill_color=fill_color,
            back_color=back_color,
            module_drawer=module_drawer,
            color_mask=color_mask,
            center_color=center_color,
            edge_color=edge_color,
            left_color=left_color,
            right_color=right_color,
            top_color=top_color,
            bottom_color=bottom_color,
            embed_image_name=embed_image_name
        )

        db.session.add(new_task)
        db.session.commit()

        # 8. 觸發中央排隊系統
        global_process_queue(current_app._get_current_object())
        return jsonify({'status': 'accepted', 'task_id': task_id})

    except Exception as e:
        logging.error(f"Failed to queue QR Code generation: {e}", exc_info=True)
        return jsonify({"error": f"提交任務時發生未預期的錯誤: {str(e)}"}), 500

@qrcode_bp.route('/api/qrcode/status/<task_id>')
def api_status(task_id):
    task = QrCodeTask.query.get(task_id)
    if not task:
        return jsonify({'status': 'error', 'message': '任務已不存在'}), 404

    task.last_polled = datetime.utcnow()
    db.session.commit()

    queue_pos = 0
    if task.status == 'waiting':
        queue_pos = get_global_queue_position(task.created_at)

    result = {
        'status': task.status,
        'queue_position': queue_pos,
        'file': task.file_name,
        'download_url': f'/api/qrcode/download/{task.file_name}' if task.status == 'finished' else None
    }

    # 讀取結束後將其刪除以節省資料庫空間
    if task.status in ['finished', 'error']:
        db.session.delete(task)
        db.session.commit()

    return jsonify(result)

@qrcode_bp.route('/api/qrcode/download/<path:filename>')
def api_download(filename):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)

def cleanup_qrcode_tasks(app):
    """
    清理過期的暫存排隊任務
    """
    with app.app_context():
        now = datetime.utcnow()
        timeout_threshold = now - timedelta(seconds=30)
        orphans = QrCodeTask.query.filter(QrCodeTask.last_polled < timeout_threshold).all()
        
        if orphans:
            for task in orphans:
                # 刪除暫存嵌入圖片與成品
                if task.embed_image_name:
                    temp_p = os.path.join(OUTPUT_DIR, task.embed_image_name)
                    if os.path.exists(temp_p):
                        try: os.remove(temp_p)
                        except: pass
                db.session.delete(task)
            db.session.commit()
            print(f"[Cleanup] qrcode 已移除 {len(orphans)} 個超時任務")

register_tool('qrcode', QrCodeTask, actual_qrcode_worker)