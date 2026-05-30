
import sqlite3
import os

basedir = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))
db_path = os.path.join(basedir, 'database/yucl_adb_tools_data.db')

def fix_database():
    if not os.path.exists(db_path):
        print(f"資料庫檔案不存在，app.py 啟動時會自動建立。")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("--- 資料庫修復程序開始 ---")

    # 1. 為 managed_tool 補上 is_active 欄位
    try:
        cursor.execute("ALTER TABLE managed_tool ADD COLUMN is_active BOOLEAN DEFAULT 1")
        print("[V] 已成功為 managed_tool 新增 is_active 欄位")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("[!] is_active 欄位已存在，跳過")
        else:
            print(f"[X] 新增 is_active 失敗: {e}")

    # 2. 建立 server_metric 表格
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS server_metric (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cpu_usage FLOAT,
                ram_usage FLOAT,
                disk_usage FLOAT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("[V] 已確保 server_metric 表格存在")
    except Exception as e:
        print(f"[X] 建立 server_metric 失敗: {e}")

    # 3. 建立 system_config 表格
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key VARCHAR(50) UNIQUE NOT NULL,
                value VARCHAR(255),
                description VARCHAR(255)
            )
        """)
        print("[V] 已確保 system_config 表格存在")
    except Exception as e:
        print(f"[X] 建立 system_config 失敗: {e}")

    conn.commit()
    conn.close()
    print("--- 資料庫修復完成，現在請重新啟動 app.py ---")

if __name__ == "__main__":
    fix_database()
