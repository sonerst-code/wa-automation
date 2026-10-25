"""
WhatsApp Randevu Otomasyonu - v1
Twilio'dan gelen WhatsApp mesajlarını karşılar, basit bir durum makinesiyle
(karşılama -> tarih/saat -> isim -> onay) randevu bilgisi toplar ve otomatik
yanıt gönderir. Google Calendar entegrasyonu ikinci aşamada eklenecek.

Not: Twilio'nun resmi Python SDK'sı yerine, webhook yanıtı için elle TwiML
(basit bir XML) üretiyoruz ve proaktif gönderim gerektiğinde (hatırlatma vb.)
`requests` ile doğrudan Twilio REST API'sine POST atıyoruz. Böylece ek
bağımlılık olmadan, yalnızca Flask + requests + python-dotenv ile çalışır.
"""

import os
from xml.sax.saxutils import escape as xml_escape

import requests
from flask import Flask, request
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")

# --- Basit, bellek-içi konuşma durumu (demo amaçlı; üretimde bir veritabanı kullanılmalı) ---
# key: gönderenin WhatsApp numarası, value: { "step": str, "data": dict }
conversations = {}

STEP_NEW = "NEW"
STEP_AWAITING_TIME = "AWAITING_TIME"
STEP_AWAITING_NAME = "AWAITING_NAME"
STEP_AWAITING_CONFIRM = "AWAITING_CONFIRM"


def get_state(sender: str) -> dict:
    if sender not in conversations:
        conversations[sender] = {"step": STEP_NEW, "data": {}}
    return conversations[sender]


def reset_state(sender: str) -> None:
    conversations[sender] = {"step": STEP_NEW, "data": {}}


def handle_message(sender: str, message: str) -> str:
    """Gelen mesaja göre bir sonraki adımı belirler ve gönderilecek yanıt metnini döner."""
    message = (message or "").strip()
    state = get_state(sender)
    step = state["step"]

    if step == STEP_NEW:
        state["step"] = STEP_AWAITING_TIME
        return (
            "Merhaba! Randevu talebiniz için hangi gün ve saat sizin için uygun? "
            "(Örn: Perşembe 14:00)"
        )

    if step == STEP_AWAITING_TIME:
        state["data"]["time"] = message
        state["step"] = STEP_AWAITING_NAME
        return "Teşekkürler. Randevu için adınızı ve soyadınızı alabilir miyim?"

    if step == STEP_AWAITING_NAME:
        state["data"]["name"] = message
        state["step"] = STEP_AWAITING_CONFIRM
        return (
            f"Özet:\n"
            f"Ad Soyad: {state['data']['name']}\n"
            f"Talep edilen zaman: {state['data']['time']}\n\n"
            f"Onaylıyor musunuz? (Evet / Hayır)"
        )

    if step == STEP_AWAITING_CONFIRM:
        answer = message.lower()
        if answer in ("evet", "e", "yes", "evet.", "onaylıyorum"):
            # TODO: Google Calendar entegrasyonu burada çağrılacak (2. aşama)
            name = state["data"].get("name", "")
            time_text = state["data"].get("time", "")
            reset_state(sender)
            return (
                f"Randevunuz alınmıştır, {name}! ({time_text})\n"
                f"Herhangi bir değişiklik için bize tekrar yazabilirsiniz."
            )
        elif answer in ("hayır", "h", "no", "hayir"):
            reset_state(sender)
            return "Talebiniz iptal edildi. Yeniden randevu almak isterseniz bana yazmanız yeterli."
        else:
            return "Anlayamadım, lütfen 'Evet' ya da 'Hayır' yazın."

    # Beklenmeyen durum: sıfırla ve baştan başla
    reset_state(sender)
    return handle_message(sender, message)


def build_twiml(reply_text: str) -> str:
    """Twilio'nun beklediği minimal TwiML yanıtını elle üretir (ek SDK gerektirmez)."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response><Message>{xml_escape(reply_text)}</Message></Response>"
    )


def send_whatsapp_message(to: str, body: str) -> None:
    """Konuşma akışı dışında proaktif mesaj göndermek için (örn. hatırlatma).
    Twilio REST API'sine doğrudan HTTP POST atar; SDK gerektirmez."""
    if not (TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN):
        raise RuntimeError("TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN tanımlı değil (.env dosyasını kontrol et).")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    resp = requests.post(
        url,
        data={"From": TWILIO_WHATSAPP_NUMBER, "To": to, "Body": body},
        auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
        timeout=15,
    )
    resp.raise_for_status()


@app.route("/whatsapp-webhook", methods=["POST"])
def whatsapp_webhook():
    incoming_message = request.form.get("Body", "")
    sender = request.form.get("From", "")

    reply_text = handle_message(sender, incoming_message)

    return build_twiml(reply_text), 200, {"Content-Type": "text/xml"}


@app.route("/health", methods=["GET"])
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
