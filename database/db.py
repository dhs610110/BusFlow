#받은 데이터를 SQLite에 저장하는 파일

import sqlite3


DB_PATH = "data/busflow.db"


def create_tables():
    conn = sqlite3.connect(DB_PATH)

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS congestion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            opr_ymd TEXT NOT NULL,
            dow_nm TEXT,
            route_id TEXT NOT NULL,
            station_id TEXT NOT NULL,
            station_seq INTEGER,
            time_zone TEXT NOT NULL,
            congestion INTEGER NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def save_congestion(items):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for item in items:
        cursor.execute(
            """
            INSERT INTO congestion (
                opr_ymd,
                dow_nm,
                route_id,
                station_id,
                station_seq,
                time_zone,
                congestion
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["opr_ymd"],
                item["dow_nm"],
                item["rte_id"],
                item["sttn_id"],
                item["sttn_seq"],
                item["tzon"],
                item["cgst"],
            )
        )

    conn.commit()
    conn.close()

if __name__ == "__main__":
    create_tables()
    print("데이터베이스 테이블 생성 완료")

