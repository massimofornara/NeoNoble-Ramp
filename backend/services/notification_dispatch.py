"""
Multi-Channel Notification Dispatch Service.

Sends alerts through ALL available channels simultaneously:
1. In-app (MongoDB + SSE push) — always active
2. Email (Resend) — for critical alerts and summaries
3. WebSocket (real-time) — for connected users
4. Browser Push (VAPID) — for offline users

Automatic triggers:
- Trade execution
- Margin liquidation warning
- KYC status change
- Card events
- SEPA/Banking events
- Security events (login, 2FA)
- Price alerts
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from database.mongodb import get_database

logger = logging.getLogger(__name__)


# ── Email Templates ──

def _trade_email(asset: str, side: str, amount: float, price: float, total_eur: float) -> str:
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0f1117;color:#e2e8f0;padding:32px;border-radius:12px;">
      <div style="text-align:center;margin-bottom:24px;">
        <h1 style="color:#a78bfa;margin:0;">NeoNoble Ramp</h1>
        <p style="color:#94a3b8;font-size:14px;">Notifica Trade</p>
      </div>
      <div style="background:#1e1b4b;border-radius:8px;padding:20px;margin-bottom:16px;">
        <h2 style="color:#34d399;margin:0 0 12px;">Ordine {'Acquisto' if side == 'buy' else 'Vendita'} Eseguito</h2>
        <table style="width:100%;color:#e2e8f0;font-size:14px;">
          <tr><td style="padding:4px 0;color:#94a3b8;">Asset</td><td style="text-align:right;font-weight:bold;">{asset}</td></tr>
          <tr><td style="padding:4px 0;color:#94a3b8;">Quantita</td><td style="text-align:right;">{amount}</td></tr>
          <tr><td style="padding:4px 0;color:#94a3b8;">Prezzo</td><td style="text-align:right;">{price:.2f} EUR</td></tr>
          <tr><td style="padding:4px 0;color:#94a3b8;border-top:1px solid #374151;padding-top:8px;">Totale</td>
              <td style="text-align:right;font-weight:bold;color:#34d399;border-top:1px solid #374151;padding-top:8px;">{total_eur:.2f} EUR</td></tr>
        </table>
      </div>
      <p style="color:#64748b;font-size:12px;text-align:center;">Questa email e stata inviata automaticamente da NeoNoble Ramp</p>
    </div>
    """


def _margin_alert_email(pair: str, side: str, leverage: int, pnl: float, alert_type: str) -> str:
    is_warning = alert_type == "liquidation_warning"
    color = "#ef4444" if is_warning else "#f59e0b"
    title = "Avviso Liquidazione" if is_warning else "Alert Margine"
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0f1117;color:#e2e8f0;padding:32px;border-radius:12px;">
      <div style="text-align:center;margin-bottom:24px;">
        <h1 style="color:#a78bfa;margin:0;">NeoNoble Ramp</h1>
        <p style="color:{color};font-size:14px;font-weight:bold;">{title}</p>
      </div>
      <div style="background:#1e1b4b;border:1px solid {color};border-radius:8px;padding:20px;">
        <p style="margin:0 0 12px;">La tua posizione <strong>{pair}</strong> ({side.upper()} x{leverage}) richiede attenzione.</p>
        <p style="margin:0;color:{color};font-size:18px;font-weight:bold;">PnL: {pnl:+.2f} EUR</p>
        {'<p style="margin:12px 0 0;color:#ef4444;">Rischio di liquidazione imminente. Aggiungi margine o chiudi la posizione.</p>' if is_warning else ''}
      </div>
    </div>
    """


def _kyc_email(status: str, tier: int) -> str:
    status_map = {
        "approved": ("Approvato", "#34d399"),
        "rejected": ("Rifiutato", "#ef4444"),
        "pending_review": ("In Revisione", "#f59e0b"),
    }
    label, color = status_map.get(status, (status, "#94a3b8"))
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0f1117;color:#e2e8f0;padding:32px;border-radius:12px;">
      <div style="text-align:center;margin-bottom:24px;">
        <h1 style="color:#a78bfa;margin:0;">NeoNoble Ramp</h1>
        <p style="color:#94a3b8;font-size:14px;">Aggiornamento KYC</p>
      </div>
      <div style="background:#1e1b4b;border-radius:8px;padding:20px;text-align:center;">
        <p style="font-size:18px;color:{color};font-weight:bold;margin:0 0 8px;">{label}</p>
        <p style="color:#94a3b8;margin:0;">Livello KYC: Tier {tier}</p>
      </div>
    </div>
    """


def _security_email(event: str, ip: str, timestamp: str) -> str:
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#0f1117;color:#e2e8f0;padding:32px;border-radius:12px;">
      <div style="text-align:center;margin-bottom:24px;">
        <h1 style="color:#a78bfa;margin:0;">NeoNoble Ramp</h1>
        <p style="color:#f59e0b;font-size:14px;">Avviso di Sicurezza</p>
      </div>
      <div style="background:#1e1b4b;border:1px solid #f59e0b;border-radius:8px;padding:20px;">
        <p style="margin:0 0 8px;"><strong>{event}</strong></p>
        <p style="color:#94a3b8;margin:0;font-size:13px;">IP: {ip} | {timestamp}</p>
        <p style="color:#94a3b8;margin:8px 0 0;font-size:13px;">Se non sei stato tu, cambia immediatamente la password.</p>
      </div>
    </div>
    """


# ── Dispatch Functions ──

async def _get_user_preferences(user_id: str) -> dict:
    """Get user notification preferences."""
    db = get_database()
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "notification_prefs": 1, "email": 1})
    prefs = (user or {}).get("notification_prefs", {})
    return {
        "email": user.get("email", ""),
        "email_enabled": prefs.get("email_trade", True),
        "email_margin": prefs.get("email_margin", True),
        "email_kyc": prefs.get("email_kyc", True),
        "email_security": prefs.get("email_security", True),
        "push_enabled": prefs.get("push", True),
    }


async def _send_email_notification(to_email: str, subject: str, html: str):
    """Send email via Resend."""
    try:
        from services.email_service import get_email_service
        service = get_email_service()
        if service and service.is_configured():
            await service.send_email(to_email, subject, html)
    except Exception as e:
        logger.error(f"[DISPATCH] Email failed to {to_email}: {e}")


async def _push_inapp(user_id: str, title: str, message: str, notif_type: str, severity: str = "info", action_url: str = None):
    """Push in-app + SSE notification."""
    try:
        from routes.notification_routes import push_notification
        await push_notification(user_id, title, message, notif_type, severity, action_url)
    except Exception as e:
        logger.error(f"[DISPATCH] In-app push failed for {user_id}: {e}")


async def _push_browser(user_id: str, title: str, body: str):
    """Store browser push payload for Service Worker to pick up."""
    db = get_database()
    await db.browser_push_queue.insert_one({
        "user_id": user_id,
        "title": title,
        "body": body,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "delivered": False,
    })


# ── Public Dispatch API ──

async def notify_trade_executed(user_id: str, asset: str, side: str, amount: float, price: float, total_eur: float):
    """Notify user about trade execution through all channels."""
    title = f"{'Acquisto' if side == 'buy' else 'Vendita'} {asset} Eseguito"
    message = f"{amount} {asset} a {price:.2f} EUR (Totale: {total_eur:.2f} EUR)"

    prefs = await _get_user_preferences(user_id)

    tasks = [
        _push_inapp(user_id, title, message, "trade", "info", "/portfolio"),
        _push_browser(user_id, title, message),
    ]
    if prefs["email_enabled"] and prefs["email"]:
        tasks.append(_send_email_notification(
            prefs["email"],
            f"[NeoNoble] {title}",
            _trade_email(asset, side, amount, price, total_eur),
        ))

    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info(f"[DISPATCH] Trade notification sent to {user_id} ({len(tasks)} channels)")


async def notify_margin_alert(user_id: str, pair: str, side: str, leverage: int, pnl: float, alert_type: str = "warning"):
    """Notify user about margin position alert through all channels."""
    is_liquidation = alert_type == "liquidation_warning"
    title = "Avviso Liquidazione" if is_liquidation else f"Alert Margine {pair}"
    message = f"Posizione {pair} {side.upper()} x{leverage}: PnL {pnl:+.2f} EUR"
    severity = "critical" if is_liquidation else "warning"

    prefs = await _get_user_preferences(user_id)

    tasks = [
        _push_inapp(user_id, title, message, "margin", severity, "/margin-trading"),
        _push_browser(user_id, title, message),
    ]
    if prefs["email_margin"] and prefs["email"]:
        tasks.append(_send_email_notification(
            prefs["email"],
            f"[NeoNoble] {title}",
            _margin_alert_email(pair, side, leverage, pnl, alert_type),
        ))

    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info(f"[DISPATCH] Margin alert sent to {user_id} ({len(tasks)} channels, severity={severity})")


async def notify_kyc_status(user_id: str, status: str, tier: int = 0):
    """Notify user about KYC status change."""
    status_labels = {"approved": "Approvato", "rejected": "Rifiutato", "pending_review": "In Revisione"}
    title = f"KYC {status_labels.get(status, status)}"
    message = f"Il tuo stato KYC e stato aggiornato a: {status_labels.get(status, status)} (Tier {tier})"

    prefs = await _get_user_preferences(user_id)

    tasks = [
        _push_inapp(user_id, title, message, "kyc", "info", "/kyc"),
        _push_browser(user_id, title, message),
    ]
    if prefs["email_kyc"] and prefs["email"]:
        tasks.append(_send_email_notification(
            prefs["email"],
            f"[NeoNoble] {title}",
            _kyc_email(status, tier),
        ))

    await asyncio.gather(*tasks, return_exceptions=True)


async def notify_security_event(user_id: str, event: str, ip: str = "unknown"):
    """Notify user about security event."""
    title = "Avviso di Sicurezza"
    timestamp = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
    message = f"{event} | IP: {ip} | {timestamp}"

    prefs = await _get_user_preferences(user_id)

    tasks = [
        _push_inapp(user_id, title, message, "security", "warning"),
        _push_browser(user_id, title, message),
    ]
    if prefs["email_security"] and prefs["email"]:
        tasks.append(_send_email_notification(
            prefs["email"],
            f"[NeoNoble] {title}",
            _security_email(event, ip, timestamp),
        ))

    await asyncio.gather(*tasks, return_exceptions=True)


async def notify_banking_event(user_id: str, event_type: str, amount: float, currency: str = "EUR", reference: str = ""):
    """Notify user about banking event (deposit, withdrawal)."""
    type_labels = {"deposit": "Deposito Ricevuto", "withdrawal": "Prelievo Elaborato", "sepa_sent": "Bonifico SEPA Inviato"}
    title = type_labels.get(event_type, event_type)
    message = f"{amount:.2f} {currency} | Ref: {reference}" if reference else f"{amount:.2f} {currency}"

    await asyncio.gather(
        _push_inapp(user_id, title, message, "system", "info", "/wallet"),
        _push_browser(user_id, title, message),
        return_exceptions=True,
    )


async def notify_card_event(user_id: str, event_type: str, card_type: str = "virtual", details: str = ""):
    """Notify user about card event."""
    type_labels = {"issued": "Carta Emessa", "activated": "Carta Attivata", "shipped": "Carta Spedita", "transaction": "Transazione Carta"}
    title = type_labels.get(event_type, event_type)
    message = f"Carta {card_type}: {details}" if details else f"Carta {card_type} {title.lower()}"

    await asyncio.gather(
        _push_inapp(user_id, title, message, "system", "info", "/cards"),
        _push_browser(user_id, title, message),
        return_exceptions=True,
    )


async def notify_price_alert(user_id: str, asset: str, price: float, condition: str, threshold: float):
    """Notify user about price alert trigger."""
    direction = "sopra" if condition == "above" else "sotto"
    title = f"Alert Prezzo {asset}"
    message = f"{asset} ha raggiunto {price:.2f} EUR ({direction} soglia {threshold:.2f} EUR)"

    await asyncio.gather(
        _push_inapp(user_id, title, message, "trade", "info", "/portfolio-tracker"),
        _push_browser(user_id, title, message),
        _send_sms_notification(user_id, f"[NeoNoble] {title}: {message}"),
        return_exceptions=True,
    )


# ── SMS Dispatch (Twilio-ready) ──

async def _send_sms_notification(user_id: str, message: str):
    """Send SMS via Twilio if configured. Falls back silently if not."""
    import os
    twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    twilio_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    twilio_from = os.environ.get("TWILIO_PHONE_NUMBER", "")

    if not (twilio_sid and twilio_token and twilio_from):
        return  # SMS not configured, skip silently

    db = get_database()
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "phone": 1, "notification_prefs": 1})
    if not user:
        return

    phone = user.get("phone", "")
    prefs = user.get("notification_prefs", {})
    if not phone or not prefs.get("sms_enabled", False):
        return

    try:
        import httpx
        auth = (twilio_sid, twilio_token)
        url = f"https://api.twilio.com/2010-04-01/Accounts/{twilio_sid}/Messages.json"
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, data={
                "From": twilio_from,
                "To": phone,
                "Body": message[:1600],
            }, auth=auth)
            if resp.status_code in (200, 201):
                logger.info(f"[SMS] Sent to {user_id}: {phone}")
                await db.sms_log.insert_one({
                    "user_id": user_id, "phone": phone, "message": message[:200],
                    "status": "sent", "sid": resp.json().get("sid", ""),
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                })
            else:
                logger.warning(f"[SMS] Failed: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        logger.error(f"[SMS] Error sending to {user_id}: {e}")


async def notify_dca_executed(user_id: str, asset: str, qty: float, price: float, amount_eur: float):
    """Notify user about DCA execution."""
    title = f"DCA {asset} Eseguito"
    message = f"Acquistati {qty:.8f} {asset} @ {price:.2f} EUR (Investiti: {amount_eur:.2f} EUR)"

    await asyncio.gather(
        _push_inapp(user_id, title, message, "trade", "info", "/wallet"),
        _push_browser(user_id, title, message),
        return_exceptions=True,
    )
