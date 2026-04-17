# -*- coding: utf-8 -*-
"""
دوال الذكاء الاصطناعي باستخدام Gemini API
"""

import os
import logging
import requests
import json

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
# استخدم نموذجاً متاحاً (جرب gemini-2.0-flash أولاً)
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


async def get_channel_recommendations(channel_details):
    """
    الحصول على توصيات لتحسين القناة باستخدام Gemini API
    """
    if not GEMINI_API_KEY:
        return "⚠️ خدمة الذكاء الاصطناعي غير متاحة حالياً."
    
    # إذا لم يكن هناك مفتاح صحيح
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
            # جرب نموذجاً بديلاً إذا فشل الأول
            if "gemini-2.0-flash" in GEMINI_API_URL:
                # جرب gemini-1.0-pro كبديل
                alt_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.0-pro:generateContent"
                alt_response = requests.post(
                    f"{alt_url}?key={GEMINI_API_KEY}",
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
            return f"⚠️ عذراً، حدث خطأ في جلب التوصيات. (الرمز: {response.status_code})"
        
    except Exception as e:
        logger.error(f"Error getting advanced recommendations: {e}")
        return f"⚠️ عذراً، حدث خطأ: {str(e)[:100]}"
