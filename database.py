'''
Moduł do obsługi bazy danych SQLite.
'''
import sqlite3
import os

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

    # W tym miejscu w przyszłości dodamy komendy CREATE TABLE dla nowych funkcji.
    # Przykład:
    # cursor.execute('''
    #     CREATE TABLE IF NOT EXISTS users (
    #         user_id INTEGER PRIMARY KEY,
    #         balance INTEGER DEFAULT 0
    #     )
    # ''')

    conn.commit()
    conn.close()
    print("Baza danych jest gotowa.")
