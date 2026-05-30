# github_stats.py
from flask import Blueprint, Response, request, render_template, jsonify
import requests
import json
import os
import base64
import yaml
from datetime import datetime
import random

# --- 1. 初始化與設定 ---
github_bp = Blueprint('github_bp', __name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "github_cache")
USERS_FILE = os.path.join(CACHE_DIR, "tracked_users.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.yml")

if not os.path.exists(CACHE_DIR): os.makedirs(CACHE_DIR)
if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, 'w', encoding='utf-8') as f: json.dump(["clre20"], f)

# --- 載入設定 ---
def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        return {}

config = load_config()
GH_TOKEN = config.get("github", {}).get("key")


# --- 2. 核心邏輯區 ---
def get_tracked_users():
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: return []

def save_tracked_user(username):
    users = get_tracked_users()
    if username not in users:
        users.append(username)
        with open(USERS_FILE, 'w', encoding='utf-8') as f: json.dump(users, f)

def fetch_single_user_data(username, app_logger=None):
    if not GH_TOKEN or "貼這裡" in GH_TOKEN:
        print("❌ Token Error")
        return False
    headers = {"Authorization": f"bearer {GH_TOKEN}"}
    try:
        query = """
        query($login: String!) {
          user(login: $login) {
            name
            followers { totalCount }
            repositories(first: 100, ownerAffiliations: OWNER, isFork: false) { totalCount }
            contributionsCollection { contributionCalendar { totalContributions } }
          }
        }
        """
        r = requests.post("https://api.github.com/graphql", json={"query": query, "variables": {"login": username}}, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if "errors" in data: return False
            user = data["data"]["user"]
            save_data = {
                "username": username,
                "name": user["name"] or username,
                "followers": user["followers"]["totalCount"],
                "repos": user["repositories"]["totalCount"],
                "contributions": user["contributionsCollection"]["contributionCalendar"]["totalContributions"],
                "skin_base64": "", 
                "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            with open(os.path.join(CACHE_DIR, f"{username}.json"), 'w', encoding='utf-8') as f: json.dump(save_data, f)
            return True
    except: pass
    return False

def update_github_data(app):
    with app.app_context():
        users = get_tracked_users()
        for username in users:
            fetch_single_user_data(username, app.logger)

# --- 3. 樣式設計工廠 ---

THEMES_CONFIG = {
    "default": {
        "ui_bg": "#0f0f12", "ui_text": "#e0e0e0", "ui_accent": "#7aa2f7", 
        "ui_panel": "rgba(255, 255, 255, 0.05)", "ui_border": "rgba(255, 255, 255, 0.1)", "ui_input": "rgba(0, 0, 0, 0.3)"
    },
    "depth": {
        "ui_bg": "#1a1b26", "ui_text": "#c0caf5", "ui_accent": "#bb9af7",
        "ui_panel": "rgba(0, 0, 0, 0.2)", "ui_border": "rgba(187, 154, 247, 0.2)", "ui_input": "rgba(0, 0, 0, 0.4)"
    },
    "terminal": {
        "ui_bg": "#000000", "ui_text": "#33ff00", "ui_accent": "#33ff00",
        "ui_panel": "rgba(51, 255, 0, 0.05)", "ui_border": "#33ff00", "ui_input": "#000000"
    },
    "pixel": {
        "ui_bg": "#2e211b", "ui_text": "#ffffff", "ui_accent": "#6dac36",
        "ui_panel": "rgba(0, 0, 0, 0.4)", "ui_border": "#5c4b43", "ui_input": "rgba(0, 0, 0, 0.6)"
    },
    "glass": {
        "ui_bg": "#e0e5ec", "ui_text": "#444444", "ui_accent": "#fd79a8",
        "ui_panel": "rgba(255, 255, 255, 0.4)", "ui_border": "rgba(255, 255, 255, 0.8)", "ui_input": "rgba(255, 255, 255, 0.6)"
    }
}

def _get_rank_info(score):
    if score > 3000: return "A++", "#ff0055" 
    if score > 2000: return "A+",  "#ff9900" 
    if score > 1200: return "A",   "#4caf50" 
    if score > 800:  return "B++", "#00bcd4" 
    if score > 500:  return "B+",  "#2196f3" 
    if score > 200:  return "B",   "#7986cb" 
    return "C", "#9e9e9e"

I18N = {
    "en": {"contribs": "CONTRIBS", "repos": "REPOS", "followers": "FOLLOWERS", "score": "Score", "player": "Player", "exp": "XP", "loading": "Loading..."},
    "zh": {"contribs": "貢獻", "repos": "倉庫", "followers": "粉絲", "score": "分數", "player": "玩家", "exp": "經驗", "loading": "載入中..."}
}

def _generate_svg(stats, style_name="default", lang="en", zoom=1.0):
    score = stats.get('contributions', 0)
    level, rank_color = _get_rank_info(score)
    name = stats['name']
    username = stats['username']
    
    txt = I18N.get(lang, I18N["en"])
    font_stack = "'Segoe UI', 'Microsoft JhengHei', 'PingFang TC', sans-serif"
    mono_stack = "'Courier New', 'Consolas', monospace"

    # 計算縮放後的尺寸
    base_w, base_h = 450, 160
    try:
        scale = float(zoom)
    except:
        scale = 1.0
    w = int(base_w * scale)
    h = int(base_h * scale)

    # 1. Classic (經典)
    if style_name == "default":
        return f"""
        <svg width="{w}" height="{h}" viewBox="0 0 450 160" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
            <style>
                @keyframes draw {{ to {{ stroke-dashoffset: 0; }} }}
                .bg {{ fill: #1a1b26; }}
                .card {{ fill: none; stroke: #414868; stroke-width: 2px; rx: 15px; }}
                .text {{ font-family: {font_stack}; fill: #c0caf5; }}
                .val {{ font-family: {font_stack}; font-weight: bold; fill: {rank_color}; font-size: 18px; }}
                .circle {{ fill: none; stroke: {rank_color}; stroke-width: 4px; stroke-dasharray: 251; stroke-dashoffset: 251; animation: draw 1.5s ease-out forwards; transform: rotate(-90deg); transform-origin: 390px 80px; stroke-linecap: round; }}
            </style>
            <rect width="450" height="160" class="bg" rx="15" />
            <rect x="2" y="2" width="446" height="156" class="card" />
            <text x="30" y="55" class="text" font-size="22" font-weight="bold">{name}</text>
            <text x="30" y="75" class="text" fill="#565f89" font-size="14">@{username}</text>
            <g transform="translate(30, 110)">
                <text x="0" y="0" class="text" font-size="12" fill="#565f89">{txt['contribs']}</text><text x="0" y="22" class="val">{stats['contributions']}</text>
                <text x="80" y="0" class="text" font-size="12" fill="#565f89">{txt['repos']}</text><text x="80" y="22" class="val">{stats['repos']}</text>
                <text x="150" y="0" class="text" font-size="12" fill="#565f89">{txt['followers']}</text><text x="150" y="22" class="val">{stats['followers']}</text>
            </g>
            <circle cx="390" cy="80" r="40" stroke="#2e3440" stroke-width="4" fill="none"/>
            <circle cx="390" cy="80" r="40" class="circle"/>
            <text x="390" y="90" text-anchor="middle" class="text" font-weight="900" font-size="32" fill="{rank_color}">{level}</text>
        </svg>
        """

    # 2. Depth (景深)
    elif style_name == "depth":
        return f"""
        <svg width="{w}" height="{h}" viewBox="0 0 450 160" xmlns="http://www.w3.org/2000/svg">
            <style>
                .bg {{ fill: #24283b; }}
                .big-letter {{ font-family: sans-serif; font-weight: 900; font-size: 150px; fill: {rank_color}; opacity: 0.15; }}
                .name {{ font-family: {font_stack}; font-size: 26px; font-weight: bold; fill: #c0caf5; }}
                .sub {{ font-family: {font_stack}; font-size: 14px; fill: #565f89; }}
                .lbl {{ font-family: {font_stack}; font-size: 10px; fill: #565f89; letter-spacing: 1px; font-weight: bold; }}
                .val {{ font-family: {font_stack}; font-size: 20px; font-weight: bold; fill: #7aa2f7; }}
                .rank-full {{ font-family: sans-serif; font-size: 32px; font-weight: 900; fill: {rank_color}; }}
                .line {{ stroke: #414868; stroke-width: 2; stroke-linecap: round; }}
            </style>
            <rect width="450" height="160" class="bg" rx="10"/>
            <text x="420" y="145" text-anchor="end" class="big-letter">{level[0]}</text>
            <text x="30" y="50" class="name">{name}</text>
            <text x="30" y="75" class="sub">@{username}</text>
            <text x="420" y="50" text-anchor="end" class="rank-full">{level}</text>
            <line x1="30" y1="95" x2="250" y2="95" class="line"/>
            <g transform="translate(30, 130)">
                <text x="0" y="-15" class="lbl">{txt['contribs']}</text><text x="0" y="5" class="val">{score}</text>
                <text x="110" y="-15" class="lbl">{txt['repos']}</text><text x="110" y="5" class="val">{stats['repos']}</text>
                <text x="180" y="-15" class="lbl">{txt['followers']}</text><text x="180" y="5" class="val">{stats['followers']}</text>
            </g>
        </svg>
        """

    # 3. Terminal (終端機)
    elif style_name == "terminal":
        bar_len = min(20, int(score / 3000 * 20))
        ascii_bar = "[" + "#" * bar_len + "." * (20 - bar_len) + "]"
        content_y_start = 50
        cmd_text = f"./stats --user={username}"
        char_count = len(cmd_text)
        cmd_width = char_count * 8.5
        
        return f"""
        <svg width="{w}" height="{h}" viewBox="0 0 450 160" xmlns="http://www.w3.org/2000/svg">
            <style>
                .term-bg {{ fill: #000000; }}
                .term-bar {{ fill: #333333; }}
                .term-text {{ font-family: {mono_stack}; fill: #33ff00; font-size: 13px; font-weight: bold; white-space: pre; }}
                .term-white {{ fill: #ffffff; }}
                .term-dim {{ fill: #777777; }}
                .typing-cmd {{ overflow: hidden; white-space: nowrap; width: 0; animation: typing 1.5s steps({char_count}, end) forwards; animation-delay: 0.2s; }}
                @keyframes typing {{ from {{ width: 0; }} to {{ width: {cmd_width}px; }} }}
                .fade-in {{ opacity: 0; animation: fadeIn 0.2s ease-out forwards; }}
                @keyframes fadeIn {{ to {{ opacity: 1; }} }}
                .cursor {{ animation: blink 1s infinite; }}
                @keyframes blink {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0; }} }}
            </style>
            <rect width="450" height="160" class="term-bg" rx="6" />
            <path d="M0 6 C0 3 3 0 6 0 L444 0 C447 0 450 3 450 6 L450 25 L0 25 Z" class="term-bar" />
            <circle cx="20" cy="12.5" r="5" fill="#ff5f56" />
            <circle cx="38" cy="12.5" r="5" fill="#ffbd2e" />
            <circle cx="56" cy="12.5" r="5" fill="#27c93f" />
            <text x="225" y="17" text-anchor="middle" font-family="sans-serif" font-size="10" fill="#999">bash</text>
            <g transform="translate(15, {content_y_start})">
                <text x="0" y="0" class="term-text">root@github:~# </text>
                <svg x="110" y="-15" width="{cmd_width+10}" height="20">
                    <text x="0" y="15" class="term-text term-white typing-cmd">{cmd_text}</text>
                </svg>
                <g class="fade-in" style="animation-delay: 1.3s;">
                    <text x="0" y="20" class="term-text term-dim">---------------------------------------</text>
                </g>
                <g class="fade-in" style="animation-delay: 1.4s;">
                    <text x="0" y="40" class="term-text">Name: <tspan class="term-white">{name}</tspan>   Rank: <tspan fill="{rank_color}">{level}</tspan></text>
                </g>
                <g class="fade-in" style="animation-delay: 1.5s;">
                    <text x="0" y="60" class="term-text">{txt['contribs']}: {score}   {txt['repos']}: {stats['repos']}</text>
                </g>
                <g class="fade-in" style="animation-delay: 1.6s;">
                    <text x="0" y="80" class="term-text">{txt['followers']}: {stats['followers']}   {txt['exp']}: {ascii_bar}</text>
                </g>
                <g class="fade-in" style="animation-delay: 1.7s;">
                    <text x="0" y="100" class="term-text">root@github:~# <tspan class="cursor" fill="#33ff00">_</tspan></text>
                </g>
            </g>
        </svg>
        """

    # 4. Pixel (像素)
    elif style_name == "pixel":
        xp_percent = min((score / 3000) * 100, 100)
        return f"""
        <svg width="{w}" height="{h}" viewBox="0 0 450 160" xmlns="http://www.w3.org/2000/svg">
            <style>
                .mc-text {{ font-family: {mono_stack}; fill: #ffffff; text-shadow: 2px 2px #000; }}
            </style>
            <rect width="450" height="160" fill="#3b302a" stroke="#000" stroke-width="4"/>
            <rect x="4" y="4" width="442" height="152" fill="none" stroke="#5c4b43" stroke-width="4"/>
            <text x="30" y="45" class="mc-text" font-size="24" font-weight="bold">{name}</text>
            <text x="30" y="70" class="mc-text" font-size="14" fill="#aaa">{txt['player']}: {username}</text>
            <rect x="30" y="85" width="120" height="30" fill="#000" fill-opacity="0.3"/>
            <text x="35" y="105" class="mc-text" font-size="14">{txt['score']}: {score}</text>
            <rect x="160" y="85" width="100" height="30" fill="#000" fill-opacity="0.3"/>
            <text x="165" y="105" class="mc-text" font-size="14">{txt['repos'].capitalize()}: {stats['repos']}</text>
            <text x="420" y="50" text-anchor="end" class="mc-text" font-size="32" fill="{rank_color}">{level}</text>
            <rect x="24" y="125" width="402" height="15" fill="#1a1a1a" stroke="#fff" stroke-width="2"/>
            <rect x="26" y="127" width="0" height="11" fill="#80ff00"><animate attributeName="width" from="0" to="{4 * xp_percent}" dur="1s" fill="freeze" calcMode="discrete"/></rect>
            <text x="225" y="136" text-anchor="middle" font-size="10" fill="#fff" font-family="{font_stack}">{txt['exp']}</text>
        </svg>
        """

    # 5. Glass (毛玻璃)
    elif style_name == "glass":
        return f"""
        <svg width="{w}" height="{h}" viewBox="0 0 450 160" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
            <defs>
                <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0%" stop-color="#e0e5ec"/>
                    <stop offset="100%" stop-color="#ffffff"/>
                </linearGradient>
            </defs>
            <style>
                .glass {{ fill: rgba(255,255,255,0.7); stroke: #fff; stroke-width: 1; }}
                .txt {{ font-family: {font_stack}; fill: #333; }}
                .val {{ font-family: {font_stack}; font-weight: bold; font-size: 20px; fill: #fd79a8; }}
            </style>
            <rect width="450" height="160" fill="url(#bg)" rx="15"/>
            <circle cx="50" cy="120" r="80" fill="#74b9ff" opacity="0.2"/>
            <circle cx="400" cy="30" r="60" fill="#fd79a8" opacity="0.2"/>
            <rect x="20" y="20" width="410" height="120" rx="15" class="glass" style="filter: drop-shadow(0 5px 15px rgba(0,0,0,0.1));"/>
            <text x="40" y="55" class="txt" font-size="22" font-weight="bold">{name}</text>
            <text x="40" y="75" class="txt" font-size="14" fill="#666">@{username}</text>
            <text x="390" y="60" text-anchor="end" class="txt" font-size="32" fill="{rank_color}" font-weight="bold">{level}</text>
            <line x1="40" y1="85" x2="390" y2="85" stroke="#ddd" stroke-width="1"/>
            <g transform="translate(40, 110)">
                <text x="0" y="-10" class="txt" font-size="10" fill="#888">{txt['contribs']}</text><text x="0" y="10" class="val">{score}</text>
                <text x="100" y="-10" class="txt" font-size="10" fill="#888">{txt['repos']}</text><text x="100" y="10" class="val">{stats['repos']}</text>
                <text x="200" y="-10" class="txt" font-size="10" fill="#888">{txt['followers']}</text><text x="200" y="10" class="val">{stats['followers']}</text>
            </g>
        </svg>
        """
    
    return _generate_svg(stats, "default", lang, zoom)

# --- 4. 路由與 UI ---
@github_bp.route('/github_stats')
def ui():
    return render_template('tool/github_stats.html', theme_config=THEMES_CONFIG)

@github_bp.route('/api/github_stats/sample')
def get_sample_card():
    style = request.args.get('style', 'default')
    lang = request.args.get('lang', 'en')
    zoom = request.args.get('zoom', 1.0)
    dummy_stats = {
        'name': 'Demo User', 'username': 'demo_user',
        'contributions': 2500, 'repos': 42, 'followers': 120,
        'skin_base64': '', 'last_updated': 'PREVIEW'
    }
    return Response(_generate_svg(dummy_stats, style, lang, zoom), mimetype='image/svg+xml', headers={'Cache-Control': 'public, max-age=86400'})

@github_bp.route('/api/github_stats/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    if not username: return jsonify({"success": False}), 400
    save_tracked_user(username)
    success = fetch_single_user_data(username)
    if success: return jsonify({"success": True})
    return jsonify({"success": False, "message": "Check Token"}), 404

@github_bp.route('/api/github_stats')
def get_card():
    username = request.args.get('username', 'clre20')
    style = request.args.get('style', 'default')
    lang = request.args.get('lang', 'en')
    zoom = request.args.get('zoom', 1.0)
    
    file_path = os.path.join(CACHE_DIR, f"{username}.json")
    def serve_svg_from_cache():
        try:
            with open(file_path, 'r', encoding='utf-8') as f: stats = json.load(f)
            return Response(_generate_svg(stats, style, lang, zoom), mimetype='image/svg+xml', headers={'Cache-Control': 'public, max-age=300'})
        except: return None
    if os.path.exists(file_path):
        resp = serve_svg_from_cache()
        if resp: return resp
    save_tracked_user(username)
    success = fetch_single_user_data(username)
    if success:
        resp = serve_svg_from_cache()
        if resp: return resp
    return Response(
        '<svg width="450" height="160" xmlns="http://www.w3.org/2000/svg"><rect width="450" height="160" fill="#1a1b26"/><text x="50%" y="50%" fill="#e0af68" text-anchor="middle">Loading...</text></svg>', 
        mimetype='image/svg+xml', headers={'Cache-Control': 'no-cache'}
    )