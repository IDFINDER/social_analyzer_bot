# -*- coding: utf-8 -*-
"""
دوال تحليل حسابات تيك توك (TikTok API) - للبوت
"""

import os
import logging
import aiohttp
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# ========== إعدادات TikTok API ==========
TIKTOK_CLIENT_KEY = os.environ.get('TIKTOK_CLIENT_KEY')
TIKTOK_CLIENT_SECRET = os.environ.get('TIKTOK_CLIENT_SECRET')
RENDER_URL = os.environ.get('RENDER_URL', 'social-analyzer-flask.onrender.com')
TIKTOK_REDIRECT_URI = f"https://{RENDER_URL}/callback/tiktok"


def get_tiktok_auth_url(user_id: int) -> str:
    """
    إنشاء رابط مصادقة TikTok OAuth
    
    المعاملات:
    - user_id: معرف المستخدم (سيتم استخدامه كـ state)
    
    الإرجاع:
    - رابط مصادقة TikTok
    """
    import secrets
    import urllib.parse
    
    state = secrets.token_urlsafe(32)
    
    scope = [
        'user.info.basic',
        'user.info.profile',
        'user.info.stats',
        'video.list'
    ]
    
    params = {
        'client_key': TIKTOK_CLIENT_KEY,
        'scope': ','.join(scope),
        'response_type': 'code',
        'redirect_uri': TIKTOK_REDIRECT_URI,
        'state': f"{user_id}_{state}"
    }
    
    auth_url = f"https://www.tiktok.com/v2/auth/authorize/?{urllib.parse.urlencode(params)}"
    
    return auth_url


async def exchange_code_for_token(code: str, user_id: int) -> Optional[Dict]:
    """استبدال رمز التفويض بـ Access Token"""
    if not TIKTOK_CLIENT_KEY or not TIKTOK_CLIENT_SECRET:
        logger.error("TikTok API credentials not configured")
        return None
    
    # ✅ استخدام البيانات الصحيحة فقط (بدون معاملات إضافية)
    data = {
        'client_key': TIKTOK_CLIENT_KEY,
        'client_secret': TIKTOK_CLIENT_SECRET,
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': TIKTOK_REDIRECT_URI
    }
    
    # ✅ طباعة البيانات للتصحيح (بدون الـ secret)
    logger.info(f"Token exchange request for user {user_id}")
    logger.info(f"Redirect URI: {TIKTOK_REDIRECT_URI}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                'https://open-api.tiktok.com/oauth/access_token/',
                data=data,  # ✅ استخدام data وليس json
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                response_text = await response.text()
                logger.info(f"TikTok response: {response_text}")
                
                if response.status == 200:
                    result = json.loads(response_text)
                    
                    if result.get('data', {}).get('access_token'):
                        token_data = {
                            'access_token': result['data']['access_token'],
                            'open_id': result['data']['open_id'],
                            'refresh_token': result['data'].get('refresh_token'),
                            'expires_in': result['data'].get('expires_in', 86400),
                            'created_at': datetime.now().isoformat()
                        }
                        logger.info(f"✅ TikTok token obtained for user {user_id}")
                        return token_data
                    else:
                        logger.error(f"Token exchange failed: {result}")
                        return None
                else:
                    logger.error(f"Token exchange error: {response.status} - {response_text}")
                    return None
                    
    except Exception as e:
        logger.error(f"TikTok token exchange exception: {e}")
        return None


def save_tiktok_token(user_id: int, token_data: Dict) -> bool:
    """حفظ توكن TikTok في قاعدة البيانات"""
    try:
        from utils.db import supabase
        
        existing = supabase.table('tiktok_tokens')\
            .select('id')\
            .eq('user_id', user_id)\
            .execute()
        
        record = {
            'user_id': user_id,
            'access_token': token_data.get('access_token'),
            'refresh_token': token_data.get('refresh_token'),
            'open_id': token_data.get('open_id'),
            'expires_in': token_data.get('expires_in', 86400),
            'updated_at': datetime.now().isoformat()
        }
        
        if existing.data:
            supabase.table('tiktok_tokens').update(record).eq('user_id', user_id).execute()
            logger.info(f"✅ TikTok token updated for user {user_id}")
        else:
            record['created_at'] = datetime.now().isoformat()
            supabase.table('tiktok_tokens').insert(record).execute()
            logger.info(f"✅ TikTok token saved for user {user_id}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error saving TikTok token: {e}")
        return False


def get_tiktok_token(user_id: int) -> Optional[Dict]:
    """جلب توكن TikTok للمستخدم"""
    try:
        from utils.db import supabase
        
        response = supabase.table('tiktok_tokens')\
            .select('*')\
            .eq('user_id', user_id)\
            .execute()
        
        if response.data:
            return response.data[0]
        return None
        
    except Exception as e:
        logger.error(f"Error getting TikTok token: {e}")
        return None


async def get_user_info(access_token: str, open_id: str) -> Optional[Dict]:
    """جلب معلومات المستخدم من TikTok"""
    try:
        params = {
            'access_token': access_token,
            'open_id': open_id
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                'https://open-api.tiktok.com/user/info/',
                params=params,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    
                    if result.get('data'):
                        user_data = result['data'].get('user', {})
                        return {
                            'open_id': open_id,
                            'username': user_data.get('unique_id', ''),
                            'display_name': user_data.get('display_name', ''),
                            'bio_description': user_data.get('bio_description', ''),
                            'follower_count': user_data.get('follower_count', 0),
                            'following_count': user_data.get('following_count', 0),
                            'video_count': user_data.get('video_count', 0),
                            'like_count': user_data.get('like_count', 0),
                            'is_verified': user_data.get('is_verified', False)
                        }
                    else:
                        logger.error(f"Failed to get user info: {result}")
                        return None
                else:
                    error_text = await response.text()
                    logger.error(f"Get user info error: {response.status} - {error_text}")
                    return None
                    
    except Exception as e:
        logger.error(f"Get user info exception: {e}")
        return None


async def get_user_videos(access_token: str, open_id: str, limit: int = 5) -> Optional[list]:
    """جلب فيديوهات المستخدم من TikTok"""
    try:
        params = {
            'access_token': access_token,
            'open_id': open_id,
            'max_count': min(limit, 20)
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                'https://open-api.tiktok.com/video/list/',
                params=params,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    
                    if result.get('data'):
                        videos = []
                        for video in result['data'].get('videos', []):
                            videos.append({
                                'id': video.get('id', ''),
                                'title': video.get('title', ''),
                                'play_count': video.get('play_count', 0),
                                'like_count': video.get('like_count', 0),
                                'comment_count': video.get('comment_count', 0),
                                'share_count': video.get('share_count', 0),
                                'video_url': video.get('share_url', ''),
                                'create_time': video.get('create_time', 0)
                            })
                        return videos
                    else:
                        return []
                else:
                    return []
                    
    except Exception as e:
        logger.error(f"Get videos exception: {e}")
        return []


async def format_tiktok_report(user_id: int) -> str:
    """تنسيق تقرير تحليل حساب TikTok وإرساله للمستخدم"""
    token_data = get_tiktok_token(user_id)
    
    if not token_data:
        return "❌ لم يتم تفعيل حساب TikTok بعد. يرجى استخدام زر التفعيل أولاً."
    
    access_token = token_data.get('access_token')
    open_id = token_data.get('open_id')
    
    # جلب معلومات المستخدم
    user_info = await get_user_info(access_token, open_id)
    if not user_info:
        return "❌ فشل في جلب معلومات حساب TikTok. يرجى المحاولة مرة أخرى."
    
    # جلب الفيديوهات
    videos = await get_user_videos(access_token, open_id, limit=5)
    
    # بناء التقرير
    report = f"""
📊 <b>تقرير تحليل حساب TikTok</b>

👤 <b>المعلومات الأساسية:</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• الاسم: {user_info.get('display_name', 'غير معروف')}
• المعرف: @{user_info.get('username', 'غير معروف')}
• البايو: {user_info.get('bio_description', 'لا يوجد')[:100]}
• موثق: {'✅ نعم' if user_info.get('is_verified') else '❌ لا'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 <b>الإحصائيات:</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
👥 المتابعين: {user_info.get('follower_count', 0):,}
👤 يتابع: {user_info.get('following_count', 0):,}
🎬 فيديوهات: {user_info.get('video_count', 0):,}
❤️ إجمالي الإعجابات: {user_info.get('like_count', 0):,}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎥 <b>أحدث الفيديوهات:</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    if videos:
        for i, video in enumerate(videos[:5], 1):
            from datetime import datetime
            video_date = datetime.fromtimestamp(video.get('create_time', 0)).strftime('%Y-%m-%d') if video.get('create_time') else 'تاريخ غير معروف'
            
            report += f"""
{i}. 🎬 {video.get('title', 'بدون عنوان')[:50]}
   👁️ مشاهدات: {video.get('play_count', 0):,} | ❤️ إعجابات: {video.get('like_count', 0):,}
   💬 تعليقات: {video.get('comment_count', 0):,} | 📅 {video_date}
"""
    else:
        report += "\n❌ لا توجد فيديوهات لعرضها\n"
    
    report += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🤖 تم التحليل بواسطة <b>Social Analyzer Bot</b>
📌 للاشتراك المميز: @Social_Media_tools_bot
👨‍💻 المطور: @Alshabany_Ai
"""
    
    return report