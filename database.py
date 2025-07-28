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
    # Umożliwia dostęp do kolumn przez ich nazwy (działa jak słownik)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_db():
    """
    Inicjalizuje bazę danych. Tworzy plik bazy danych, jeśli nie istnieje,
    oraz przygotowuje podstawową strukturę (tabele).
    """
    print("Sprawdzanie i inicjalizowanie bazy danych...")
    conn = get_db_connection()
    cursor = conn.cursor()

    # Tabela do przechowywania informacji o panelach służby
    # Zmieniono na dwa message_id
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS duty_panels (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER NOT NULL,
            active_message_id INTEGER,
            summary_message_id INTEGER
        )
    ''')

    # Tabela do przechowywania informacji o użytkownikach AKTUALNIE na służbie
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS active_duty_users (
            user_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            start_time TEXT NOT NULL,
            PRIMARY KEY (user_id, guild_id)
        )
    ''')

    # Tabela do przechowywania sumarycznych godzin służby dla użytkowników
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_duty_stats (
            user_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            total_duty_seconds INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, guild_id)
        )
    ''')

    # Tabela do logowania zdarzeń służby
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

    # Migracja danych ze starej tabeli on_duty_users do nowych
    # (jeśli istnieją i nie zostały jeszcze zmigrowane)
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='on_duty_users';")
        if cursor.fetchone(): # Jeśli stara tabela istnieje
            print("Wykryto starą tabelę 'on_duty_users'. Rozpoczynanie migracji...")
            # Przenieś sumaryczne godziny do user_duty_stats
            cursor.execute('''
                INSERT OR IGNORE INTO user_duty_stats (user_id, guild_id, total_duty_seconds)
                SELECT user_id, guild_id, total_duty_seconds FROM on_duty_users
            ''')
            # Przenieś aktywnych użytkowników do active_duty_users
            cursor.execute('''
                INSERT OR IGNORE INTO active_duty_users (user_id, guild_id, start_time)
                SELECT user_id, guild_id, start_time FROM on_duty_users
                WHERE start_time IS NOT NULL -- Tylko ci, którzy byli na służbie
            ''')
            # Usuń starą tabelę po migracji
            cursor.execute("DROP TABLE on_duty_users")
            print("Migracja zakończona pomyślnie. Stara tabela 'on_duty_users' usunięta.")
    except Exception as e:
        print(f"Błąd podczas migracji starej tabeli: {e}")

    # Dodaj kolumny active_message_id i summary_message_id do duty_panels, jeśli nie istnieją
    try:
        cursor.execute("ALTER TABLE duty_panels ADD COLUMN active_message_id INTEGER")
    except sqlite3.OperationalError as e:
        if "duplicate column name" not in str(e):
            raise
    try:
        cursor.execute("ALTER TABLE duty_panels ADD COLUMN summary_message_id INTEGER")
    except sqlite3.OperationalError as e:
        if "duplicate column name" not in str(e):
            raise

    conn.commit()
    conn.close()
    print("Baza danych jest gotowa.")

# --- Funkcje do zarządzania panelem służby ---

def set_duty_panel(guild_id, channel_id, active_message_id, summary_message_id):
    """Zapisuje lub aktualizuje informacje o panelu służby dla danego serwera."""
    with get_db_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO duty_panels (guild_id, channel_id, active_message_id, summary_message_id) VALUES (?, ?, ?, ?)",
            (guild_id, channel_id, active_message_id, summary_message_id)
        )
        conn.commit()

def get_duty_panel(guild_id):
    """Pobiera informacje o panelu służby dla danego serwera."""
    with get_db_connection() as conn:
        panel = conn.execute("SELECT * FROM duty_panels WHERE guild_id = ?", (guild_id,)).fetchone()
    return panel

def get_all_duty_panels():
    """Pobiera informacje o wszystkich panelach służby."""
    with get_db_connection() as conn:
        panels = conn.execute("SELECT * FROM duty_panels").fetchall()
    return panels

# --- Funkcje do zarządzania użytkownikami na służbie (aktywni) ---

def is_user_on_duty(user_id, guild_id):
    """Sprawdza, czy użytkownik jest aktualnie na służbie."""
    with get_db_connection() as conn:
        result = conn.execute("SELECT 1 FROM active_duty_users WHERE user_id = ? AND guild_id = ?", (user_id, guild_id)).fetchone()
    return result is not None

def add_user_to_duty(user_id, guild_id, start_time):
    """Dodaje użytkownika do listy osób na służbie."""
    with get_db_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO active_duty_users (user_id, guild_id, start_time) VALUES (?, ?, ?)",
            (user_id, guild_id, start_time.isoformat())
        )
        conn.commit()

def remove_user_from_duty(user_id, guild_id):
    """Usuwa użytkownika z listy osób na służbie."""
    with get_db_connection() as conn:
        conn.execute("DELETE FROM active_duty_users WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
        conn.commit()

def get_on_duty_users(guild_id):
    """Pobiera listę wszystkich użytkowników na służbie na danym serwerze."""
    with get_db_connection() as conn:
        users = conn.execute("SELECT * FROM active_duty_users WHERE guild_id = ?", (guild_id,)).fetchall()
    return users

# --- Funkcje do zarządzania sumarycznymi godzinami służby ---

def set_user_total_duty_seconds(user_id, guild_id, seconds):
    """Ustawia sumę czasu służby dla użytkownika."""
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO user_duty_stats (user_id, guild_id, total_duty_seconds) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, guild_id) DO UPDATE SET total_duty_seconds = ?",
            (user_id, guild_id, seconds)
        )
        conn.commit()

def adjust_user_total_duty_seconds(user_id, guild_id, seconds_delta):
    """Dodaje lub odejmuje określoną liczbę sekund od sumy czasu służby użytkownika."""
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO user_duty_stats (user_id, guild_id, total_duty_seconds) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, guild_id) DO UPDATE SET total_duty_seconds = total_duty_seconds + ?",
            (user_id, guild_id, seconds_delta)
        )
        conn.commit()

def get_user_total_duty_seconds(user_id, guild_id):
    """Pobiera sumę czasu służby dla konkretnego użytkownika."""
    with get_db_connection() as conn:
        result = conn.execute("SELECT total_duty_seconds FROM user_duty_stats WHERE user_id = ? AND guild_id = ?", (user_id, guild_id)).fetchone()
    return result['total_duty_seconds'] if result else 0

def get_all_total_duty_seconds(guild_id):
    """Pobiera sumę czasu służby dla wszystkich użytkowników na danym serwerze."""
    with get_db_connection() as conn:
        # Usunięto filtr total_duty_seconds > 0
        users = conn.execute("SELECT user_id, total_duty_seconds FROM user_duty_stats WHERE guild_id = ? ORDER BY total_duty_seconds DESC", (guild_id,)).fetchall()
    return users

def reset_all_total_duty_seconds(guild_id):
    """Resetuje sumę czasu służby dla wszystkich użytkowników na danym serwerze."""
    with get_db_connection() as conn:
        conn.execute("UPDATE user_duty_stats SET total_duty_seconds = 0 WHERE guild_id = ?", (guild_id,))
        conn.commit()

def reset_user_total_duty_seconds(user_id, guild_id):
    """Resetuje sumę czasu służby dla konkretnego użytkownika."""
    with get_db_connection() as conn:
        conn.execute("UPDATE user_duty_stats SET total_duty_seconds = 0 WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
        conn.commit()

# --- Funkcje do logowania zdarzeń służby ---

def log_duty_event(guild_id, user_id, action, details=None):
    """Loguje zdarzenie związane ze służbą."""
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO duty_logs (timestamp, guild_id, user_id, action, details) VALUES (?, ?, ?, ?, ?)",
            (datetime.datetime.utcnow().isoformat(), guild_id, user_id, action, details)
        )
        conn.commit()

def get_duty_logs(guild_id, limit=100):
    """Pobiera logi zdarzeń służby dla danego serwera."""
    with get_db_connection() as conn:
        logs = conn.execute(
            "SELECT * FROM duty_logs WHERE guild_id = ? ORDER BY timestamp DESC LIMIT ?",
            (guild_id, limit)
        ).fetchall()
    return logs
