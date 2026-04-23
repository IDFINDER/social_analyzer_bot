# -*- coding: utf-8 -*-
"""
================================================================================
اسم الملف: app.py
الوصف: خادم Flask لخدمة صفحات البايو وصفحة الدفع ولوحة التحكم
المشروع: Social Media Analyzer Bot
المطور: @E_Alshabany
التاريخ: 2026
================================================================================
"""

import os
import sys
import logging
from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for, render_template_string
from datetime import datetime, timedelta
from functools import wraps

# =================================================================================
# القسم 1: إعدادات المسارات والمكتبات
# =================================================================================

# إضافة مجلد utils إلى المسار
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils.db import (
    get_bio_page_by_page_url, 
    get_user_info, 
    increment_bio_views, 
    supabase,
    get_bio_page,
    get_user_social_accounts,
    save_user_account,
    delete_user_account,
    create_or_update_bio_page,
    update_bio_text,
    update_bio_theme,
    update_bio_avatar,
    supabase_admin
)
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
BOT_NAME = os.environ.get('BOT_NAME', 'social_analyzer')

# ========== إعدادات المصادحة المتقدمة ==========
# طبقة الأمان 1: جلسة المدير (Session)
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Admin@123#Secure!')
SECRET_KEY = os.environ.get('SECRET_KEY', 'dGhpcyBpcyBhIHZlcnkgc2VjcmV0IGtleQ==')
app.secret_key = SECRET_KEY
app.permanent_session_lifetime = timedelta(hours=24)

# طبقة الأمان 2: القائمة البيضاء لأرقام المستخدمين المسموح لهم
ADMIN_USER_IDS = os.environ.get('ADMIN_USER_IDS', '7850462368').split(',')
ADMIN_USER_IDS = [int(x.strip()) for x in ADMIN_USER_IDS if x.strip().isdigit()]

# طبقة الأمان 3: Basic Authentication (كلمة مرور إضافية)
BASIC_AUTH_PASSWORD = os.environ.get('BASIC_AUTH_PASSWORD', 'Admin@123#Secure!')

# =================================================================================
# القسم 3: رؤوس الأمان (Security Headers)
# =================================================================================

@app.after_request
def set_security_headers(resp):
    """إضافة رؤوس أمان لمنع تحذيرات المتصفح"""
    resp.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['X-Frame-Options'] = 'SAMEORIGIN'
    resp.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net https://code.jquery.com 'unsafe-inline'; style-src 'self' 'unsafe-inline'; font-src 'self' https://fonts.gstatic.com;"
    return resp
    
# =================================================================================
# القسم 4: دوال المصادحة المساعدة
# =================================================================================


def login_required(f):
    """
    طبقة أمان: التحقق من جلسة المدير
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# =================================================================================
# القسم: صفحات سياسة الخصوصية و robots.txt
# =================================================================================

@app.route('/privacy')
def privacy_policy():
    """صفحة سياسة الخصوصية"""
    try:
        return render_template('privacy.html')
    except Exception as e:
        logger.error(f"Error in privacy page: {e}")
        return "Privacy policy page", 200

@app.route('/robots.txt')
def robots_txt():
    """ملف robots.txt لمحركات البحث"""
    try:
        return send_from_directory('static', 'robots.txt')
    except Exception as e:
        logger.error(f"Error serving robots.txt: {e}")
        return "User-agent: *\nAllow: /", 200

@app.route('/sitemap.xml')
def sitemap():
    """خريطة الموقع لمحركات البحث"""
    from flask import send_from_directory
    try:
        return send_from_directory('static', 'sitemap.xml')
    except Exception as e:
        logger.error(f"Error serving sitemap: {e}")
        return "Sitemap not available", 404

@app.route('/terms')
def terms_of_service():
    """صفحة شروط الخدمة"""
    try:
        return render_template('terms.html')
    except Exception as e:
        logger.error(f"Error in terms page: {e}")
        return "Terms of Service page", 200             
# =================================================================================
# القسم 5: نقاط نهاية فحص الصحة (Health Checks)
# =================================================================================

@app.route('/')
@app.route('/health')
@app.route('/healthcheck')
def health():
    """فحص صحة الخادم - يستخدمه Render للتأكد من أن الخدمة تعمل"""
    return jsonify({"status": "ok", "service": "flask"}), 200

# =================================================================================
# القسم 6: صفحة الدفع (Payment Page)
# =================================================================================

@app.route('/payment')
def payment_page():
    """صفحة الدفع الموحدة للاشتراك المميز"""
    try:
        from utils.db import get_all_prices
        prices = get_all_prices()
        
        # الحصول على الخطة المختارة من المعاملات (GET)
        plan = request.args.get('plan', 'half_yearly')
        amount = request.args.get('amount', prices.get('price_half_yearly', 30))
        
        # تحديد تفاصيل الخطة
        plan_details = {
            'monthly': {'name': 'شهري', 'price': prices.get('price_monthly', 10)},
            'half_yearly': {'name': 'نصف سنوي', 'price': prices.get('price_half_yearly', 30)},
            'yearly': {'name': 'سنوي', 'price': prices.get('price_yearly', 48)},
            'lifetime': {'name': 'مدى الحياة', 'price': prices.get('price_lifetime', 100)}
        }
        
        current_plan = plan_details.get(plan, plan_details['half_yearly'])
        
        return render_template('payment.html', 
                              free_limit=FREE_LIMIT,
                              prices=prices,
                              plan=current_plan,
                              selected_plan=plan,
                              amount=amount)
    except Exception as e:
        logger.error(f"Payment page error: {e}")
        return f"Error loading payment page: {e}", 500

# =================================================================================
# القسم 7: صفحة البايو الشخصية (Bio Page)
# =================================================================================

@app.route('/bio/<page_url>')
def bio_page(page_url):
    """
    صفحة البايو الشخصية
    تعرض حسابات المستخدم وروابطه في صفحة واحدة جميلة
    """
    try:
        logger.info(f"🔍 Bio page requested: {page_url}")
        
        bio = get_bio_page_by_page_url(page_url)
        if not bio:
            logger.warning(f"❌ Bio not found: {page_url}")
            return "Page not found", 404
        
        user_info = get_user_info(bio['user_id'])
        if not user_info:
            logger.warning(f"❌ User not found: {bio['user_id']}")
            return "User not found", 404
        
        increment_bio_views(page_url)
        
        accounts = bio.get('accounts', {})
        custom_links = bio.get('custom_links', [])
        
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
                clean_identifier = identifier
                if clean_identifier.startswith('@'):
                    clean_identifier = clean_identifier[1:]
                
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
        
        custom_links_list = []
        for link in custom_links:
            custom_links_list.append({
                'title': link.get('title', 'رابط مخصص'),
                'url': link.get('url', '#')
            })
        
        theme_name = bio.get('theme_name', 'default')
        
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
# القسم: WebApp لإعدادات صفحة البايو
# =================================================================================
        
@app.route('/webapp/api/action', methods=['POST'])
def webapp_action():
    """API لتنفيذ الإجراءات من WebApp"""
    try:
        user_id = int(request.headers.get('X-Telegram-User-Id', 0))
        if not user_id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        
        data = request.get_json()
        action = data.get('action')
        
        if action == 'update_name':
            new_name = data.get('name')
            supabase.table('users').update({'first_name': new_name}).eq('user_id', user_id).execute()
            # تحديث صفحة البايو
            accounts = get_user_social_accounts(user_id)
            formatted = {p: {'account_identifier': a['account_identifier']} for p, a in accounts.items()}
            create_or_update_bio_page(user_id, new_name, formatted)
            return jsonify({'success': True})
        
        elif action == 'update_bio':
            new_bio = data.get('bio')
            update_bio_text(user_id, new_bio)
            return jsonify({'success': True})
        
        elif action == 'update_theme':
            theme = data.get('theme')
            update_bio_theme(user_id, theme)
            return jsonify({'success': True})
        
        elif action == 'add_account':
            platform = data.get('platform')
            identifier = data.get('identifier')
            save_user_account(user_id, platform, identifier)
            # تحديث صفحة البايو
            accounts = get_user_social_accounts(user_id)
            user_info = get_user_info(user_id)
            formatted = {p: {'account_identifier': a['account_identifier']} for p, a in accounts.items()}
            create_or_update_bio_page(user_id, user_info.get('first_name', 'مستخدم'), formatted)
            return jsonify({'success': True})
        
        elif action == 'delete_account':
            platform = data.get('platform')
            delete_user_account(user_id, platform)
            # تحديث صفحة البايو
            accounts = get_user_social_accounts(user_id)
            user_info = get_user_info(user_id)
            formatted = {p: {'account_identifier': a['account_identifier']} for p, a in accounts.items()}
            create_or_update_bio_page(user_id, user_info.get('first_name', 'مستخدم'), formatted)
            return jsonify({'success': True})
        
        elif action == 'reset_page':
            update_bio_text(user_id, '')
            update_bio_avatar(user_id, None)
            return jsonify({'success': True})
        
        elif action == 'reset_url':
            accounts = get_user_social_accounts(user_id)
            user_info = get_user_info(user_id)
            formatted = {p: {'account_identifier': a['account_identifier']} for p, a in accounts.items()}
            # حذف الصفحة القديمة
            from utils.db import supabase_admin
            supabase_admin.table('bio_pages').delete().eq('user_id', user_id).execute()
            # إنشاء صفحة جديدة
            new_url = create_or_update_bio_page(user_id, user_info.get('first_name', 'مستخدم'), formatted)
            flask_url = os.environ.get('RENDER_URL', 'social-analyzer-flask.onrender.com')
            return jsonify({'success': True, 'new_url': f"https://{flask_url}/bio/{new_url}"})
        
        elif action == 'delete_page':
            from utils.db import supabase_admin
            supabase_admin.table('bio_pages').delete().eq('user_id', user_id).execute()
            return jsonify({'success': True})
        
        return jsonify({'success': False, 'error': 'Unknown action'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
# =================================================================================
# القسم 8: واجهة برمجة التطبيقات (API Endpoints)
# =================================================================================

@app.route('/api/save_theme', methods=['POST'])
def save_theme():
    """API لحفظ ثيم صفحة البايو"""
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        theme_name = data.get('theme_name')
        
        if not user_id or not theme_name:
            return jsonify({'status': 'error', 'message': 'بيانات ناقصة'}), 400
        
        valid_themes = ['default', 'dark']
        if theme_name not in valid_themes:
            return jsonify({'status': 'error', 'message': 'قالب غير صالح'}), 400
        
        bio = supabase.table('bio_pages').select('*').eq('user_id', user_id).execute()
        if not bio.data:
            return jsonify({'status': 'error', 'message': 'لم يتم العثور على صفحة البايو'}), 404
        
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
# القسم 9: خدمة الملفات الثابتة (Static Files)
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
# القسم 10: معالجة الأخطاء (Error Handlers)
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
# القسم 11: نظام المصادحة المتقدم (Advanced Authentication)
# =================================================================================

@app.route('/secure/x7K9mP2/login', methods=['GET', 'POST'])
def admin_login():
    """صفحة دخول المدير - الطبقة الأولى"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            session.permanent = True
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template_string('''
                <!DOCTYPE html>
                <html dir="rtl" lang="ar">
                <head>
                    <meta charset="UTF-8">
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <title>دخول المدير</title>
                    <style>
                        * { margin: 0; padding: 0; box-sizing: border-box; }
                        body {
                            font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            min-height: 100vh;
                            display: flex;
                            justify-content: center;
                            align-items: center;
                        }
                        .login-card {
                            background: white;
                            border-radius: 20px;
                            padding: 40px;
                            width: 100%;
                            max-width: 400px;
                            box-shadow: 0 20px 40px rgba(0,0,0,0.2);
                            text-align: center;
                        }
                        h1 { color: #2c3e50; margin-bottom: 10px; }
                        .error { color: #e74c3c; margin-bottom: 20px; padding: 10px; background: #fdecea; border-radius: 10px; }
                        input {
                            width: 100%;
                            padding: 12px 15px;
                            margin: 10px 0;
                            border: 1px solid #ddd;
                            border-radius: 10px;
                            font-size: 16px;
                            font-family: inherit;
                        }
                        input:focus { outline: none; border-color: #667eea; }
                        button {
                            width: 100%;
                            padding: 12px;
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            color: white;
                            border: none;
                            border-radius: 10px;
                            font-size: 16px;
                            cursor: pointer;
                            margin-top: 10px;
                        }
                        button:hover { opacity: 0.9; transform: scale(1.02); }
                    </style>
                </head>
                <body>
                    <div class="login-card">
                        <h1>🔐 دخول المدير</h1>
                        <p style="color: #7f8c8d; margin-bottom: 20px;">أدخل بيانات الدخول</p>
                        <div class="error">❌ اسم المستخدم أو كلمة المرور غير صحيحة</div>
                        <form method="POST">
                            <input type="text" name="username" placeholder="اسم المستخدم" required autofocus>
                            <input type="password" name="password" placeholder="كلمة المرور" required>
                            <button type="submit">دخول</button>
                        </form>
                    </div>
                </body>
                </html>
            ''', 401)
    
    return render_template_string('''
        <!DOCTYPE html>
        <html dir="rtl" lang="ar">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>دخول المدير</title>
            <style>
                * { margin: 0; padding: 0; box-sizing: border-box; }
                body {
                    font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                }
                .login-card {
                    background: white;
                    border-radius: 20px;
                    padding: 40px;
                    width: 100%;
                    max-width: 400px;
                    box-shadow: 0 20px 40px rgba(0,0,0,0.2);
                    text-align: center;
                }
                h1 { color: #2c3e50; margin-bottom: 10px; }
                .subtitle { color: #7f8c8d; margin-bottom: 30px; font-size: 14px; }
                input {
                    width: 100%;
                    padding: 12px 15px;
                    margin: 10px 0;
                    border: 1px solid #ddd;
                    border-radius: 10px;
                    font-size: 16px;
                    font-family: inherit;
                    transition: all 0.3s;
                }
                input:focus { outline: none; border-color: #667eea; box-shadow: 0 0 0 3px rgba(102,126,234,0.1); }
                button {
                    width: 100%;
                    padding: 12px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    border: none;
                    border-radius: 10px;
                    font-size: 16px;
                    cursor: pointer;
                    margin-top: 20px;
                    transition: all 0.3s;
                }
                button:hover { opacity: 0.9; transform: scale(1.02); }
                .footer { margin-top: 30px; font-size: 12px; color: #95a5a6; }
            </style>
        </head>
        <body>
            <div class="login-card">
                <h1>🔐 لوحة التحكم</h1>
                <div class="subtitle">بوتات الأدوات الاجتماعية</div>
                <form method="POST">
                    <input type="text" name="username" placeholder="اسم المستخدم" required autofocus>
                    <input type="password" name="password" placeholder="كلمة المرور" required>
                    <button type="submit">دخول</button>
                </form>
                <div class="footer">🔒 صفحة مخصصة للمدير فقط</div>
            </div>
        </body>
        </html>
    ''')

@app.route('/secure/x7K9mP2/logout')
def admin_logout():
    """تسجيل الخروج من لوحة التحكم"""
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

# =================================================================================
# القسم 12: لوحة التحكم الرئيسية (مع طبقات أمان متعددة)
# =================================================================================


@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    """لوحة تحكم المدير - تعتمد على users مباشرة"""
    try:
        from utils.db import supabase
        from datetime import datetime
        
        default_gemini_limit = int(os.environ.get('GEMINI_MONTHLY_LIMIT', '20'))
        
        # جلب جميع المستخدمين من users
        users_response = supabase.table('users').select('*').order('user_id', desc=False).execute()
        
        users_list = []
        for user in (users_response.data or []):
            user_id = user['user_id']
            
            # جلب صفحة البايو
            bio_response = supabase.table('bio_pages').select('page_url, views_count').eq('user_id', user_id).execute()
            bio = bio_response.data[0] if bio_response.data else {}
            
            # جلب الاشتراك النشط (مع حماية من الخطأ)
            subscription = None
            if user.get('status') == 'premium':
                try:
                    sub_response = supabase.table('user_subscriptions_social').select('*, subscription_plans_social(name, name_ar)').eq('user_id', user_id).eq('status', 'active').execute()
                    if sub_response.data:
                        subscription = sub_response.data[0]
                except Exception as e:
                    logger.warning(f"Could not fetch subscription for user {user_id}: {e}")
                    # لا نوقف العملية، نستمر بدون بيانات الاشتراك
            
            # جلب gemini_limit
            gemini_limit_response = supabase.table('user_gemini_limits').select('monthly_limit').eq('user_id', user_id).execute()
            gemini_limit = gemini_limit_response.data[0]['monthly_limit'] if gemini_limit_response.data else default_gemini_limit
            
            # جلب gemini_used
            current_month = datetime.now().strftime('%Y-%m')
            gemini_used_response = supabase.table('gemini_usage').select('monthly_recommendations').eq('user_id', user_id).eq('last_use_month', current_month).execute()
            gemini_used = gemini_used_response.data[0]['monthly_recommendations'] if gemini_used_response.data else 0
            
            users_list.append({
                'user_id': user_id,
                'first_name': user.get('first_name', ''),
                'username': user.get('username', ''),
                'status': user.get('status', 'free'),
                'created_at': user.get('created_at', ''),
                'bio_page_url': bio.get('page_url'),
                'bio_views': bio.get('views_count', 0),
                'total_usage': {
                    'youtube': user.get('youtube_uses', 0),
                    'instagram': user.get('instagram_uses', 0),
                    'tiktok': user.get('tiktok_uses', 0),
                    'facebook': user.get('facebook_uses', 0)
                },
                'daily_uses': user.get('daily_uses', 0),
                'subscription_plan': subscription.get('subscription_plans_social', {}).get('name_ar', '-') if subscription else '-',
                'subscription_end_date': subscription.get('end_date', '-') if subscription else '-',
                'subscription_start_date': subscription.get('start_date', '-') if subscription else '-',
                'gemini_limit': gemini_limit,
                'gemini_used': gemini_used
            })
        
        # إحصائيات عامة
        total_users = len(users_list)
        premium_users = len([u for u in users_list if u['status'] == 'premium'])
        free_users = total_users - premium_users
        total_uses = sum([u.get('total_uses', 0) for u in users_list])
        
        # إحصائيات المنصات
        platform_stats = {
            'youtube': sum([u['total_usage']['youtube'] for u in users_list]),
            'instagram': sum([u['total_usage']['instagram'] for u in users_list]),
            'tiktok': sum([u['total_usage']['tiktok'] for u in users_list]),
            'facebook': sum([u['total_usage']['facebook'] for u in users_list])
        }
        
        # إحصائيات الاشتراكات (محاولة جلبها بأمان)
        subscription_stats = {'monthly': 0, 'half_yearly': 0, 'yearly': 0, 'lifetime': 0}
        try:
            # إذا كان جدول user_subscriptions_social موجوداً
            subs_response = supabase.table('user_subscriptions_social').select('plan_id').eq('status', 'active').execute()
            if subs_response.data:
                for sub in subs_response.data:
                    plan_response = supabase.table('subscription_plans_social').select('name').eq('id', sub['plan_id']).execute()
                    if plan_response.data:
                        plan_name = plan_response.data[0]['name']
                        if plan_name == 'monthly':
                            subscription_stats['monthly'] += 1
                        elif plan_name == 'half_yearly':
                            subscription_stats['half_yearly'] += 1
                        elif plan_name == 'yearly':
                            subscription_stats['yearly'] += 1
                        elif plan_name == 'lifetime':
                            subscription_stats['lifetime'] += 1
        except Exception as e:
            logger.warning(f"Could not fetch subscription stats: {e}")
        
        stats = {
            'total_users': total_users,
            'premium_users': premium_users,
            'free_users': free_users,
            'total_uses': total_uses,
            'total_bio_pages': len([u for u in users_list if u.get('bio_page_url')]),
            'total_bio_views': sum([u.get('bio_views', 0) for u in users_list]),
            'platform_stats': platform_stats,
            'subscription_stats': subscription_stats,
            'total_gemini_uses': sum([u.get('gemini_used', 0) for u in users_list]),
            'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        return render_template('admin_dashboard.html', 
                              users=users_list, 
                              stats=stats, 
                              free_limit=FREE_LIMIT,
                              RENDER_URL=os.environ.get('RENDER_URL', 'social-analyzer-flask.onrender.com'))
        
    except Exception as e:
        logger.error(f"Error in admin_dashboard: {e}")
        return f"حدث خطأ: {e}", 500
# =================================================================================
# مسار ترقية المستخدم مع اختيار الخطة
# =================================================================================

@app.route('/upgrade-user', methods=['POST'])
@login_required
def upgrade_user():
    """ترقية مستخدم مع اختيار الخطة"""
    user_id = request.form.get('user_id')
    plan_type = request.form.get('plan_type')
    
    if not user_id or not plan_type:
        return redirect(url_for('admin_dashboard'))
    
    from utils.db import get_bot_setting
    from utils.db import supabase
    from datetime import datetime, timedelta
    import requests
    
    # تحديد الخطة
    plan_details = {
        'monthly': {'name': 'شهري', 'name_en': 'monthly', 'days': 30, 'price_key': 'price_monthly'},
        'half_yearly': {'name': 'نصف سنوي', 'name_en': 'half_yearly', 'days': 180, 'price_key': 'price_half_yearly'},
        'yearly': {'name': 'سنوي', 'name_en': 'yearly', 'days': 365, 'price_key': 'price_yearly'},
        'lifetime': {'name': 'مدى الحياة', 'name_en': 'lifetime', 'days': 36500, 'price_key': 'price_lifetime'}
    }
    
    plan = plan_details.get(plan_type, plan_details['half_yearly'])
    
    # جلب السعر من قاعدة البيانات
    price = int(get_bot_setting(plan['price_key'], '30'))
    
    # حساب تاريخ الانتهاء
    start_date = datetime.now().date()
    end_date = start_date + timedelta(days=plan['days'])
    end_date_str = end_date.strftime('%Y-%m-%d')
    
    try:
        # ========== 1. تحديث جدول users مباشرة ==========
        result = supabase.table('users').update({
            'status': 'premium',
            'premium_until': end_date_str,
            'updated_at': datetime.now().isoformat()
        }).eq('user_id', int(user_id)).execute()
        
        if not result.data:
            logger.error(f"User {user_id} not found in users table")
            return redirect(url_for('admin_dashboard'))
        
        # ========== 2. تسجيل الاشتراك في جدول user_subscriptions_social ==========
        try:
            # جلب معرف الخطة من جدول الخطط
            plan_response = supabase.table('subscription_plans_social').select('id').eq('name', plan['name_en']).execute()
            plan_id = plan_response.data[0]['id'] if plan_response.data else None
            
            if plan_id:
                supabase.table('user_subscriptions_social').insert({
                    'user_id': int(user_id),
                    'plan_id': plan_id,
                    'status': 'active',
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'payment_amount': price,
                    'created_at': datetime.now().isoformat()
                }).execute()
                logger.info(f"✅ Subscription record created for user {user_id}")
            else:
                logger.warning(f"Plan {plan['name_en']} not found in subscription_plans_social")
        except Exception as e:
            logger.error(f"Error creating subscription record: {e}")
            # لا نوقف العملية إذا فشل تسجيل الاشتراك
        
        # ========== 3. إرسال رسالة تأكيد للمستخدم ==========
        TOKEN = os.environ.get('TELEGRAM_TOKEN')
        message = f"""🎉 <b>تم ترقية حسابك بنجاح!</b>

📅 <b>خطتك:</b> {plan['name']}
💰 <b>المبلغ:</b> {price}$
⏰ <b>تنتهي في:</b> {end_date_str}

✅ يمكنك الآن الاستمتاع بالمميزات:
• تحليل غير محدود
• توصيات الذكاء الاصطناعي
• صفحة بايو شخصية

شكراً لثقتك! 🙏
"""
        try:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                         data={'chat_id': user_id, 'text': message, 'parse_mode': 'HTML'}, timeout=5)
            logger.info(f"✅ Upgrade message sent to user {user_id}")
        except Exception as e:
            logger.error(f"Error sending upgrade message: {e}")
        
        return redirect(url_for('admin_dashboard'))
        
    except Exception as e:
        logger.error(f"Error upgrading user {user_id}: {e}")
        return f"حدث خطأ: {e}", 500


# =================================================================================
# مسار خفض المستخدم
# =================================================================================

@app.route('/downgrade-user', methods=['POST'])
@login_required
def downgrade_user():
    """خفض مستخدم إلى خطة مجانية"""
    user_id = request.form.get('user_id')
    
    if not user_id:
        return redirect(url_for('admin_dashboard'))
    
    from utils.db import supabase
    from datetime import datetime
    import requests
    
    try:
        # ========== 1. تحديث جدول users مباشرة ==========
        result = supabase.table('users').update({
            'status': 'free',
            'premium_until': None,
            'updated_at': datetime.now().isoformat()
        }).eq('user_id', int(user_id)).execute()
        
        if not result.data:
            logger.error(f"User {user_id} not found in users table")
            return redirect(url_for('admin_dashboard'))
        
        logger.info(f"✅ User {user_id} downgraded to free in users table")
        
        # ========== 2. تحديث حالة الاشتراك في جدول user_subscriptions_social ==========
        try:
            supabase.table('user_subscriptions_social').update({
                'status': 'cancelled',
                'updated_at': datetime.now().isoformat()
            }).eq('user_id', int(user_id)).eq('status', 'active').execute()
            logger.info(f"✅ Subscription record updated for user {user_id}")
        except Exception as e:
            logger.error(f"Error updating subscription status: {e}")
            # لا نوقف العملية إذا فشل تحديث الاشتراك
        
        # ========== 3. إرسال رسالة للمستخدم ==========
        FREE_LIMIT = int(os.environ.get('FREE_LIMIT', '2'))
        TOKEN = os.environ.get('TELEGRAM_TOKEN')
        message = f"""📉 <b>تم خفض اشتراكك إلى الخطة المجانية</b>

✅ لا يزال بإمكانك استخدام:
• {FREE_LIMIT} تحليل يومياً

💎 للعودة إلى الخطة المميزة، استخدم الأمر /premium
"""
        try:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", 
                         data={'chat_id': user_id, 'text': message, 'parse_mode': 'HTML'}, timeout=5)
            logger.info(f"✅ Downgrade message sent to user {user_id}")
        except Exception as e:
            logger.error(f"Error sending downgrade message: {e}")
        
        return redirect(url_for('admin_dashboard'))
        
    except Exception as e:
        logger.error(f"Error downgrading user {user_id}: {e}")
        return f"حدث خطأ: {e}", 500
# =================================================================================
# القسم 13: APIs مساعدة (Helper APIs)
# =================================================================================

@app.route('/admin/api/stats')
@login_required
def admin_api_stats():
    """API لإحصائيات لوحة التحكم (JSON)"""
    try:
        from utils.db import get_global_stats
        stats = get_global_stats(BOT_NAME)
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/users')
@login_required
def admin_api_users():
    """API لقائمة المستخدمين (JSON)"""
    try:
        from utils.db import get_all_users_with_stats
        users = get_all_users_with_stats(BOT_NAME)
        return jsonify(users)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# =================================================================================
# القسم 14: معلومات الأمان (Security Info)
# =================================================================================

@app.route('/admin/security-info')
def security_info():
    """معلومات عن طبقات الأمان"""
    return jsonify({
        'message': 'نظام حماية لوحة التحكم',
        'security_layers': [
            {'layer': 1, 'name': 'Session Authentication', 'description': 'التحقق من جلسة المستخدم عبر اسم المستخدم وكلمة المرور'},
            {'layer': 2, 'name': 'Security Headers', 'description': 'رؤوس أمان تمنع هجمات XSS و MIME sniffing'},
            {'layer': 3, 'name': 'HTTPS', 'description': 'تشفير البيانات أثناء الإرسال عبر Render'},
        ],
        'admin_url': '/secure/x7K9mP2/login',
        'dashboard_url': '/admin/dashboard',
        'protection_level': 'عالية'
    })

# =================================================================================
# مسارات إضافية للوحة التحكم
# =================================================================================

@app.route('/admin-prices', methods=['GET', 'POST'])
@login_required
def admin_prices():
    """صفحة تعديل الأسعار والإعدادات - تعتمد على bot_settings_social"""
    from utils.db import update_bot_setting, get_all_prices
    
    if request.method == 'POST':
        try:
            # حفظ الأسعار
            update_bot_setting('price_monthly', request.form.get('price_monthly', '10'))
            update_bot_setting('price_half_yearly', request.form.get('price_half_yearly', '30'))
            update_bot_setting('price_yearly', request.form.get('price_yearly', '48'))
            update_bot_setting('price_lifetime', request.form.get('price_lifetime', '100'))
            
            # حفظ المدة
            update_bot_setting('duration_monthly', request.form.get('duration_monthly', '30'))
            update_bot_setting('duration_half_yearly', request.form.get('duration_half_yearly', '180'))
            update_bot_setting('duration_yearly', request.form.get('duration_yearly', '365'))
            update_bot_setting('duration_lifetime', request.form.get('duration_lifetime', '36500'))
            
            # حفظ الحدود
            update_bot_setting('free_limit', request.form.get('free_limit', '2'))
            update_bot_setting('gemini_monthly_limit', request.form.get('gemini_monthly_limit', '20'))
            update_bot_setting('gemini_free_limit', request.form.get('gemini_free_limit', '0'))
            
            # حفظ العروض
            update_bot_setting('promo_active', request.form.get('promo_active', 'false'))
            update_bot_setting('promo_half_yearly', request.form.get('promo_half_yearly', '25'))
            update_bot_setting('promo_yearly', request.form.get('promo_yearly', '40'))
            update_bot_setting('promo_end_date', request.form.get('promo_end_date', ''))
            
            # حفظ معلومات التواصل
            update_bot_setting('payment_number', request.form.get('payment_number', '772130931'))
            update_bot_setting('developer_link', request.form.get('developer_link', 'https://t.me/E_Alshabany'))
            update_bot_setting('bot_link', request.form.get('bot_link', 'https://t.me/Social_Media_tools_bot'))
            
            logger.info("✅ All settings updated successfully")
            return redirect(url_for('admin_prices'))
            
        except Exception as e:
            logger.error(f"Error updating settings: {e}")
            return f"حدث خطأ في حفظ الإعدادات: {e}", 500
    
    # عرض الإعدادات الحالية
    prices = get_all_prices()
    return render_template('admin_prices.html', prices=prices)


@app.route('/notifications-history')
@login_required
def notifications_history():
    """سجل الإشعارات"""
    from utils.db import get_notifications_history
    notifications = get_notifications_history(100)
    return render_template('notifications_history.html', notifications=notifications)


@app.route('/send-notification', methods=['POST'])
@login_required
def send_notification():
    """إرسال إشعارات للمستخدمين"""
    import requests
    from utils.db import log_notification, log_notification_delivery
    
    data = request.get_json()
    target = data.get('target')
    user_id = data.get('user_id')
    message = data.get('message')
    
    if not message:
        return jsonify({'success': False, 'message': 'الرسالة مطلوبة'})
    
    TOKEN = os.environ.get('TELEGRAM_TOKEN')
    users_to_notify = []
    
    if target == 'user' and user_id:
        users_to_notify = [int(user_id)]
        notification_type = 'individual'
        target_audience = f'user_{user_id}'
    
    elif target == 'all_premium':
        response = supabase.table('users').select('user_id').eq('status', 'premium').execute()
        users_to_notify = [u['user_id'] for u in (response.data or [])]
        notification_type = 'broadcast'
        target_audience = 'all_premium'
    
    elif target == 'free_users':
        response = supabase.table('users').select('user_id').eq('status', 'free').execute()
        users_to_notify = [u['user_id'] for u in (response.data or [])]
        notification_type = 'broadcast'
        target_audience = 'free_users'
    
    elif target in ['half_yearly', 'yearly', 'lifetime', 'monthly']:
        # جلب مستخدمي خطة معينة
        response = supabase.table('user_subscriptions_social').select('user_id, plan_id').eq('status', 'active').execute()
        plan_names = {'half_yearly': 'half_yearly', 'yearly': 'yearly', 'lifetime': 'lifetime', 'monthly': 'monthly'}
        for sub in (response.data or []):
            plan_response = supabase.table('subscription_plans_social').select('name').eq('id', sub['plan_id']).execute()
            if plan_response.data and plan_response.data[0]['name'] == plan_names.get(target):
                users_to_notify.append(sub['user_id'])
        notification_type = 'broadcast'
        target_audience = target
    
    else:
        return jsonify({'success': False, 'message': 'هدف غير صحيح'}), 400
    
    if not users_to_notify:
        return jsonify({'success': False, 'message': 'لا يوجد مستخدمين مستهدفين'}), 404
    
    notification_id = log_notification(notification_type, target_audience, int(user_id) if user_id and target == 'user' else None, message)
    
    sent_count = 0
    for uid in users_to_notify:
        try:
            api_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
            response = requests.post(api_url, data={'chat_id': uid, 'text': message, 'parse_mode': 'HTML'}, timeout=5)
            if response.status_code == 200:
                sent_count += 1
                if notification_id:
                    log_notification_delivery(notification_id, uid, 'sent')
            else:
                if notification_id:
                    log_notification_delivery(notification_id, uid, 'failed')
        except Exception as e:
            logger.error(f"Error sending to {uid}: {e}")
            if notification_id:
                log_notification_delivery(notification_id, uid, 'failed')
    
    if notification_id:
        supabase.table('notification_log_social').update({'sent_count': sent_count}).eq('id', notification_id).execute()
    
    return jsonify({'success': True, 'message': f'تم إرسال الإشعار إلى {sent_count} من {len(users_to_notify)} مستخدم'})
# =================================================================================
# القسم: صفحات التحقق (Verification Pages)
# =================================================================================

@app.route('/google4324552e195bad11.html')
def google_verification_file():
    """ملف التحقق من Google"""
    try:
        with open('static/google4324552e195bad11.html', 'r', encoding='utf-8') as f:
            content = f.read()
        return content, 200, {'Content-Type': 'text/html'}
    except Exception as e:
        return f"File not found: {e}", 404

@app.route('/tiktokqpTHen1C0AsF1UmIXCVMMc6qc8EgpOAO.txt')
def tiktok_verification():
    """ملف التحقق من TikTok"""
    try:
        with open('static/tiktokqpTHen1C0AsF1UmIXCVMMc6qc8EgpOAO.txt', 'r', encoding='utf-8') as f:
            content = f.read()
        return content, 200, {'Content-Type': 'text/plain'}
    except Exception as e:
        return f"File not found: {e}", 404

# =================================================================================
# القسم: تكامل TikTok OAuth
# =================================================================================

import secrets
import requests
from urllib.parse import urlencode

# إعدادات TikTok
TIKTOK_CLIENT_KEY = os.environ.get('TIKTOK_CLIENT_KEY', '')
TIKTOK_CLIENT_SECRET = os.environ.get('TIKTOK_CLIENT_SECRET', '')
TIKTOK_REDIRECT_URI = f"https://{RENDER_URL}/callback/tiktok"

@app.route('/login/tiktok')
def tiktok_login():
    """بدء عملية تسجيل الدخول بتيك توك"""
    if not TIKTOK_CLIENT_KEY:
        return "TikTok API not configured", 500
    
    state = secrets.token_urlsafe(32)
    session['tiktok_state'] = state
    
    params = {
        'client_key': TIKTOK_CLIENT_KEY,
        'scope': 'user.info.basic,user.info.profile,user.info.stats,video.list',
        'response_type': 'code',
        'redirect_uri': TIKTOK_REDIRECT_URI,
        'state': state
    }
    
    auth_url = f"https://www.tiktok.com/v2/auth/authorize/?{urlencode(params)}"
    return redirect(auth_url)

@app.route('/callback/tiktok')
def tiktok_callback():
    """معالج إعادة التوجيه بعد تسجيل الدخول"""
    error = request.args.get('error')
    if error:
        return f"Error: {error}", 400
    
    state = request.args.get('state')
    stored_state = session.get('tiktok_state')
    if not state or state != stored_state:
        return "Invalid state parameter", 400
    
    code = request.args.get('code')
    if not code:
        return "No authorization code received", 400
    
    token_url = "https://open-api.tiktok.com/oauth/access_token/"
    data = {
        'client_key': TIKTOK_CLIENT_KEY,
        'client_secret': TIKTOK_CLIENT_SECRET,
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': TIKTOK_REDIRECT_URI
    }
    
    try:
        response = requests.post(token_url, data=data)
        token_data = response.json()
        
        if token_data.get('data', {}).get('access_token'):
            access_token = token_data['data']['access_token']
            open_id = token_data['data']['open_id']
            
            session['tiktok_access_token'] = access_token
            session['tiktok_open_id'] = open_id
            
            return render_template_string('''
                <!DOCTYPE html>
                <html dir="rtl" lang="ar">
                <head>
                    <meta charset="UTF-8">
                    <title>تم الاتصال بنجاح</title>
                    <style>
                        body {
                            font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            min-height: 100vh;
                            display: flex;
                            justify-content: center;
                            align-items: center;
                            margin: 0;
                            padding: 20px;
                        }
                        .card {
                            background: white;
                            border-radius: 20px;
                            padding: 40px;
                            text-align: center;
                            max-width: 400px;
                            box-shadow: 0 20px 40px rgba(0,0,0,0.2);
                        }
                        h1 { color: #2c3e50; margin-bottom: 10px; }
                        .success { color: #48bb78; font-size: 64px; }
                        button {
                            background: #667eea;
                            color: white;
                            border: none;
                            padding: 12px 30px;
                            border-radius: 10px;
                            margin-top: 20px;
                            cursor: pointer;
                        }
                        button:hover { opacity: 0.9; }
                    </style>
                </head>
                <body>
                    <div class="card">
                        <div class="success">✅</div>
                        <h1>تم الاتصال بتيك توك بنجاح!</h1>
                        <p>يمكنك الآن العودة إلى البوت واستخدام ميزات تحليل تيك توك.</p>
                        <button onclick="window.location.href='https://t.me/Social_Media_tools_bot'">
                            🚀 العودة إلى البوت
                        </button>
                    </div>
                </body>
                </html>
            ''')
        else:
            return f"Error getting access token: {token_data}", 400
            
    except Exception as e:
        return f"Exception: {e}", 500

@app.route('/tiktok/profile')
def tiktok_profile():
    """جلب معلومات ملف تعريف المستخدم (بعد المصادقة)"""
    access_token = session.get('tiktok_access_token')
    open_id = session.get('tiktok_open_id')
    
    if not access_token:
        return redirect(url_for('tiktok_login'))
    
    user_info_url = "https://open-api.tiktok.com/user/info/"
    params = {
        'access_token': access_token,
        'open_id': open_id
    }
    
    try:
        response = requests.get(user_info_url, params=params)
        data = response.json()
        return jsonify(data)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/debug/tiktok-flow')
def tiktok_flow_debug():
    """صفحة توضيحية لتدفق TikTok OAuth"""
    return '''
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <title>تدفق TikTok - شرح</title>
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Arial, sans-serif;
                background: #f5f7fa;
                padding: 20px;
            }
            .container {
                max-width: 800px;
                margin: 0 auto;
                background: white;
                border-radius: 20px;
                padding: 30px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1 { color: #2c3e50; }
            .step {
                background: #f8f9fa;
                padding: 15px;
                margin: 15px 0;
                border-radius: 10px;
                border-right: 4px solid #667eea;
            }
            .code {
                background: #2d2d2d;
                color: #f8f8f2;
                padding: 10px;
                border-radius: 8px;
                font-family: monospace;
                font-size: 12px;
                overflow-x: auto;
            }
            .success { color: #48bb78; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔄 تدفق تكامل TikTok</h1>
            <p>شرح كيفية عمل المصادقة وإعادة التوجيه</p>
            
            <div class="step">
                <strong>📌 الخطوة 1: بدء المصادقة</strong><br>
                المستخدم يضغط على رابط تسجيل الدخول:<br>
                <code>/login/tiktok</code>
            </div>
            
            <div class="step">
                <strong>📌 الخطوة 2: إعادة التوجيه إلى TikTok</strong><br>
                يتم توجيه المستخدم إلى:<br>
                <code>https://www.tiktok.com/v2/auth/authorize/...</code>
            </div>
            
            <div class="step">
                <strong>📌 الخطوة 3: تسجيل الدخول والموافقة</strong><br>
                المستخدم يسجل دخوله على TikTok ويوافق على الصلاحيات
            </div>
            
            <div class="step">
                <strong>📌 الخطوة 4: إعادة التوجيه إلى callback</strong><br>
                TikTok يعيد توجيه المستخدم إلى:<br>
                <code class="success">✅ /callback/tiktok?code=xxxx&state=yyyy</code>
            </div>
            
            <div class="step">
                <strong>📌 الخطوة 5: تبادل الرمز للحصول على Access Token</strong><br>
                الخادم يرسل طلباً إلى:<br>
                <code>https://open-api.tiktok.com/oauth/access_token/</code>
            </div>
            
            <div class="step">
                <strong>📌 الخطوة 6: عرض النتيجة</strong><br>
                تظهر صفحة النجاح مع رابط العودة إلى البوت
            </div>
            
            <hr>
            <p><strong>🔗 روابط الاختبار:</strong></p>
            <ul>
                <li><a href="/login/tiktok" target="_blank">بدء تسجيل الدخول بتيك توك</a></li>
                <li><a href="/tiktok/profile" target="_blank">عرض معلومات الملف الشخصي (بعد المصادقة)</a></li>
            </ul>
        </div>
    </body>
    </html>
    '''

# =================================================================================
# القسم: إدارة حدود توصيات Gemini
# =================================================================================

@app.route('/admin/set-gemini-limit', methods=['POST'])
@login_required
def set_gemini_limit():
    """تعديل حصة التوصيات الشهرية لمستخدم معين"""
    try:
        user_id = int(request.form.get('user_id'))
        gemini_limit = int(request.form.get('gemini_limit'))
        
        from utils.db import supabase_admin
        from datetime import datetime
        
        result = supabase_admin.table('user_gemini_limits').upsert({
            'user_id': user_id,
            'monthly_limit': gemini_limit,
            'updated_at': datetime.now().isoformat()
        }, on_conflict='user_id').execute()
        
        if result.data:
            logger.info(f"✅ Gemini limit updated for user {user_id} to {gemini_limit}")
        else:
            logger.error(f"Failed to update Gemini limit for user {user_id}")
            
        return redirect(url_for('admin_dashboard'))
    except Exception as e:
        logger.error(f"Error setting gemini limit: {e}")
        return redirect(url_for('admin_dashboard'))


@app.route('/admin/gemini-limits')
@login_required
def gemini_limits_page():
    """صفحة لعرض وتعديل حدود التوصيات لجميع المستخدمين"""
    try:
        from utils.db import supabase
        from datetime import datetime
        
        default_limit = int(os.environ.get('GEMINI_MONTHLY_LIMIT', '20'))
        
        # جلب جميع المستخدمين المميزين
        users_response = supabase.table('users').select('user_id, first_name, username, status').eq('status', 'premium').execute()
        
        # جلب الحدود المخصصة
        limits_response = supabase.table('user_gemini_limits').select('user_id, monthly_limit').execute()
        user_limits = {l['user_id']: l['monthly_limit'] for l in (limits_response.data or [])}
        
        user_list = []
        for user in (users_response.data or []):
            user_list.append({
                'user_id': user['user_id'],
                'first_name': user.get('first_name', ''),
                'username': user.get('username', ''),
                'status': user.get('status', 'free'),
                'current_limit': user_limits.get(user['user_id'], default_limit)
            })
        
        return render_template('gemini_limits.html', users=user_list, default_limit=default_limit)
    except Exception as e:
        logger.error(f"Error in gemini_limits_page: {e}")
        return f"حدث خطأ: {e}", 500
# =================================================================================
# القسم 15: تشغيل التطبيق
# =================================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Flask Server for Social Media Analyzer Bot")
    print(f"📁 Static files served from: /static/")
    print(f"🎨 Themes served from: /static/themes/")
    print(f"📄 Bio page available at: /bio/<page_url>")
    print(f"💳 Payment page available at: /payment")
    print(f"🔐 Admin login: /secure/x7K9mP2/login")
    print(f"🛡️ Admin dashboard: /admin/dashboard (requires 2-factor auth)")
    print(f"🌐 Running on port: {PORT}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=PORT, debug=False)
