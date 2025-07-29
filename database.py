'''
Moduł do obsługi bazy danych SQLite.
'''
import sqlite3
import os
import datetime

# Ścieżka do pliku bazy danych. Plik zostanie utworzony w tym samym folderze co bot.
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database.db')

def get_db_connection():
    """Nawiązuje połączenie z bazą danych i zwraca obiekt połączenia."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_db():
    """
    Inicjalizuje bazę danych, tworząc tabele, jeśli nie istnieją,
    i dodając nowe kolumny w razie potrzeby.
    """
    print("Sprawdzanie i inicjalizowanie bazy danych...")
    with get_db_connection() as conn:
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS duty_panels (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                active_message_id INTEGER,
                summary_message_id INTEGER,
                log_channel_id INTEGER
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS active_duty_users (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                start_time TEXT NOT NULL,
                log_message_id INTEGER,
                PRIMARY KEY (user_id, guild_id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_duty_stats (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                total_duty_seconds INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS duty_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                details TEXT
            )
        ''')

        # Sprawdzenie i dodanie kolumn, jeśli nie istnieją
        for table, column, type in [('duty_panels', 'log_channel_id', 'INTEGER'), 
                                     ('active_duty_users', 'log_message_id', 'INTEGER')]:
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {type}")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e):
                    raise
        
        conn.commit()
    print("Baza danych jest gotowa.")

# --- Funkcje panelu służby ---

def set_duty_panel(guild_id, channel_id, active_message_id, summary_message_id):
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO duty_panels (guild_id, channel_id, active_message_id, summary_message_id) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET channel_id = ?, active_message_id = ?, summary_message_id = ?",
            (guild_id, channel_id, active_message_id, summary_message_id, channel_id, active_message_id, summary_message_id)
        )

def set_duty_log_channel(guild_id, log_channel_id):
    with get_db_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO duty_panels (guild_id, channel_id) VALUES (?, 0)", (guild_id,))
        conn.execute("UPDATE duty_panels SET log_channel_id = ? WHERE guild_id = ?", (log_channel_id, guild_id))

def get_duty_panel(guild_id):
    with get_db_connection() as conn:
        return conn.execute("SELECT * FROM duty_panels WHERE guild_id = ?", (guild_id,)).fetchone()

def get_all_duty_panels():
    with get_db_connection() as conn:
        return conn.execute("SELECT * FROM duty_panels").fetchall()

# --- Funkcje aktywnych użytkowników ---

def is_user_on_duty(user_id, guild_id):
    with get_db_connection() as conn:
        return conn.execute("SELECT 1 FROM active_duty_users WHERE user_id = ? AND guild_id = ?", (user_id, guild_id)).fetchone() is not None

def add_user_to_duty(user_id, guild_id, start_time, log_message_id):
    with get_db_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO active_duty_users (user_id, guild_id, start_time, log_message_id) VALUES (?, ?, ?, ?)",
            (user_id, guild_id, start_time.isoformat(), log_message_id)
        )

def get_user_duty_entry(user_id, guild_id):
    """Pobiera konkretny wpis aktywnej służby dla użytkownika."""
    with get_db_connection() as conn:
        return conn.execute("SELECT * FROM active_duty_users WHERE user_id = ? AND guild_id = ?", (user_id, guild_id)).fetchone()

def remove_user_from_duty(user_id, guild_id):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM active_duty_users WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))

def get_on_duty_users(guild_id):
    with get_db_connection() as conn:
        return conn.execute("SELECT * FROM active_duty_users WHERE guild_id = ?", (guild_id,)).fetchall()

# --- Funkcje statystyk służby ---

def adjust_user_total_duty_seconds(user_id, guild_id, seconds_delta):
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO user_duty_stats (user_id, guild_id, total_duty_seconds) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, guild_id) DO UPDATE SET total_duty_seconds = MAX(0, total_duty_seconds + ?)",
            (user_id, guild_id, max(0, seconds_delta), seconds_delta)
        )

def get_user_total_duty_seconds(user_id, guild_id):
    with get_db_connection() as conn:
        result = conn.execute("SELECT total_duty_seconds FROM user_duty_stats WHERE user_id = ? AND guild_id = ?", (user_id, guild_id)).fetchone()
    return result['total_duty_seconds'] if result else 0

def get_all_total_duty_seconds(guild_id):
    with get_db_connection() as conn:
        return conn.execute("SELECT user_id, total_duty_seconds FROM user_duty_stats WHERE guild_id = ? ORDER BY total_duty_seconds DESC", (guild_id,)).fetchall()

def reset_all_total_duty_seconds(guild_id):
    with get_db_connection() as conn:
        conn.execute("UPDATE user_duty_stats SET total_duty_seconds = 0 WHERE guild_id = ?", (guild_id,))

def set_user_total_duty_seconds(user_id, guild_id, seconds):
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO user_duty_stats (user_id, guild_id, total_duty_seconds) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, guild_id) DO UPDATE SET total_duty_seconds = ?",
            (user_id, guild_id, seconds, seconds)
        )

def reset_user_total_duty_seconds(user_id, guild_id):
    with get_db_connection() as conn:
        conn.execute("UPDATE user_duty_stats SET total_duty_seconds = 0 WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))

# --- Funkcje logów zdarzeń ---

def log_duty_event(guild_id, user_id, action, details=None):
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO duty_logs (timestamp, guild_id, user_id, action, details) VALUES (?, ?, ?, ?, ?)",
            (datetime.datetime.utcnow().isoformat(), guild_id, user_id, action, details)
        )

def get_duty_logs(guild_id, limit=100):
    with get_db_connection() as conn:
        return conn.execute("SELECT * FROM duty_logs WHERE guild_id = ? ORDER BY timestamp DESC LIMIT ?", (guild_id, limit)).fetchall()