from flask import Blueprint, render_template, jsonify, render_template_string, request
import os
import json
import yaml
from werkzeug.utils import secure_filename
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.yml")
YUEYOU_bp = Blueprint(
    'YUEYOU', 
    __name__, 
    static_folder='static', 
    static_url_path='/static/yueyou', 
    template_folder='templates'
)

# --- 載入設定 ---
def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        return {}

config = load_config()
API_KEY = config.get("github", {}).get("key")

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def get_json_path():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(current_dir, 'static', 'data', 'portfolio-data.json')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@YUEYOU_bp.route('/oneself')
def home():
    json_path = get_json_path()
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            json_files = json.load(f)
    except Exception as e:
        json_files = []
    return render_template('yueyou/index.html', json_files=json_files)

@YUEYOU_bp.route('/api/portfolio', methods=['GET'])
def get_portfolio():
    json_path = get_json_path()
    try:
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return jsonify(data)
        return jsonify([])
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@YUEYOU_bp.route('/api/portfolio/update', methods=['POST'])
def update_portfolio():
    provided_key = request.headers.get('X-API-Key')
    if provided_key != API_KEY:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    
    try:
        new_data = request.json
        if not isinstance(new_data, list):
            return jsonify({"status": "error", "message": "Data must be a JSON array"}), 400
        
        json_path = get_json_path()
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(new_data, f, indent=4, ensure_ascii=False)
            
        return jsonify({"status": "success", "message": "Portfolio updated successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@YUEYOU_bp.route('/api/portfolio/upload_image', methods=['POST'])
def upload_image():
    provided_key = request.headers.get('X-API-Key')
    if provided_key != API_KEY:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
        
    if 'image' not in request.files:
        return jsonify({"status": "error", "message": "No file part"}), 400
        
    file = request.files['image']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"}), 400
        
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        current_dir = os.path.dirname(os.path.abspath(__file__))
        upload_folder = os.path.join(current_dir, 'static', 'picture')
        os.makedirs(upload_folder, exist_ok=True)
        
        file_path = os.path.join(upload_folder, filename)
        file.save(file_path)
        
        web_path = f"/static/yueyou/picture/{filename}"
        return jsonify({
            "status": "success", 
            "message": "Image uploaded successfully",
            "imageSrc": web_path
        })
    else:
        return jsonify({"status": "error", "message": "File type not allowed"}), 400
    

