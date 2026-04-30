# utils/snapchat_auth.py
import os
import logging
from datetime import datetime, timedelta
from utils.db import supabase

logger = logging.getLogger(__name__)

# متغيرات البيئة - تأكد من إضافتها في Render
SNAPCHAT_CLIENT_ID = os.environ.get('SNAPCHAT_CLIENT_ID')
SNAPCHAT_CLIENT_SECRET = os.environ.get('SNAPCHAT_CLIENT_SECRET')
SNAPCHAT_REDIRECT_URI = os.environ.get('SNAPCHAT_REDIRECT_URI', 'https://social-analyzer-flask-2.onrender.com/snapchat/callback')

def get_auth_url(user_id):
    """إنشاء رابط مصادقة Snapchat"""
    import urllib.parse
    params = {
        'client_id': SNAPCHAT_CLIENT_ID,
        'redirect_uri': SNAPCHAT_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'snapchat-profile-api',
        'state': str(user_id)
    }
    return f"https://accounts.snapchat.com/login/oauth2/authorize?{urllib.parse.urlencode(params)}"

def save_token(user_id, token_data):
    """حفظ التوكن بعد التفعيل"""
    expires_at = datetime.now() + timedelta(seconds=token_data.get('expires_in', 3600))
    supabase.table('snapchat_tokens').upsert({
        'user_id': user_id,
        'access_token': token_data['access_token'],
        'refresh_token': token_data.get('refresh_token'),
        'expires_at': expires_at.isoformat(),
        'updated_at': datetime.now().isoformat()
    }, on_conflict='user_id').execute()
    logger.info(f"Token saved for user {user_id}")

def get_token(user_id):
    """استرجاع التوكن المخزن"""
    response = supabase.table('snapchat_tokens').select('*').eq('user_id', user_id).execute()
    if response.data:
        return response.data[0]['access_token']
    return None
