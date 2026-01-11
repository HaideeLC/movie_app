from flask import Flask, render_template, request, redirect, url_for, g, session
from werkzeug.security import check_password_hash

import os



import sqlite3
import uuid
from datetime import datetime

print("🔍 Flask 啟動時的工作目錄:", os.getcwd())
print("📂 templates 目錄內容:", os.listdir("templates"))

app = Flask(__name__)
app.secret_key = "super_secret_key"
DATABASE = "database.db"

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

# 3️⃣ teardown
@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db:
        db.close()


# -------------------------
# 資料庫工具
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
            showtime TEXT NOT NULL,
            poster_url TEXT,
            total_seats INTEGER DEFAULT 250
        )
    """)

    # 訂票表
    db.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT UNIQUE,
            movie_id INTEGER,
            customer_name TEXT,
            tickets INTEGER
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

    # 預設電影資料
    if db.execute("SELECT COUNT(*) FROM movies").fetchone()[0] == 0:
        db.execute(
            "INSERT INTO movies (title, showtime, poster_url,total_seats) VALUES (?, ?, ?,?)",
            ("多哥", "19:00", "posters/多哥.png",100)
        )
        db.execute(
            "INSERT INTO movies (title, showtime,poster_url,total_seats) VALUES (?, ?,?,?)",
            ("天劫倒數", "21:00","posters/天劫倒數.png",150)
        )

    # 預設使用者
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        db.execute("INSERT INTO users (username, password) VALUES (?, ?)", ("testuser", "1234"))

    # 預設員工
    if db.execute("SELECT COUNT(*) FROM employees").fetchone()[0] == 0:
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
        # 查詢時同時拿到 full_name
        user = db.execute(
            "SELECT * FROM users WHERE username=? AND password=?", 
            (username, password)
        ).fetchone()

        if not user:
            return "帳號或密碼錯誤", 400

        # 登入成功，把帳號、id、姓名存進 session
        session["user_id"] = user["id"]
        session["username"] = user["username"]      # 可保留
        session["full_name"] = user["full_name"]    # 新增姓名

        return "", 200

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("movies"))

@app.route("/")
def movies():
    db = get_db()
    movies = db.execute("""
        SELECT 
            m.id,
            m.title,
            m.showtime,
            m.poster_url,
            m.total_seats,
            IFNULL(SUM(b.tickets), 0) as booked_seats,
            (m.total_seats - IFNULL(SUM(b.tickets), 0)) as remaining_seats
        FROM movies m
        LEFT JOIN bookings b ON m.id = b.movie_id
        GROUP BY m.id
    """).fetchall()
    
    return render_template("movies.html", movies=movies)

@app.route("/book/<int:movie_id>", methods=["GET", "POST"])
@app.route("/book/<int:movie_id>", methods=["GET", "POST"])
def book(movie_id):
    # 🚨 先檢查是否登入
    if "user_id" not in session:
        return redirect(url_for("login"))

    db = get_db()

    # 取得電影資訊和剩餘座位
    movie = db.execute("""
        SELECT 
            m.*,
            m.total_seats,
            IFNULL(SUM(b.tickets), 0) AS booked_seats,
            (m.total_seats - IFNULL(SUM(b.tickets), 0)) AS remaining_seats
        FROM movies m
        LEFT JOIN bookings b ON m.id = b.movie_id
        WHERE m.id = ?
        GROUP BY m.id
    """, (movie_id,)).fetchone()

    if not movie:
        return "電影不存在", 404

    if request.method == "POST":
        name = request.form["name"]
        tickets = int(request.form["tickets"])
        order_no = generate_unique_order_no(db)

        # 🔹 檢查剩餘座位
        if tickets > movie["remaining_seats"]:
            return f"剩餘座位不足，剩餘 {movie['remaining_seats']} 席", 400

        # 新增訂單
        db.execute("""
            INSERT INTO bookings (order_no, movie_id, customer_name, tickets)
            VALUES (?, ?, ?, ?)
        """, (order_no, movie_id, name, tickets))
        db.commit()

        return redirect(url_for("success", order_no=order_no))

    # GET 顯示訂票頁
    return render_template("book.html", movie=movie)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()

        # 後端驗證姓名
        if full_name.isdigit() or len(full_name) == 0:
            return "姓名不能全為數字，請輸入正確姓名", 400

        # 後端驗證電話
        if not phone.isdigit():
            return "電話只能包含數字", 400
        
        if len(phone) < 8 or len(phone) > 15:
            return "電話長度需介於 8~15 位數", 400

        db = get_db()
        exists = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if exists:
            return "帳號已存在", 400

        db.execute(
            "INSERT INTO users (username, password, full_name, phone) VALUES (?, ?, ?, ?)",
            (username, password, full_name, phone)
        )
        db.commit()

        return "", 200

    return render_template("register.html")

@app.route("/success/<order_no>")
def success(order_no):
    return render_template("success.html", order_no=order_no)


@app.route("/order", methods=["GET", "POST"])
def query_order():
    db = get_db()
    user_name = session.get("username")
    results = []
    searched = False  # 標記是否已查詢過

    if request.method == "POST":
        searched = True  # 表示使用者提交查詢
        order_no = request.form.get("order_no")

        if order_no:
            if user_name:
                results = db.execute("""
                    SELECT b.order_no, b.customer_name, b.tickets, m.title, m.showtime
                    FROM bookings b
                    JOIN movies m ON b.movie_id = m.id
                    WHERE b.order_no=? AND b.customer_name=?
                """, (order_no, user_name)).fetchall()
            else:
                results = db.execute("""
                    SELECT b.order_no, b.customer_name, b.tickets, m.title, m.showtime
                    FROM bookings b
                    JOIN movies m ON b.movie_id = m.id
                    WHERE b.order_no=?
                """, (order_no,)).fetchall()
        else:
            if user_name:
                results = db.execute("""
                    SELECT b.order_no, b.customer_name, b.tickets, m.title, m.showtime
                    FROM bookings b
                    JOIN movies m ON b.movie_id = m.id
                    WHERE b.customer_name=?
                """, (user_name,)).fetchall()
            # 未登入且未輸入訂單號 → 不顯示任何資料

    elif user_name:
        # GET 請求 → 登入者自動查自己所有訂單
        results = db.execute("""
            SELECT b.order_no, b.customer_name, b.tickets, m.title, m.showtime
            FROM bookings b
            JOIN movies m ON b.movie_id = m.id
            WHERE b.customer_name=?
        """, (user_name,)).fetchall()

    return render_template("order.html", results=results, user_name=user_name, searched=searched)




@app.route("/delete_order/<order_no>", methods=["POST"])
def delete_order(order_no):
    user_name = session.get("username")
    if not user_name:
        return redirect(url_for("login"))

    db = get_db()
    # 確保使用者只能刪自己訂單
    db.execute("DELETE FROM bookings WHERE order_no=? AND customer_name=?", (order_no, user_name))
    db.commit()
    return redirect(url_for("query_order"))
# -------------------------
#  員工登入
# -------------------------

@app.route("/employee_login", methods=["GET", "POST"])
def employee_login():
    error = None

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        db = get_db()
        employee = db.execute(
            "SELECT * FROM employees WHERE username=? AND password=?",
            (username, password)
        ).fetchone()

        if employee:
            session["employee_id"] = employee["id"]
            session["employee_username"] = employee["username"]
            return redirect(url_for("manage_movies"))
        else:
            error = "帳號或密碼錯誤"

    return render_template("employee_login.html", error=error)


@app.route("/manage_movies", methods=["GET", "POST"])
def manage_movies():
    # 先檢查是否登入員工
    if "employee_id" not in session:
        return redirect(url_for("employee_login"))

    db = get_db()

    # 新增電影
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        showtime = request.form.get("showtime", "").strip()
        poster_file = request.form.get("poster_url", "").strip()  # 使用者只輸入檔名
        total_seats = request.form.get("total_seats", "").strip()
        # 移除多餘的路徑，只保留檔名
        poster_file = poster_file.split("/")[-1] if poster_file else ""

        poster_url = f"posters/{poster_file}" if poster_file else None

        total_seats = request.form.get("total_seats", "").strip()
   
        # 如果 total_seats 沒填或非數字，給預設值 250
        try:
            total_seats = int(total_seats)
            if total_seats <= 0:
                total_seats = 250
        except ValueError:
            total_seats = 250

        if title and showtime:
            # 如果有輸入檔名，組成完整路徑；沒填就 None
            poster_url = f"posters/{poster_file}" if poster_file else None

            db.execute(
                "INSERT INTO movies (title, showtime, poster_url, total_seats) VALUES (?, ?, ?, ?)",
                (title, showtime, poster_url, total_seats)
            )
            db.commit()

    # 取得所有電影
    movies = db.execute("SELECT * FROM movies").fetchall()

    return render_template(
        "manage_movies.html",
        movies=movies,
        employee_name=session.get("employee_username")
    )

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