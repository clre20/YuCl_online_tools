
import os
import sqlite3

basedir = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))
db_path = os.path.join(basedir, 'database/yucl_adb_tools_data.db')

def migrate():
    if not os.path.exists(db_path):
        print(f"找不到資料庫檔案: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("正在重構 'access_log' 表格以匹配新系統模型...")
    
    # 1. 備份舊資料 (如果有的話，但目前是 0)
    # 2. 刪除舊表格
    cursor.execute("DROP TABLE IF EXISTS access_log")
    
    # 3. 建立符合新模型的表格
    # 模型：ip_address, country, path, timestamp, duration
    cursor.execute("""
        CREATE TABLE access_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address VARCHAR(45) NOT NULL,
            country VARCHAR(10),
            path VARCHAR(255) NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            duration FLOAT
        )
    """)
    
    print("正在確保 'system_log' 表格正確...")
    cursor.execute("DROP TABLE IF EXISTS system_log")
    cursor.execute("""
        CREATE TABLE system_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            level VARCHAR(20) DEFAULT 'INFO',
            module VARCHAR(50),
            message TEXT,
            value FLOAT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    print("資料庫重構完成！所有欄位已與新系統同步。")

if __name__ == "__main__":
    migrate()
