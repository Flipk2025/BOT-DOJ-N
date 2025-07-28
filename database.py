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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS duty_panels (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL
        )
    ''')

    # Tabela do przechowywania informacji o użytkownikach na służbie
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS on_duty_users (
            user_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            start_time TEXT NOT NULL,
            PRIMARY KEY (user_id, guild_id)
        )
    ''')

    conn.commit()
    conn.close()
    print("Baza danych jest gotowa.")

# --- Funkcje do zarządzania panelem służby ---

def set_duty_panel(guild_id, channel_id, message_id):
    """Zapisuje lub aktualizuje informacje o panelu służby dla danego serwera."""
    with get_db_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO duty_panels (guild_id, channel_id, message_id) VALUES (?, ?, ?)",
            (guild_id, channel_id, message_id)
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

# --- Funkcje do zarządzania użytkownikami na służbie ---

def is_user_on_duty(user_id, guild_id):
    """Sprawdza, czy użytkownik jest aktualnie na służbie."""
    with get_db_connection() as conn:
        result = conn.execute("SELECT 1 FROM on_duty_users WHERE user_id = ? AND guild_id = ?", (user_id, guild_id)).fetchone()
    return result is not None

def add_user_to_duty(user_id, guild_id, start_time):
    """Dodaje użytkownika do listy osób na służbie."""
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO on_duty_users (user_id, guild_id, start_time) VALUES (?, ?, ?)",
            (user_id, guild_id, start_time.isoformat())
        )
        conn.commit()

def remove_user_from_duty(user_id, guild_id):
    """Usuwa użytkownika z listy osób na służbie."""
    with get_db_connection() as conn:
        conn.execute("DELETE FROM on_duty_users WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
        conn.commit()

def get_on_duty_users(guild_id):
    """Pobiera listę wszystkich użytkowników na służbie na danym serwerze."""
    with get_db_connection() as conn:
        users = conn.execute("SELECT * FROM on_duty_users WHERE guild_id = ?", (guild_id,)).fetchall()
    return users