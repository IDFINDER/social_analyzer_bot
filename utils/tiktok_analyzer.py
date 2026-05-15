# -*- coding: utf-8 -*-
"""
دوال تحليل حسابات تيك توك المحدثة (TikTok API V2) - الإصدار الاحترافي
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
TIKTOK_REDIRECT_URI = os.environ.get('TIKTOK_REDIRECT_URI')

# الروابط الجديدة للإصدار الثاني V2
BASE_URL_V2 = "https://open.tiktokapis.com/v2"

def get_tiktok_auth_url(user_id: int) -> str:
    """إصدار V2: إنشاء رابط مصادقة TikTok مع تحديث حي للمتغيرات"""
    import secrets
    import urllib.parse

    client_key = os.environ.get('TIKTOK_CLIENT_KEY')
    redirect_uri = os.environ.get('TIKTOK_REDIRECT_URI')
    
    if not redirect_uri or redirect_uri == "None":
        render_url = os.environ.get('RENDER_URL', 'social-analyzer-flask.onrender.com')
        redirect_uri = f"https://{render_url}/callback/tiktok"

    state = f"{user_id}_{secrets.token_urlsafe(16)}"
    scope = ['user.info.basic', 'user.info.profile', 'user.info.stats', 'video.list']
    
    params = {
        'client_key': client_key,
        'scope': ','.join(scope),
        'response_type': 'code',
        'redirect_uri': redirect_uri,
        'state': state
    }
    
    return f"https://www.tiktok.com/v2/auth/authorize/?{urllib.parse.urlencode(params)}"


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


def save_tiktok_token(user_id: int, token_data: Dict) -> bool:
    """حفظ توكن TikTok في قاعدة البيانات"""
    try:
        from utils.db import supabase
        record = {
            'user_id': user_id,
            'access_token': token_data.get('access_token'),
            'refresh_token': token_data.get('refresh_token'),
            'open_id': token_data.get('open_id'),
            'expires_in': token_data.get('expires_in', 86400),
            'updated_at': datetime.now().isoformat()
        }
        existing = supabase.table('tiktok_tokens').select('id').eq('user_id', user_id).execute()
        if existing.data:
            supabase.table('tiktok_tokens').update(record).eq('user_id', user_id).execute()
        else:
            record['created_at'] = datetime.now().isoformat()
            supabase.table('tiktok_tokens').insert(record).execute()
        return True
    except Exception as e:
        logger.error(f"Error saving TikTok token: {e}")
        return False


def get_tiktok_token(user_id: int) -> Optional[Dict]:
    """جلب توكن TikTok للمستخدم"""
    try:
        from utils.db import supabase
        response = supabase.table('tiktok_tokens').select('*').eq('user_id', user_id).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error(f"Error getting TikTok token: {e}")
        return None


async def get_user_info(access_token: str) -> Optional[Dict]:
    """جلب معلومات المستخدم V2 مع جلب الـ username"""
    URL = f"{BASE_URL_V2}/user/info/"
    # ✅ إضافة username هنا
    fields = "open_id,union_id,avatar_url,display_name,username,bio_description,is_verified,follower_count,following_count,video_count,like_count"
    
    headers = {'Authorization': f'Bearer {access_token}'}
    params = {'fields': fields}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(URL, headers=headers, params=params) as response:
                result = await response.json()
                if response.status == 200 and 'data' in result:
                    u = result['data'].get('user', {})
                    return {
                        'display_name': u.get('display_name', 'مستخدم تيك توك'),
                        'username': u.get('username', 'Unknown'), # ✅ جلب المعرف الحقيقي
                        'bio_description': u.get('bio_description', 'لا يوجد بايو'),
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
    """جلب فيديوهات المستخدم باستخدام TikTok API V2 وتصحيح الحقول"""
    URL = f"{BASE_URL_V2}/video/list/"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }
    # ✅ تصحيح: استخدام view_count بدلاً من play_count المرفوض
    fields = "id,title,view_count,like_count,comment_count,share_count,share_url,create_time"
    params = {'fields': fields}
    data = {"max_count": min(limit, 20)}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(URL, headers=headers, params=params, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    if 'data' in result and 'videos' in result['data']:
                        videos = []
                        for video in result['data'].get('videos', []):
                            videos.append({
                                'id': video.get('id', ''),
                                'title': video.get('title', 'بدون عنوان'),
                                'view_count': video.get('view_count', 0), # ✅ الحقل الصحيح
                                'like_count': video.get('like_count', 0),
                                'comment_count': video.get('comment_count', 0),
                                'share_count': video.get('share_count', 0),
                                'video_url': video.get('share_url', '#'),
                                'create_time': video.get('create_time', 0)
                            })
                        return videos
                return []
    except Exception as e:
        logger.error(f"Get videos V2 exception: {e}")
        return []


async def format_tiktok_report(user_id: int) -> str:
    """تنسيق تقرير تحليل حساب TikTok بالتنسيق الفاخر المطلوب"""
    try:
        from datetime import datetime
        now = datetime.now()
        
        token_data = get_tiktok_token(user_id)
        if not token_data:
            return "❌ لم يتم العثور على بيانات الربط. يرجى إعادة تفعيل الحساب."
        
        access_token = token_data.get('access_token')
        user_info = await get_user_info(access_token)
        
        if not user_info:
            return "❌ فشل في جلب معلومات الحساب. قد يكون التوكن قد انتهى."
        
        videos = await get_user_videos(access_token, limit=5)
        
        # ✅ بناء التقرير بالتنسيق الاحترافي
        report = f"╔══════════════════════════════════╗\n"
        report += f"║          📊 تقرير تحليل حساب TikTok          ║\n"
        report += f"║             @{user_info.get('username', 'غير معروف')}             ║\n"
        report += f"╚══════════════════════════════════╝\n\n"
        
        report += f"📅 تاريخ التحليل: {now.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        report += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        report += f"👤 <b>معلومات الحساب:</b>\n"
        report += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        report += f"• الاسم: {user_info.get('display_name', 'غير معروف')}\n"
        report += f"• المعرف: @{user_info.get('username', 'غير معروف')}\n"
        report += f"• البايو: {user_info.get('bio_description', 'لا يوجد')[:100]}\n"
        report += f"• موثق: {'✅ نعم' if user_info.get('is_verified') else '❌ لا'}\n\n"
        
        report += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        report += f"📊 <b>الإحصائيات:</b>\n"
        report += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        report += f"👥 المتابعين: {user_info.get('follower_count', 0):,}\n"
        report += f"👤 يتابع: {user_info.get('following_count', 0):,}\n"
        report += f"🎬 فيديوهات: {user_info.get('video_count', 0):,}\n"
        report += f"❤️ إجمالي الإعجابات: {user_info.get('like_count', 0):,}\n\n"
        
        report += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        report += f"🎥 <b>أحدث الفيديوهات:</b>\n"
        report += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        
        if videos:
            for i, video in enumerate(videos, 1):
                video_date = datetime.fromtimestamp(video.get('create_time', 0)).strftime('%Y-%m-%d') if video.get('create_time') else 'تاريخ غير معروف'
                report += f"{i}. 📹 {video.get('title', 'بدون عنوان')[:40]}...\n"
                report += f"   👁️ {video.get('view_count', 0):,} | ❤️ {video.get('like_count', 0):,} | 💬 {video.get('comment_count', 0):,}\n"
                report += f"   📅 {video_date} | 🔗 <a href='{video.get('video_url')}'>مشاهدة</a>\n\n"
        else:
            report += "❌ لا توجد فيديوهات عامة متاحة للتحليل حالياً.\n"
            
        report += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        report += f"🤖 تم التحليل بواسطة <b>@Logistics_Bot</b>\n"
        report += f"📌 للاشتراك المميز: @Social_Media_tools_bot\n"
        report += f"👨‍💻 المطور: @Alshabany_Ai"
        
        return report

    except Exception as e:
        logger.error(f"Error in format_tiktok_report: {e}")
        return "⚠️ حدث خطأ فني أثناء إنشاء التقرير."