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
# استخدام نموذج متاح (gemini-2.0-flash أو gemini-1.5-pro أو gemini-1.0-pro)
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
# النموذج البديل في حال فشل الأول
GEMINI_ALT_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.0-pro:generateContent"


# ========== الدوال الرئيسية ==========
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

# قائمة النماذج المتاحة (جربها بالترتيب حتى يعمل واحد)
GEMINI_MODELS = [
    "gemini-1.0-pro",           # الأقدم والأكثر استقراراً
    "gemini-1.0-pro-vision",    # بديل
    "gemini-pro",               # اسم مختصر
]

# رابط API الأساسي
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
                logger.warning(f"Model {model} failed: {response.status_code}")
                continue
                
        except Exception as e:
            logger.warning(f"Error with model {model}: {e}")
            continue
    
    return None, "⚠️ عذراً، جميع نماذج الذكاء الاصطناعي غير متاحة حالياً."


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
async def get_channel_recommendations(channel_details):
    """
    الحصول على توصيات لتحسين القناة باستخدام Gemini API
    """
    if not GEMINI_API_KEY:
        return "⚠️ خدمة الذكاء الاصطناعي غير متاحة حالياً."
    
    # التحقق من صحة المفتاح
    if GEMINI_API_KEY == "YOUR_API_KEY_HERE" or len(GEMINI_API_KEY) < 10:
        return "⚠️ مفتاح API غير صالح. يرجى إضافة مفتاح صحيح في متغيرات البيئة."
    
    try:
        prompt = f"""
        أنت خبير في تحسين قنوات يوتيوب. قدم نصائح مختصرة لهذه القناة:
        
        اسم القناة: {channel_details.get('title')}
        عدد المشتركين: {channel_details.get('subscribers')}
        عدد الفيديوهات: {channel_details.get('total_videos')}
        إجمالي المشاهدات: {channel_details.get('total_views')}
        متوسط المشاهدات: {channel_details.get('avg_views')}
        
        قدم 3-5 نصائح عملية ومحددة باللغة العربية.
        """
        
        response = requests.post(
            f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{
                    "parts": [{"text": prompt}]
                }]
            },
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            return data['candidates'][0]['content']['parts'][0]['text']
        else:
            logger.error(f"Gemini API error: {response.status_code} - {response.text}")
            
            # جرب النموذج البديل إذا فشل الأول
            if "gemini-2.0-flash" in GEMINI_API_URL:
                alt_response = requests.post(
                    f"{GEMINI_ALT_URL}?key={GEMINI_API_KEY}",
                    headers={"Content-Type": "application/json"},
                    json={
                        "contents": [{
                            "parts": [{"text": prompt}]
                        }]
                    },
                    timeout=30
                )
                if alt_response.status_code == 200:
                    data = alt_response.json()
                    return data['candidates'][0]['content']['parts'][0]['text']
            
            return f"⚠️ عذراً، حدث خطأ في جلب التوصيات. (الرمز: {response.status_code})"
        
    except Exception as e:
        logger.error(f"Error getting Gemini recommendations: {e}")
        return f"⚠️ عذراً، حدث خطأ في جلب التوصيات: {str(e)[:100]}"


async def get_advanced_recommendations(channel_details, prompt):
    """
    الحصول على توصيات متقدمة من Gemini API (مع تحليل تاريخي)
    """
    if not GEMINI_API_KEY:
        return "⚠️ خدمة الذكاء الاصطناعي غير متاحة حالياً."
    
    try:
        response = requests.post(
            f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{
                    "parts": [{"text": prompt}]
                }],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 800,
                    "topP": 0.9
                }
            },
            timeout=45
        )
        
        if response.status_code == 200:
            data = response.json()
            return data['candidates'][0]['content']['parts'][0]['text']
        else:
            logger.error(f"Gemini API error: {response.status_code} - {response.text}")
            
            # جرب النموذج البديل
            alt_response = requests.post(
                f"{GEMINI_ALT_URL}?key={GEMINI_API_KEY}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{
                        "parts": [{"text": prompt}]
                    }],
                    "generationConfig": {
                        "temperature": 0.7,
                        "maxOutputTokens": 800,
                        "topP": 0.9
                    }
                },
                timeout=45
            )
            if alt_response.status_code == 200:
                data = alt_response.json()
                return data['candidates'][0]['content']['parts'][0]['text']
            
            return f"⚠️ عذراً، حدث خطأ في جلب التوصيات. (الرمز: {response.status_code})"
        
    except Exception as e:
        logger.error(f"Error getting advanced recommendations: {e}")
        return f"⚠️ عذراً، حدث خطأ: {str(e)[:100]}"


async def get_username_recommendations(platform, current_username, target_username):
    """
    الحصول على توصيات لتحسين اسم المستخدم
    """
    if not GEMINI_API_KEY:
        return "⚠️ خدمة الذكاء الاصطناعي غير متاحة حالياً."
    
    try:
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
        
        response = requests.post(
            f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{
                    "parts": [{"text": prompt}]
                }]
            },
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            return data['candidates'][0]['content']['parts'][0]['text']
        else:
            logger.error(f"Gemini API error (username): {response.status_code}")
            
            # جرب النموذج البديل
            alt_response = requests.post(
                f"{GEMINI_ALT_URL}?key={GEMINI_API_KEY}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{
                        "parts": [{"text": prompt}]
                    }]
                },
                timeout=30
            )
            if alt_response.status_code == 200:
                data = alt_response.json()
                return data['candidates'][0]['content']['parts'][0]['text']
            
            return "⚠️ عذراً، حدث خطأ في جلب التوصيات."
        
    except Exception as e:
        logger.error(f"Error getting username recommendations: {e}")
        return "⚠️ عذراً، حدث خطأ في جلب التوصيات."


async def get_bio_page_suggestions(user_data, accounts):
    """
    الحصول على اقتراحات لصفحة البايو
    """
    if not GEMINI_API_KEY:
        return "⚠️ خدمة الذكاء الاصطناعي غير متاحة حالياً."
    
    try:
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
        
        response = requests.post(
            f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{
                    "parts": [{"text": prompt}]
                }]
            },
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            return data['candidates'][0]['content']['parts'][0]['text']
        else:
            logger.error(f"Gemini API error (bio): {response.status_code}")
            
            # جرب النموذج البديل
            alt_response = requests.post(
                f"{GEMINI_ALT_URL}?key={GEMINI_API_KEY}",
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{
                        "parts": [{"text": prompt}]
                    }]
                },
                timeout=30
            )
            if alt_response.status_code == 200:
                data = alt_response.json()
                return data['candidates'][0]['content']['parts'][0]['text']
            
            return "⚠️ عذراً، حدث خطأ في جلب الاقتراحات."
        
    except Exception as e:
        logger.error(f"Error getting bio page suggestions: {e}")
        return "⚠️ عذراً، حدث خطأ في جلب الاقتراحات."
