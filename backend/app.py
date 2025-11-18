from flask import Flask, jsonify
import csv
import os

app = Flask(__name__)

# CSV 파일 경로 설정
CSV_PATH = os.path.join(os.path.dirname(__file__), "data", "hospitals.csv")

def load_hospitals():
    hospitals = []

    # CSV가 아직 없으면 빈 리스트 반환 (초기 단계 대비)
    if not os.path.isfile(CSV_PATH):
        return hospitals

    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            hospitals.append(row)

    return hospitals


@app.route("/")
def home():
    return "WITH Flask Server Running"


@app.route("/api/hospitals")
def get_hospitals():
    data = load_hospitals()
    return jsonify(data)


if __name__ == "__main__":
    app.run(debug=True)
