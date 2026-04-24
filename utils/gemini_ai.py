# -*- coding: utf-8 -*-
"""
دوال الذكاء الاصطناعي باستخدام Gemini API مع Service Account
الإصدار الاحترافي 2026
"""
import asyncio
import os
import json
import logging
import aiohttp
from google.oauth2 import service_account
import google.auth.transport.requests

logger = logging.getLogger(__name__)

# ========== إعدادات Gemini API ==========
# سيتم قراءة بيانات اعتماد Service Account من متغير البيئة
GOOGLE_CREDENTIALS_JSON = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS_JSON')
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-1.5-flash')

# نماذج احتياطية (في حال فشل النموذج الأساسي)
FALLBACK_MODELS = [
    "gemini-1.5-pro",
    "gemini-2.0-flash-exp",
    "gemini-flash-latest",
]

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# البرومبت السحري (System Instruction) ليتم دمجه مع كل طلب
SYSTEM_INSTRUCTION = """
أنت الآن "الخبير الاستراتيجي الأول لنمو السوشيال ميديا". طبق القواعد التالية:
1. استخدم لغة الأرقام والنسب المئوية التقديرية.
2. قدم نصائح كأنك تدير الحساب فعلياً.
3. حلل الـ Hooks واقترح بدائل.
4. اقترح كلمات مفتاحية وأوسمة لخوارزميات 2026.
5. استخدم الجداول والرموز التعبيرية بشكل بسيط.
6. قدم 5 أفكار محتوى وسكربتاً واحداً جاهزاً.
أجب باللغة العربية بأسلوب احترافي محفز.
"""


async def get_access_token():
    """جلب توكن وصول (Access Token) من Service Account"""
    if not GOOGLE_CREDENTIALS_JSON:
        return None, "⚠️ متغير GOOGLE_APPLICATION_CREDENTIALS_JSON غير موجود في البيئة"
    
    try:
        creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
        credentials = service_account.Credentials.from_service_account_info(
            creds_dict,
            scopes=['https://www.googleapis.com/auth/cloud-platform']
        )
        # تجديد التوكن إذا كان منتهياً
        auth_req = google.auth.transport.requests.Request()
        credentials.refresh(auth_req)
        return credentials.token, None
    except Exception as e:
        logger.error(f"خطأ في الحصول على التوكن: {e}")
        return None, f"⚠️ فشل المصادقة: {str(e)[:100]}"


async def call_gemini_api(prompt, max_tokens=2000):
    """استدعاء Gemini API باستخدام Bearer Token من Service Account"""
    # الحصول على التوكن
    token, error = await get_access_token()
    if error:
        return None, error
    
    models_to_try = [GEMINI_MODEL] + FALLBACK_MODELS
    
    async with aiohttp.ClientSession() as session:
        for model in models_to_try:
            try:
                api_url = f"{GEMINI_BASE_URL}/models/{model}:generateContent"
                headers = {
                    'Authorization': f'Bearer {token}',
                    'Content-Type': 'application/json'
                }
                
                # دمج التعليمات البرمجية مع طلب المستخدم
                full_content = f"{SYSTEM_INSTRUCTION}\n\n{prompt}"
                
                payload = {
                    "contents": [{
                        "parts": [{"text": full_content}]
                    }],
                    "generationConfig": {
                        "temperature": 0.8,
                        "maxOutputTokens": max_tokens,
                        "topP": 0.95
                    }
                }
                
                async with session.post(api_url, headers=headers, json=payload, timeout=60) as response:
                    if response.status == 200:
                        data = await response.json()
                        result = data['candidates'][0]['content']['parts'][0]['text']
                        logger.info(f"✅ Gemini API succeeded with model: {model}")
                        return result, None
                    else:
                        error_text = await response.text()
                        logger.warning(f"Model {model} failed: {response.status} - {error_text[:100]}")
                        continue
                        
            except asyncio.TimeoutError:
                logger.warning(f"Timeout with model {model}")
                continue
            except Exception as e:
                logger.warning(f"Error with model {model}: {e}")
                continue
    
    return None, "⚠️ جميع نماذج الذكاء الاصطناعي غير متاحة حالياً."


async def get_advanced_recommendations(channel_details, user_context=""):
    """
    الدالة الرئيسية للتوصيات الاستراتيجية المتقدمة (نسخة مختصرة مكتملة)
    """
    prompt = f"""
📊 تحليل استراتيجي لقناة يوتيوب (مختصر ومكتمل):

📺 القناة: {channel_details.get('title', 'غير معروف')}
👥 المشتركين: {channel_details.get('subscribers', '0')}
👁️ المشاهدات: {channel_details.get('total_views', '0')}
📹 الفيديوهات: {channel_details.get('total_videos', '0')}
📊 متوسط المشاهدات: {channel_details.get('avg_views', '0')}

📝 سياق إضافي: {user_context if user_context else 'لا يوجد'}

المطلوب (باختصار):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 نقطتا قوة ونقطتا ضعف
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎬 اقتراحان لتحسين أول 3 ثوانٍ (Hooks)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 5 أفكار محتوى جديدة (عنوان + شرح قصير)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📜 سكربت واحد جاهز (30 ثانية)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚀 3 نصائح سريعة للنمو

اجعل الإجابات مركزة ومباشرة. استخدم لغة عربية سلسة.
"""
    result, error = await call_gemini_api(prompt, max_tokens=2000)
    return result if result else error


async def get_channel_recommendations(channel_details):
    """دالة للتوافق مع الكود القديم"""
    return await get_advanced_recommendations(channel_details)


async def get_username_recommendations(platform, current_username, target_username):
    """توصيات لتحسين اسم المستخدم"""
    prompt = f"""
قدم نصائح مختصرة لتحسين اسم المستخدم:

• المنصة: {platform}
• الاسم الحالي: {current_username}
• الاسم المطلوب: {target_username}

المطلوب:
1. تقييم الاسم (جملة واحدة)
2. اقتراح اسمين بديلين
3. 3 نصائح سريعة لاختيار اسم جذاب
"""
    result, error = await call_gemini_api(prompt, max_tokens=500)
    return result if result else error
