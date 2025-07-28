from flask import Flask, jsonify, request
from threading import Thread
import datetime
import logging

# Inicjalizacja Flask
app = Flask(__name__)

# Zmienna startowa do liczenia uptime
start_time = datetime.datetime.utcnow()

# Logger dla połączeń
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')

# Root endpoint
@app.route("/")
def home():
    ip = request.remote_addr
    logging.info(f"Received ping from {ip}")
    return "✅ Bot działa i żyje!"

# Status endpoint z uptime
@app.route("/status")
def status():
    uptime = datetime.datetime.utcnow() - start_time
    return jsonify({
        "status": "running",
        "uptime": str(uptime),
        "started": start_time.isoformat() + "Z"
    })

# Funkcja do uruchomienia Flask w tle
def run():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    thread = Thread(target=run)
    thread.daemon = True
    thread.start()
    logging.info("🌐 Keep-alive webserver started on port 8080.")
