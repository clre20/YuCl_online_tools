# tool/tool.py
from tool.ytdl.ytdl import ytdl_bp, cleanup_ytdl_tasks
from tool.gcode.gcode import gcode_bp
from tool.qrcode.qrcode import qrcode_bp, cleanup_qrcode_tasks
from tool.uuidv4.uuidv4 import uuidv4_bp
from tool.imgedit.imgedit import imgedit_bp, cleanup_imgedit_tasks
from tool.github_stats.github_stats import github_bp
from tool.shorturl.shorturl import shorturl_bp

def register_tools(app):
    """
    將所有獨立的工具藍圖註冊到主要的 Flask app 中
    """
    app.register_blueprint(ytdl_bp)
    app.register_blueprint(gcode_bp)
    app.register_blueprint(qrcode_bp)
    app.register_blueprint(uuidv4_bp)
    app.register_blueprint(imgedit_bp)
    app.register_blueprint(github_bp)
    app.register_blueprint(shorturl_bp)
