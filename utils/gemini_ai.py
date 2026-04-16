# -*- coding: utf-8 -*-
"""
================================================================================
الملف: gemini_ai.py
الوصف: دوال الذكاء الاصطناعي باستخدام Google Gemini API
================================================================================
"""

import os
import logging
import asyncio
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# محاولة استيراد Gemini API
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("⚠️ مكتبة google-generativeai غير مثبتة. قم بتثبيتها باستخدام: pip install google-generativeai")

# الحصول على مفتاح API من متغيرات البيئة
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# تهيئة Gemini API إذا كان المفتاح موجوداً
if GEMINI_API_KEY and GEMINI_AVAILABLE:
    genai.configure(api_key=GEMINI_API_KEY)
    logger.info("✅ تم تهيئة Gemini API بنجاح")
elif not GEMINI_API_KEY:
    logger.warning("⚠️ GEMINI_API_KEY غير موجود في متغيرات البيئة")
elif not GEMINI_AVAILABLE:
    logger.warning("⚠️ مكتبة google-generativeai غير مثبتة")

# النموذج المستخدم (يجب أن يكون متوافق مع v1beta)
# ملاحظة: gemini-1.5-flash غير متوفر في v1beta، استخدم gemini-pro بدلاً منه
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-pro')


async def get_channel_recommendations(channel_details: Dict[str, Any]) -> str:
    """
    الحصول على توصيات من Gemini لتحسين قناة اليوتيوب
    
    Args:
        channel_details: تفاصيل القناة (الاسم، المشتركين، الفيديوهات، إلخ)
    
    Returns:
        نص التوصيات أو رسالة خطأ
    """
    
    # التحقق من توفر Gemini
    if not GEMINI_API_KEY:
        return "⚠️ خدمة الذكاء الاصطناعي غير متاحة. يرجى التواصل مع المطور."
    
    if not GEMINI_AVAILABLE:
        return "⚠️ مكتبة الذكاء الاصطناعي غير مثبتة. يرجى التواصل مع المطور."
    
    try:
        # استخدام النموذج المتوافق مع v1beta
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        # بناء نص الاستعلام بالعربية
        prompt = f"""
أنت خبير في تحسين قنوات اليوتيوب. قم بتحليل القناة التالية وقدم توصيات عملية:

📺 **اسم القناة:** {channel_details.get('title', 'غير معروف')}
👥 **عدد المشتركين:** {channel_details.get('subscribers', 0):,}
🎬 **عدد الفيديوهات:** {channel_details.get('total_videos', 0):,}
👁️ **إجمالي المشاهدات:** {channel_details.get('total_views', 0):,}
📅 **تاريخ الإنشاء:** {channel_details.get('created_date', 'غير معروف')}
📝 **وصف القناة:** {channel_details.get('description', 'لا يوجد')[:200]}

**المطلوب:**
قدم 5 نصائح عملية ومحددة لتحسين القناة وزيادة المشتركين والمشاهدات.

**ملاحظات مهمة:**
- اجعل النصائح عملية وقابلة للتنفيذ
- ركز على تحسين محتوى اليوتيوب العربي
- اذكر أدوات مفيدة إذا لزم الأمر
- استخدم لغة عربية بسيطة وواضحة
"""
        
        # إرسال الطلب إلى Gemini
        logger.info(f"🤖 إرسال طلب إلى Gemini API (النموذج: {GEMINI_MODEL})")
        response = await asyncio.to_thread(model.generate_content, prompt)
        
        if response and response.text:
            logger.info("✅ تم استلام التوصيات بنجاح")
            return response.text
        else:
            return "⚠️ لم يتم الحصول على رد من الذكاء الاصطناعي. حاول مرة أخرى."
    
    except Exception as e:
        logger.error(f"❌ خطأ في Gemini API: {str(e)}")
        
        # معالجة أخطاء محددة
        error_msg = str(e).lower()
        if "404" in error_msg or "not found" in error_msg:
            return f"""⚠️ **خطأ في نموذج الذكاء الاصطناعي**

النموذج `{GEMINI_MODEL}` غير متوفر حالياً.

**الحلول المقترحة:**
1️⃣ تواصل مع المطور لتحديث النموذج إلى `gemini-pro`
2️⃣ انتظر التحديث القادم للبوت

**ملاحظة:** هذه الميزة قيد التطوير حالياً."""
        
        elif "429" in error_msg or "quota" in error_msg:
            return "⚠️ لقد تجاوزت الحد اليومي للاستخدام المجاني. يرجى المحاولة غداً."
        
        elif "403" in error_msg or "permission" in error_msg:
            return "⚠️ مفتاح API غير صالح أو منتهي الصلاحية. يرجى التواصل مع المطور."
        
        else:
            return f"❌ حدث خطأ في الاتصال بالذكاء الاصطناعي: {str(e)[:200]}"


async def get_username_recommendations(platform: str, keyword: str) -> str:
    """
    الحصول على اقتراحات لأسماء مستخدمين من Gemini
    
    Args:
        platform: المنصة (youtube, instagram, tiktok, facebook)
        keyword: الكلمة المفتاحية أو الاسم المطلوب
    
    Returns:
        اقتراحات الأسماء
    """
    
    if not GEMINI_API_KEY or not GEMINI_AVAILABLE:
        return "⚠️ خدمة اقتراحات الأسماء غير متاحة حالياً."
    
    try:
        model = genai.GenerativeModel(GEMINI_MODEL)
        
        platform_names = {
            'youtube': 'يوتيوب',
            'instagram': 'انستقرام',
            'tiktok': 'تيك توك',
            'facebook': 'فيسبوك'
        }
        
        platform_name = platform_names.get(platform, platform)
        
        prompt = f"""
أنت خبير في أسماء المستخدمين على وسائل التواصل الاجتماعي.

**المطلوب:**
اقترح 10 أسماء مستخدمين مميزة وجذابة لمنصة {platform_name} بناءً على الكلمة المفتاحية: "{keyword}"

**الشروط:**
- أسماء قصيرة وسهلة التذكر
- مناسبة للمحتوى العربي
- غير مستخدمة بشكل شائع
- تعكس الاحترافية

قدم الأسماء فقط، كل اسم في سطر جديد.
"""
        
        response = await asyncio.to_thread(model.generate_content, prompt)
        
        if response and response.text:
            return response.text
        else:
            return "⚠️ لم يتم الحصول على اقتراحات. حاول مرة أخرى."
    
    except Exception as e:
        logger.error(f"❌ خطأ في اقتراحات الأسماء: {str(e)}")
        return f"❌ حدث خطأ: {str(e)[:100]}"


def check_gemini_status() -> Tuple[bool, str]:
    """
    التحقق من حالة خدمة Gemini
    
    Returns:
        tuple: (متاحة, رسالة الحالة)
    """
    if not GEMINI_API_KEY:
        return False, "❌ مفتاح API غير موجود"
    
    if not GEMINI_AVAILABLE:
        return False, "❌ مكتبة google-generativeai غير مثبتة"
    
    try:
        # محاولة بسيطة للتحقق من صحة المفتاح
        model = genai.GenerativeModel(GEMINI_MODEL)
        return True, f"✅ Gemini يعمل (النموذج: {GEMINI_MODEL})"
    except Exception as e:
        return False, f"⚠️ خطأ في الاتصال: {str(e)[:50]}"
