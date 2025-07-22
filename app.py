from flask import Flask, render_template, request, redirect, session, url_for, flash
import sqlite3
from datetime import datetime


from init_db import cursor

app = Flask(__name__)
app.secret_key = 'secret123'

# Conectare la baza de date
def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# Ruta principală (test)
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect('/dashboard')
    else:
        return redirect('/login')

# Ruta de înregistrare
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
            conn.commit()
            conn.close()
            return redirect('/login')
        except:
            conn.close()
            return "Utilizatorul există deja. Încearcă alt nume."

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
        user = cursor.fetchone()
        conn.close()

        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            return redirect('/dashboard')
        else:
            return "Username sau parolă incorectă."

    return render_template('login.html')

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    categorie_filtru = request.args.get('categorie') or None
    username = session['username']

    conn = get_db_connection()
    cursor = conn.cursor()

    # Dacă adaugă o cheltuială
    if request.method == 'POST':
        amount = request.form['amount']
        category = request.form['category']
        description = request.form['description']
        date = request.form['date'] or datetime.now().strftime('%Y-%m-%d')

        cursor.execute('''
            INSERT INTO expenses (user_id, amount, category, description, date)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, amount, category, description, date))
        conn.commit()

    # Afișează cheltuielile utilizatorului
    # Aplicăm filtrul și pe cheltuielile curente
    cautare = request.args.get('cautare') or ""

    if categorie_filtru and cautare:
        cursor.execute('''
            SELECT * FROM expenses
            WHERE user_id = ? AND category = ? AND description LIKE ?
            ORDER BY date DESC
        ''', (user_id, categorie_filtru, f"%{cautare}%"))
    elif categorie_filtru:
        cursor.execute('''
            SELECT * FROM expenses
            WHERE user_id = ? AND category = ?
            ORDER BY date DESC
        ''', (user_id, categorie_filtru))
    elif cautare:
        cursor.execute('''
            SELECT * FROM expenses
            WHERE user_id = ? AND description LIKE ?
            ORDER BY date DESC
        ''', (user_id, f"%{cautare}%"))
    else:
        cursor.execute('''
            SELECT * FROM expenses
            WHERE user_id = ?
            ORDER BY date DESC
        ''', (user_id,))
    expenses = cursor.fetchall()

    # Total cheltuit în lista curentă de cheltuieli (afișate pe dashboard)
    total_listat = sum([row['amount'] for row in expenses])

    # 💸 Total cheltuit luna aceasta
    current_month = datetime.now().strftime('%Y-%m')
    cursor.execute('SELECT SUM(amount) FROM expenses WHERE user_id = ? AND strftime("%Y-%m", date) = ?', (user_id, current_month))
    total_cheltuit = cursor.fetchone()[0] or 0

    # 📊 Bugetul setat pentru luna aceasta
    cursor.execute('SELECT amount FROM budgets WHERE user_id = ? AND month = ?', (user_id, current_month))
    buget_row = cursor.fetchone()
    buget = buget_row['amount'] if buget_row else 0
    # 🔔 Avertismente despre buget
    diferenta = buget - total_cheltuit
    avertisment = ""

    if buget == 0:
        avertisment = "❗ Nu ai setat un buget pentru luna aceasta!"
    elif diferenta < 0:
        avertisment = f"❗ Ai depășit bugetul cu {abs(diferenta):.2f} lei!"
    elif diferenta <= 100:
        avertisment = f"⚠️ Mai ai doar {diferenta:.2f} lei din buget!"
    elif diferenta <= 500:
        avertisment = f"🔸 Atenție! Bugetul se apropie de limită ({diferenta:.2f} lei rămași)."

    categorie_filtru = request.args.get('categorie') or None

    luna_selectata = request.args.get('luna_istoric')  # ex: "2025-06"

    if luna_selectata:
        cursor.execute('''
            SELECT ea.*, ba.amount AS archived_budget
            FROM expenses_archive ea
            LEFT JOIN budgets_archive ba
            ON strftime('%Y-%m', ea.date) = ba.month AND ea.user_id = ba.user_id
            WHERE ea.user_id = ? AND strftime('%Y-%m', ea.date) = ?
            ORDER BY ea.date DESC
        ''', (user_id, luna_selectata))
    else:
        cursor.execute('''
            SELECT ea.*, ba.amount AS archived_budget
            FROM expenses_archive ea
            LEFT JOIN budgets_archive ba
            ON strftime('%Y-%m', ea.date) = ba.month AND ea.user_id = ba.user_id
            WHERE ea.user_id = ?
            ORDER BY ea.date DESC
        ''', (user_id,))
    istoric_raw = cursor.fetchall()

    # Grupăm pe lună
    istoric = {}
    for row in istoric_raw:
        luna = row['date'][:7]  # ex: 2024-06
        if luna not in istoric:
            istoric[luna] = {
                'cheltuieli': [],
                'buget': row['archived_budget'] or 0
            }
        istoric[luna]['cheltuieli'].append(row)

    # Cheltuieli pe categorii pentru luna curentă
    cursor.execute('''
        SELECT category, SUM(amount) AS total
        FROM expenses
        WHERE user_id = ? AND strftime("%Y-%m", date) = ?
        GROUP BY category
    ''', (user_id, current_month))
    categorii = cursor.fetchall()

    conn.close()


    return render_template(
    'dashboard.html',
    username=username,
    expenses=expenses,
    total_cheltuit=total_cheltuit,
    buget=buget,
    istoric=istoric,
    categorii=categorii,
    avertisment=avertisment , # ➕ adăugat
    total_listat=total_listat

)



@app.route('/set-budget', methods=['POST'])
def set_budget():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    amount = request.form['budget']
    current_month = datetime.now().strftime('%Y-%m')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Dacă există deja buget pentru luna asta, îl înlocuim
    cursor.execute('DELETE FROM budgets WHERE user_id = ? AND month = ?', (user_id, current_month))
    cursor.execute('INSERT INTO budgets (user_id, month, amount) VALUES (?, ?, ?)', (user_id, current_month, amount))
    conn.commit()
    conn.close()

    return redirect('/dashboard')


@app.route('/logout')
def logout():
    session.clear()  # șterge datele de login din sesiune
    return redirect('/login')  # duce utilizatorul la login


@app.route('/reset-luna', methods=['POST'])
def reset_luna():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    current_month = datetime.now().strftime('%Y-%m')

    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Salvăm cheltuielile lunii în arhivă
    cursor.execute('''
        INSERT INTO expenses_archive (user_id, amount, category, description, date)
        SELECT user_id, amount, category, description, date
        FROM expenses
        WHERE user_id = ? AND strftime("%Y-%m", date) = ?
    ''', (user_id, current_month))

    # 2. Salvăm bugetul lunii în arhivă înainte de a-l șterge
    cursor.execute('SELECT amount FROM budgets WHERE user_id = ? AND month = ?', (user_id, current_month))
    row = cursor.fetchone()
    if row:
        buget_curent = row['amount']
        cursor.execute('''
            INSERT INTO budgets_archive (user_id, month, amount)
            VALUES (?, ?, ?)
        ''', (user_id, current_month, buget_curent))

    # 3. Ștergem cheltuielile și bugetul lunii curente
    cursor.execute('DELETE FROM expenses WHERE user_id = ? AND strftime("%Y-%m", date) = ?', (user_id, current_month))
    cursor.execute('DELETE FROM budgets WHERE user_id = ? AND month = ?', (user_id, current_month))

    # 4. Finalizăm tranzacția
    conn.commit()
    conn.close()

    return redirect('/dashboard')


@app.route('/delete-account', methods=['POST'])
def delete_account():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']

    conn = get_db_connection()
    cursor = conn.cursor()

    # Ștergem tot ce ține de utilizator
    cursor.execute('DELETE FROM expenses WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM expenses_archive WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM budgets WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM budgets_archive WHERE user_id = ?', (user_id,))
    cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))

    conn.commit()
    conn.close()

    session.clear()
    return redirect('/register')
@app.route('/delete-expense/<int:expense_id>', methods=['POST'])
def delete_expense(expense_id):
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('DELETE FROM expenses WHERE id = ? AND user_id = ?', (expense_id, user_id))
    conn.commit()
    conn.close()

    return redirect('/dashboard')
@app.route('/edit-expense/<int:expense_id>', methods=['GET', 'POST'])
def edit_expense(expense_id):
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        amount = request.form['amount']
        category = request.form['category']
        description = request.form['description']
        date = request.form['date']

        cursor.execute('''
            UPDATE expenses
            SET amount = ?, category = ?, description = ?, date = ?
            WHERE id = ? AND user_id = ?
        ''', (amount, category, description, date, expense_id, user_id))
        conn.commit()
        conn.close()

        return redirect('/dashboard')

    # dacă GET – afișăm formularul precompletat
    cursor.execute('SELECT * FROM expenses WHERE id = ? AND user_id = ?', (expense_id, user_id))
    expense = cursor.fetchone()
    conn.close()

    if not expense:
        return "Cheltuială inexistentă sau nu ai acces la ea."

    return render_template('edit_expense.html', expense=expense)
@app.route('/statistici-buget')
def statistici_buget():
    if 'user_id' not in session:
        return redirect('/login')

    user_id = session['user_id']
    current_month = datetime.now().strftime('%Y-%m')
    conn = get_db_connection()
    cursor = conn.cursor()

    # Cheltuieli pe categorii luna curentă
    cursor.execute('''
        SELECT category, SUM(amount) AS total
        FROM expenses
        WHERE user_id = ? AND strftime("%Y-%m", date) = ?
        GROUP BY category
    ''', (user_id, current_month))
    statistici = cursor.fetchall()
    conn.close()

    return render_template('statistici_buget.html', statistici=statistici, luna=current_month)

import os

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))  # ia portul din variabila de mediu sau pune 5000 implicit
    app.run(host='0.0.0.0', port=port, debug=True)
