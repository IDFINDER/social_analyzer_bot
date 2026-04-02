# -*- coding: utf-8 -*-
"""
دوال الذكاء الاصطناعي باستخدام Gemini API (بدون مكتبة خارجية)
"""

import os
import logging
import requests
import json

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"


async def get_channel_recommendations(channel_details):
    """
    الحصول على توصيات لتحسين القناة باستخدام Gemini API
    """
    if not GEMINI_API_KEY:
        return "⚠️ خدمة الذكاء الاصطناعي غير متاحة حالياً."
    
    try:
        prompt = f"""
        أنت خبير في تحسين قنوات يوتيوب. قدم نصائح مختصرة لهذه القناة:
        
        اسم القناة: {channel_details.get('title')}
        عدد المشتركين: {channel_details.get('subscribers')}
        عدد الفيديوهات: {channel_details.get('total_videos')}
        إجمالي المشاهدات: {channel_details.get('total_views')}
        متوسط المشاهدات: {channel_details.get('avg_views')}
        
        قدم 3-5 نصائح عملية ومحددة لتحسين القناة وزيادة التفاعل.
        اجعل النصائح قصيرة ومباشرة باللغة العربية.
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
            return "⚠️ عذراً، حدث خطأ في جلب التوصيات. حاول مرة أخرى لاحقاً."
        
    except Exception as e:
        logger.error(f"Error getting Gemini recommendations: {e}")
        return "⚠️ عذراً، حدث خطأ في جلب التوصيات. حاول مرة أخرى لاحقاً."


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
            return "⚠️ عذراً، حدث خطأ في جلب الاقتراحات."
        
    except Exception as e:
        logger.error(f"Error getting bio page suggestions: {e}")
        return "⚠️ عذراً، حدث خطأ في جلب الاقتراحات."
