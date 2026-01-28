from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
import os
from werkzeug.utils import secure_filename
from functools import wraps

app = Flask(__name__)
app.secret_key = 'super_secret_key'

# --- CONFIGURATION ---
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- 🔐 ADMIN CREDENTIALS ---
ADMIN_USERNAME = 'admin123'
ADMIN_PASSWORD = 'adminpanelaccess1234'

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('books.db')
    c = conn.cursor()
    
    # 1. Books Table
    c.execute("SELECT count(name) FROM sqlite_master WHERE type='table' AND name='books'")
    if c.fetchone()[0] == 0:
        c.execute('''CREATE TABLE books 
                     (id INTEGER PRIMARY KEY, title TEXT, author TEXT, description TEXT, image TEXT, preview_image TEXT)''')
    else:
        c.execute("PRAGMA table_info(books)")
        columns = [column[1] for column in c.fetchall()]
        if 'preview_image' not in columns:
             c.execute("ALTER TABLE books ADD COLUMN preview_image TEXT")

    # 2. Users Table
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT)''')

    # 3. NEW: Messages Table (For Contact Form)
    c.execute('''CREATE TABLE IF NOT EXISTS messages 
                 (id INTEGER PRIMARY KEY, name TEXT, email TEXT, subject TEXT, message TEXT)''')

    conn.commit()
    conn.close()

init_db()

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- SECURITY DECORATORS ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'admin':
            flash("⛔ Access Denied: Admins only.", "danger")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'role' not in session:
            flash("🔒 Please log in first.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- ROUTES ---

@app.route('/')
def index():
    conn = sqlite3.connect('books.db')
    c = conn.cursor()
    c.execute("SELECT * FROM books")
    books = c.fetchall()
    conn.close()
    return render_template('index.html', books=books)

# UPDATED: Contact Form Handler (Saves to DB now)
@app.route('/contact', methods=['POST'])
def contact():
    name = request.form.get('name')
    email = request.form.get('email')
    subject = request.form.get('subject')
    message = request.form.get('message')

    conn = sqlite3.connect('books.db')
    c = conn.cursor()
    c.execute("INSERT INTO messages (name, email, subject, message) VALUES (?, ?, ?, ?)",
              (name, email, subject, message))
    conn.commit()
    conn.close()

    flash(f"✅ Thank you, {name}! We have received your enquiry.", "success")
    return redirect(url_for('index'))

# --- AUTH ROUTES ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect('books.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
            flash("✅ Account created! Please log in.", "success")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("❌ Username already exists.", "danger")
        finally:
            conn.close()
            
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_input = request.form['username']
        pass_input = request.form['password']
        
        if user_input == ADMIN_USERNAME and pass_input == ADMIN_PASSWORD:
            session['role'] = 'admin'
            session['user'] = 'Administrator'
            flash("✅ Welcome to the Command Center.", "success")
            return redirect(url_for('admin'))
        
        conn = sqlite3.connect('books.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND password=?", (user_input, pass_input))
        user = c.fetchone()
        conn.close()

        if user:
            session['role'] = 'user'
            session['user'] = user[1]
            flash(f"Welcome back, {user[1]}!", "success")
            return redirect(url_for('index'))
        else:
            flash("❌ Invalid Credentials", "danger")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

# --- ADMIN ROUTES ---

# UPDATED: Admin Route (Fetches Messages AND Books)
@app.route('/admin', methods=['GET', 'POST'])
@admin_required
def admin():
    conn = sqlite3.connect('books.db')
    c = conn.cursor()

    # Handle Book Upload
    if request.method == 'POST':
        title = request.form['title']
        author = request.form['author']
        desc = request.form['description']
        cover_file = request.files.get('image')
        preview_file = request.files.get('preview_image')

        if not title or not author or not desc:
            flash("All text fields are required!", "danger")
        elif not cover_file or cover_file.filename == '':
            flash("❌ Missing Cover Image!", "danger")
        elif not preview_file or preview_file.filename == '':
             flash("❌ Missing Preview Image!", "danger")
        elif cover_file and allowed_file(cover_file.filename) and preview_file and allowed_file(preview_file.filename):
            cover_filename = secure_filename(cover_file.filename)
            cover_file.save(os.path.join(app.config['UPLOAD_FOLDER'], cover_filename))
            cover_path = f"/static/uploads/{cover_filename}"

            preview_filename = secure_filename(preview_file.filename)
            preview_file.save(os.path.join(app.config['UPLOAD_FOLDER'], preview_filename))
            preview_path = f"/static/uploads/{preview_filename}"

            c.execute("INSERT INTO books (title, author, description, image, preview_image) VALUES (?, ?, ?, ?, ?)",
                      (title, author, desc, cover_path, preview_path))
            conn.commit()
            flash("✅ Book added successfully!", "success")
            return redirect(url_for('admin'))

    # Fetch Data for Dashboard
    c.execute("SELECT * FROM books")
    books = c.fetchall()
    
    # NEW: Fetch Messages
    c.execute("SELECT * FROM messages ORDER BY id DESC")
    messages = c.fetchall()
    
    conn.close()
    return render_template('admin.html', books=books, messages=messages)

@app.route('/delete/<int:book_id>')
@admin_required
def delete_book(book_id):
    conn = sqlite3.connect('books.db')
    c = conn.cursor()
    c.execute("SELECT image, preview_image FROM books WHERE id=?", (book_id,))
    row = c.fetchone()
    if row:
        try: os.remove(row[0].lstrip('/')) 
        except: pass
        try: 
            if row[1]: os.remove(row[1].lstrip('/')) 
        except: pass

    c.execute("DELETE FROM books WHERE id=?", (book_id,))
    conn.commit()
    conn.close()
    flash("🗑️ Book deleted.", "warning")
    return redirect(url_for('admin'))

# NEW: Delete Message Route
@app.route('/delete_message/<int:msg_id>')
@admin_required
def delete_message(msg_id):
    conn = sqlite3.connect('books.db')
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE id=?", (msg_id,))
    conn.commit()
    conn.close()
    flash("🗑️ Message deleted.", "warning")
    return redirect(url_for('admin'))

@app.route('/preview/<int:book_id>')
@login_required
def preview(book_id):
    conn = sqlite3.connect('books.db')
    c = conn.cursor()
    c.execute("SELECT * FROM books WHERE id=?", (book_id,))
    book = c.fetchone()
    conn.close()
    if book:
        return render_template('preview.html', book=book)
    else:
        flash("Book not found.", "danger")
        return redirect(url_for('index'))

# --- NEW EDIT ROUTE ---
@app.route('/edit/<int:book_id>', methods=['GET', 'POST'])
@admin_required
def edit_book(book_id):
    conn = sqlite3.connect('books.db')
    c = conn.cursor()

    if request.method == 'POST':
        title = request.form['title']
        author = request.form['author']
        desc = request.form['description']
        
        # Get new files (optional)
        cover_file = request.files.get('image')
        preview_file = request.files.get('preview_image')

        # 1. Update Text Fields First
        c.execute("UPDATE books SET title=?, author=?, description=? WHERE id=?", 
                  (title, author, desc, book_id))
        
        # 2. Update Cover Image ONLY if a new one was uploaded
        if cover_file and cover_file.filename != '' and allowed_file(cover_file.filename):
            filename = secure_filename(cover_file.filename)
            cover_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            new_path = f"/static/uploads/{filename}"
            c.execute("UPDATE books SET image=? WHERE id=?", (new_path, book_id))

        # 3. Update Preview Image ONLY if a new one was uploaded
        if preview_file and preview_file.filename != '' and allowed_file(preview_file.filename):
            p_filename = secure_filename(preview_file.filename)
            preview_file.save(os.path.join(app.config['UPLOAD_FOLDER'], p_filename))
            new_p_path = f"/static/uploads/{p_filename}"
            c.execute("UPDATE books SET preview_image=? WHERE id=?", (new_p_path, book_id))

        conn.commit()
        conn.close()
        flash("✅ Book updated successfully!", "success")
        return redirect(url_for('admin'))

    # GET request: Load the form with existing data
    c.execute("SELECT * FROM books WHERE id=?", (book_id,))
    book = c.fetchone()
    conn.close()
    
    if book:
        return render_template('edit_book.html', book=book)
    else:
        flash("Book not found.", "danger")
        return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(debug=True)
