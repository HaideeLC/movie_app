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

# -------------------------
# 資料庫工具
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

    db.execute("""
        CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)
    # movies table
    db.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            showtime TEXT NOT NULL
        )
    """)

    # bookings table
    db.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT UNIQUE,
            movie_id INTEGER,
            customer_name TEXT,
            tickets INTEGER
        )
    """)

    # users table
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT
        )
    """)

    # 預設電影資料
    if db.execute("SELECT COUNT(*) FROM movies").fetchone()[0] == 0:
        db.execute("INSERT INTO movies (title, showtime) VALUES (?, ?)", ("Inception", "19:00"))
        db.execute("INSERT INTO movies (title, showtime) VALUES (?, ?)", ("Interstellar", "21:00"))

    # 預設使用者
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        db.execute("INSERT INTO users (username, password) VALUES (?, ?)", ("testuser", "1234"))
    #預設使用者
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
        username = request.form["username"]
        password = request.form["password"]
        db = get_db()
        
        # 先檢查帳號是否存在
        user_exists = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if not user_exists:
            return render_template("login.html", error="尚未註冊")

        # 帳號存在，再檢查密碼
        user = db.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password)).fetchone()
        if user:
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("movies"))
        else:
            return render_template("login.html", error="密碼錯誤")
    
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
def movies():
    db = get_db()
    movies = db.execute("SELECT * FROM movies").fetchall()
    return render_template("movies.html", movies=movies)

@app.route("/book/<int:movie_id>", methods=["GET", "POST"])
def book(movie_id):
    # 🚨 先檢查是否登入
    if "user_id" not in session:
        return redirect(url_for("login"))

    db = get_db()
    movie = db.execute("SELECT * FROM movies WHERE id=?", (movie_id,)).fetchone()

    if request.method == "POST":
        name = request.form["name"]
        tickets = int(request.form["tickets"])
        order_no = generate_unique_order_no(db)

        db.execute("""
            INSERT INTO bookings (order_no, movie_id, customer_name, tickets)
            VALUES (?, ?, ?, ?)
        """, (order_no, movie_id, name, tickets))
        db.commit()

        return redirect(url_for("success", order_no=order_no))

    return render_template("book.html", movie=movie)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        db = get_db()
        # 檢查帳號是否已存在
        exists = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if exists:
            return render_template("register.html", error="帳號已存在")
        
        # 新增使用者
        db.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
        db.commit()
        return redirect(url_for("login"))

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
            return redirect(url_for("mange_movies"))
        else:
            error = "帳號或密碼錯誤"

    return render_template("employee_login.html", error=error)


@app.route("/manage_movies", methods=["GET", "POST"])
def manage_movies():
    if "employee_id" not in session:
        return redirect(url_for("employee_login"))

    db = get_db()

    # 新增電影
    if request.method == "POST":
        title = request.form.get("title")
        showtime = request.form.get("showtime")
        if title and showtime:
            db.execute(
                "INSERT INTO movies (title, showtime) VALUES (?, ?)",
                (title, showtime)
            )
            db.commit()

    movies = db.execute("SELECT * FROM movies").fetchall()

    return render_template(
        "manage_movies.html",
        movies=movies,
        employee_name=session["employee_username"]
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