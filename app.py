
import os
import hmac
import logging
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

@app.get("/")
def health():
    return jsonify({"service": "Diamond Alerts relay", "status": "ok"}), 200

@app.post("/tv-webhook")
def tradingview_webhook():
    if not WEBHOOK_SECRET or not BOT_TOKEN or not CHAT_ID:
        return jsonify({"error": "Server not configured"}), 503

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Expected JSON"}), 400

    # Le secret doit être ajouté au JSON envoyé par Pine Script.
    supplied_secret = str(data.get("secret", ""))
    if not hmac.compare_digest(supplied_secret, WEBHOOK_SECRET):
        return jsonify({"error": "Unauthorized"}), 401

    side = str(data.get("side", "")).upper()
    if side not in ("LONG", "SHORT"):
        return jsonify({"error": "Invalid side"}), 400

    required = ("symbol", "entry", "sl", "tp", "risk_usd", "lots_estimate")
    if any(key not in data for key in required):
        return jsonify({"error": "Missing signal fields"}), 400

    try:
        entry = float(data["entry"])
        sl = float(data["sl"])
        tp = float(data["tp"])
        risk = float(data["risk_usd"])
        lots = float(data["lots_estimate"])
        if not all(map(lambda x: x == x and abs(x) != float("inf"),
                       (entry, sl, tp, risk, lots))):
            raise ValueError("Invalid numeric value")
        if min(risk, lots) <= 0:
            raise ValueError("Risk and lots must be positive")
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid numeric values"}), 400

    message = (
        f"🔔 Diamond Alerts — XAU/USD\n"
        f"Direction : {side}\n"
        f"Symbole : {str(data['symbol'])[:40]}\n"
        f"Entrée théorique : {entry}\n"
        f"Stop-loss : {sl}\n"
        f"Take-profit : {tp}\n"
        f"Risque théorique : ${risk:.2f}\n"
        f"Lot estimé : {lots}\n"
        f"⚠️ Signal indicatif — vérifier le prix et le risque avant toute entrée."
    )

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": message},
            timeout=2.0
        )
        response.raise_for_status()
        result = response.json()
        if not result.get("ok"):
            app.logger.error("Telegram API rejected the message")
            return jsonify({"error": "Telegram delivery failed"}), 502
    except requests.RequestException:
        app.logger.exception("Telegram delivery error")
        return jsonify({"error": "Telegram unavailable"}), 502

    return jsonify({"status": "sent"}), 200
