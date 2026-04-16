# -*- coding: utf-8 -*-
"""
دوال الذكاء الاصطناعي باستخدام Gemini API
"""

import os
import logging
import requests

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')


async def get_channel_recommendations(channel_details):
    """
    الحصول على توصيات لتحسين القناة باستخدام Gemini API
    """
    if not GEMINI_API_KEY:
        return "⚠️ مفتاح API غير موجود. يرجى إضافة GEMINI_API_KEY في متغيرات البيئة."
    
    # قائمة بالنماذج المحتملة (جرب كل واحد)
    models = [
        "gemini-1.5-flash",
        "gemini-1.5-pro",
        "gemini-pro",
        "gemini-2.0-flash-exp"
    ]
    
    prompt = f"""
    أنت خبير في تحسين قنوات يوتيوب. قدم نصائح مختصرة لهذه القناة:
    
    اسم القناة: {channel_details.get('title')}
    عدد المشتركين: {channel_details.get('subscribers')}
    عدد الفيديوهات: {channel_details.get('total_videos')}
    
    قدم 3 نصائح عملية ومحددة لتحسين القناة وزيادة التفاعل.
    اجعل النصائح قصيرة ومباشرة باللغة العربية.
    """
    
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        
        try:
            print(f"🔍 Trying model: {model}")
            response = requests.post(
                url,
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
                result = data['candidates'][0]['content']['parts'][0]['text']
                print(f"✅ Success with model: {model}")
                return result
            else:
                print(f"❌ Model {model} failed: {response.status_code}")
                
        except Exception as e:
            print(f"❌ Model {model} error: {e}")
            continue
    
    return "⚠️ عذراً، لم نتمكن من الاتصال بخدمة الذكاء الاصطناعي. حاول مرة أخرى لاحقاً."


# دوال أخرى (يمكن إضافتها لاحقاً)
async def get_username_recommendations(platform, current_username, target_username):
    return "⚠️ هذه الميزة قيد التطوير حالياً."


async def get_bio_page_suggestions(user_data, accounts):
    return "⚠️ هذه الميزة قيد التطوير حالياً."
