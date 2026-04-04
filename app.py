# -*- coding: utf-8 -*-
"""
Flask Server for Social Media Analyzer Bot
"""

import os
import sys
import logging
from flask import Flask, render_template, request, jsonify

# إضافة مجلد utils إلى المسار
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils.db import get_bio_page_by_url, get_user_info, increment_bio_views
from utils.helpers import escape_html

# إعدادات logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
PORT = int(os.environ.get('PORT', 10000))
FREE_LIMIT = int(os.environ.get('FREE_LIMIT', '5'))


@app.route('/')
@app.route('/health')
@app.route('/healthcheck')
def health():
    """فحص صحة الخادم"""
    return "OK", 200


@app.route('/payment')
def payment_page():
    """صفحة الدفع الموحدة"""
    try:
        return render_template('payment.html', free_limit=FREE_LIMIT)
    except Exception as e:
        logger.error(f"Payment page error: {e}")
        return f"Error loading payment page: {e}", 500


@app.route('/bio/<page_url>')
def bio_page(page_url):
    """صفحة البايو الشخصية"""
    try:
        logger.info(f"🔍 Bio page requested: {page_url}")
        
        bio = get_bio_page_by_url(page_url)
        if not bio:
            logger.warning(f"❌ Bio not found: {page_url}")
            return "Page not found", 404
        
        user_info = get_user_info(bio['user_id'])
        if not user_info:
            logger.warning(f"❌ User not found: {bio['user_id']}")
            return "User not found", 404
        
        # زيادة عدد المشاهدات
        increment_bio_views(page_url)
        
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
        
        accounts_list = []
        for platform, acc in accounts.items():
            identifier = acc.get('account_identifier', '')
            if identifier:
                if identifier.startswith('@'):
                    identifier = identifier[1:]
                accounts_list.append({
                    'platform': platform,
                    'name': platform_names.get(platform, platform.capitalize()),
                    'url': f"https://{platform}.com/{identifier}",
                    'icon': platform_icons.get(platform, '')
                })
        
        custom_links_list = []
        for link in custom_links:
            custom_links_list.append({
                'title': link.get('title', 'رابط مخصص'),
                'url': link.get('url', '#')
            })
        
        # استخدام القالب بدلاً من HTML المضمن
        return render_template(
            'bio_page.html',
            display_name=bio['display_name'],
            username=user_info.get('username', ''),
            bio=bio.get('bio', ''),
            accounts=accounts_list,
            custom_links=custom_links_list
        )
        
    except Exception as e:
        logger.error(f"Error in bio_page: {e}")
        return f"Internal error: {e}", 500
@app.route('/api/save_theme', methods=['POST'])
def save_theme():
    """API لحفظ ثيم صفحة البايو"""
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
        
        # تحديث قاعدة البيانات
        from utils.db import supabase
        from datetime import datetime
        
        result = supabase.table('bio_pages').update({
            'theme_name': theme_name,
            'updated_at': datetime.now().isoformat()
        }).eq('user_id', user_id).execute()
        
        if result.data:
            return jsonify({'status': 'ok', 'message': 'تم حفظ الثيم بنجاح'})
        else:
            return jsonify({'status': 'error', 'message': 'لم يتم العثور على صفحة البايو'}), 404
            
    except Exception as e:
        logger.error(f"Error in save_theme: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT, debug=False)
