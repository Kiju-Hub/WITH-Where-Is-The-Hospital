# [init_db.py] - 진료과목 데이터 추가 버전
import csv
import os
import pymysql
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
CSV_FILE = os.path.join(os.path.dirname(__file__), "data", "hospitals.csv")

def safe_float(val):
    try:
        if not val or val.strip() == "": return None
        return float(val)
    except: return None

def init_database():
    conn = pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD, db=DB_NAME,
        charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor
    )

    try:
        with conn.cursor() as cur:
            print("🗑️ 기존 데이터 삭제 중...")
            cur.execute("TRUNCATE TABLE hospitals;")
            
            print(f"📂 CSV 파일 읽기: {CSV_FILE}")
            data_list = []
            
            with open(CSV_FILE, encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    x = safe_float(r.get("좌표(X)"))
                    y = safe_float(r.get("좌표(Y)"))
                    if x is None or y is None: continue

                    # 🚨 여기를 본인 CSV 헤더에 맞게 수정하세요!
                    # 예: '진료과목코드명', '진료과목내용' 등
                    dept = r.get("진료과목코드명", "") 
                    if not dept: dept = ""

                    data_list.append((
                        r.get("암호화요양기호"),
                        r.get("요양기관명"),
                        dept,  # 진료과목
                        r.get("주소"),
                        r.get("전화번호"),
                        x, y
                    ))

            print(f"🚀 {len(data_list)}개 데이터 삽입 시작...")
            
            # departments 컬럼 추가된 쿼리
            sql = """
            INSERT INTO hospitals (ykiho, name, departments, addr, tel_no, x_pos, y_pos)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            
            batch_size = 1000
            for i in range(0, len(data_list), batch_size):
                batch = data_list[i:i + batch_size]
                cur.executemany(sql, batch)
                print(f"   -> {i + len(batch)} 완료")

            conn.commit()
            print("✅ 데이터 입력 완료!")

    except Exception as e:
        print(f"❌ 에러 발생: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    init_database()