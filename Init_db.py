import csv
import os
import pymysql
from dotenv import load_dotenv

# 1. 환경 변수 로드
load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
CSV_FILE = os.path.join(os.path.dirname(__file__), "data", "hospitals.csv")

def safe_float(val):
    """빈 문자열이나 에러 발생 시 None 반환"""
    try:
        if not val or val.strip() == "":
            return None
        return float(val)
    except:
        return None

def init_database():
    print("🔄 데이터베이스 연결 중...")
    conn = pymysql.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        db=DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
    )

    try:
        with conn.cursor() as cur:
            # 2. 기존 데이터 싹 비우기 (중복 방지)
            print("🗑️ 기존 데이터 삭제 중 (TRUNCATE)...")
            cur.execute("TRUNCATE TABLE hospitals;")
            
            # 3. CSV 파일 열기
            print(f"📂 CSV 파일 읽기: {CSV_FILE}")
            data_list = []
            
            with open(CSV_FILE, encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                
                for r in reader:
                    # 좌표가 없는 데이터는 DB에 넣어도 쓸모 없으므로 건너뜀 (선택사항)
                    x = safe_float(r.get("좌표(X)"))
                    y = safe_float(r.get("좌표(Y)"))
                    
                    if x is None or y is None:
                        continue

                    # 4. DB 컬럼에 맞게 데이터 매핑
                    # (ykiho, name, addr, tel_no, x_pos, y_pos)
                    data_list.append((
                        r.get("암호화요양기호"),
                        r.get("요양기관명"),
                        r.get("주소"),
                        r.get("전화번호"),
                        x, # 경도 (Longitude)
                        y  # 위도 (Latitude)
                    ))

            # 5. 대량 데이터 한방에 넣기 (속도 최적화)
            print(f"🚀 {len(data_list)}개 데이터 삽입 시작...")
            
            # 쿼리는 본인의 테이블 컬럼에 맞춰야 함.
            # 여기서는 핵심 컬럼만 넣습니다. (나머지는 NULL로 들어감)
            sql = """
            INSERT INTO hospitals (ykiho, name, addr, tel_no, x_pos, y_pos)
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            
            # 1000개씩 끊어서 넣기 (메모리 보호)
            batch_size = 1000
            for i in range(0, len(data_list), batch_size):
                batch = data_list[i:i + batch_size]
                cur.executemany(sql, batch)
                print(f"   -> {i + len(batch)} / {len(data_list)} 완료")

            conn.commit()
            print("✅ 데이터 입력 완료!")

    except Exception as e:
        print(f"❌ 에러 발생: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    init_database()