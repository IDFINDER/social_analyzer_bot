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

# الحصول على النموذج من متغيرات البيئة (يمكن تغييره دون تعديل الكود)
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-1.5-flash')

# النماذج الاحتياطية (إذا فشل النموذج الرئيسي)
FALLBACK_MODELS = [
    "gemini-flash-latest",
    "gemini-1.5-pro",
    "gemini-pro",
    "gemini-1.0-pro",
]

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


async def call_gemini_api(prompt, max_tokens=800):
    """
    استدعاء Gemini API مع إمكانية استخدام نموذج بديل
    """
    if not GEMINI_API_KEY:
        return None, "⚠️ خدمة الذكاء الاصطناعي غير متاحة حالياً."
    
    if len(GEMINI_API_KEY) < 10:
        return None, "⚠️ مفتاح API غير صالح."
    
    # قائمة النماذج للتجربة (الأساسي + الاحتياطية)
    models_to_try = [GEMINI_MODEL] + FALLBACK_MODELS
    
    for model in models_to_try:
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
                logger.warning(f"Model {model} failed: {response.status_code}")
                continue
                
        except Exception as e:
            logger.warning(f"Error with model {model}: {e}")
            continue
    
    return None, "⚠️ عذراً، جميع نماذج الذكاء الاصطناعي غير متاحة حالياً."


# باقي الدوال كما هي...
async def get_channel_recommendations(channel_details):
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
    return result if result else error


async def get_advanced_recommendations(channel_details, prompt):
    """الحصول على توصيات متقدمة من Gemini API (مع تحليل تاريخي)"""
    result, error = await call_gemini_api(prompt, max_tokens=2000)  # زيادة إلى 2000
    
    if error:
        return error
    return result

async def get_username_recommendations(platform, current_username, target_username):
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
    return result if result else error


async def get_bio_page_suggestions(user_data, accounts):
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
    return result if result else error
