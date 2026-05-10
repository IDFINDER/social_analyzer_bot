# -*- coding: utf-8 -*-
"""
دوال مساعدة للبوت
"""

import re
import hashlib
import time
import os
from datetime import datetime


def escape_html(text):
    """هروب الأحرف الخاصة في HTML"""
    if not text or not isinstance(text, str):
        return ""
    return (text
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
        .replace("'", '&#39;')
    )


def clean_filename(text):
    """تنظيف النص لاستخدامه كاسم ملف"""
    if not text:
        return "unknown"
    text = re.sub(r'[^\w\s\u0600-\u06FF\-]', '_', text)
    text = re.sub(r'\s+', '_', text)
    text = re.sub(r'_+', '_', text)
    return text[:50]


def format_number(num):
    """تنسيق الأرقام الكبيرة"""
    if num is None:
        return "N/A"
    try:
        num = int(num)
        if num >= 1_000_000_000:
            return f"{num/1_000_000_000:.1f}B"
        elif num >= 1_000_000:
            return f"{num/1_000_000:.1f}M"
        elif num >= 1_000:
            return f"{num/1_000:.1f}K"
        else:
            return str(num)
    except:
        return str(num)

# أضف هذه الدالة في ملف utils/helpers.py بعد دالة format_number

def parse_number(value):
    """
    تحويل النص المنسق (مثل 723.5K, 1.2M) إلى رقم صحيح
    """
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str):
        return 0
    try:
        # إزالة الفواصل
        value = value.replace(',', '')
        # التعامل مع B (Billions)
        if 'B' in value.upper():
            return int(float(value.upper().replace('B', '')) * 1_000_000_000)
        # التعامل مع M (Millions)
        elif 'M' in value.upper():
            return int(float(value.upper().replace('M', '')) * 1_000_000)
        # التعامل مع K (Thousands)
        elif 'K' in value.upper():
            return int(float(value.upper().replace('K', '')) * 1_000)
        else:
            return int(float(value))
    except (ValueError, TypeError):
        return 0


def format_duration(duration_iso):
    """تحويل مدة الفيديو من ISO 8601"""
    if not duration_iso:
        return "N/A"
    
    duration = duration_iso[2:]
    hours = minutes = seconds = 0
    
    if 'H' in duration:
        h_part = duration.split('H')[0]
        hours = int(h_part)
        duration = duration.split('H')[1]
    
    if 'M' in duration:
        m_part = duration.split('M')[0]
        minutes = int(m_part)
        duration = duration.split('M')[1]
    
    if 'S' in duration:
        s_part = duration.split('S')[0]
        seconds = int(s_part)
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes}:{seconds:02d}"


# ========== دوال التشفير للـ WebApp ==========

def create_secure_token(user_id):
    """إنشاء token آمن باستخدام user_id والتوقيت"""
    secret = os.environ.get('SECRET_KEY', 'your-secret-key-here-change-it')
    timestamp = int(time.time())
    data = f"{user_id}:{timestamp}"
    signature = hashlib.sha256(f"{data}:{secret}".encode()).hexdigest()[:16]
    return f"{data}:{signature}"


# =================================================================================
# تعديل دالة verify_token في utils/helpers.py
# =================================================================================

import time  # تأكد من إضافة هذا الـ import

def verify_token(token):
    """التحقق من صحة token واستخراج user_id مع صلاحية زمنية (ساعة واحدة)"""
    if not token or not isinstance(token, str):
        return None
    
    try:
        parts = token.split(':')
        if len(parts) < 2:
            return None
        
        # استخراج user_id من أول جزء
        user_id_str = parts[0]
        user_id = int(user_id_str)
        
        # إذا كان هناك timestamp في الـ token، تحقق من الصلاحية
        if len(parts) >= 3:
            try:
                timestamp = int(parts[1])
                current_time = int(time.time())
                # صلاحية ساعة واحدة (3600 ثانية)
                if current_time - timestamp > 3600:
                    return None  # token منتهي الصلاحية
            except (ValueError, TypeError):
                pass  # تجاهل أخطاء timestamp
        
        return user_id
    except (ValueError, TypeError, IndexError):
        return None
# =================================================================================
# =================================================================================
def create_secure_token(user_id):
    """إنشاء token آمن باستخدام user_id والتوقيت"""
    secret = os.environ.get('SECRET_KEY', 'your-secret-key-here-change-it')
    timestamp = int(time.time())
    data = f"{user_id}:{timestamp}"
    signature = hashlib.sha256(f"{data}:{secret}".encode()).hexdigest()[:16]
    return f"{data}:{timestamp}:{signature}"

def extract_token_from_request(request):
    """استخراج التوكن من الطلب (يدعم Header, Query, Body)"""
    token = None
    
    # 1. من Header
    auth_header = request.headers.get('Authorization')
    if auth_header:
        parts = auth_header.split(' ')
        if len(parts) == 2 and parts[0].lower() == 'bearer':
            token = parts[1]
    
    # 2. من Query String
    if not token:
        token = request.args.get('token')
    
    # 3. من JSON body
    if not token and request.is_json:
        data = request.get_json(silent=True)
        if data:
            token = data.get('token')
    
    # 4. من Form data
    if not token:
        token = request.form.get('token')
    
    return token
