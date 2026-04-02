# -*- coding: utf-8 -*-
"""
دوال مساعدة للبوت
"""

import re
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