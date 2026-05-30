import io
import os
import uuid
import threading
import logging
import re
import time
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, jsonify, send_from_directory, current_app
import yt_dlp
import static_ffmpeg

# 初始化 ffmpeg 路徑
static_ffmpeg.add_paths()

from core.database import db, YtdlTask, YtdlUsageLog, ManagedTool, record_tool_visit, record_tool_usage, record_system_log
from core.queue_manager import register_tool, global_process_queue, get_global_queue_position

ytdl_bp = Blueprint('ytdl_bp', __name__)
OUTPUT_DIR = 'Downloads'
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

def actual_download_worker(app, task_id):
    """
    統一的 YouTube 下載背景工作 (支援 MP3 及 MP4)
    """
    start_time = time.time()
    with app.app_context():
        task = YtdlTask.query.get(task_id)
        if not task:
            return

        try:
            temp_uuid = uuid.uuid4().hex
            temp_path = os.path.join(OUTPUT_DIR, temp_uuid)

            if task.download_type == 'mp3':
                ext = 'mp3' if 'mp3' in task.quality else 'flac'
                temp_file_path = temp_path + f".{ext}"
                
                # 取得音訊比特率 (如 320, 256, 192, 128)
                bitrate = '320'
                if '-' in task.quality:
                    parts = task.quality.split('-')
                    if len(parts) > 1:
                        bitrate = parts[1]

                ydl_opts = {
                    'format': 'bestaudio/best',
                    'outtmpl': temp_path + '.%(ext)s',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': ext,
                        'preferredquality': bitrate,
                    }],
                    'quiet': True,
                }
            else: # mp4
                ext = 'mp4'
                temp_file_path = temp_path + ".mp4"
                
                # 建立高度限制與格式字串
                height_map = {
                    '4k': 2160,
                    '2k': 1440,
                    '1080p': 1080,
                    '720p': 720,
                    '480p': 480,
                    '360p': 360
                }
                
                height_limit = ''
                requested_quality = task.quality.replace('mp4-', '')
                if requested_quality in height_map:
                    height_limit = f'[height<={height_map[requested_quality]}]'
                
                # 格式優先順序：最好影像(符合高度)+最好音訊 / 最好影像 / 最好
                # 移除嚴格的 [ext=mp4] 限制，因為 4K/1080p 往往只有 webm/vp9/av1
                fmt_str = f'bestvideo{height_limit}+bestaudio/best{height_limit}/best'
                
                ydl_opts = {
                    'format': fmt_str,
                    'outtmpl': temp_path + '.%(ext)s',
                    'merge_output_format': 'mp4',
                    'postprocessor_args': {
                        'ffmpeg': ['-c:a', 'aac']
                    },
                    'quiet': True,
                    'noplaylist': True,
                }
                
                # 為了確保輸出的副檔名正確，我們需要知道 ydl 最後會產生什麼
                temp_file_path = temp_path + ".mp4" 


            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(task.video_url, download=True)
                # 取得實際下載後的路徑 (yt-dlp 會處理好副檔名與合併)
                downloaded_file = ydl.prepare_filename(info)
                
                # 如果有進行合併，副檔名會是 merge_output_format 指定的
                if 'requested_formats' in info and ydl_opts.get('merge_output_format'):
                    ext = ydl_opts['merge_output_format']
                    downloaded_file = os.path.splitext(downloaded_file)[0] + "." + ext
                else:
                    ext = info.get('ext', ext)

                raw_title = task.file_name if task.file_name else info.get('title', 'video')
                base_name = re.sub(r'[\\/*?:"<>|#%&]', '_', raw_title)

            # 檔名衝突處理 (1), (2)...
            final_filename = f"{base_name}.{ext}"
            counter = 1
            while os.path.exists(os.path.join(OUTPUT_DIR, final_filename)):
                final_filename = f"{base_name}({counter}).{ext}"
                counter += 1

            if os.path.exists(downloaded_file):
                os.rename(downloaded_file, os.path.join(OUTPUT_DIR, final_filename))
            else:
                # 備援方案：如果 ydl.prepare_filename 不準確，嘗試尋找 temp_uuid 開頭的文件
                found = False
                for f in os.listdir(OUTPUT_DIR):
                    if f.startswith(temp_uuid):
                        actual_path = os.path.join(OUTPUT_DIR, f)
                        actual_ext = os.path.splitext(f)[1].replace('.', '')
                        ext = actual_ext
                        final_filename = f"{base_name}.{ext}"
                        # 重新檢查衝突
                        c2 = 1
                        while os.path.exists(os.path.join(OUTPUT_DIR, final_filename)):
                            final_filename = f"{base_name}({c2}).{ext}"
                            c2 += 1
                        os.rename(actual_path, os.path.join(OUTPUT_DIR, final_filename))
                        found = True
                        break
                if not found:
                    raise Exception("找不到下載的暫存檔案")

            duration = round(time.time() - start_time, 2)
            record_system_log('SUCCESS', 'ytdl', f'影片下載成功: {final_filename} ({task.download_type.upper()})', value=duration)

            db.session.add(YtdlUsageLog(action='convert_success'))
            task.status = 'finished'
            task.file_name = final_filename
            db.session.commit()

        except Exception as e:
            record_system_log('ERROR', 'ytdl', f'下載失敗: {str(e)}')
            logging.error(f"Download Error: {str(e)}", exc_info=True)
            if task:
                task.status = 'error'
            db.session.commit()
        finally:
            global_process_queue(app)

@ytdl_bp.route('/ytdl')
def ytdl_page():
    record_tool_visit('ytdl')
    db.session.add(YtdlUsageLog(action='browse'))
    db.session.commit()
    return render_template('tool/ytdl.html')

@ytdl_bp.route('/api/ytdl/convert', methods=['POST'])
def api_convert():
    url = request.form.get('video_url')
    user_filename = request.form.get('output_filename', '').strip()
    download_type = request.form.get('download_type', 'mp3')
    quality = request.form.get('quality', 'mp3-320')

    if not url:
        return jsonify({'status': 'error', 'message': '請輸入影片連結'}), 400

    tool = ManagedTool.query.filter_by(name='ytdl').first()
    if not tool:
        tool = ManagedTool(name='ytdl', url='/ytdl', blueprint='ytdl_bp', max_concurrent=1)
        db.session.add(tool)
        db.session.commit()

    record_tool_usage('ytdl')

    task_id = str(uuid.uuid4())
    new_task = YtdlTask(
        id=task_id,
        tool_id=tool.id,
        status='waiting',
        video_url=url,
        download_type=download_type,
        quality=quality,
        file_name=user_filename
    )
    db.session.add(new_task)
    db.session.add(YtdlUsageLog(action='convert_request'))
    db.session.commit()

    global_process_queue(current_app._get_current_object())
    return jsonify({'status': 'accepted', 'task_id': task_id})

@ytdl_bp.route('/api/ytdl/status/<task_id>')
def api_status(task_id):
    task = YtdlTask.query.get(task_id)
    if not task:
        return jsonify({'status': 'error', 'message': '任務已不存在'}), 404

    task.last_polled = datetime.utcnow()
    db.session.commit()

    queue_pos = 0
    if task.status == 'waiting':
        queue_pos = get_global_queue_position(task.created_at)

    from urllib.parse import quote
    result = {
        'status': task.status,
        'queue_position': queue_pos,
        'file': task.file_name,
        'download_url': f'/api/ytdl/download/{quote(task.file_name)}' if task.status == 'finished' else None
    }

    if task.status in ['finished', 'error']:
        db.session.delete(task)
        db.session.commit()

    return jsonify(result)

@ytdl_bp.route('/api/ytdl/download/<path:filename>')
def api_download(filename):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)

def cleanup_ytdl_tasks(app):
    """
    清除過期任務
    """
    with app.app_context():
        now = datetime.utcnow()
        timeout_threshold = now - timedelta(seconds=30)
        orphans = YtdlTask.query.filter(YtdlTask.last_polled < timeout_threshold).all()
        if orphans:
            for task in orphans:
                db.session.delete(task)
            db.session.commit()
            print(f"[Cleanup] ytdl 已移除 {len(orphans)} 個超時任務")

register_tool('ytdl', YtdlTask, actual_download_worker)
