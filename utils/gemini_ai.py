# -*- coding: utf-8 -*-
"""
دوال الذكاء الاصطناعي باستخدام Gemini API
"""

import os
import logging
import requests
import json

logger = logging.getLogger(__name__)

# ========== إعدادات Gemini API ==========
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# النماذج المتاحة (من القائمة التي ظهرت)
GEMINI_MODELS = [
    "gemini-2.0-flash",           # سريع ومناسب للاستخدام العام
    "gemini-2.5-flash",           # أحدث نسخة
    "gemini-flash-latest",        # دائماً أحدث نسخة
    "gemini-2.5-pro",             # أقوى ولكن أبطأ
]

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


async def call_gemini_api(prompt, max_tokens=800):
    """
    استدعاء Gemini API مع تجربة عدة نماذج
    """
    if not GEMINI_API_KEY:
        return None, "⚠️ خدمة الذكاء الاصطناعي غير متاحة حالياً."
    
    if GEMINI_API_KEY == "YOUR_API_KEY_HERE" or len(GEMINI_API_KEY) < 10:
        return None, "⚠️ مفتاح API غير صالح. يرجى إضافة مفتاح صحيح في متغيرات البيئة."
    
    for model in GEMINI_MODELS:
        try:
            api_url = GEMINI_BASE_URL.format(model=model)
            
            response = requests.post(
                f"{api_url}?key={GEMINI_API_KEY}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{
                        "parts": [{"text": prompt}]
                    }],
                    "generationConfig": {
                        "temperature": 0.7,
                        "maxOutputTokens": max_tokens,
                        "topP": 0.9
                    }
                },
                timeout=45
            )
            
            if response.status_code == 200:
                data = response.json()
                result = data['candidates'][0]['content']['parts'][0]['text']
                logger.info(f"✅ Gemini API succeeded with model: {model}")
                return result, None
            else:
                logger.warning(f"Model {model} failed: {response.status_code} - {response.text[:100]}")
                continue
                
        except Exception as e:
            logger.warning(f"Error with model {model}: {e}")
            continue
    
    return None, "⚠️ عذراً، جميع نماذج الذكاء الاصطناعي غير متاحة حالياً. تحقق من مفتاح API."


async def get_channel_recommendations(channel_details):
    """
    الحصول على توصيات لتحسين القناة باستخدام Gemini API
    """
    prompt = f"""
    أنت خبير في تحسين قنوات يوتيوب. قدم نصائح مختصرة لهذه القناة:
    
    اسم القناة: {channel_details.get('title')}
    عدد المشتركين: {channel_details.get('subscribers')}
    عدد الفيديوهات: {channel_details.get('total_videos')}
    إجمالي المشاهدات: {channel_details.get('total_views')}
    متوسط المشاهدات: {channel_details.get('avg_views')}
    
    قدم 3-5 نصائح عملية ومحددة باللغة العربية.
    """
    
    result, error = await call_gemini_api(prompt, max_tokens=500)
    
    if error:
        return error
    return result


async def get_advanced_recommendations(channel_details, prompt):
    """
    الحصول على توصيات متقدمة من Gemini API (مع تحليل تاريخي)
    """
    result, error = await call_gemini_api(prompt, max_tokens=800)
    
    if error:
        return error
    return result


async def get_username_recommendations(platform, current_username, target_username):
    """
    الحصول على توصيات لتحسين اسم المستخدم
    """
    prompt = f"""
    أنت خبير في تحسين أسماء المستخدمين على منصة {platform}.
    
    الاسم الحالي: {current_username}
    الاسم المطلوب التحقق منه: {target_username}
    
    قدم نصائح:
    1. هل الاسم {target_username} جيد؟ لماذا؟
    2. اقتراح 3 أسماء بديلة أفضل
    3. نصائح عامة لاختيار اسم مستخدم جيد
    
    اجعل الرد مختصراً باللغة العربية.
    """
    
    result, error = await call_gemini_api(prompt, max_tokens=400)
    
    if error:
        return error
    return result


async def get_bio_page_suggestions(user_data, accounts):
    """
    الحصول على اقتراحات لصفحة البايو
    """
    accounts_text = "\n".join([f"- {platform}: {identifier}" for platform, identifier in accounts.items()])
    
    prompt = f"""
    أنت خبير في تصميم صفحات البايو الاحترافية.
    
    اسم المستخدم: {user_data.get('display_name', user_data.get('first_name'))}
    حسابات المستخدم:
    {accounts_text}
    
    قدم اقتراحات لتحسين صفحة البايو:
    1. ترتيب الحسابات المقترح
    2. نصائح لكتابة وصف جذاب
    3. اقتراحات لإضافة روابط مفيدة
    
    اجعل الرد مختصراً باللغة العربية.
    """
    
    result, error = await call_gemini_api(prompt, max_tokens=500)
    
    if error:
        return error
    return result
