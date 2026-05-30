import os
import uuid
import time
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, jsonify, send_from_directory, current_app
from PIL import Image
import io

from core.database import db, ManagedTool, record_tool_visit, record_tool_usage, ImgeditTask, record_system_log
from core.queue_manager import register_tool, global_process_queue, get_global_queue_position

imgedit_bp = Blueprint('imgedit_bp', __name__)

# 使用與 ytdl 相同的 Downloads 目錄作為輸出
OUTPUT_DIR = 'Downloads'
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

@imgedit_bp.route('/imgedit')
def imgedit_page():
    record_tool_visit('imgedit')
    return render_template('tool/imgedit.html')

def actual_imgedit_worker(app, task_id):
    """
    非同步圖片編輯背景工作
    """
    start_time = time.time()
    with app.app_context():
        task = ImgeditTask.query.get(task_id)
        if not task:
            return

        try:
            input_filepath = os.path.join(OUTPUT_DIR, task.input_file_name)
            if not os.path.exists(input_filepath):
                raise FileNotFoundError("找不到上傳的原始圖片檔案")

            img = Image.open(input_filepath)
            orig_format = img.format if img.format else 'PNG'
            
            # 1. 尺寸調整
            width = task.width
            height = task.height
            keep_aspect = task.keep_aspect
            
            if width or height:
                orig_w, orig_h = img.size
                if keep_aspect:
                    if width and not height:
                        height = int(orig_h * (width / orig_w))
                    elif height and not width:
                        width = int(orig_w * (height / orig_h))
                    elif width and height:
                        ratio = min(width / orig_w, height / orig_h)
                        width = int(orig_w * ratio)
                        height = int(orig_h * ratio)
                
                width = width if width else orig_w
                height = height if height else orig_h
                img = img.resize((width, height), Image.Resampling.LANCZOS)

            # 2. 色彩平衡 (Photoshop 雙極色彩增益調整)
            cyan_red = task.cyan_red if task.cyan_red is not None else 0
            magenta_green = task.magenta_green if task.magenta_green is not None else 0
            yellow_blue = task.yellow_blue if task.yellow_blue is not None else 0
            
            if cyan_red != 0 or magenta_green != 0 or yellow_blue != 0:
                if img.mode not in ('RGB', 'RGBA'):
                    img = img.convert('RGBA' if 'transparency' in img.info or 'A' in img.mode else 'RGB')
                
                has_alpha = (img.mode == 'RGBA')
                if has_alpha:
                    r, g, b, a = img.split()
                else:
                    r, g, b = img.split()
                
                # Scale factor for smoother shifts (Photoshop-like feel)
                scale = 0.5
                cr_val = cyan_red * scale
                mg_val = magenta_green * scale
                yb_val = yellow_blue * scale
                
                r_shift = cr_val - mg_val - yb_val
                g_shift = -cr_val + mg_val - yb_val
                b_shift = -cr_val - mg_val + yb_val
                
                if r_shift != 0:
                    r = r.point(lambda i: min(255, max(0, int(i + r_shift))))
                if g_shift != 0:
                    g = g.point(lambda i: min(255, max(0, int(i + g_shift))))
                if b_shift != 0:
                    b = b.point(lambda i: min(255, max(0, int(i + b_shift))))
                
                if has_alpha:
                    img = Image.merge('RGBA', (r, g, b, a))
                else:
                    img = Image.merge('RGB', (r, g, b))

            # 3. 色彩微調 (亮度、對比、飽和度)
            from PIL import ImageEnhance
            brightness = task.brightness
            contrast = task.contrast
            saturation = task.saturation
            
            if brightness != 1.0:
                img = ImageEnhance.Brightness(img).enhance(brightness)
            if contrast != 1.0:
                img = ImageEnhance.Contrast(img).enhance(contrast)
            if saturation != 1.0:
                img = ImageEnhance.Color(img).enhance(saturation)

            # 4. 濾鏡處理
            filter_type = task.filter_type
            if filter_type != 'none':
                if filter_type == 'grayscale':
                    img = ImageEnhance.Color(img).enhance(0.0)
                elif filter_type == 'sepia':
                    if img.mode not in ('RGB', 'RGBA'):
                        img = img.convert('RGBA' if 'transparency' in img.info or 'A' in img.mode else 'RGB')
                    has_alpha = (img.mode == 'RGBA')
                    if has_alpha:
                        r, g, b, a = img.split()
                    else:
                        r, g, b = img.split()
                    matrix = (
                        0.393, 0.769, 0.189, 0,
                        0.349, 0.686, 0.168, 0,
                        0.272, 0.534, 0.131, 0
                    )
                    if has_alpha:
                        rgb_img = Image.merge('RGB', (r, g, b)).convert('RGB', matrix)
                        r2, g2, b2 = rgb_img.split()
                        img = Image.merge('RGBA', (r2, g2, b2, a))
                    else:
                        img = img.convert('RGB', matrix)
                elif filter_type == 'blur':
                    from PIL import ImageFilter
                    img = img.filter(ImageFilter.BLUR)
                elif filter_type == 'sharpen':
                    from PIL import ImageFilter
                    img = img.filter(ImageFilter.SHARPEN)
                elif filter_type == 'edge_enhance':
                    from PIL import ImageFilter
                    img = img.filter(ImageFilter.EDGE_ENHANCE)
                elif filter_type == 'contour':
                    from PIL import ImageFilter
                    img = img.filter(ImageFilter.CONTOUR)
                elif filter_type == 'invert':
                    from PIL import ImageOps
                    if img.mode == 'RGBA':
                        r, g, b, a = img.split()
                        rgb_img = Image.merge('RGB', (r, g, b))
                        inverted_rgb = ImageOps.invert(rgb_img)
                        r2, g2, b2 = inverted_rgb.split()
                        img = Image.merge('RGBA', (r2, g2, b2, a))
                    else:
                        if img.mode not in ('RGB', 'L'):
                            img = img.convert('RGB')
                        img = ImageOps.invert(img)

            # 5. 格式與輸出準備 (支援自訂格式轉換)
            target_format = task.output_format.lower() if task.output_format else 'original'
            
            if target_format == 'original':
                save_format = orig_format.upper()
                ext = orig_format.lower()
            else:
                save_format = target_format.upper()
                ext = target_format
                
            if save_format == 'JPG': 
                save_format = 'JPEG'
            
            if ext == 'jpg':
                ext = 'jpg'
            elif ext == 'jpeg':
                ext = 'jpg'
            
            if save_format in ['JPG', 'JPEG'] and img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
                
            filename = f"imgedit_{task.id}.{ext}"
            filepath = os.path.join(OUTPUT_DIR, filename)
            
            img.save(filepath, format=save_format)

            # Clean up original file to save space
            try:
                os.remove(input_filepath)
            except Exception as ex:
                pass

            duration = round(time.time() - start_time, 2)
            record_system_log('SUCCESS', 'imgedit', f'圖片處理成功: {filename}', value=duration)

            task.status = 'finished'
            task.file_name = filename
            db.session.commit()

        except Exception as e:
            record_system_log('ERROR', 'imgedit', f'圖片處理失敗: {str(e)}')
            task.status = 'error'
            db.session.commit()
        finally:
            global_process_queue(app)

@imgedit_bp.route('/api/imgedit/process', methods=['POST'])
def process_image():
    """
    建立排隊任務處理圖像
    """
    try:
        file = request.files.get('image')
        if not file:
            return jsonify({'status': 'error', 'message': '未上傳圖片'}), 400

        task_id = str(uuid.uuid4())
        
        orig_filename = file.filename
        ext = 'png'
        if '.' in orig_filename:
            ext = orig_filename.rsplit('.', 1)[1].lower()
        
        input_file_name = f"uploaded_{task_id}.{ext}"
        input_filepath = os.path.join(OUTPUT_DIR, input_file_name)
        file.save(input_filepath)

        # 尺寸調整參數
        width = request.form.get('width', type=int)
        height = request.form.get('height', type=int)
        keep_aspect = request.form.get('keep_aspect') == 'true'

        # 濾鏡與色彩微調參數
        filter_type = request.form.get('filter_type', 'none').lower()
        brightness = request.form.get('brightness', type=float, default=1.0)
        contrast = request.form.get('contrast', type=float, default=1.0)
        saturation = request.form.get('saturation', type=float, default=1.0)
        
        # 色彩平衡參數 (Photoshop 滑桿 -100 到 +100)
        cyan_red = request.form.get('cyan_red', type=int, default=0)
        magenta_green = request.form.get('magenta_green', type=int, default=0)
        yellow_blue = request.form.get('yellow_blue', type=int, default=0)

        # 輸出格式轉換參數
        output_format = request.form.get('output_format', 'original').lower()

        # Ensure tool is registered
        tool = ManagedTool.query.filter_by(name='imgedit').first()
        if not tool:
            tool = ManagedTool(name='imgedit', url='/imgedit', blueprint='imgedit_bp', max_concurrent=1)
            db.session.add(tool)
            db.session.commit()
            
        record_tool_usage('imgedit')

        new_task = ImgeditTask(
            id=task_id,
            tool_id=tool.id,
            status='waiting',
            width=width,
            height=height,
            keep_aspect=keep_aspect,
            filter_type=filter_type,
            brightness=brightness,
            contrast=contrast,
            saturation=saturation,
            cyan_red=cyan_red,
            magenta_green=magenta_green,
            yellow_blue=yellow_blue,
            output_format=output_format,
            input_file_name=input_file_name
        )
        db.session.add(new_task)
        db.session.commit()

        # Trigger queue
        global_process_queue(current_app._get_current_object())
        return jsonify({'status': 'accepted', 'task_id': task_id})

    except Exception as e:
        record_system_log('ERROR', 'imgedit', f'排隊圖片任務失敗: {str(e)}')
        return jsonify({'status': 'error', 'message': f'排隊失敗: {str(e)}'}), 500

@imgedit_bp.route('/api/imgedit/status/<task_id>')
def api_status(task_id):
    task = ImgeditTask.query.get(task_id)
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
        'download_url': f'/api/imgedit/download/{task.file_name}' if task.status == 'finished' else None
    }

    if task.status in ['finished', 'error']:
        db.session.delete(task)
        db.session.commit()

    return jsonify(result)

@imgedit_bp.route('/api/imgedit/download/<path:filename>')
def download_file(filename):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)

def cleanup_imgedit_tasks(app):
    """
    清理過期的暫存圖片編輯任務與遺留檔案
    """
    with app.app_context():
        now = datetime.utcnow()
        timeout_threshold = now - timedelta(seconds=30)
        orphans = ImgeditTask.query.filter(ImgeditTask.last_polled < timeout_threshold).all()
        
        if orphans:
            for task in orphans:
                if task.input_file_name:
                    in_p = os.path.join(OUTPUT_DIR, task.input_file_name)
                    if os.path.exists(in_p):
                        try: os.remove(in_p)
                        except: pass
                db.session.delete(task)
            db.session.commit()
            print(f"[Cleanup] imgedit 已移除 {len(orphans)} 個超時任務")

register_tool('imgedit', ImgeditTask, actual_imgedit_worker)
