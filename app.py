from flask import Flask, render_template, request, redirect, url_for, g, session, jsonify
import sqlite3
import os
import uuid
from datetime import datetime
from collections import defaultdict


app = Flask(__name__)
app.secret_key = "super_secret_key"
DATABASE = "database.db"

# -------------------------
# 資料庫連線
# -------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db:
        db.close()

# -------------------------
# 初始化資料庫
# -------------------------
def init_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row

    # 員工表
    db.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    # 電影表
    db.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            poster_url TEXT,
            total_seats INTEGER DEFAULT 100
        )
    """)

    # 場次表
    db.execute("""
        CREATE TABLE IF NOT EXISTS showtimes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            movie_id INTEGER NOT NULL,
            weekday TEXT NOT NULL,
            time TEXT NOT NULL,
            total_seats INTEGER DEFAULT 100,
            FOREIGN KEY (movie_id) REFERENCES movies(id)
        )
    """)

    # 訂票表
    db.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT UNIQUE,
            showtime_id INTEGER NOT NULL,
            customer_name TEXT NOT NULL,
            tickets INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (showtime_id) REFERENCES showtimes(id)
        )
    """)

    # 使用者表
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            full_name TEXT,
            phone TEXT
        )
    """)

    # ------------------------
    # 預設電影資料
    # ------------------------
    movies = db.execute("SELECT id, title FROM movies").fetchall()
    if len(movies) == 0:
        # 新增電影
        db.execute("INSERT INTO movies (title, poster_url, total_seats) VALUES (?, ?, ?)", ("多哥", "posters/多哥.png", 100))
        db.execute("INSERT INTO movies (title, poster_url, total_seats) VALUES (?, ?, ?)", ("天劫倒數", "posters/天劫倒數.png", 150))
        db.execute("INSERT INTO movies (title, poster_url, total_seats) VALUES (?, ?, ?)", ("氣象戰", "posters/氣象戰.png", 180))
        db.execute("INSERT INTO movies (title, poster_url, total_seats) VALUES (?, ?, ?)", ("塔羅牌", "posters/塔羅牌.png", 230))
        db.commit()
        # 重新抓電影 ID
        movies = db.execute("SELECT id, title FROM movies").fetchall()

    # ------------------------
    # 預設場次資料
    # ------------------------
    # 先查詢 showtimes 是否已經有資料
    showtimes_count = db.execute("SELECT COUNT(*) FROM showtimes").fetchone()[0]

    if showtimes_count == 0:
        # 假設 movies 已經查好，是 list[dict]
        
        # 電影 1：週二、週四、週日 19:00，座位 100
        for day in ["週二", "週四", "週日"]:
            db.execute(
                "INSERT INTO showtimes (movie_id, weekday, time, total_seats) VALUES (?, ?, ?, ?)",
                (movies[0]["id"], day, "19:00", 100)
            )

        # 電影 2：週二、週三、週五 21:00，座位 150
        for day in ["週二", "週三", "週五"]:
            db.execute(
                "INSERT INTO showtimes (movie_id, weekday, time, total_seats) VALUES (?, ?, ?, ?)",
                (movies[1]["id"], day, "21:00", 150)
            )

        # 電影 3：週一、週三、週六 12:00，座位 180
        for day in ["週一", "週三", "週六"]:
            db.execute(
                "INSERT INTO showtimes (movie_id, weekday, time, total_seats) VALUES (?, ?, ?, ?)",
                (movies[2]["id"], day, "12:00", 180)
            )

        # 電影 4：週一、週二、週四、週五 21:00，座位 230
        for day in ["週一", "週二", "週四", "週五"]:
            db.execute(
                "INSERT INTO showtimes (movie_id, weekday, time, total_seats) VALUES (?, ?, ?, ?)",
                (movies[3]["id"], day, "21:00", 230)
            )

        db.commit()
    # ------------------------
    # 預設使用者
    # ------------------------
    users_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if users_count == 0:
        db.execute("INSERT INTO users (username, password, full_name, phone) VALUES (?, ?, ?, ?)",
                   ("testuser", "1234", "測試用戶", "0912345678"))
        db.commit()
    # ------------------------
    # 預設員工
    # ------------------------
    employees_count = db.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
    if employees_count == 0:
        db.execute("INSERT INTO employees (username, password) VALUES (?, ?)", ("aa", "111"))

    db.commit()
    db.close()
# -------------------------
# 訂單號生成
# -------------------------
def generate_order_no():
    date_str = datetime.now().strftime("%Y%m%d")
    random_str = uuid.uuid4().hex[:6].upper()
    return f"ORD-{date_str}-{random_str}"

def generate_unique_order_no(db):
    while True:
        order_no = generate_order_no()
        exists = db.execute("SELECT 1 FROM bookings WHERE order_no = ?", (order_no,)).fetchone()
        if not exists:
            return order_no

# -------------------------
# Routes
# -------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password)).fetchone()
        if not user:
            return "帳號或密碼錯誤", 400
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["full_name"] = user["full_name"]
        return "", 200
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("movies"))

# -------------------------
# 首頁：電影列表
# -------------------------
@app.route("/")
def movies():
    db = get_db()

    # 取得所有電影
    movies = db.execute("SELECT * FROM movies").fetchall()
    movies = [dict(m) for m in movies]

    # 取得所有場次和剩餘座位
    showtimes = db.execute("""
        SELECT 
            s.id AS showtime_id,
            s.movie_id,
            s.time AS showtime,
            s.total_seats,
            IFNULL(SUM(b.tickets),0) AS booked_seats,
            (s.total_seats - IFNULL(SUM(b.tickets),0)) AS remaining_seats
        FROM showtimes s
        LEFT JOIN bookings b ON s.id = b.showtime_id
        GROUP BY s.id
    """).fetchall()
    showtimes = [dict(s) for s in showtimes]

    # 將場次依電影分組
    movie_showtimes_map = {}
    for st in showtimes:
        movie_id = st['movie_id']
        if movie_id not in movie_showtimes_map:
            movie_showtimes_map[movie_id] = []
        movie_showtimes_map[movie_id].append(st)

    # 每部電影加上總剩餘座位、首頁展示用的時間
    for movie in movies:
        m_id = movie['id']
        sts = movie_showtimes_map.get(m_id, [])
        movie['showtimes'] = sts                     # 方便訂票頁面用
        movie['total_remaining_seats'] = sum(st['remaining_seats'] for st in sts)
        movie['showtime'] = sts[0]['showtime'] if sts else '尚無場次'
        # 標記是否已售完
        movie['sold_out'] = (movie['total_remaining_seats'] == 0)


    return render_template(
        "movies.html",
        movies=movies,
        full_name=session.get("full_name"),
        username=session.get("username"),
        employee_id=session.get("employee_id")
    )

# -------------------------
# 訂票頁
# -------------------------

@app.route("/book/<int:movie_id>", methods=["GET", "POST"])
def book(movie_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    db = get_db()
    movie = db.execute("SELECT * FROM movies WHERE id=?", (movie_id,)).fetchone()
    if not movie:
        return "電影不存在", 404

    showtimes = db.execute("""
        SELECT 
            s.id AS showtime_id,
            s.weekday,
            s.time AS showtime,
            s.total_seats,
            COALESCE(SUM(b.tickets),0) AS booked_seats,
            s.total_seats - COALESCE(SUM(b.tickets),0) AS remaining_seats
        FROM showtimes s
        LEFT JOIN bookings b ON s.id = b.showtime_id
        WHERE s.movie_id=?
        GROUP BY s.id, s.weekday, s.time, s.total_seats
    """, (movie_id,)).fetchall()

    showtimes = [dict(s) for s in showtimes]

    # ✅ 依星期 + 時間排序
    weekday_order = {"一":1, "二":2, "三":3, "四":4, "五":5, "六":6, "日":7}
    showtimes.sort(key=lambda st: (weekday_order.get(st['weekday'], 8), st['showtime']))

    if request.method == "POST":
        selected_showtime_id = int(request.form.get("showtime_id"))
        tickets = int(request.form.get("tickets"))
        name = session.get("username")
        order_no = generate_unique_order_no(db)

        st = next((s for s in showtimes if s["showtime_id"] == selected_showtime_id), None)
        if not st:
            return "場次不存在", 404

        if tickets > st["remaining_seats"]:
            return f"剩餘座位不足，剩餘 {st['remaining_seats']} 席", 400

        db.execute("""
            INSERT INTO bookings (order_no, showtime_id, customer_name, tickets)
            VALUES (?, ?, ?, ?)
        """, (order_no, selected_showtime_id, name, tickets))
        db.commit()

        return redirect(url_for("success", order_no=order_no))

    return render_template(
        "book.html",
        movie=movie,
        showtimes=showtimes
    )




# -------------------------
# 註冊頁
# -------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        if full_name.isdigit() or len(full_name) == 0:
            return "姓名不能全為數字，請輸入正確姓名", 400
        if not phone.isdigit() or len(phone)<8 or len(phone)>15:
            return "電話格式錯誤", 400
        db = get_db()
        if db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone():
            return "帳號已存在", 400
        db.execute("INSERT INTO users (username, password, full_name, phone) VALUES (?, ?, ?, ?)",
                   (username, password, full_name, phone))
        db.commit()
        user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["full_name"] = user["full_name"]
        return redirect(url_for("movies"))
    return render_template("register.html")

# -------------------------
# 訂票成功頁
# -------------------------
@app.route("/success/<order_no>")
def success(order_no):
    return render_template("success.html", order_no=order_no)

# -------------------------
# 訂單查詢
# -------------------------

@app.route("/order", methods=["GET", "POST"])
def order():
    db = get_db()
    results = []
    searched = False

    # 未登入：透過訂單編號查詢
    if request.method == "POST" and not session.get("username"):
        order_no = request.form.get("order_no", "").strip()
        searched = True
        if order_no:
            results = db.execute("""
                SELECT o.order_no, o.customer_name, o.tickets, m.title, s.time AS showtime
                FROM bookings o
                JOIN showtimes s ON o.showtime_id = s.id
                JOIN movies m ON s.movie_id = m.id
                WHERE o.order_no = ?
            """, (order_no,)).fetchall()
            results = [dict(r) for r in results]

            # 計算星期
            for r in results:
                dt = datetime.strptime(r['showtime'], "%H:%M")
                r['weekday'] = ["一","二","三","四","五","六","日"][dt.weekday()]

    # 已登入：顯示該使用者所有訂單
    elif session.get("username"):
        user_name = session.get("username")
        results = db.execute("""
            SELECT o.order_no, o.customer_name, o.tickets, m.title, s.time AS showtime
            FROM bookings o
            JOIN showtimes s ON o.showtime_id = s.id
            JOIN movies m ON s.movie_id = m.id
            WHERE o.customer_name = ?
        """, (user_name,)).fetchall()
        results = [dict(r) for r in results]

        # 計算星期
        for r in results:
            dt = datetime.strptime(r['showtime'], "%H:%M")
            r['weekday'] = ["一","二","三","四","五","六","日"][dt.weekday()]

    return render_template("order.html", results=results, searched=searched)










# -------------------------
# 刪除訂單
# -------------------------
@app.route("/delete_order/<order_no>", methods=["POST"])
def delete_order(order_no):
    db = get_db()
    user_name = session.get("username")
    if user_name:
        cur = db.execute("DELETE FROM bookings WHERE order_no=? AND customer_name=?", (order_no, user_name))
    else:
        cur = db.execute("DELETE FROM bookings WHERE order_no=?", (order_no,))
    db.commit()
    if cur.rowcount == 0:
        return jsonify({"success": False, "message": "查無訂單"})
    return jsonify({"success": True})

# -------------------------
# 員工登入與電影管理
# -------------------------
@app.route("/employee_login", methods=["GET", "POST"])
def employee_login():
    error = None
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        db = get_db()
        employee = db.execute("SELECT * FROM employees WHERE username=? AND password=?", (username, password)).fetchone()
        if employee:
            session["employee_id"] = employee["id"]
            session["employee_username"] = employee["username"]
            return redirect(url_for("manage_movies"))
        else:
            error = "帳號或密碼錯誤"
    return render_template("employee_login.html", error=error)

@app.route("/manage_movies", methods=["GET", "POST"])
def manage_movies():
    if "employee_id" not in session:
        return redirect(url_for("employee_login"))
    db = get_db()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        poster_file = request.form.get("poster_url", "").strip()
        total_seats = request.form.get("total_seats", "").strip()
        poster_file = poster_file.split("/")[-1] if poster_file else ""
        poster_url = f"posters/{poster_file}" if poster_file else None
        try:
            total_seats = int(total_seats)
            if total_seats <= 0:
                total_seats = 250
        except ValueError:
            total_seats = 250
        if title:
            db.execute("INSERT INTO movies (title, poster_url, total_seats) VALUES (?, ?, ?)", (title, poster_url, total_seats))
            db.commit()
    movies = db.execute("SELECT * FROM movies").fetchall()
    return render_template("manage_movies.html", movies=movies, employee_name=session.get("employee_username"))

@app.route("/delete_movie/<int:movie_id>", methods=["POST"])
def delete_movie(movie_id):
    if "employee_id" not in session:
        return redirect(url_for("employee_login"))
    db = get_db()
    db.execute("DELETE FROM movies WHERE id=?", (movie_id,))
    db.commit()
    return redirect(url_for("manage_movies"))

# -------------------------
# 主程式
# -------------------------
if __name__ == "__main__":
    init_db()
    app.run(debug=True)