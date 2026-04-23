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
                timeout=60  # زيادة المهلة للتوصيات الطويلة
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


async def get_channel_recommendations(channel_details):
    """
    الحصول على توصيات لتحسين القناة (نسخة محسنة ومختصرة)
    """
    # استخراج البيانات الأساسية فقط
    title = channel_details.get('title', 'غير معروف')
    subscribers = channel_details.get('subscribers', '0')
    total_views = channel_details.get('total_views', '0')
    total_videos = channel_details.get('total_videos', '0')
    avg_views = channel_details.get('avg_views', '0')
    
    prompt = f"""
قدم توصيات احترافية لتحسين قناة يوتيوب:

📺 القناة: {title}
👥 المشتركين: {subscribers}
👁️ المشاهدات: {total_views}
📹 الفيديوهات: {total_videos}
📊 متوسط المشاهدات: {avg_views}

المطلوب:
1. نقاط القوة (ما يميز القناة)
2. نقاط الضعف (الأخطاء الشائعة)
3. 5 توصيات محددة لزيادة المشاهدات والمشتركين
4. نصيحة أخيرة

استخدم لغة عربية بسيطة، ورتب الإجابات بشكل واضح.
"""
    result, error = await call_gemini_api(prompt, max_tokens=1000)
    return result if result else error


async def get_advanced_recommendations(channel_details, prompt):
    """
    الحصول على توصيات متقدمة من Gemini API (مع تحليل تاريخي وذاكرة)
    """
    result, error = await call_gemini_api(prompt, max_tokens=2000)
    
    if error:
        return error
    return result


async def get_username_recommendations(platform, current_username, target_username):
    """
    توصيات لتحسين اسم المستخدم (للمنصات المختلفة)
    """
    prompt = f"""
قدم نصائح لتحسين اسم المستخدم:

• المنصة: {platform}
• الاسم الحالي: {current_username}
• الاسم المطلوب: {target_username}

المطلوب:
1. هل الاسم {target_username} مناسب؟ لماذا؟
2. اقتراح 3 أسماء بديلة أفضل
3. نصائح عامة لاختيار اسم مستخدم جذاب

استخدم لغة عربية مختصرة.
"""
    result, error = await call_gemini_api(prompt, max_tokens=500)
    return result if result else error


async def analyze_channel_strengths_weaknesses(channel_details):
    """
    تحليل نقاط القوة والضعف في القناة (بدون توصيات، فقط تحليل)
    """
    prompt = f"""
حلل القناة التالية وأخبرني فقط نقاط القوة ونقاط الضعف:

📺 القناة: {channel_details.get('title')}
👥 المشتركين: {channel_details.get('subscribers')}
👁️ المشاهدات: {channel_details.get('total_views')}
📹 الفيديوهات: {channel_details.get('total_videos')}
📊 متوسط المشاهدات: {channel_details.get('avg_views')}

المطلوب:
✅ نقاط القوة (3 نقاط)
❌ نقاط الضعف (3 نقاط)

لا تقدم توصيات الآن.
"""
    result, error = await call_gemini_api(prompt, max_tokens=600)
    return result if result else error


async def get_growth_strategy(channel_details, period_days=30):
    """
    استراتيجية نمو مخصصة للقناة خلال فترة زمنية محددة
    """
    prompt = f"""
ضع خطة نمو للقناة التالية خلال {period_days} يوماً:

📺 القناة: {channel_details.get('title')}
👥 المشتركين: {channel_details.get('subscribers')}
👁️ المشاهدات: {channel_details.get('total_views')}
📹 الفيديوهات: {channel_details.get('total_videos')}
📊 متوسط المشاهدات: {channel_details.get('avg_views')}

المطلوب:
• هدف أسبوعي واقعي
• 3 استراتيجيات رئيسية للتحقيق
• مؤشرات قياس الأداء (KPIs)

اجعل الخطة عملية وقابلة للتنفيذ.
"""
    result, error = await call_gemini_api(prompt, max_tokens=1200)
    return result if result else error


async def compare_with_similar_channels(current_channel, similar_channels_data):
    """
    مقارنة القناة الحالية بقنوات مشابهة (تحليل المنافسين)
    """
    prompt = f"""
قارن القناة التالية مع قنوات مشابهة:

📺 قناتي:
• الاسم: {current_channel.get('title')}
• المشتركين: {current_channel.get('subscribers')}
• المشاهدات: {current_channel.get('total_views')}
• الفيديوهات: {current_channel.get('total_videos')}

📊 بيانات القنوات المشابهة المتوسطة:
• متوسط المشتركين: {similar_channels_data.get('avg_subscribers', 'غير متوفر')}
• متوسط المشاهدات: {similar_channels_data.get('avg_views', 'غير متوفر')}
• متوسط الفيديوهات: {similar_channels_data.get('avg_videos', 'غير متوفر')}

المطلوب:
1. أين أتفوق على المنافسين؟
2. أين أتأخر عنهم؟
3. فرص للتحسين مقارنة بهم

استخدم لغة عربية واضحة.
"""
    result, error = await call_gemini_api(prompt, max_tokens=800)
    return result if result else error
