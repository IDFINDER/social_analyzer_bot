# -*- coding: utf-8 -*-
"""
دوال الذكاء الاصطناعي باستخدام Gemini 3 Flash - الإصدار الاحترافي 2026
المطور: E_Alshabany & Gemini AI Collaboration
"""

import os
import logging
import aiohttp
import json

logger = logging.getLogger(__name__)

# ========== إعدادات Gemini API المحدثة ==========
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-3-flash')

FALLBACK_MODELS = [
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-2.0-flash-exp",
]

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

SYSTEM_INSTRUCTION = """
أنت الآن "الخبير الاستراتيجي الأول لنمو السوشيال ميديا". مهمتك هي استقبال بيانات حساب وتحويلها إلى تقرير تنفيذي عالي المستوى.
طبق القواعد التالية:
1. التحليل العشوائي مرفوض: استخدم لغة الأرقام والنسب المئوية التقديرية.
2. عقلية "مدير الحساب": أعطِ نصائح كأنك تديره فعلياً وتتحمل مسؤولية نموه.
3. التركيز على الـ Retention: حلل أول 3 ثواني (الـ Hooks) واقترح بدائل تجذب المشاهد فوراً.
4. استراتيجية الـ SEO: اقترح كلمات مفتاحية وأوسمة (Hashtags) ذكية لخوارزميات 2026.
5. التنسيق: استخدم الجداول، الرموز التعبيرية، والخطوط العريضة.
6. القيمة المضافة: قدم دائماً 10 أفكار محتوى و3 سكربتات جاهزة للتنفيذ.
أجب باللغة العربية بأسلوب: احترافي، محفز، مباشر، وذكي جداً.
"""


async def call_gemini_api(prompt, max_tokens=2000):
    """استدعاء Gemini API بشكل غير متزامن"""
    if not GEMINI_API_KEY:
        return None, "⚠️ خدمة الذكاء الاصطناعي غير متاحة حالياً."
    
    models_to_try = [GEMINI_MODEL] + FALLBACK_MODELS
    
    async with aiohttp.ClientSession() as session:
        for model in models_to_try:
            try:
                api_url = f"{GEMINI_BASE_URL.format(model=model)}?key={GEMINI_API_KEY}"
                
                full_content = f"{SYSTEM_INSTRUCTION}\n\nبيانات الحساب والمطلوب:\n{prompt}"
                
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
                
                async with session.post(api_url, json=payload, timeout=60) as response:
                    if response.status == 200:
                        data = await response.json()
                        result = data['candidates'][0]['content']['parts'][0]['text']
                        logger.info(f"✅ Gemini API succeeded with model: {model}")
                        return result, None
                    else:
                        error_text = await response.text()
                        logger.warning(f"Model {model} failed: {response.status}")
                        continue
                        
            except Exception as e:
                logger.warning(f"Error with model {model}: {e}")
                continue
    
    return None, "⚠️ عذراً، جميع نماذج الذكاء الاصطناعي غير متاحة حالياً."


async def get_advanced_recommendations(channel_details, user_context=""):
    """الدالة الرئيسية للتوصيات الاستراتيجية المتقدمة"""
    prompt = f"""
قم بتحليل قناة يوتيوب التالية بشكل استراتيجي:
📺 القناة: {channel_details.get('title')}
👥 المشتركين: {channel_details.get('subscribers')}
👁️ المشاهدات الكلية: {channel_details.get('total_views')}
📹 الفيديوهات: {channel_details.get('total_videos')}
📊 متوسط المشاهدات: {channel_details.get('avg_views')}
📝 سياق إضافي: {user_context if user_context else 'لا يوجد'}

المطلوب:
1. تحليل نقاط القوة والضعف
2. 10 أفكار محتوى جديدة
3. 3 سكربتات جاهزة للتنفيذ
4. استراتيجية نمو للأسبوعين القادمين
"""
    return await call_gemini_api(prompt, max_tokens=2500)
