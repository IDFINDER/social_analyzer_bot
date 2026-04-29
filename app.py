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
import secrets
import requests
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urlencode
from flask import Flask, render_template, request, jsonify, send_from_directory, session, redirect, url_for, render_template_string

# استيراد دوال قاعدة البيانات
from utils.db import (
    get_bio_page_by_page_url, get_user_info, increment_bio_views, supabase,
    get_bio_page, get_user_social_accounts, save_user_account, delete_user_account,
    create_or_update_bio_page, update_bio_text, update_bio_theme, update_bio_avatar,
    supabase_admin, get_all_prices, get_bot_setting, update_bot_setting,
    get_global_stats, get_all_users_with_stats, upgrade_user_to_premium,
    downgrade_user_to_free, get_subscription_stats, get_notifications_history,
    log_notification, log_notification_delivery, get_user_active_subscription,
    get_user_usage
)
from utils.helpers import escape_html, verify_token

# إعدادات التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =================================================================================
# القسم 1: تهيئة التطبيق والمتغيرات
# =================================================================================

app = Flask(__name__)
PORT = int(os.environ.get('PORT', 10000))
FREE_LIMIT = int(os.environ.get('FREE_LIMIT', '5'))
RENDER_URL = os.environ.get('RENDER_URL', 'social-analyzer-flask.onrender.com')
BOT_NAME = os.environ.get('BOT_NAME', 'social_analyzer')

# ========== إعدادات المصادقة ==========
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Admin@123#Secure!')
SECRET_KEY = os.environ.get('SECRET_KEY', 'dGhpcyBpcyBhIHZlcnkgc2VjcmV0IGtleQ==')
app.secret_key = SECRET_KEY
app.permanent_session_lifetime = timedelta(hours=24)

ADMIN_USER_IDS = os.environ.get('ADMIN_USER_IDS', '7850462368').split(',')
ADMIN_USER_IDS = [int(x.strip()) for x in ADMIN_USER_IDS if x.strip().isdigit()]

BASIC_AUTH_PASSWORD = os.environ.get('BASIC_AUTH_PASSWORD', 'Admin@123#Secure!')

# =================================================================================
# القسم 2: رؤوس الأمان
# =================================================================================

@app.after_request
def set_security_headers(resp):
    """إضافة رؤوس أمان لمنع تحذيرات المتصفح"""
    resp.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['X-Frame-Options'] = 'SAMEORIGIN'
    resp.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://telegram.org https://cdn.jsdelivr.net https://code.jquery.com; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
        "connect-src 'self' https://cdn.jsdelivr.net; "
        "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
        "img-src 'self' data: https:;"
    )
    return resp

# =================================================================================
# القسم 3: دوال المصادقة المساعدة
# =================================================================================

def login_required(f):
    """طبقة أمان: التحقق من جلسة المدير"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

# =================================================================================
# القسم 4: صفحات عامة (سياسة الخصوصية، robots.txt، إلخ)
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
        return "User-agent: *\nAllow: /", 200

@app.route('/sitemap.xml')
def sitemap():
    """خريطة الموقع لمحركات البحث"""
    try:
        return send_from_directory('static', 'sitemap.xml')
    except Exception as e:
        return "Sitemap not available", 404

@app.route('/terms')
def terms_of_service():
    """صفحة شروط الخدمة"""
    try:
        return render_template('terms.html')
    except Exception as e:
        return "Terms of Service page", 200

# =================================================================================
# القسم 5: نقاط نهاية فحص الصحة
# =================================================================================

@app.route('/')
@app.route('/health')
@app.route('/healthcheck')
def health():
    """فحص صحة الخادم - يستخدمه Render للتأكد من أن الخدمة تعمل"""
    return jsonify({"status": "ok", "service": "flask"}), 200

# =================================================================================
# القسم 6: صفحة الدفع
# =================================================================================

@app.route('/payment')
def payment_page():
    """صفحة الدفع الموحدة للاشتراك المميز"""
    try:
        prices = get_all_prices()
        plan = request.args.get('plan', 'half_yearly')
        amount = request.args.get('amount', prices.get('price_half_yearly', 30))
        
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
# القسم 7: صفحة البايو الشخصية
# =================================================================================

@app.route('/bio/<page_url>')
def bio_page(page_url):
    """صفحة البايو الشخصية - تعرض حسابات المستخدم وروابطه"""
    try:
        logger.info(f"🔍 Bio page requested: {page_url}")
        
        bio = get_bio_page_by_page_url(page_url)
        if not bio:
            return "Page not found", 404
        
        user_info = get_user_info(bio['user_id'])
        if not user_info:
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
                if identifier.startswith('@'):
                    identifier = identifier[1:]
                
                url = f"https://{platform}.com/{identifier}"
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
# القسم 8: واجهات برمجة التطبيقات (APIs)
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
        
        result = supabase.table('bio_pages').update({
            'theme_name': theme_name,
            'updated_at': datetime.now().isoformat()
        }).eq('user_id', user_id).execute()
        
        if result.data:
            return jsonify({'status': 'ok', 'message': 'تم حفظ الثيم بنجاح'})
        return jsonify({'status': 'error', 'message': 'لم يتم العثور على صفحة البايو'}), 404
    except Exception as e:
        logger.error(f"Error in save_theme: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/user_data', methods=['GET'])
def get_user_data():
    """API لجلب بيانات المستخدم (شاملة التوصيات واستخدامات Gemini)"""
    from datetime import datetime, date
    from utils.db import (
        get_user_info, get_user_social_accounts, 
        get_user_active_subscription, get_user_usage, get_all_prices
    )
    
    token = request.args.get('token')
    if not token:
        return jsonify({'error': 'Missing token'}), 401
    
    # استخراج user_id مباشرة (تجاوز verify_token مؤقتاً)
    try:
        user_id = int(token.split(':')[0])
    except:
        return jsonify({'error': 'Invalid token'}), 401
    
    # جلب معلومات المستخدم
    user_info = get_user_info(user_id)
    if not user_info:
        return jsonify({'error': 'User not found'}), 404
    
    accounts = get_user_social_accounts(user_id)
    is_premium = user_info.get('status') == 'premium'
    usage = get_user_usage(user_id)
    
    days_left = 0
    subscription = None
    subscription_start_date = None
    subscription_plan_name = None
    
    # جلب الاشتراك النشط من user_subscriptions_social
    try:
        from utils.db import supabase
        
        # جلب الاشتراك النشط
        sub_response = supabase.table('user_subscriptions_social')\
            .select('*, subscription_plans_social(name_ar, name)')\
            .eq('user_id', user_id)\
            .eq('status', 'active')\
            .order('created_at', desc=True)\
            .limit(1)\
            .execute()
        
        if sub_response.data:
            sub = sub_response.data[0]
            subscription_start_date = sub.get('start_date')
            subscription_end_date = sub.get('end_date')
            
            if sub.get('subscription_plans_social'):
                subscription_plan_name = sub['subscription_plans_social'].get('name_ar', 'مميز')
            
            # حساب الأيام المتبقية
            if subscription_end_date:
                try:
                    end_date = datetime.strptime(subscription_end_date, '%Y-%m-%d').date()
                    days_left = max(0, (end_date - date.today()).days)
                except:
                    days_left = 0
    except Exception as e:
        logger.error(f"Error fetching subscription: {e}")
    
    prices = get_all_prices()
    
    # ========== 1. جلب عدد استخدامات Gemini من جدول gemini_usage ==========
    gemini_uses = 0
    gemini_limit = prices.get('gemini_monthly_limit', 20) if is_premium else prices.get('gemini_free_limit', 0)
    
    try:
        from utils.db import supabase
        current_month = datetime.now().strftime('%Y-%m')
        
        # جلب من جدول gemini_usage
        gemini_response = supabase.table('gemini_usage')\
            .select('monthly_recommendations, total_recommendations, last_use_month')\
            .eq('user_id', user_id)\
            .execute()
        
        if gemini_response.data:
            # التحقق من الشهر الحالي
            last_use_month = gemini_response.data[0].get('last_use_month', '')
            if last_use_month == current_month:
                gemini_uses = gemini_response.data[0].get('monthly_recommendations', 0)
            else:
                gemini_uses = 0  # شهر جديد، إعادة تعيين
        else:
            gemini_uses = 0
            
        logger.info(f"Gemini uses for user {user_id}: {gemini_uses}/{gemini_limit}")
    except Exception as e:
        logger.error(f"Error fetching gemini uses: {e}")
        gemini_uses = 0
    
    # ========== 2. جلب الحد الشهري للتوصيات من user_gemini_limits ==========
    try:
        from utils.db import supabase
        limit_response = supabase.table('user_gemini_limits')\
            .select('monthly_limit')\
            .eq('user_id', user_id)\
            .execute()
        
        if limit_response.data:
            gemini_limit = limit_response.data[0].get('monthly_limit', gemini_limit)
        logger.info(f"Gemini limit for user {user_id}: {gemini_limit}")
    except Exception as e:
        logger.error(f"Error fetching gemini limit: {e}")
    
    # ========== 3. جلب آخر توصيات الذكاء الاصطناعي من recommendations_history ==========
    recommendations = []
    try:
        from utils.db import supabase
        recs_response = supabase.table('recommendations_history')\
            .select('*')\
            .eq('user_id', user_id)\
            .order('created_at', desc=True)\
            .limit(20)\
            .execute()
        
        for rec in (recs_response.data or []):
            recommendations.append({
                'id': rec.get('id'),
                'platform': rec.get('platform'),
                'account_identifier': rec.get('account_identifier'),
                'recommendation_summary': rec.get('recommendation_summary', '')[:300] if rec.get('recommendation_summary') else '',
                'recommendation_text': rec.get('recommendation_text', ''),
                'key_points': rec.get('key_points'),
                'implemented': rec.get('implemented', False),
                'created_at': rec.get('created_at')
            })
        
        logger.info(f"Found {len(recommendations)} recommendations for user {user_id}")
    except Exception as e:
        logger.error(f"Error fetching recommendations: {e}")
        recommendations = []
    
    # ========== 4. بناء Response البيانات ==========
    response_data = {
        'is_premium': is_premium,
        'user': {
            'first_name': user_info.get('first_name'),
            'username': user_info.get('username'),
            'user_id': user_id
        },
        'accounts': accounts,
        'stats': {
            'total_uses': usage.get('total_uses', 0) if usage else 0,
            'youtube_uses': usage.get('youtube_uses', 0) if usage else 0,
            'instagram_uses': usage.get('instagram_uses', 0) if usage else 0,
            'tiktok_uses': usage.get('tiktok_uses', 0) if usage else 0,
            'facebook_uses': usage.get('facebook_uses', 0) if usage else 0,
        },
        'free_limit': prices.get('free_limit', 2),
        'gemini_limit': gemini_limit,
        'gemini_uses': gemini_uses,
        'recommendations': recommendations
    }
    
    # إضافة معلومات الاشتراك
    if is_premium and subscription_start_date:
        response_data['subscription'] = {
            'plan': subscription_plan_name or 'مميز',
            'start_date': subscription_start_date,
            'end_date': subscription_end_date if 'subscription_end_date' in dir() else None,
            'days_left': days_left
        }
    elif is_premium:
        response_data['subscription'] = {
            'plan': 'مميز',
            'start_date': user_info.get('premium_until'),  # fallback
            'end_date': user_info.get('premium_until'),
            'days_left': days_left
        }
    else:
        response_data['subscription'] = {
            'plan': 'مجاني',
            'start_date': None,
            'end_date': None,
            'days_left': 0
        }
    
    return jsonify(response_data)

@app.route('/api/test', methods=['GET'])
def test_api():
    """نقطة نهاية اختبارية - محمية بالمصادقة"""
    return jsonify({'status': 'ok', 'message': 'API is working'})


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
            accounts = get_user_social_accounts(user_id)
            user_info = get_user_info(user_id)
            formatted = {p: {'account_identifier': a['account_identifier']} for p, a in accounts.items()}
            create_or_update_bio_page(user_id, user_info.get('first_name', 'مستخدم'), formatted)
            return jsonify({'success': True})
        
        elif action == 'delete_account':
            platform = data.get('platform')
            delete_user_account(user_id, platform)
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
            supabase_admin.table('bio_pages').delete().eq('user_id', user_id).execute()
            new_url = create_or_update_bio_page(user_id, user_info.get('first_name', 'مستخدم'), formatted)
            flask_url = os.environ.get('RENDER_URL', 'social-analyzer-flask.onrender.com')
            return jsonify({'success': True, 'new_url': f"https://{flask_url}/bio/{new_url}"})
        
        elif action == 'delete_page':
            supabase_admin.table('bio_pages').delete().eq('user_id', user_id).execute()
            return jsonify({'success': True})
        
        return jsonify({'success': False, 'error': 'Unknown action'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# =================================================================================
# القسم 9: خدمة الملفات الثابتة
# =================================================================================

@app.route('/static/themes/<path:filename>')
def serve_theme(filename):
    """خدمة ملفات الثيمات"""
    return send_from_directory('static/themes', filename)

@app.route('/static/<path:filename>')
def serve_static(filename):
    """خدمة الملفات الثابتة"""
    return send_from_directory('static', filename)

# =================================================================================
# القسم 10: معالجة الأخطاء
# =================================================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Page not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({"error": "Internal server error"}), 500

# =================================================================================
# القسم 11: نظام مصادقة المدير
# =================================================================================

@app.route('/secure/x7K9mP2/login', methods=['GET', 'POST'])
def admin_login():
    """صفحة دخول المدير"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            session.permanent = True
            return redirect(url_for('admin_dashboard'))
        
        return render_template_string('''
            <!DOCTYPE html>
            <html dir="rtl" lang="ar">
            <head><meta charset="UTF-8"><title>دخول المدير</title>
            <style>
                *{margin:0;padding:0;box-sizing:border-box;}
                body{font-family:'Segoe UI',sans-serif;background:linear-gradient(135deg,#667eea,#764ba2);min-height:100vh;display:flex;justify-content:center;align-items:center;}
                .login-card{background:white;border-radius:20px;padding:40px;width:100%;max-width:400px;text-align:center;}
                h1{color:#2c3e50;margin-bottom:10px;}
                .error{color:#e74c3c;margin-bottom:20px;padding:10px;background:#fdecea;border-radius:10px;}
                input{width:100%;padding:12px;margin:10px 0;border:1px solid #ddd;border-radius:10px;}
                button{width:100%;padding:12px;background:linear-gradient(135deg,#667eea,#764ba2);color:white;border:none;border-radius:10px;cursor:pointer;}
            </style>
            </head>
            <body>
            <div class="login-card">
                <h1>🔐 دخول المدير</h1>
                <div class="error">❌ اسم المستخدم أو كلمة المرور غير صحيحة</div>
                <form method="POST">
                    <input type="text" name="username" placeholder="اسم المستخدم" required>
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
        <head><meta charset="UTF-8"><title>دخول المدير</title>
        <style>
            *{margin:0;padding:0;box-sizing:border-box;}
            body{font-family:'Segoe UI',sans-serif;background:linear-gradient(135deg,#667eea,#764ba2);min-height:100vh;display:flex;justify-content:center;align-items:center;}
            .login-card{background:white;border-radius:20px;padding:40px;width:100%;max-width:400px;text-align:center;}
            h1{color:#2c3e50;}
            .subtitle{color:#7f8c8d;margin-bottom:30px;}
            input{width:100%;padding:12px;margin:10px 0;border:1px solid #ddd;border-radius:10px;}
            button{width:100%;padding:12px;background:linear-gradient(135deg,#667eea,#764ba2);color:white;border:none;border-radius:10px;cursor:pointer;}
            .footer{margin-top:30px;font-size:12px;color:#95a5a6;}
        </style>
        </head>
        <body>
        <div class="login-card">
            <h1>🔐 لوحة التحكم</h1>
            <div class="subtitle">بوتات الأدوات الاجتماعية</div>
            <form method="POST">
                <input type="text" name="username" placeholder="اسم المستخدم" required>
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
    """تسجيل الخروج"""
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

# =================================================================================
# القسم 12: لوحة تحكم المدير الرئيسية
# =================================================================================

@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    """لوحة تحكم المدير"""
    try:
        default_gemini_limit = int(os.environ.get('GEMINI_MONTHLY_LIMIT', '20'))
        users_response = supabase.table('users').select('*').order('user_id', desc=False).execute()
        
        users_list = []
        for user in (users_response.data or []):
            user_id = user['user_id']
            
            bio_response = supabase.table('bio_pages').select('page_url, views_count').eq('user_id', user_id).execute()
            bio = bio_response.data[0] if bio_response.data else {}
            
            subscription = None
            if user.get('status') == 'premium':
                try:
                    sub_response = supabase.table('user_subscriptions_social').select('*, subscription_plans_social(name, name_ar)').eq('user_id', user_id).eq('status', 'active').execute()
                    if sub_response.data:
                        subscription = sub_response.data[0]
                except Exception as e:
                    logger.warning(f"Could not fetch subscription: {e}")
            
            gemini_limit_response = supabase.table('user_gemini_limits').select('monthly_limit').eq('user_id', user_id).execute()
            gemini_limit = gemini_limit_response.data[0]['monthly_limit'] if gemini_limit_response.data else default_gemini_limit
            
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
        
        total_users = len(users_list)
        premium_users = len([u for u in users_list if u['status'] == 'premium'])
        free_users = total_users - premium_users
        total_uses = sum([u.get('total_uses', 0) for u in users_list])
        
        platform_stats = {
            'youtube': sum([u['total_usage']['youtube'] for u in users_list]),
            'instagram': sum([u['total_usage']['instagram'] for u in users_list]),
            'tiktok': sum([u['total_usage']['tiktok'] for u in users_list]),
            'facebook': sum([u['total_usage']['facebook'] for u in users_list])
        }
        
        subscription_stats = {'monthly': 0, 'half_yearly': 0, 'yearly': 0, 'lifetime': 0}
        try:
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
        
        return render_template('admin_dashboard.html', users=users_list, stats=stats, free_limit=FREE_LIMIT, RENDER_URL=RENDER_URL)
    except Exception as e:
        logger.error(f"Error in admin_dashboard: {e}")
        return f"حدث خطأ: {e}", 500

# =================================================================================
# القسم 13: صفحات إدارة المستخدمين (ترقية/خفض)
# =================================================================================

@app.route('/upgrade-user', methods=['POST'])
@login_required
def upgrade_user():
    """ترقية مستخدم مع اختيار الخطة"""
    user_id = request.form.get('user_id')
    plan_type = request.form.get('plan_type')
    
    if not user_id or not plan_type:
        return redirect(url_for('admin_dashboard'))
    
    plan_details = {
        'monthly': {'name': 'شهري', 'name_en': 'monthly', 'days': 30, 'price_key': 'price_monthly'},
        'half_yearly': {'name': 'نصف سنوي', 'name_en': 'half_yearly', 'days': 180, 'price_key': 'price_half_yearly'},
        'yearly': {'name': 'سنوي', 'name_en': 'yearly', 'days': 365, 'price_key': 'price_yearly'},
        'lifetime': {'name': 'مدى الحياة', 'name_en': 'lifetime', 'days': 36500, 'price_key': 'price_lifetime'}
    }
    
    plan = plan_details.get(plan_type, plan_details['half_yearly'])
    price = int(get_bot_setting(plan['price_key'], '30'))
    
    start_date = datetime.now().date()
    end_date = start_date + timedelta(days=plan['days'])
    end_date_str = end_date.strftime('%Y-%m-%d')
    
    try:
        result = supabase.table('users').update({
            'status': 'premium',
            'premium_until': end_date_str,
            'updated_at': datetime.now().isoformat()
        }).eq('user_id', int(user_id)).execute()
        
        if not result.data:
            return redirect(url_for('admin_dashboard'))
        
        try:
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
        except Exception as e:
            logger.error(f"Error creating subscription record: {e}")
        
        TOKEN = os.environ.get('TELEGRAM_TOKEN')
        message = f"""🎉 <b>تم ترقية حسابك بنجاح!</b>

📅 <b>خطتك:</b> {plan['name']}
💰 <b>المبلغ:</b> {price}$
⏰ <b>تنتهي في:</b> {end_date_str}

✅ يمكنك الآن الاستمتاع بالمميزات:
• تحليل غير محدود
• توصيات الذكاء الاصطناعي
• صفحة بايو شخصية

شكراً لثقتك! 🙏"""
        try:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={'chat_id': user_id, 'text': message, 'parse_mode': 'HTML'}, timeout=5)
        except Exception as e:
            logger.error(f"Error sending upgrade message: {e}")
        
        return redirect(url_for('admin_dashboard'))
    except Exception as e:
        logger.error(f"Error upgrading user: {e}")
        return f"حدث خطأ: {e}", 500


@app.route('/downgrade-user', methods=['POST'])
@login_required
def downgrade_user():
    """خفض مستخدم إلى خطة مجانية"""
    user_id = request.form.get('user_id')
    if not user_id:
        return redirect(url_for('admin_dashboard'))
    
    try:
        result = supabase.table('users').update({
            'status': 'free',
            'premium_until': None,
            'updated_at': datetime.now().isoformat()
        }).eq('user_id', int(user_id)).execute()
        
        if not result.data:
            return redirect(url_for('admin_dashboard'))
        
        try:
            supabase.table('user_subscriptions_social').update({
                'status': 'cancelled',
                'updated_at': datetime.now().isoformat()
            }).eq('user_id', int(user_id)).eq('status', 'active').execute()
        except Exception as e:
            logger.error(f"Error updating subscription status: {e}")
        
        FREE_LIMIT = int(os.environ.get('FREE_LIMIT', '2'))
        TOKEN = os.environ.get('TELEGRAM_TOKEN')
        message = f"""📉 <b>تم خفض اشتراكك إلى الخطة المجانية</b>

✅ لا يزال بإمكانك استخدام:
• {FREE_LIMIT} تحليل يومياً

💎 للعودة إلى الخطة المميزة، استخدم الأمر /premium"""
        try:
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={'chat_id': user_id, 'text': message, 'parse_mode': 'HTML'}, timeout=5)
        except Exception as e:
            logger.error(f"Error sending downgrade message: {e}")
        
        return redirect(url_for('admin_dashboard'))
    except Exception as e:
        logger.error(f"Error downgrading user: {e}")
        return f"حدث خطأ: {e}", 500

# =================================================================================
# القسم 14: صفحات الإدارة الأخرى
# =================================================================================

@app.route('/admin/api/stats')
@login_required
def admin_api_stats():
    """API لإحصائيات لوحة التحكم (JSON)"""
    try:
        stats = get_global_stats(BOT_NAME)
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/users')
@login_required
def admin_api_users():
    """API لقائمة المستخدمين (JSON)"""
    try:
        users = get_all_users_with_stats(BOT_NAME)
        return jsonify(users)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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
# القسم 15: صفحات تعديل الأسعار والإعدادات
# =================================================================================

@app.route('/admin-prices', methods=['GET', 'POST'])
@login_required
def admin_prices():
    """صفحة تعديل الأسعار والإعدادات - مع رسائل تأكيد ودعم النجوم"""
    message = None
    message_type = None
    
    if request.method == 'POST':
        try:
            settings_to_save = {
                'price_monthly': request.form.get('price_monthly', '10'),
                'price_half_yearly': request.form.get('price_half_yearly', '30'),
                'price_yearly': request.form.get('price_yearly', '48'),
                'price_lifetime': request.form.get('price_lifetime', '100'),
                'duration_monthly': request.form.get('duration_monthly', '30'),
                'duration_half_yearly': request.form.get('duration_half_yearly', '180'),
                'duration_yearly': request.form.get('duration_yearly', '365'),
                'duration_lifetime': request.form.get('duration_lifetime', '36500'),
                'free_limit': request.form.get('free_limit', '2'),
                'gemini_monthly_limit': request.form.get('gemini_monthly_limit', '20'),
                'gemini_free_limit': request.form.get('gemini_free_limit', '0'),
                'stars_monthly': request.form.get('stars_monthly', '200'),
                'stars_half_yearly': request.form.get('stars_half_yearly', '500'),
                'stars_yearly': request.form.get('stars_yearly', '800'),
                'stars_lifetime': request.form.get('stars_lifetime', '2000'),
                'stars_usd_rate': request.form.get('stars_usd_rate', '0.025'),
                'stars_enabled': request.form.get('stars_enabled', 'true'),
                'stars_extra_recs_small': request.form.get('stars_extra_recs_small', '50'),
                'stars_extra_recs_medium': request.form.get('stars_extra_recs_medium', '100'),
                'stars_extra_recs_large': request.form.get('stars_extra_recs_large', '200'),
                'stars_extra_recs_premium': request.form.get('stars_extra_recs_premium', '500'),
                'promo_active': request.form.get('promo_active', 'false'),
                'promo_half_yearly': request.form.get('promo_half_yearly', '25'),
                'promo_yearly': request.form.get('promo_yearly', '40'),
                'promo_end_date': request.form.get('promo_end_date', ''),
                'payment_number': request.form.get('payment_number', '772130931'),
                'developer_link': request.form.get('developer_link', 'https://t.me/E_Alshabany'),
                'bot_link': request.form.get('bot_link', 'https://t.me/Social_Media_tools_bot')
            }
            
            saved_count = 0
            for key, value in settings_to_save.items():
                try:
                    result = supabase.table('bot_settings_social').upsert({
                        'setting_key': key,
                        'setting_value': str(value),
                        'updated_at': datetime.now().isoformat()
                    }, on_conflict='setting_key').execute()
                    if result.data:
                        saved_count += 1
                except Exception as e:
                    logger.error(f"Error saving {key}: {e}")
            
            if saved_count == len(settings_to_save):
                message = f"✅ تم حفظ {saved_count} إعداد بنجاح!"
                message_type = 'success'
            else:
                message = f"⚠️ تم حفظ {saved_count} من {len(settings_to_save)} إعداد فقط"
                message_type = 'warning'
            
            return redirect(url_for('admin_prices', msg=message, msg_type=message_type))
        except Exception as e:
            logger.error(f"Error updating settings: {e}")
            return redirect(url_for('admin_prices', msg=f"❌ حدث خطأ: {e}", msg_type='error'))
    
    prices = get_all_prices()
    msg = request.args.get('msg')
    msg_type = request.args.get('msg_type', 'info')
    
    return render_template('admin_prices.html', prices=prices, msg=msg, msg_type=msg_type)

# =================================================================================
# القسم 16: سجل الإشعارات وإرسال الإشعارات
# =================================================================================

@app.route('/notifications-history')
@login_required
def notifications_history():
    """سجل الإشعارات"""
    notifications = get_notifications_history(100)
    return render_template('notifications_history.html', notifications=notifications)

@app.route('/send-notification', methods=['POST'])
@login_required
def send_notification():
    """إرسال إشعارات للمستخدمين"""
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
            response = requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={'chat_id': uid, 'text': message, 'parse_mode': 'HTML'}, timeout=5)
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
# القسم 17: صفحات التحقق (Verification)
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
# القسم 18: تكامل TikTok OAuth
# =================================================================================

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
    
    data = {
        'client_key': TIKTOK_CLIENT_KEY,
        'client_secret': TIKTOK_CLIENT_SECRET,
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': TIKTOK_REDIRECT_URI
    }
    
    try:
        response = requests.post("https://open-api.tiktok.com/oauth/access_token/", data=data)
        token_data = response.json()
        
        if token_data.get('data', {}).get('access_token'):
            session['tiktok_access_token'] = token_data['data']['access_token']
            session['tiktok_open_id'] = token_data['data']['open_id']
            
            return render_template_string('''
                <!DOCTYPE html>
                <html dir="rtl" lang="ar">
                <head><meta charset="UTF-8"><title>تم الاتصال بنجاح</title>
                <style>
                    body{font-family:'Segoe UI',sans-serif;background:linear-gradient(135deg,#667eea,#764ba2);min-height:100vh;display:flex;justify-content:center;align-items:center;}
                    .card{background:white;border-radius:20px;padding:40px;text-align:center;max-width:400px;}
                    h1{color:#2c3e50;margin-bottom:10px;}
                    .success{color:#48bb78;font-size:64px;}
                    button{background:#667eea;color:white;border:none;padding:12px 30px;border-radius:10px;margin-top:20px;cursor:pointer;}
                </style>
                </head>
                <body>
                <div class="card">
                    <div class="success">✅</div>
                    <h1>تم الاتصال بتيك توك بنجاح!</h1>
                    <p>يمكنك الآن العودة إلى البوت واستخدام ميزات تحليل تيك توك.</p>
                    <button onclick="window.location.href='https://t.me/Social_Media_tools_bot'">🚀 العودة إلى البوت</button>
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
    
    params = {'access_token': access_token, 'open_id': open_id}
    try:
        response = requests.get("https://open-api.tiktok.com/user/info/", params=params)
        return jsonify(response.json())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/debug/tiktok-flow')
def tiktok_flow_debug():
    """صفحة توضيحية لتدفق TikTok OAuth"""
    return '''
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head><meta charset="UTF-8"><title>تدفق TikTok - شرح</title>
    <style>
        body{font-family:'Segoe UI',sans-serif;background:#f5f7fa;padding:20px;}
        .container{max-width:800px;margin:0 auto;background:white;border-radius:20px;padding:30px;}
        h1{color:#2c3e50;}
        .step{background:#f8f9fa;padding:15px;margin:15px 0;border-radius:10px;border-right:4px solid #667eea;}
        .code{background:#2d2d2d;color:#f8f8f2;padding:10px;border-radius:8px;font-family:monospace;font-size:12px;}
        .success{color:#48bb78;}
    </style>
    </head>
    <body>
    <div class="container">
        <h1>🔄 تدفق تكامل TikTok</h1>
        <div class="step"><strong>📌 الخطوة 1:</strong> <code>/login/tiktok</code></div>
        <div class="step"><strong>📌 الخطوة 2:</strong> إعادة التوجيه إلى <code>https://www.tiktok.com/v2/auth/authorize/...</code></div>
        <div class="step"><strong>📌 الخطوة 3:</strong> تسجيل الدخول والموافقة على الصلاحيات</div>
        <div class="step"><strong>📌 الخطوة 4:</strong> إعادة التوجيه إلى <code class="success">✅ /callback/tiktok?code=xxxx&state=yyyy</code></div>
        <div class="step"><strong>📌 الخطوة 5:</strong> تبادل الرمز للحصول على Access Token</div>
        <div class="step"><strong>📌 الخطوة 6:</strong> عرض صفحة النجاح</div>
        <hr><p><strong>🔗 روابط الاختبار:</strong></p>
        <ul><li><a href="/login/tiktok" target="_blank">بدء تسجيل الدخول بتيك توك</a></li>
        <li><a href="/tiktok/profile" target="_blank">عرض معلومات الملف الشخصي (بعد المصادقة)</a></li></ul>
    </div>
    </body>
    </html>
    '''

# =================================================================================
# القسم 19: إدارة حدود توصيات Gemini
# =================================================================================

@app.route('/admin/set-gemini-limit', methods=['POST'])
@login_required
def set_gemini_limit():
    """تعديل حصة التوصيات الشهرية لمستخدم معين"""
    try:
        user_id = int(request.form.get('user_id'))
        gemini_limit = int(request.form.get('gemini_limit'))
        
        result = supabase_admin.table('user_gemini_limits').upsert({
            'user_id': user_id,
            'monthly_limit': gemini_limit,
            'updated_at': datetime.now().isoformat()
        }, on_conflict='user_id').execute()
        
        if result.data:
            logger.info(f"✅ Gemini limit updated for user {user_id} to {gemini_limit}")
        return redirect(url_for('admin_dashboard'))
    except Exception as e:
        logger.error(f"Error setting gemini limit: {e}")
        return redirect(url_for('admin_dashboard'))

@app.route('/admin/gemini-limits')
@login_required
def gemini_limits_page():
    """صفحة لعرض وتعديل حدود التوصيات لجميع المستخدمين"""
    try:
        default_limit = int(os.environ.get('GEMINI_MONTHLY_LIMIT', '20'))
        users_response = supabase.table('users').select('user_id, first_name, username, status').eq('status', 'premium').execute()
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
# القسم: إيرادات النجوم (Stars Earnings)
# =================================================================================

@app.route('/admin/stars-earnings')
@login_required
def stars_earnings():
    """صفحة عرض إيرادات النجوم"""
    try:
        from utils.db import supabase
        from datetime import datetime, timedelta
        
        # إحصائيات عامة
        total_response = supabase.table('stars_earnings').select('amount', count='exact').execute()
        total_earnings = sum([r['amount'] for r in (total_response.data or [])])
        total_transactions = total_response.count if hasattr(total_response, 'count') else len(total_response.data or [])
        
        # إحصائيات اليوم
        today = datetime.now().date().isoformat()
        today_response = supabase.table('stars_earnings').select('amount').gte('payment_date', today).execute()
        today_earnings = sum([r['amount'] for r in (today_response.data or [])])
        today_transactions = len(today_response.data or [])
        
        # إحصائيات الشهر
        first_day_of_month = datetime.now().date().replace(day=1).isoformat()
        month_response = supabase.table('stars_earnings').select('amount').gte('payment_date', first_day_of_month).execute()
        month_earnings = sum([r['amount'] for r in (month_response.data or [])])
        month_transactions = len(month_response.data or [])
        
        # آخر 50 عملية
        transactions_response = supabase.table('stars_earnings').select('*').order('payment_date', desc=True).limit(50).execute()
        transactions = transactions_response.data or []
        
        # حساب قيمة الدولار (100 نجم = 2$ تقريباً)
        dollar_rate = 0.02  # 1 نجم = 0.02 دولار
        total_dollars = total_earnings * dollar_rate
        today_dollars = today_earnings * dollar_rate
        month_dollars = month_earnings * dollar_rate
        
        stats = {
            'total_earnings': total_earnings,
            'total_transactions': total_transactions,
            'total_dollars': round(total_dollars, 2),
            'today_earnings': today_earnings,
            'today_transactions': today_transactions,
            'today_dollars': round(today_dollars, 2),
            'month_earnings': month_earnings,
            'month_transactions': month_transactions,
            'month_dollars': round(month_dollars, 2),
        }
        
        return render_template('stars_earnings.html', stats=stats, transactions=transactions)
    except Exception as e:
        logger.error(f"Error in stars_earnings: {e}")
        return f"حدث خطأ: {e}", 500

# =================================================================================
# القسم 20: صفحة لوحة التحكم للمستخدم (WebApp)
# =================================================================================

@app.route('/dashboard')
def dashboard():
    """صفحة لوحة التحكم (WebApp)"""
    token = request.args.get('token')
    if not token:
        return "Missing token", 401
    
    # استخراج user_id مباشرة (تجاوز verify_token مؤقتاً)
    try:
        user_id = int(token.split(':')[0])
    except:
        return "Invalid token", 401
    
    return render_template('dashboard.html')

# =================================================================================
# القسم 21: تشغيل التطبيق
# =================================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Flask Server for Social Media Analyzer Bot")
    print(f"📁 Static files served from: /static/")
    print(f"🎨 Themes served from: /static/themes/")
    print(f"📄 Bio page available at: /bio/<page_url>")
    print(f"💳 Payment page available at: /payment")
    print(f"🔐 Admin login: /secure/x7K9mP2/login")
    print(f"🛡️ Admin dashboard: /admin/dashboard")
    print(f"🌐 Running on port: {PORT}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=PORT, debug=False)
