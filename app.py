import os, uuid, json, re, requests
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, send_file, abort, session, redirect, url_for
import sqlite3

app = Flask(__name__)

DATA_DIR      = os.environ.get('DATA_DIR', os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(DATA_DIR, 'uploads')
DB_PATH       = os.path.join(DATA_DIR, 'transactions.db')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.secret_key                  = os.environ.get('SECRET_KEY', 'honest-seoul-secret-2026')
app.permanent_session_lifetime  = timedelta(hours=6)
MANAGER_PASSWORD                = os.environ.get('MANAGER_PASSWORD', 'honestseoul1')
AGIT_WEBHOOK_URL     = os.environ.get('AGIT_WEBHOOK_URL', '')
CLOVA_OCR_URL        = os.environ.get('CLOVA_OCR_URL', '')
CLOVA_OCR_SECRET     = os.environ.get('CLOVA_OCR_SECRET', '')


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
                grade2          TEXT,
                prepay          TEXT    DEFAULT '-',
                balance         TEXT    DEFAULT '-',
                igi_number      TEXT,
                igi_number2     TEXT,
                cert1_file      TEXT,
                cert2_file      TEXT,
                receipt_file    TEXT,
                order_file      TEXT,
                memo            TEXT,
                agit_posted     INTEGER DEFAULT 0,
                created_at      TEXT    DEFAULT (datetime('now', 'localtime')),
                deleted_at      TEXT    DEFAULT NULL
            )
        ''')
        # 기존 테이블에 deleted_at 컬럼 마이그레이션
        try:
            conn.execute('ALTER TABLE transactions ADD COLUMN deleted_at TEXT DEFAULT NULL')
        except Exception:
            pass
        conn.commit()


def cleanup_trash():
    """3일 지난 휴지통 항목 영구 삭제"""
    with get_db() as conn:
        conn.execute("""
            DELETE FROM transactions
            WHERE deleted_at IS NOT NULL
            AND datetime(deleted_at) < datetime('now', '-3 days', 'localtime')
        """)
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
        f"- 등급①: {tx['grade']}"
        + (f"\n- 등급②: {tx['grade2']}" if tx.get('grade2') else "")
        + f"\n\n👉 관리자 페이지: https://honest-seoul-app.onrender.com/manager"
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

@app.route('/manager-login', methods=['GET', 'POST'])
def manager_login():
    error = False
    if request.method == 'POST':
        if request.form.get('password') == MANAGER_PASSWORD:
            session.permanent = True
            session['manager_auth'] = True
            return redirect(url_for('manager'))
        error = True
    return render_template('manager_login.html', error=error)

@app.route('/manager-logout')
def manager_logout():
    session.pop('manager_auth', None)
    return redirect(url_for('manager_login'))

@app.route('/manager')
def manager():
    if not session.get('manager_auth'):
        return redirect(url_for('manager_login'))
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
               gem_lab, grade, grade2, prepay, balance,
               igi_number, igi_number2,
               cert1_file, cert2_file, receipt_file, order_file, memo)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''', (
            f.get('store'), f.get('date'),
            f.get('customer_name'), f.get('order_number'),
            diamond, setting, total,
            f.get('gem_lab', 'IGI'), f.get('grade'), f.get('grade2', ''),
            f.get('prepay', '-'), f.get('balance', '-'),
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
    cleanup_trash()
    month = request.args.get('month', '')   # e.g. '2026-03'
    with get_db() as conn:
        if month:
            rows = conn.execute(
                "SELECT * FROM transactions WHERE deleted_at IS NULL AND date LIKE ? ORDER BY date DESC",
                (f'{month.replace("-", ".")}%',)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM transactions WHERE deleted_at IS NULL ORDER BY date DESC"
            ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/transactions/<int:tx_id>', methods=['DELETE'])
def delete_transaction(tx_id):
    """소프트 삭제 — 휴지통으로 이동"""
    with get_db() as conn:
        conn.execute(
            "UPDATE transactions SET deleted_at = datetime('now', 'localtime') WHERE id = ?",
            (tx_id,)
        )
        conn.commit()
    return jsonify({'success': True})


@app.route('/api/trash', methods=['GET'])
def get_trash():
    cleanup_trash()
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM transactions WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC"
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/trash/<int:tx_id>/restore', methods=['POST'])
def restore_transaction(tx_id):
    with get_db() as conn:
        conn.execute(
            "UPDATE transactions SET deleted_at = NULL WHERE id = ?",
            (tx_id,)
        )
        conn.commit()
    return jsonify({'success': True})


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
@app.route('/api/transactions/<int:tx_id>/images', methods=['POST'])
def upload_image(tx_id):
    """수정 모달에서 이미지 교체 업로드"""
    field_map = {
        'cert1':     'cert1_file',
        'cert2':     'cert2_file',
        'receipt':   'receipt_file',
        'order_img': 'order_file',
    }
    uploaded = {}
    for key, col in field_map.items():
        f = request.files.get(key)
        if f and f.filename:
            # 기존 파일 삭제
            row = get_db().execute(f'SELECT {col} FROM transactions WHERE id=?', (tx_id,)).fetchone()
            if row and row[0]:
                old_path = os.path.join(UPLOAD_FOLDER, row[0])
                if os.path.exists(old_path):
                    os.remove(old_path)
            fname = save_upload(f)
            if fname:
                with get_db() as conn:
                    conn.execute(f'UPDATE transactions SET {col}=? WHERE id=?', (fname, tx_id))
                    conn.commit()
                uploaded[key] = fname
    if uploaded:
        return jsonify({'success': True, 'uploaded': uploaded})
    return jsonify({'error': '업로드된 파일 없음'}), 400


@app.route('/api/transactions/<int:tx_id>/images/<field>', methods=['DELETE'])
def delete_image(tx_id, field):
    """수정 모달에서 이미지 삭제"""
    field_map = {
        'cert1':     'cert1_file',
        'cert2':     'cert2_file',
        'receipt':   'receipt_file',
        'order_img': 'order_file',
    }
    col = field_map.get(field)
    if not col:
        return jsonify({'error': '잘못된 필드'}), 400
    row = get_db().execute(f'SELECT {col} FROM transactions WHERE id=?', (tx_id,)).fetchone()
    if row and row[0]:
        old_path = os.path.join(UPLOAD_FOLDER, row[0])
        if os.path.exists(old_path):
            os.remove(old_path)
    with get_db() as conn:
        conn.execute(f'UPDATE transactions SET {col}=NULL WHERE id=?', (tx_id,))
        conn.commit()
    return jsonify({'success': True})


@app.route('/api/transactions/<int:tx_id>', methods=['PATCH'])
def update_transaction(tx_id):
    data = request.get_json()
    allowed = ['store','date','customer_name','order_number',
               'diamond_amount','setting_fee','total_amount',
               'gem_lab','grade','grade2','prepay','balance',
               'igi_number','igi_number2','memo']
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
# Clova OCR
# ──────────────────────────────────────────────
@app.route('/api/ocr', methods=['POST'])
def ocr_image():
    if not CLOVA_OCR_URL or not CLOVA_OCR_SECRET:
        return jsonify({'error': 'OCR이 설정되지 않았습니다.'}), 503

    file     = request.files.get('image')
    img_type = request.form.get('type', 'cert1')  # cert1 | cert2 | order

    if not file:
        return jsonify({'error': '이미지가 없습니다.'}), 400

    ext       = file.filename.rsplit('.', 1)[-1].lower()
    fmt_map   = {'jpg':'jpg','jpeg':'jpg','png':'png','gif':'gif','webp':'webp'}
    img_fmt   = fmt_map.get(ext, 'jpg')

    message = {
        "version": "V2",
        "requestId": str(uuid.uuid4()),
        "timestamp": int(datetime.now().timestamp() * 1000),
        "lang": "ko",
        "images": [{"format": img_fmt, "name": "image"}],
        "enableTableDetection": False
    }

    try:
        resp = requests.post(
            CLOVA_OCR_URL,
            headers={'X-OCR-SECRET': CLOVA_OCR_SECRET},
            files={'file': (file.filename, file.stream, file.content_type)},
            data={'message': json.dumps(message)},
            timeout=15
        )
        result = resp.json()
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    try:
        fields    = result['images'][0]['fields']
        lines     = [f['inferText'] for f in fields]
        full_text = ' '.join(lines)
    except Exception:
        return jsonify({'error': 'OCR 응답 파싱 실패'}), 500

    extracted = {}

    if img_type in ('cert1', 'cert2'):
        # IGI 번호 (9자리 숫자)
        m = re.search(r'\b(\d{9})\b', full_text)
        if m:
            extracted['igi_number'] = m.group(1)

        # 등급: 캐럿 + 컬러 + 투명도 + 컷
        carat_m = re.search(r'([\d.]+)\s*(?:ct|CT|carat|CARAT)', full_text)
        color_m = re.search(r'\b([DEFGHIJ])\b', full_text)
        clar_m  = re.search(r'\b(FL|IF|VVS1|VVS2|VS1|VS2|SI1|SI2)\b', full_text, re.I)
        cut_m   = re.search(r'\b(EXCELLENT|VERY GOOD|IDEAL)\b', full_text, re.I)

        if carat_m:
            grade = carat_m.group(1) + 'ct'
            if color_m: grade += ' ' + color_m.group(1)
            if clar_m:  grade += ' ' + clar_m.group(1).upper()
            if cut_m:   grade += ' ' + cut_m.group(1).upper()
            extracted['grade'] = grade.strip()

    elif img_type == 'order':
        # 판매날짜
        date_m = re.search(r'(\d{4})[.\-\/](\d{1,2})[.\-\/](\d{1,2})', full_text)
        if date_m:
            y, m, d = date_m.group(1), date_m.group(2).zfill(2), date_m.group(3).zfill(2)
            extracted['date'] = f'{y}.{m}.{d}'

        # 고객명
        for i, line in enumerate(lines):
            if re.search(r'고객명|고객|성함|구매자', line):
                nm = re.sub(r'고객명|고객|성함|구매자|[:：\s]', '', line)
                nm_m = re.search(r'[가-힣]{2,5}', nm)
                if nm_m:
                    extracted['customer_name'] = nm_m.group(); break
                if i + 1 < len(lines):
                    nm2 = re.match(r'^[가-힣]{2,5}$', lines[i+1])
                    if nm2:
                        extracted['customer_name'] = nm2.group(); break

        # 주문번호
        order_m = re.search(r'\d{8}[-]\d{4,}', full_text)
        if order_m:
            extracted['order_number'] = order_m.group()

    return jsonify({'success': True, 'extracted': extracted})


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
