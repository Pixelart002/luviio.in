"""
WhatsApp Cloud API Integration — Enterprise Dispatcher
======================================================
Path: app/integrations/whatsapp/client.py
"""
import os
import json
import logging
import requests
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)

# Meta/Facebook Developer Console Secrets
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID", "")
TEAM_PHONE_NUMBER = os.environ.get("TEAM_WHATSAPP_NUMBER", "")  # e.g., "919876543210"

def _send_whatsapp_message(to_number: str, message: str) -> bool:
    """Synchronous HTTP call to Meta Graph API"""
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_ID:
        logger.warning("[WHATSAPP] API Keys missing. Skipping message.")
        return False

    url = f"https://graph.facebook.com/v17.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": message}
    }
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        resp.raise_for_status()
        logger.info(f"[WHATSAPP] Message successfully delivered to {to_number}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"[WHATSAPP] Failed to send message: {e.response.text if hasattr(e, 'response') and e.response else e}")
        return False

async def notify_team(message: str) -> bool:
    """Async Wrapper for sending alerts to the team"""
    if not TEAM_PHONE_NUMBER:
        return False
        
    # We use run_in_threadpool so it doesn't block FastAPI's async event loop
    return await run_in_threadpool(_send_whatsapp_message, TEAM_PHONE_NUMBER, message)