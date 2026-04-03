# -*- coding: utf-8 -*-
"""
Flask Server for Social Media Analyzer Bot
"""

import os
import sys
import logging
from flask import Flask, render_template

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
            return f"Page not found: {page_url}", 404
        
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
        
        html = f"""
<!DOCTYPE html>
<html lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escape_html(bio['display_name'])} | صفحة البايو</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 30px;
        }}
        .container {{ max-width: 550px; margin: 0 auto; }}
        .card {{
            background: white;
            border-radius: 25px;
            padding: 35px 25px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.2);
            text-align: center;
        }}
        .avatar {{
            width: 100px;
            height: 100px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 50%;
            margin: 0 auto 20px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 45px;
            color: white;
        }}
        .name {{ font-size: 28px; font-weight: bold; color: #2c3e50; margin-bottom: 5px; }}
        .username {{ font-size: 14px; color: #7f8c8d; margin-bottom: 25px; }}
        .divider {{ height: 1px; background: #e0e0e0; margin: 20px 0; }}
        .account-btn {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 12px;
            width: 85%;
            margin: 12px auto;
            padding: 12px 20px;
            border-radius: 50px;
            text-decoration: none;
            font-size: 16px;
            font-weight: 500;
            transition: all 0.3s ease;
            color: white;
        }}
        .account-btn:hover {{ transform: translateY(-2px); opacity: 0.9; box-shadow: 0 5px 15px rgba(0,0,0,0.2); }}
        .account-icon {{ width: 24px; height: 24px; }}
        .youtube {{ background: #ff0000; }}
        .instagram {{ background: #e4405f; }}
        .tiktok {{ background: #000000; }}
        .facebook {{ background: #1877f2; }}
        .custom-link {{ background: #667eea; }}
        .footer {{ text-align: center; margin-top: 25px; font-size: 13px; color: white; }}
        .footer a {{ color: #ffd700; text-decoration: none; font-weight: bold; }}
        @media (max-width: 600px) {{
            body {{ padding: 15px; }}
            .card {{ padding: 25px 15px; }}
            .name {{ font-size: 24px; }}
            .account-btn {{ width: 95%; padding: 10px 15px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <div class="avatar">👤</div>
            <div class="name">{escape_html(bio['display_name'])}</div>
            <div class="username">@{escape_html(user_info.get('username', ''))}</div>
            {f'<div class="divider"></div>' if accounts_list else ''}
"""
        
        for acc in accounts_list:
            html += f"""
            <a href="{acc['url']}" class="account-btn {acc['platform']}" target="_blank">
                <img src="{acc['icon']}" class="account-icon" alt="{acc['name']}">
                {acc['name']}
            </a>
"""
        
        for link in custom_links:
            html += f"""
            <a href="{link.get('url', '#')}" class="account-btn custom-link" target="_blank">
                🔗 {escape_html(link.get('title', 'رابط مخصص'))}
            </a>
"""
        
        html += f"""
        </div>
        <div class="footer">
            لإنشاء صفحة بايو مثل هذه <a href="https://t.me/Social_Media_tools_bot" target="_blank">اضغط هنا وانتقل للبوت</a>
        </div>
    </div>
</body>
</html>
"""
        return html
        
    except Exception as e:
        logger.error(f"Error in bio_page: {e}")
        return f"Internal error: {e}", 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=PORT, debug=False)
