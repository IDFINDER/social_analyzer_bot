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
    """استدعاء Gemini API بشكل غير متزامن مع إمكانية التبديل التلقائي للنماذج"""
    if not GEMINI_API_KEY:
        return None, "⚠️ خدمة الذكاء الاصطناعي غير متاحة حالياً."
    
    if len(GEMINI_API_KEY) < 10:
        return None, "⚠️ مفتاح API غير صالح."
    
    models_to_try = [GEMINI_MODEL] + FALLBACK_MODELS
    
    async with aiohttp.ClientSession() as session:
        for model in models_to_try:
            try:
                api_url = f"{GEMINI_BASE_URL.format(model=model)}?key={GEMINI_API_KEY}"
                
                # دمج التعليمات البرمجية مع طلب المستخدم
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
                        
            except asyncio.TimeoutError:
                logger.warning(f"Timeout with model {model}")
                continue
            except Exception as e:
                logger.warning(f"Error with model {model}: {e}")
                continue
    
    return None, "⚠️ عذراً، جميع نماذج الذكاء الاصطناعي غير متاحة حالياً."


async def get_advanced_recommendations(channel_details, user_context=""):
    """
    الدالة الرئيسية للتوصيات الاستراتيجية المتقدمة (النسخة الاحترافية)
    """
    prompt = f"""
📊 تحليل استراتيجي لقناة يوتيوب:

📺 اسم القناة: {channel_details.get('title', 'غير معروف')}
👥 عدد المشتركين: {channel_details.get('subscribers', '0')}
👁️ إجمالي المشاهدات: {channel_details.get('total_views', '0')}
📹 عدد الفيديوهات: {channel_details.get('total_videos', '0')}
📊 متوسط المشاهدات: {channel_details.get('avg_views', '0')}

📝 ملاحظات إضافية: {user_context if user_context else 'لا توجد ملاحظات إضافية'}

المطلوب:
1️⃣ تحليل نقاط القوة والضعف
2️⃣ 10 أفكار محتوى مبتكرة وجاهزة للتصوير
3️⃣ 3 سكربتات مفصلة (لكل فكرة رئيسية)
4️⃣ استراتيجية نمو للأسبوعين القادمين
5️⃣ نصائح لتحسين الـ Hooks والعناوين SEO

⚠️ استخدم اللغة العربية الفصحى البسيطة مع لمسة شبابية جذابة.
"""
    result, error = await call_gemini_api(prompt, max_tokens=2500)
    return result if result else error


async def get_channel_recommendations(channel_details):
    """دالة للتوافق مع الكود القديم (تستخدم التوصيات المتقدمة)"""
    return await get_advanced_recommendations(channel_details)


async def get_username_recommendations(platform, current_username, target_username):
    """توصيات لتحسين اسم المستخدم (للمنصات المختلفة)"""
    prompt = f"""
قدم نصائح احترافية لتحسين اسم المستخدم:

• المنصة: {platform}
• الاسم الحالي: {current_username}
• الاسم المطلوب التحقق منه: {target_username}

المطلوب:
1. تقييم الاسم {target_username} (مناسب/غير مناسب مع الشرح)
2. اقتراح 3 أسماء بديلة أفضل مع شرح سبب الاقتراح
3. 5 نصائح عامة لاختيار اسم مستخدم جذاب لا يُنسى

استخدم لغة عربية واضحة واحترافية.
"""
    result, error = await call_gemini_api(prompt, max_tokens=500)
    return result if result else error


# ========== دوال للتوافق مع الكود القديم (يمكن الاستغناء عنها لاحقاً) ==========

async def analyze_channel_strengths_weaknesses(channel_details):
    """تحليل نقاط القوة والضعف (متوافق مع الكود القديم)"""
    prompt = f"""
حلل القناة التالية وأخبرني فقط نقاط القوة ونقاط الضعف:

📺 القناة: {channel_details.get('title')}
👥 المشتركين: {channel_details.get('subscribers')}
👁️ المشاهدات: {channel_details.get('total_views')}
📹 الفيديوهات: {channel_details.get('total_videos')}
📊 متوسط المشاهدات: {channel_details.get('avg_views')}

المطلوب:
✅ نقاط القوة (3 نقاط مع شرح)
❌ نقاط الضعف (3 نقاط مع شرح)

لا تقدم توصيات الآن، فقط تحليل.
"""
    result, error = await call_gemini_api(prompt, max_tokens=600)
    return result if result else error


async def get_growth_strategy(channel_details, period_days=30):
    """استراتيجية نمو مخصصة (متوافق مع الكود القديم)"""
    prompt = f"""
ضع خطة نمو عملية للقناة التالية خلال {period_days} يوماً:

📺 القناة: {channel_details.get('title')}
👥 المشتركين: {channel_details.get('subscribers')}
👁️ المشاهدات: {channel_details.get('total_views')}
📹 الفيديوهات: {channel_details.get('total_videos')}
📊 متوسط المشاهدات: {channel_details.get('avg_views')}

المطلوب:
• هدف أسبوعي واقعي وقابل للقياس
• 3 استراتيجيات رئيسية للتحقيق
• مؤشرات قياس الأداء (KPIs) لتتبع التقدم

اجعل الخطة عملية وتناسب حجم القناة.
"""
    result, error = await call_gemini_api(prompt, max_tokens=1000)
    return result if result else error
