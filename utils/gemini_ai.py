# -*- coding: utf-8 -*-
"""
دوال الذكاء الاصطناعي باستخدام Gemini API - النسخة المستقرة
"""

import os
import logging
import aiohttp
import json

logger = logging.getLogger(__name__)

# ========== إعدادات Gemini API ==========
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-flash-latest')

FALLBACK_MODELS = [
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


async def call_gemini_api(prompt, max_tokens=2000):
    """استدعاء Gemini API"""
    if not GEMINI_API_KEY:
        return None, "⚠️ خدمة الذكاء الاصطناعي غير متاحة حالياً."
    
    models_to_try = [GEMINI_MODEL] + FALLBACK_MODELS
    
    async with aiohttp.ClientSession() as session:
        for model in models_to_try:
            try:
                api_url = f"{GEMINI_BASE_URL}/models/{model}:generateContent?key={GEMINI_API_KEY}"
                
                payload = {
                    "contents": [{
                        "parts": [{"text": prompt}]
                    }],
                    "generationConfig": {
                        "temperature": 0.8,
                        "maxOutputTokens": max_tokens,
                        "topP": 0.95
                    }
                }
                
                async with session.post(api_url, json=payload, timeout=60) as response:
                    if response.status == 200:
                        data = await response.json()
                        result = data['candidates'][0]['content']['parts'][0]['text']
                        logger.info(f"✅ Gemini API succeeded with model: {model}")
                        return result, None
                    else:
                        logger.warning(f"Model {model} failed: {response.status}")
                        continue
                        
            except Exception as e:
                logger.warning(f"Error with model {model}: {e}")
                continue
    
    return None, "⚠️ جميع نماذج الذكاء الاصطناعي غير متاحة حالياً."


async def get_advanced_recommendations(channel_details, user_context=""):
    """الدالة الرئيسية للتوصيات (نسخة مختصرة مكتملة)"""
    prompt = f"""
أنت خبير استراتيجي في تحسين قنوات يوتيوب. قدم تقريراً مختصراً ولكنه مكتمل لهذه القناة:

📺 القناة: {channel_details.get('title', 'غير معروف')}
👥 المشتركين: {channel_details.get('subscribers', '0')}
👁️ المشاهدات: {channel_details.get('total_views', '0')}
📹 الفيديوهات: {channel_details.get('total_videos', '0')}
📊 متوسط المشاهدات: {channel_details.get('avg_views', '0')}

المطلوب:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 نقطتا قوة ونقطتا ضعف
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎬 اقتراحان لتحسين أول 3 ثوانٍ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 5 أفكار محتوى جديدة (عنوان + جملة شرح)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📜 سكربت واحد جاهز (30 ثانية)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚀 3 نصائح سريعة للنمو

استخدم اللغة العربية، كن مختصراً ومركزاً.
"""
    result, error = await call_gemini_api(prompt, max_tokens=1800)
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
1. تقييم الاسم (جملة)
2. اسمان بديلان
3. 3 نصائح سريعة
"""
    result, error = await call_gemini_api(prompt, max_tokens=400)
    return result if result else error
