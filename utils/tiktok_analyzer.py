# -*- coding: utf-8 -*-
"""
دوال تحليل حسابات تيك توك المحدثة (TikTok API V2) - للبوت
تطوير: @Alshabany_Ai
"""

import os
import logging
import aiohttp
import json
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# ========== إعدادات TikTok API المحدثة ==========
TIKTOK_CLIENT_KEY = os.environ.get('TIKTOK_CLIENT_KEY')
TIKTOK_CLIENT_SECRET = os.environ.get('TIKTOK_CLIENT_SECRET')
# استخدام الرابط من رندر أو المتغير مباشرة
TIKTOK_REDIRECT_URI = os.environ.get('TIKTOK_REDIRECT_URI')

# الروابط الجديدة للإصدار الثاني V2
BASE_URL_V2 = "https://open.tiktokapis.com/v2"

def get_tiktok_auth_url(user_id: int) -> str:
    """إصدار V2: إنشاء رابط مصادقة TikTok مع تحديث حي للمتغيرات"""
    import secrets
    import urllib.parse
    import os

    # 1. جلب المفتاح الأساسي (Client Key) من رندر
    client_key = os.environ.get('TIKTOK_CLIENT_KEY')
    
    # 2. جلب رابط الـ Redirect URI من رندر "في كل مرة تُطلب فيها الدالة"
    # هذا يضمن أن الزر لن يحمل قيمة None بعد الآن
    redirect_uri = os.environ.get('TIKTOK_REDIRECT_URI')
    
    # 💡 معالجة احتياطية: إذا لم يجد المتغير في رندر، يقوم ببنائه تلقائياً
    if not redirect_uri or redirect_uri == "None":
        render_url = os.environ.get('RENDER_URL', 'social-analyzer-flask.onrender.com')
        redirect_uri = f"https://{render_url}/callback/tiktok"

    # إنشاء حالة فريدة (State) للأمان وربطها بـ user_id
    state = f"{user_id}_{secrets.token_urlsafe(16)}"
    
    # الصلاحيات المطلوبة (Scopes) لـ V2
    scope = [
        'user.info.basic',
        'user.info.profile',
        'user.info.stats',
        'video.list'
    ]
    
    # بناء المعاملات (Parameters)
    params = {
        'client_key': client_key,
        'scope': ','.join(scope),
        'response_type': 'code',
        'redirect_uri': redirect_uri,
        'state': state
    }
    
    # الرابط الرسمي للإصدار الثاني V2
    auth_url = f"https://www.tiktok.com/v2/auth/authorize/?{urllib.parse.urlencode(params)}"
    
    # طباعة في سجلات رندر للتأكد عند الفحص (اختياري)
    print(f"DEBUG: Redirect URI used: {redirect_uri}")
    
    return auth_url


async def exchange_code_for_token(code: str, user_id: int) -> Optional[Dict]:
    """استبدال الرمز بـ Access Token باستخدام V2"""
    TOKEN_URL = f"{BASE_URL_V2}/oauth/token/"
    
    data = {
        'client_key': TIKTOK_CLIENT_KEY,
        'client_secret': TIKTOK_CLIENT_SECRET,
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': TIKTOK_REDIRECT_URI
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                TOKEN_URL,
                data=data,
                headers={'Content-Type': 'application/x-www-form-urlencoded'}
            ) as response:
                res_text = await response.text()
                logger.info(f"TikTok Token Response: {res_text}")
                
                if response.status == 200:
                    result = json.loads(res_text)
                    if 'access_token' in result:
                        return {
                            'access_token': result['access_token'],
                            'open_id': result.get('open_id'),
                            'refresh_token': result.get('refresh_token'),
                            'expires_in': result.get('expires_in', 86400),
                            'created_at': datetime.now().isoformat()
                        }
                return None
    except Exception as e:
        logger.error(f"Error exchanging token: {e}")
        return None


async def get_user_info(access_token: str) -> Optional[Dict]:
    """جلب معلومات المستخدم V2 - تطلب Fields محددة"""
    URL = f"{BASE_URL_V2}/user/info/"
    
    # تحديد الحقول المطلوبة بدقة كما في V2
    fields = "open_id,union_id,avatar_url,display_name,bio_description,is_verified,follower_count,following_count,video_count,like_count"
    
    headers = {'Authorization': f'Bearer {access_token}'}
    params = {'fields': fields}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(URL, headers=headers, params=params) as response:
                result = await response.json()
                if response.status == 200 and 'data' in result:
                    u = result['data'].get('user', {})
                    return {
                        'display_name': u.get('display_name'),
                        'username': u.get('display_name'), # V2 قد لا يعيد unique_id إلا بـ scope خاص
                        'bio_description': u.get('bio_description', ''),
                        'follower_count': u.get('follower_count', 0),
                        'following_count': u.get('following_count', 0),
                        'video_count': u.get('video_count', 0),
                        'like_count': u.get('like_count', 0),
                        'is_verified': u.get('is_verified', False)
                    }
                return None
    except Exception as e:
        logger.error(f"Error fetching user info: {e}")
        return None


async def get_user_videos(access_token: str, limit: int = 5) -> list:
    """جلب قائمة الفيديوهات V2"""
    URL = f"{BASE_URL_V2}/video/list/"
    headers = {'Authorization': f'Bearer {access_token}'}
    
    # الحقول المطلوبة للفيديو في V2
    fields = "id,title,play_count,like_count,comment_count,share_count,cover_image_url,share_url,create_time"
    
    data = {
        'max_count': min(limit, 20)
    }
    params = {'fields': fields}

    try:
        async with aiohttp.ClientSession() as session:
            # ملاحظة: في V2 طلب الفيديو أحياناً يكون POST
            async with session.post(URL, headers=headers, params=params, json=data) as response:
                result = await response.json()
                if response.status == 200 and 'data' in result:
                    videos_list = result['data'].get('videos', [])
                    return [{
                        'title': v.get('title', 'بدون عنوان'),
                        'play_count': v.get('play_count', 0),
                        'like_count': v.get('like_count', 0),
                        'comment_count': v.get('comment_count', 0),
                        'create_time': v.get('create_time', 0)
                    } for v in videos_list]
                return []
    except Exception as e:
        logger.error(f"Error fetching videos: {e}")
        return []

# دالة الحفظ والجلب (تبقى كما هي لأنها تتعامل مع Supabase)
# ... (save_tiktok_token و get_tiktok_token تبقى كما هي في كودك الأصلي)

def save_tiktok_token(user_id: int, token_data: Dict) -> bool:
    """حفظ توكن TikTok في قاعدة البيانات"""
    try:
        from utils.db import supabase
        from datetime import datetime
        
        logger.info(f"Saving token for user {user_id}")
        logger.info(f"Token data: {token_data.keys() if token_data else 'None'}")
        
        # التحقق من وجود سجل مسبق
        existing = supabase.table('tiktok_tokens')\
            .select('id')\
            .eq('user_id', user_id)\
            .execute()
        
        logger.info(f"Existing record: {existing.data}")
        
        record = {
            'user_id': user_id,
            'access_token': token_data.get('access_token'),
            'refresh_token': token_data.get('refresh_token'),
            'open_id': token_data.get('open_id'),
            'expires_in': token_data.get('expires_in', 86400),
            'updated_at': datetime.now().isoformat()
        }
        
        if existing.data:
            result = supabase.table('tiktok_tokens').update(record).eq('user_id', user_id).execute()
            logger.info(f"✅ TikTok token updated for user {user_id}")
        else:
            record['created_at'] = datetime.now().isoformat()
            result = supabase.table('tiktok_tokens').insert(record).execute()
            logger.info(f"✅ TikTok token saved for user {user_id}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error saving TikTok token: {e}")
        import traceback
        traceback.print_exc()
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


async def get_user_info(access_token: str) -> Optional[Dict]:
    # 1. الرابط الجديد المعتمد لـ V2
    URL = "https://open.tiktokapis.com/v2/user/info/"
    
    # 2. تحديد الحقول (Fields) إلزامي في V2 لجلب الأرقام (متابعين، إعجابات...)
    fields = "open_id,union_id,avatar_url,display_name,bio_description,is_verified,follower_count,following_count,video_count,like_count"
    
    # 3. في V2 التوكن يرسل في الـ Headers وليس في الرابط
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    
    params = {
        'fields': fields
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                URL,
                headers=headers, # التوكن هنا
                params=params,   # الحقول هنا
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                response_text = await response.text()
                logger.info(f"TikTok V2 Response: {response_text}")
                
                if response.status == 200:
                    result = await response.json()
                    if 'data' in result and 'user' in result['data']:
                        user_data = result['data']['user']
                        return {
                            'display_name': user_data.get('display_name', 'مستخدم تيك توك'),
                            'username': user_data.get('display_name'), 
                            'bio_description': user_data.get('bio_description', ''),
                            'follower_count': user_data.get('follower_count', 0),
                            'following_count': user_data.get('following_count', 0),
                            'video_count': user_data.get('video_count', 0),
                            'like_count': user_data.get('like_count', 0),
                            'is_verified': user_data.get('is_verified', False)
                        }
                
                logger.error(f"Failed to get V2 info: {response.status} - {response_text}")
                return None
                    
    except Exception as e:
        logger.error(f"TikTok V2 Exception: {e}")
        return None


async def get_user_videos(access_token: str, limit: int = 5) -> list:
    """جلب فيديوهات المستخدم باستخدام TikTok API V2"""
    # 1. الرابط الجديد المعتمد (V2 يستخدم POST لجلب قائمة الفيديوهات)
    URL = "https://open.tiktokapis.com/v2/video/list/"
    
    # 2. التوكن في الهيدرز (إلزامي في V2)
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    
    # 3. تحديد الحقول المطلوبة (Fields)
    # ملاحظة: بدون هذه الحقول لن تعود إليك أي بيانات للفيديو
    fields = "id,title,play_count,like_count,comment_count,share_count,share_url,create_time"
    params = {'fields': fields}
    
    # 4. جسم الطلب (Body) يحدد العدد المطلوب
    data = {
        "max_count": min(limit, 20)
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            # 💡 ملاحظة: تيك توك V2 يطلب استخدام POST لهذا المسار
            async with session.post(
                URL,
                headers=headers,
                params=params,
                json=data,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                res_text = await response.text()
                logger.info(f"TikTok Videos V2 Response: {res_text}")
                
                if response.status == 200:
                    result = await response.json()
                    if 'data' in result and 'videos' in result['data']:
                        videos = []
                        for video in result['data'].get('videos', []):
                            videos.append({
                                'id': video.get('id', ''),
                                'title': video.get('title', 'بدون عنوان'),
                                'play_count': video.get('play_count', 0),
                                'like_count': video.get('like_count', 0),
                                'comment_count': video.get('comment_count', 0),
                                'share_count': video.get('share_count', 0),
                                'video_url': video.get('share_url', ''),
                                'create_time': video.get('create_time', 0)
                            })
                        return videos
                
                logger.error(f"Failed to get videos: {response.status} - {res_text}")
                return []
                    
    except Exception as e:
        logger.error(f"Get videos V2 exception: {e}")
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
