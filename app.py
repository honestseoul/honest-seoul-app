import os, uuid, json, requests
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_file, abort
import sqlite3

app = Flask(__name__)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
DB_PATH = os.path.join(os.path.dirname(__file__), 'transactions.db')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

AGIT_WEBHOOK_URL = os.environ.get('AGIT_WEBHOOK_URL', '')


# ──────────────────────────────────────────────
# DB 초기화
# ──────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                store           TEXT    NOT NULL,
                date            TEXT    NOT NULL,
                customer_name   TEXT,
                order_number    TEXT,
                diamond_amount  INTEGER NOT NULL,
                setting_fee     INTEGER NOT NULL,
                total_amount    INTEGER NOT NULL,
                gem_lab         TEXT    DEFAULT 'IGI',
                grade           TEXT    NOT NULL,
                balance         TEXT    DEFAULT '-',
                igi_number      TEXT,
                igi_number2     TEXT,
                cert1_file      TEXT,
                cert2_file      TEXT,
                receipt_file    TEXT,
                order_file      TEXT,
                memo            TEXT,
                agit_posted     INTEGER DEFAULT 0,
                created_at      TEXT    DEFAULT (datetime('now', 'localtime'))
            )
        ''')
        conn.commit()


# ──────────────────────────────────────────────
# 파일 저장 유틸
# ──────────────────────────────────────────────
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf'}

def save_upload(file_obj):
    if not file_obj or not file_obj.filename:
        return None
    ext = file_obj.filename.rsplit('.', 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return None
    fname = f'{uuid.uuid4().hex}.{ext}'
    file_obj.save(os.path.join(UPLOAD_FOLDER, fname))
    return fname


# ──────────────────────────────────────────────
# 아지트 웹훅
# ──────────────────────────────────────────────
def post_to_agit(tx):
    if not AGIT_WEBHOOK_URL:
        return
    text = (
        f"📋 나석키 전환 요청 (자동 등록 #{tx['id']})\n\n"
        f"- 판매날짜: {tx['date']}\n"
        f"- 점포: {tx['store']}\n"
        f"- 고객명: {tx.get('customer_name') or '-'}\n"
        f"- 주문번호: {tx.get('order_number') or '-'}\n"
        f"- 거래금액: {int(tx['total_amount']):,}원\n"
        f"- 등급: {tx['grade']}"
    )
    try:
        requests.post(AGIT_WEBHOOK_URL, json={'text': text}, timeout=5)
    except Exception as e:
        print(f'[Agit webhook error] {e}')


# ──────────────────────────────────────────────
# 페이지 라우트
# ──────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('store.html')

@app.route('/store')
def store():
    return render_template('store.html')

@app.route('/manager')
def manager():
    return render_template('manager.html')

@app.route('/print')
def print_page():
    ids = request.args.get('ids', '')
    return render_template('print_pdf.html', ids=ids)


# ──────────────────────────────────────────────
# API: 거래 등록
# ──────────────────────────────────────────────
@app.route('/api/transactions', methods=['POST'])
def create_transaction():
    f = request.form

    diamond = int(f.get('diamond_amount', 0) or 0)
    setting = int(f.get('setting_fee', 0) or 0)
    total   = diamond + setting

    cert1   = save_upload(request.files.get('cert1'))
    cert2   = save_upload(request.files.get('cert2'))
    receipt = save_upload(request.files.get('receipt'))
    order   = save_upload(request.files.get('order_img'))

    with get_db() as conn:
        cur = conn.execute('''
            INSERT INTO transactions
              (store, date, customer_name, order_number,
               diamond_amount, setting_fee, total_amount,
               gem_lab, grade, balance,
               igi_number, igi_number2,
               cert1_file, cert2_file, receipt_file, order_file, memo)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''', (
            f.get('store'), f.get('date'),
            f.get('customer_name'), f.get('order_number'),
            diamond, setting, total,
            f.get('gem_lab', 'IGI'), f.get('grade'), f.get('balance', '-'),
            f.get('igi_number'), f.get('igi_number2'),
            cert1, cert2, receipt, order,
            f.get('memo', '')
        ))
        tx_id = cur.lastrowid
        conn.commit()

    tx = dict(get_db().execute('SELECT * FROM transactions WHERE id=?', (tx_id,)).fetchone())
    post_to_agit(tx)

    return jsonify({'success': True, 'id': tx_id})


# ──────────────────────────────────────────────
# API: 거래 목록
# ──────────────────────────────────────────────
@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    month = request.args.get('month', '')   # e.g. '2026-03'
    with get_db() as conn:
        if month:
            rows = conn.execute(
                "SELECT * FROM transactions WHERE date LIKE ? ORDER BY date DESC",
                (f'{month.replace(".", "-")}%',)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM transactions ORDER BY date DESC"
            ).fetchall()
    return jsonify([dict(r) for r in rows])


# ──────────────────────────────────────────────
# API: 거래 상세 (PDF 렌더링용)
# ──────────────────────────────────────────────
@app.route('/api/transactions/<int:tx_id>', methods=['GET'])
def get_transaction(tx_id):
    row = get_db().execute(
        'SELECT * FROM transactions WHERE id=?', (tx_id,)
    ).fetchone()
    if not row:
        abort(404)
    return jsonify(dict(row))


# ──────────────────────────────────────────────
# API: 거래 수정 (관리자용)
# ──────────────────────────────────────────────
@app.route('/api/transactions/<int:tx_id>', methods=['PATCH'])
def update_transaction(tx_id):
    data = request.get_json()
    allowed = ['store','date','customer_name','order_number',
               'diamond_amount','setting_fee','total_amount',
               'gem_lab','grade','balance','igi_number','igi_number2','memo']
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({'error': 'No valid fields'}), 400

    # 합계 자동 재계산
    if 'diamond_amount' in updates or 'setting_fee' in updates:
        row = get_db().execute('SELECT * FROM transactions WHERE id=?', (tx_id,)).fetchone()
        if row:
            d = int(updates.get('diamond_amount', row['diamond_amount']))
            s = int(updates.get('setting_fee',    row['setting_fee']))
            updates['total_amount'] = d + s

    set_clause = ', '.join(f'{k}=?' for k in updates)
    values     = list(updates.values()) + [tx_id]
    with get_db() as conn:
        conn.execute(f'UPDATE transactions SET {set_clause} WHERE id=?', values)
        conn.commit()
    return jsonify({'success': True})


# ──────────────────────────────────────────────
# 이미지 서빙
# ──────────────────────────────────────────────
@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    return send_file(os.path.join(UPLOAD_FOLDER, filename))


# ──────────────────────────────────────────────
# 실행
# ──────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

init_db()
