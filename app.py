# -*- coding: utf-8 -*-
"""
================================================================================
اسم الملف: app.py
الوصف: خادم Flask لخدمة صفحات البايو وصفحة الدفع
المشروع: Social Media Analyzer Bot
المطور: @E_Alshabany
التاريخ: 2026
================================================================================
"""

import os
import sys
import logging
from flask import Flask, render_template, request, jsonify, send_from_directory
from datetime import datetime

# =================================================================================
# القسم 1: إعدادات المسارات والمكتبات
# =================================================================================

# إضافة مجلد utils إلى المسار
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils.db import get_bio_page_by_page_url, get_user_info, increment_bio_views, supabase
from utils.helpers import escape_html

# إعدادات logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =================================================================================
# القسم 2: تهيئة التطبيق والمتغيرات
# =================================================================================

app = Flask(__name__)
PORT = int(os.environ.get('PORT', 10000))
FREE_LIMIT = int(os.environ.get('FREE_LIMIT', '5'))
RENDER_URL = os.environ.get('RENDER_URL', 'social-analyzer-flask.onrender.com')

# =================================================================================
# القسم 3: نقاط نهاية فحص الصحة (Health Checks)
# =================================================================================

@app.route('/')
@app.route('/health')
@app.route('/healthcheck')
def health():
    """فحص صحة الخادم - يستخدمه Render للتأكد من أن الخدمة تعمل"""
    return jsonify({"status": "ok", "service": "flask"}), 200

# =================================================================================
# القسم 4: صفحة الدفع (Payment Page)
# =================================================================================

@app.route('/payment')
def payment_page():
    """صفحة الدفع الموحدة للاشتراك المميز"""
    try:
        return render_template('payment.html', free_limit=FREE_LIMIT)
    except Exception as e:
        logger.error(f"Payment page error: {e}")
        return f"Error loading payment page: {e}", 500

# =================================================================================
# القسم 5: صفحة البايو الشخصية (Bio Page)
# =================================================================================

@app.route('/bio/<page_url>')
def bio_page(page_url):
    """
    صفحة البايو الشخصية
    تعرض حسابات المستخدم وروابطه في صفحة واحدة جميلة
    """
    try:
        logger.info(f"🔍 Bio page requested: {page_url}")
        
        # جلب بيانات صفحة البايو من قاعدة البيانات
        bio = get_bio_page_by_page_url(page_url)
        if not bio:
            logger.warning(f"❌ Bio not found: {page_url}")
            return "Page not found", 404
        
        # جلب معلومات المستخدم
        user_info = get_user_info(bio['user_id'])
        if not user_info:
            logger.warning(f"❌ User not found: {bio['user_id']}")
            return "User not found", 404
        
        # زيادة عدد المشاهدات (بدون انتظار الرد)
        increment_bio_views(page_url)
        
        # جلب الحسابات والروابط المخصصة
        accounts = bio.get('accounts', {})
        custom_links = bio.get('custom_links', [])
        
        # أيقونات المنصات
        platform_icons = {
            'youtube': 'https://upload.wikimedia.org/wikipedia/commons/b/b8/YouTube_Logo_2017.svg',
            'instagram': 'https://upload.wikimedia.org/wikipedia/commons/a/a5/Instagram_icon.png',
            'tiktok': 'https://upload.wikimedia.org/wikipedia/commons/0/0a/TikTok_logo.svg',
            'facebook': 'https://upload.wikimedia.org/wikipedia/commons/5/51/Facebook_f_logo_%282019%29.svg'
        }
        
        platform_names = {
            'youtube': 'YouTube',
            'instagram': 'Instagram',
            'tiktok': 'TikTok',
            'facebook': 'Facebook'
        }
        
        # ========== بناء قائمة الحسابات بالروابط الصحيحة ==========
        accounts_list = []
        for platform, acc in accounts.items():
            identifier = acc.get('account_identifier', '')
            if identifier:
                # إزالة @ من البداية إذا وجدت
                clean_identifier = identifier
                if clean_identifier.startswith('@'):
                    clean_identifier = clean_identifier[1:]
                
                # بناء الرابط الصحيح حسب المنصة
                if platform == 'youtube':
                    url = f"https://www.youtube.com/@{clean_identifier}"
                elif platform == 'instagram':
                    url = f"https://www.instagram.com/{clean_identifier}"
                elif platform == 'tiktok':
                    url = f"https://www.tiktok.com/@{clean_identifier}"
                elif platform == 'facebook':
                    url = f"https://www.facebook.com/{clean_identifier}"
                else:
                    url = f"https://{platform}.com/{clean_identifier}"
                
                accounts_list.append({
                    'platform': platform,
                    'name': platform_names.get(platform, platform.capitalize()),
                    'url': url,
                    'icon': platform_icons.get(platform, '')
                })
        
        # ========== بناء قائمة الروابط المخصصة ==========
        custom_links_list = []
        for link in custom_links:
            custom_links_list.append({
                'title': link.get('title', 'رابط مخصص'),
                'url': link.get('url', '#')
            })
        
        # الحصول على اسم الثيم (افتراضي إذا لم يكن موجوداً)
        theme_name = bio.get('theme_name', 'default')
        
        # ========== تقديم الصفحة ==========
        return render_template(
            'bio_page.html',
            display_name=bio['display_name'],
            username=user_info.get('username', ''),
            bio=bio.get('bio', ''),
            accounts=accounts_list,
            custom_links=custom_links_list,
            avatar_url=bio.get('avatar_url', None),
            views_count=bio.get('views_count', 0),
            theme_name=theme_name,
            user_id=bio['user_id'],
            is_premium=(user_info.get('status') == 'premium'),
            RENDER_URL=RENDER_URL
        )
        
    except Exception as e:
        logger.error(f"Error in bio_page: {e}")
        return f"Internal error: {e}", 500

# =================================================================================
# القسم 6: واجهة برمجة التطبيقات (API Endpoints)
# =================================================================================

@app.route('/api/save_theme', methods=['POST'])
def save_theme():
    """
    API لحفظ ثيم صفحة البايو
    ملاحظة: هذه الواجهة تم تعطيلها لأسباب أمنية
    سيتم تغيير الثيم فقط من خلال البوت
    """
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        theme_name = data.get('theme_name')
        
        if not user_id or not theme_name:
            return jsonify({'status': 'error', 'message': 'بيانات ناقصة'}), 400
        
        # التحقق من أن القالب موجود
        valid_themes = ['default', 'dark']
        if theme_name not in valid_themes:
            return jsonify({'status': 'error', 'message': 'قالب غير صالح'}), 400
        
        # ========== التحقق من ملكية المستخدم للصفحة ==========
        # نتحقق من أن المستخدم هو صاحب الصفحة قبل تغيير الثيم
        bio = supabase.table('bio_pages').select('*').eq('user_id', user_id).execute()
        
        if not bio.data:
            return jsonify({'status': 'error', 'message': 'لم يتم العثور على صفحة البايو'}), 404
        
        # تحديث قاعدة البيانات
        result = supabase.table('bio_pages').update({
            'theme_name': theme_name,
            'updated_at': datetime.now().isoformat()
        }).eq('user_id', user_id).execute()
        
        if result.data:
            logger.info(f"✅ Theme updated for user {user_id} to {theme_name}")
            return jsonify({'status': 'ok', 'message': 'تم حفظ الثيم بنجاح'})
        else:
            return jsonify({'status': 'error', 'message': 'لم يتم العثور على صفحة البايو'}), 404
            
    except Exception as e:
        logger.error(f"Error in save_theme: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

# =================================================================================
# القسم 7: خدمة الملفات الثابتة (Static Files)
# =================================================================================

@app.route('/static/themes/<path:filename>')
def serve_theme(filename):
    """خدمة ملفات الثيمات من مجلد themes"""
    return send_from_directory('static/themes', filename)

@app.route('/static/<path:filename>')
def serve_static(filename):
    """خدمة الملفات الثابتة العامة (CSS, JS, Images)"""
    return send_from_directory('static', filename)

# =================================================================================
# القسم 8: معالجة الأخطاء (Error Handlers)
# =================================================================================

@app.errorhandler(404)
def not_found(error):
    """صفحة خطأ 404 - غير موجود"""
    return jsonify({"error": "Page not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    """صفحة خطأ 500 - خطأ داخلي"""
    logger.error(f"Internal server error: {error}")
    return jsonify({"error": "Internal server error"}), 500

# =================================================================================
# القسم 9: تشغيل التطبيق (Main Entry Point)
# =================================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Flask Server for Social Media Analyzer Bot")
    print(f"📁 Static files served from: /static/")
    print(f"🎨 Themes served from: /static/themes/")
    print(f"📄 Bio page available at: /bio/<page_url>")
    print(f"💳 Payment page available at: /payment")
    print(f"🌐 Running on port: {PORT}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=PORT, debug=False)
