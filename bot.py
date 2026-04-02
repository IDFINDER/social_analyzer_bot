# -*- coding: utf-8 -*-
"""
Social Media Analyzer Bot - تحليل حسابات السوشيال ميديا
@Social_Media_tools_bot
"""

import os
import sys
import logging
import threading
import asyncio
from datetime import datetime, date, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ConversationHandler
from flask import Flask, request

# إضافة مجلد utils إلى المسار
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils.db import (
    get_or_create_user, get_user_info, get_user_usage,
    increment_usage, can_analyze, get_remaining_analyses, get_total_analyses,
    get_user_social_accounts, get_user_account, save_user_account, delete_user_account,
    can_use_gemini, increment_gemini_usage,
    get_bio_page, create_or_update_bio_page, disable_bio_page
)
from utils.youtube_analyzer import get_channel_details, format_channel_report
from utils.gemini_ai import get_channel_recommendations, get_username_recommendations
from utils.helpers import escape_html

# ========== Flask Health Check ==========
app = Flask(__name__)
PORT = int(os.environ.get('PORT', 10000))

@app.route('/')
@app.route('/health')
@app.route('/healthcheck')
def health():
    return "OK", 200

def run_flask():
    app.run(host='0.0.0.0', port=PORT, debug=False)

threading.Thread(target=run_flask, daemon=True).start()
# =========================================

# ========== متغيرات البيئة ==========
TOKEN = os.environ.get('TELEGRAM_TOKEN')
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_ANON_KEY')
BOT_NAME = os.environ.get('BOT_NAME', 'social_analyzer')
FREE_LIMIT = int(os.environ.get('FREE_LIMIT', '2'))
HUB_BOT_URL = os.environ.get('HUB_BOT_URL', 'https://t.me/SocMed_tools_bot')
ADMIN_CHAT_ID = os.environ.get('ADMIN_CHAT_ID', '7850462368')
RENDER_URL = os.environ.get('RENDER_URL', 'social-analyzer.onrender.com')

if not TOKEN or not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ خطأ: تأكد من تعيين المتغيرات المطلوبة")
    exit(1)

# إعدادات logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ========== ثوابت المحادثة ==========
(ASK_NAME, ASK_YOUTUBE, ASK_INSTAGRAM, ASK_TIKTOK, ASK_FACEBOOK) = range(5)

# تخزين مؤقت لبيانات المستخدم أثناء التسجيل
user_registration_data = {}

# ========== لوحات المفاتيح ==========

def get_main_keyboard(is_premium=False):
    """لوحة المفاتيح الرئيسية"""
    keyboard = [
        [KeyboardButton("🎯 تحليل حساباتي"), KeyboardButton("📊 إحصائياتي")],
        [KeyboardButton("📝 بياناتي"), KeyboardButton("✏️ تعديل بياناتي")],
        [KeyboardButton("💎 اشتراك مميز"), KeyboardButton("ℹ️ المساعدة")]
    ]
    if is_premium:
        keyboard.insert(2, [KeyboardButton("📄 صفحة البايو"), KeyboardButton("🔍 فحص يوزرنيم")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_analysis_keyboard():
    """لوحة اختيار منصة التحليل"""
    keyboard = [
        [InlineKeyboardButton("🎬 يوتيوب", callback_data="analyze_youtube")],
        [InlineKeyboardButton("📸 انستقرام (قريباً)", callback_data="analyze_instagram")],
        [InlineKeyboardButton("🎵 تيك توك (قريباً)", callback_data="analyze_tiktok")],
        [InlineKeyboardButton("📘 فيسبوك (قريباً)", callback_data="analyze_facebook")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_premium_keyboard():
    """لوحة الاشتراك المميز"""
    keyboard = [[InlineKeyboardButton("💎 اشتراك مميز - 10$ مدى الحياة", web_app=WebAppInfo(url=f"https://{RENDER_URL}/payment"))]]
    return InlineKeyboardMarkup(keyboard)

# ========== أوامر البوت ==========

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء البوت وتسجيل المستخدم"""
    user = update.effective_user
    
    # جلب أو إنشاء المستخدم
    user_data = get_or_create_user(
        user.id,
        user.first_name,
        user.username or "",
        user.language_code or ""
    )
    
    if not user_data:
        await update.message.reply_text("❌ حدث خطأ، يرجى المحاولة لاحقاً")
        return ConversationHandler.END
    
    # التحقق من وجود حسابات مسجلة
    accounts = get_user_social_accounts(user.id)
    
    if accounts:
    is_premium = user_data['status'] == 'premium'  # ← 4 مسافات
    remaining = get_remaining_analyses(user.id)   # ← 4 مسافات
    total = get_total_analyses(user.id)
    
    if is_premium:
        status_text = "👑 مميز"
        limit_text = "غير محدود"
    else:
        status_text = "🎁 مجاني"
        limit_text = f"{remaining}/{FREE_LIMIT}"
    
    welcome_text = f"""
🌐 **مرحباً بعودتك {user.first_name}!**

💎 **حالتك:** {status_text}
📊 **التحليلات المتبقية اليوم:** {limit_text}
📈 **إجمالي التحليلات:** {total}

📱 **حساباتك المسجلة:**
"""
    for platform, acc in accounts.items():
        welcome_text += f"• {get_platform_icon(platform)} {platform.capitalize()}: {acc['account_identifier']}\n"
    
    welcome_text += """
🎯 **ماذا تريد أن تفعل؟**
• اضغط على 🎯 تحليل حساباتي
• أو استخدم الأزرار أدناه
"""
    await update.message.reply_text(welcome_text, parse_mode='Markdown', reply_markup=get_main_keyboard(is_premium))
    return ConversationHandler.END
    else:
        # مستخدم جديد - بدء التسجيل
        await update.message.reply_text(
            f"🌐 **مرحباً بك {user.first_name} في بوت تحليل الحسابات الاجتماعية!**\n\n"
            f"📊 **ماذا يمكنني أن أفعل؟**\n"
            f"• تحليل قنوات يوتيوب\n"
            f"• تحليل حسابات انستقرام (قريباً)\n"
            f"• تحليل حسابات تيك توك (قريباً)\n"
            f"• تحليل حسابات فيسبوك (قريباً)\n\n"
            f"💰 **الخطة المجانية:** {FREE_LIMIT} تحليل يومياً\n"
            f"👑 **الخطة المميزة:** 10$ مدى الحياة (غير محدود)\n\n"
            f"📝 **لنبدأ بتسجيل بياناتك...**\n\n"
            f"ما هو الاسم الذي تريد أن أناديك به؟",
            parse_mode='Markdown'
        )
        return ASK_NAME  # ← هذا هو التغيير المهم


async def cancel_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إلغاء التسجيل"""
    user_id = update.effective_user.id
    if user_id in user_registration_data:
        del user_registration_data[user_id]
    await update.message.reply_text(
        "❌ تم إلغاء التسجيل.\n\n"
        "يمكنك البدء من جديد بإرسال /start",
        reply_markup=get_main_keyboard(False)
    )
    return ConversationHandler.END


async def ask_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال الاسم"""
    user_id = update.effective_user.id
    name = update.message.text.strip()
    
    user_registration_data[user_id] = {'display_name': name}
    
    await update.message.reply_text(
        f"✅ تم حفظ اسمك: {escape_html(name)}\n\n"
        f"📺 الآن أدخل معرف قناتك على يوتيوب أو أرسل الرابط\n"
        f"💡 مثال: @E_Alshabany أو https://youtube.com/@E_Alshabany\n\n"
        f"يمكنك الضغط على /skip لتجاوز هذه الخطوة",
        parse_mode='HTML'
    )
    return ASK_YOUTUBE


async def skip_youtube(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تجاوز إدخال يوتيوب"""
    user_id = update.effective_user.id
    if user_id in user_registration_data:
        user_registration_data[user_id]['youtube'] = None
    
    await update.message.reply_text(
        f"⏭️ تم تجاوز إضافة حساب يوتيوب\n\n"
        f"📸 الآن أدخل معرف حسابك على انستقرام أو أرسل الرابط\n"
        f"💡 مثال: @E_Alshabany\n\n"
        f"يمكنك الضغط على /skip لتجاوز هذه الخطوة"
    )
    return ASK_INSTAGRAM


async def ask_youtube(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال حساب يوتيوب"""
    user_id = update.effective_user.id
    youtube_input = update.message.text.strip()
    
    if user_id in user_registration_data:
        user_registration_data[user_id]['youtube'] = youtube_input
    
    await update.message.reply_text(
        f"✅ تم إضافة حساب يوتيوب: {escape_html(youtube_input)}\n\n"
        f"📸 الآن أدخل معرف حسابك على انستقرام أو أرسل الرابط\n"
        f"💡 مثال: @E_Alshabany\n\n"
        f"يمكنك الضغط على /skip لتجاوز هذه الخطوة",
        parse_mode='HTML'
    )
    return ASK_INSTAGRAM


async def skip_instagram(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تجاوز إدخال انستقرام"""
    user_id = update.effective_user.id
    if user_id in user_registration_data:
        user_registration_data[user_id]['instagram'] = None
    
    await update.message.reply_text(
        f"⏭️ تم تجاوز إضافة حساب انستقرام\n\n"
        f"🎵 الآن أدخل معرف حسابك على تيك توك أو أرسل الرابط\n"
        f"💡 مثال: @E_Alshabany\n\n"
        f"يمكنك الضغط على /skip لتجاوز هذه الخطوة"
    )
    return ASK_TIKTOK


async def ask_instagram(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال حساب انستقرام"""
    user_id = update.effective_user.id
    instagram_input = update.message.text.strip()
    
    if user_id in user_registration_data:
        user_registration_data[user_id]['instagram'] = instagram_input
    
    await update.message.reply_text(
        f"✅ تم إضافة حساب انستقرام: {escape_html(instagram_input)}\n\n"
        f"🎵 الآن أدخل معرف حسابك على تيك توك أو أرسل الرابط\n"
        f"💡 مثال: @E_Alshabany\n\n"
        f"يمكنك الضغط على /skip لتجاوز هذه الخطوة",
        parse_mode='HTML'
    )
    return ASK_TIKTOK


async def skip_tiktok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تجاوز إدخال تيك توك"""
    user_id = update.effective_user.id
    if user_id in user_registration_data:
        user_registration_data[user_id]['tiktok'] = None
    
    await update.message.reply_text(
        f"⏭️ تم تجاوز إضافة حساب تيك توك\n\n"
        f"📘 الآن أدخل معرف حسابك على فيسبوك أو أرسل الرابط\n"
        f"💡 مثال: @E_Alshabany\n\n"
        f"يمكنك الضغط على /skip لتجاوز هذه الخطوة"
    )
    return ASK_FACEBOOK


async def ask_tiktok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال حساب تيك توك"""
    user_id = update.effective_user.id
    tiktok_input = update.message.text.strip()
    
    if user_id in user_registration_data:
        user_registration_data[user_id]['tiktok'] = tiktok_input
    
    await update.message.reply_text(
        f"✅ تم إضافة حساب تيك توك: {escape_html(tiktok_input)}\n\n"
        f"📘 الآن أدخل معرف حسابك على فيسبوك أو أرسل الرابط\n"
        f"💡 مثال: @E_Alshabany\n\n"
        f"يمكنك الضغط على /skip لتجاوز هذه الخطوة",
        parse_mode='HTML'
    )
    return ASK_FACEBOOK


async def skip_facebook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تجاوز إدخال فيسبوك"""
    user_id = update.effective_user.id
    data = user_registration_data.get(user_id, {})
    
    # حفظ جميع الحسابات
    user = update.effective_user
    accounts_to_save = [
        ('youtube', data.get('youtube')),
        ('instagram', data.get('instagram')),
        ('tiktok', data.get('tiktok')),
        ('facebook', data.get('facebook'))
    ]
    
    for platform, identifier in accounts_to_save:
        if identifier:
            save_user_account(user.id, platform, identifier)
    
    # تنظيف البيانات المؤقتة
    if user_id in user_registration_data:
        del user_registration_data[user_id]
    
    # عرض ملخص الحسابات
    accounts = get_user_social_accounts(user.id)
    summary = f"✅ **تم تسجيل بياناتك بنجاح!**\n\n📊 **ملخص حساباتك:**\n"
    for platform, acc in accounts.items():
        summary += f"• {get_platform_icon(platform)} {platform.capitalize()}: {acc['account_identifier']}\n"
    
    summary += f"\n💰 **خطتك الحالية:** مجانية ({FREE_LIMIT} تحليل يومياً)\n"
    summary += f"💎 **للبحث غير المحدود:** /premium\n\n"
    summary += f"🎯 **للبدء، اضغط على 🎯 تحليل حساباتي**"
    
    await update.message.reply_text(summary, parse_mode='Markdown', reply_markup=get_main_keyboard(False))
    return ConversationHandler.END


async def ask_facebook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """استقبال حساب فيسبوك وإنهاء التسجيل"""
    user_id = update.effective_user.id
    facebook_input = update.message.text.strip()
    
    data = user_registration_data.get(user_id, {})
    data['facebook'] = facebook_input
    
    # حفظ جميع الحسابات
    user = update.effective_user
    accounts_to_save = [
        ('youtube', data.get('youtube')),
        ('instagram', data.get('instagram')),
        ('tiktok', data.get('tiktok')),
        ('facebook', facebook_input)
    ]
    
    for platform, identifier in accounts_to_save:
        if identifier:
            save_user_account(user.id, platform, identifier)
    
    # تنظيف البيانات المؤقتة
    if user_id in user_registration_data:
        del user_registration_data[user_id]
    
    # عرض ملخص الحسابات
    accounts = get_user_social_accounts(user.id)
    summary = f"✅ **تم تسجيل بياناتك بنجاح!**\n\n📊 **ملخص حساباتك:**\n"
    for platform, acc in accounts.items():
        summary += f"• {get_platform_icon(platform)} {platform.capitalize()}: {acc['account_identifier']}\n"
    
    summary += f"\n💰 **خطتك الحالية:** مجانية ({FREE_LIMIT} تحليل يومياً)\n"
    summary += f"💎 **للبحث غير المحدود:** /premium\n\n"
    summary += f"🎯 **للبدء، اضغط على 🎯 تحليل حساباتي**"
    
    await update.message.reply_text(summary, parse_mode='Markdown', reply_markup=get_main_keyboard(False))
    return ConversationHandler.END


def get_platform_icon(platform):
    """الحصول على أيقونة المنصة"""
    icons = {
        'youtube': '🎬',
        'instagram': '📸',
        'tiktok': '🎵',
        'facebook': '📘'
    }
    return icons.get(platform, '🔗')


async def my_data_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض بيانات المستخدم"""
    user_id = update.effective_user.id
    accounts = get_user_social_accounts(user_id)
    
    if not accounts:
        await update.message.reply_text(
            "❌ لم تقم بتسجيل أي حسابات بعد.\n\n"
            "للتسجيل، أرسل /start",
            reply_markup=get_main_keyboard(False)
        )
        return
    
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    text = f"📝 **بياناتي الشخصية**\n\n"
    text += f"👤 **الاسم:** {user_info['first_name'] if user_info else '-'}\n"
    text += f"🆔 **المعرف:** @{user_info['username'] if user_info else '-'}\n"
    text += f"💎 **الخطة:** {'👑 مميز' if is_premium else '🎁 مجاني'}\n\n"
    text += f"📱 **حساباتي المسجلة:**\n"
    
    for platform, acc in accounts.items():
        text += f"• {get_platform_icon(platform)} {platform.capitalize()}: {acc['account_identifier']}\n"
    
    if is_premium:
        bio_page = get_bio_page(user_id)
        if bio_page and bio_page.get('is_enabled'):
            text += f"\n📄 **صفحة البايو:**\n"
            text += f"🔗 {RENDER_URL}/bio/{bio_page['page_url']}"
    
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=get_main_keyboard(is_premium))


async def edit_data_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعديل بيانات المستخدم"""
    user_id = update.effective_user.id
    accounts = get_user_social_accounts(user_id)
    
    keyboard = []
    for platform in ['youtube', 'instagram', 'tiktok', 'facebook']:
        if platform in accounts:
            keyboard.append([InlineKeyboardButton(f"✏️ تعديل {platform.capitalize()}", callback_data=f"edit_{platform}")])
    
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")])
    
    await update.message.reply_text(
        "✏️ **اختر الحساب الذي تريد تعديله:**",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def my_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إحصائيات المستخدم"""
    user_id = update.effective_user.id
    user_info = get_user_info(user_id)
    remaining = get_remaining_analyses(user_id)
    total = get_total_analyses(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    if is_premium:
        gemini_usage = can_use_gemini(user_id)
        gemini_remaining = gemini_usage[1] if isinstance(gemini_usage, tuple) and len(gemini_usage) > 1 else 0
        
        text = f"""
📊 **إحصائياتي الشخصية**

👤 **المستخدم:** {user_info['first_name'] if user_info else '-'}
💎 **نوع الخطة:** 👑 مميز
📈 **إجمالي التحليلات:** {total}
🤖 **توصيات AI المتبقية اليوم:** {gemini_remaining}/5
📄 **صفحة البايو:** ✅ مفعلة
🔍 **فحص اليوزرنيم:** ✅ متاح
"""
    else:
        text = f"""
📊 **إحصائياتي الشخصية**

👤 **المستخدم:** {user_info['first_name'] if user_info else '-'}
💎 **نوع الخطة:** 🎁 مجاني
📊 **التحليلات المتبقية اليوم:** {remaining}/{FREE_LIMIT}
📈 **إجمالي التحليلات:** {total}
💎 **للترقية إلى خطة مميزة:** /premium
"""
    
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=get_main_keyboard(is_premium))


async def premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معلومات الاشتراك المميز"""
    user_id = update.effective_user.id
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    if is_premium:
        text = """
👑 **أنت مشترك في الخطة المميزة!**

✅ **مميزات الاشتراك المميز:**
• تحليل غير محدود لجميع الحسابات
• توصيات الذكاء الاصطناعي (5 يومياً)
• صفحة بايو شخصية
• فحص توافر اليوزرنيم
• دعم أولوية في المعالجة

📅 **الاشتراك نشط حالياً**

شكراً لدعمك! 🙏
"""
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=get_main_keyboard(True))
    else:
        remaining = get_remaining_analyses(user_id)
        text = f"""
💎 **الاشتراك المميز**

🎁 **مميزات الخطة المميزة:**
• ✅ تحليل غير محدود
• ✅ توصيات الذكاء الاصطناعي
• ✅ صفحة بايو شخصية
• ✅ فحص توافر اليوزرنيم
• ✅ دعم أولوية في المعالجة

💰 **السعر:**
• **10 دولار مدى الحياة**

📊 **حالتك الحالية:**
• نوع الخطة: مجانية
• التحليلات المتبقية اليوم: {remaining}/{FREE_LIMIT}

🔽 **للاشتراك، اضغط على الزر أدناه:**
"""
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=get_premium_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعليمات المساعدة"""
    user_id = update.effective_user.id
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    help_text = f"""
🆘 **مساعدة بوت تحليل الحسابات الاجتماعية**

🔹 **لتحليل حساب:**
• اضغط على زر 🎯 تحليل حساباتي
• اختر المنصة المطلوبة
• سيتم تحليل الحساب المسجل تلقائياً

🔹 **للتسجيل أو تعديل البيانات:**
• اضغط على 📝 بياناتي لعرض الحسابات المسجلة
• اضغط على ✏️ تعديل بياناتي لتعديل الحسابات

💰 **نظام الاستخدام:**
• الخطة المجانية: {FREE_LIMIT} تحليل يومياً
• الخطة المميزة: غير محدود

📋 **الأوامر:**
/start - بدء الاستخدام
/help - هذه المساعدة
/mystats - إحصائياتي الشخصية
/premium - الاشتراك المميز
/mydata - عرض بياناتي

👨‍💻 **المطور:** @E_Alshabany
"""
    await update.message.reply_text(help_text, parse_mode='Markdown', reply_markup=get_main_keyboard(is_premium))
async def analyze_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء عملية التحليل"""
    user_id = update.effective_user.id
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    # التحقق من وجود حسابات مسجلة
    accounts = get_user_social_accounts(user_id)
    
    if not accounts:
        await update.message.reply_text(
            "❌ لم تقم بتسجيل أي حسابات بعد.\n\n"
            "للتسجيل، أرسل /start",
            reply_markup=get_main_keyboard(is_premium)
        )
        return
    
    # التحقق من الحد اليومي للمجانيين
    can_analyze_bool, current_uses = can_analyze(user_id)
    
    if not can_analyze_bool and not is_premium:
        keyboard = [[InlineKeyboardButton("💎 اشتراك مميز", url=HUB_BOT_URL)]]
        await update.message.reply_text(
            f"⚠️ **لقد وصلت للحد اليومي!**\n\n"
            f"📊 **الحد المسموح:** {FREE_LIMIT} تحليل يومياً\n"
            f"✅ **التحليلات اليوم:** {current_uses}\n"
            f"🎯 **المتبقي:** {FREE_LIMIT - current_uses}\n\n"
            f"💎 **للتحليل غير المحدود، اشترك في الخطة المميزة!**",
            parse_mode='Markdown',
            reply_markup=keyboard
        )
        return
    
    await update.message.reply_text(
        "🎯 **اختر المنصة التي تريد تحليلها:**",
        parse_mode='Markdown',
        reply_markup=get_analysis_keyboard()
    )


async def analyze_youtube(update: Update, context: ContextTypes.DEFAULT_TYPE, query=None):
    """تحليل قناة يوتيوب"""
    user_id = update.effective_user.id if not query else query.from_user.id
    
    if query:
        await query.answer()
        message = query.message
    else:
        message = update.message
    
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    # جلب حساب يوتيوب المسجل
    youtube_account = get_user_account(user_id, 'youtube')
    
    if not youtube_account:
        await message.reply_text(
            "❌ لم تقم بتسجيل حساب يوتيوب بعد.\n\n"
            "للتسجيل، أرسل /start ثم اتبع التعليمات",
            reply_markup=get_main_keyboard(is_premium)
        )
        return
    
    status_msg = await message.reply_text("⏳ جاري تحليل القناة...")
    
    # تحليل القناة
    channel_details, error = await get_channel_details(youtube_account['account_identifier'])
    
    if error:
        await status_msg.edit_text(f"❌ حدث خطأ: {error}")
        return
    
    if not channel_details:
        await status_msg.edit_text("❌ لم يتم العثور على القناة")
        return
    
    # زيادة عدد الاستخدامات
    remaining = get_remaining_analyses(user_id) if not is_premium else None
    increment_usage(user_id, 'youtube', {
        'account_name': channel_details['title'],
        'subscribers': channel_details['subscribers'],
        'total_posts': channel_details['total_videos'],
        'top_posts': channel_details['latest_videos'][:5],
        'duration': 0
    })
    
    # تنسيق التقرير
    message_text, file_data = format_channel_report(
        channel_details, user_id, is_premium, remaining
    )
    
    await status_msg.delete()
    
    if file_data:
        file_content, filename = file_data
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(file_content)
        
        await message.reply_text(message_text, parse_mode='Markdown')
        
        with open(filename, 'rb') as f:
            await message.reply_document(
                document=f,
                filename=filename,
                caption="📊 ملف التحليل الكامل"
            )
        
        os.remove(filename)
    else:
        await message.reply_text(message_text, parse_mode='Markdown')
    
    # عرض خيار إضافة توصيات AI للمميزين
    if is_premium:
        keyboard = [[InlineKeyboardButton("🤖 توصيات الذكاء الاصطناعي", callback_data=f"ai_recommendations_{channel_details['channel_id']}")]]
        await message.reply_text(
            "🤖 **هل تريد الحصول على توصيات لتحسين قناتك؟**",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def ai_recommendations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تقديم توصيات الذكاء الاصطناعي"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    channel_id = query.data.split('_')[-1]
    
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    if not is_premium:
        await query.edit_message_text(
            "💎 هذه الميزة متاحة فقط للمستخدمين المميزين!\n\n"
            "للاشتراك: /premium"
        )
        return
    
    # التحقق من صلاحية استخدام Gemini
    can_use, remaining, error_msg = can_use_gemini(user_id)
    
    if not can_use:
        await query.edit_message_text(error_msg)
        return
    
    # جلب تفاصيل القناة
    youtube_account = get_user_account(user_id, 'youtube')
    if not youtube_account:
        await query.edit_message_text("❌ لم يتم العثور على حساب يوتيوب مسجل")
        return
    
    channel_details, _ = await get_channel_details(youtube_account['account_identifier'])
    
    if not channel_details:
        await query.edit_message_text("❌ لم يتم العثور على القناة")
        return
    
    await query.edit_message_text("🤖 جاري توليد توصيات الذكاء الاصطناعي...")
    
    # زيادة عدد استخدامات Gemini
    increment_gemini_usage(user_id)
    
    # الحصول على التوصيات
    recommendations = await get_channel_recommendations(channel_details)
    
    response = f"🤖 **توصيات الذكاء الاصطناعي:**\n\n{recommendations}\n\n📊 **المتبقي اليوم:** {remaining - 1}/5 توصيات"
    
    await query.edit_message_text(response, parse_mode='Markdown')


async def bio_page_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إنشاء صفحة البايو"""
    user_id = update.effective_user.id
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    if not is_premium:
        await update.message.reply_text(
            "💎 **صفحة البايو**\n\n"
            "هذه الميزة متاحة فقط للمستخدمين المميزين!\n\n"
            "💎 **مميزات صفحة البايو:**\n"
            "• صفحة شخصية تعرض جميع حساباتك\n"
            "• روابط مختصرة لكل منصة\n"
            "• تصميم احترافي قابل للمشاركة\n\n"
            "للاشتراك: /premium",
            parse_mode='Markdown',
            reply_markup=get_premium_keyboard()
        )
        return
    
    accounts = get_user_social_accounts(user_id)
    
    if not accounts:
        await update.message.reply_text(
            "❌ لم تقم بتسجيل أي حسابات بعد.\n\n"
            "للتسجيل، أرسل /start",
            reply_markup=get_main_keyboard(True)
        )
        return
    
    # إنشاء صفحة البايو
    display_name = user_info.get('first_name', 'مستخدم')
    page_url = create_or_update_bio_page(user_id, display_name, accounts)
    
    if page_url:
        await update.message.reply_text(
            f"✅ **تم إنشاء صفحة البايو بنجاح!**\n\n"
            f"🔗 **رابط صفحتك:**\n"
            f"https://{RENDER_URL}/bio/{page_url}\n\n"
            f"📌 يمكنك مشاركة هذا الرابط مع الآخرين\n"
            f"🔄 لتحديث الصفحة، أضف أو عدل حساباتك ثم استخدم هذا الأمر مرة أخرى",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard(True)
        )
    else:
        await update.message.reply_text(
            "❌ حدث خطأ في إنشاء صفحة البايو. حاول مرة أخرى لاحقاً.",
            reply_markup=get_main_keyboard(True)
        )


async def username_check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فحص توافر اليوزرنيم"""
    user_id = update.effective_user.id
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    if not is_premium:
        await update.message.reply_text(
            "🔍 **فحص توافر اليوزرنيم**\n\n"
            "هذه الميزة متاحة فقط للمستخدمين المميزين!\n\n"
            "💎 **مميزات فحص اليوزرنيم:**\n"
            "• فحص توافر الاسم في جميع المنصات\n"
            "• اقتراحات ذكية لتحسين الاسم\n"
            "• توصيات لتوحيد الاسم بين المنصات\n\n"
            "للاشتراك: /premium",
            parse_mode='Markdown',
            reply_markup=get_premium_keyboard()
        )
        return
    
    await update.message.reply_text(
        "🔍 **فحص توافر اليوزرنيم**\n\n"
        "أرسل اليوزرنيم الذي تريد التحقق منه (بدون @):",
        parse_mode='Markdown'
    )
    context.user_data['awaiting_username'] = True


async def handle_username_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة اليوزرنيم المرسل للفحص"""
    if not context.user_data.get('awaiting_username'):
        return
    
    username = update.message.text.strip()
    context.user_data['awaiting_username'] = False
    
    await update.message.reply_text(f"🔍 جاري فحص اليوزرنيم: @{escape_html(username)}...")
    
    # هنا سيتم إضافة منطق فحص اليوزرنيم عبر APIs المنصات
    # حالياً نعرض رسالة تجريبية
    
    recommendations = await get_username_recommendations('youtube', username, username)
    
    response = f"🔍 **نتيجة فحص اليوزرنيم @{escape_html(username)}**\n\n"
    response += f"✅ الاسم متاح! (تجريبياً)\n\n"
    response += f"🤖 **توصيات الذكاء الاصطناعي:**\n{recommendations}"
    
    await update.message.reply_text(response, parse_mode='Markdown')


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الأزرار"""
    query = update.callback_query
    data = query.data
    
    if data == "analyze_youtube":
        await analyze_youtube(update, context, query)
    
    elif data == "analyze_instagram":
        await query.answer("📸 هذه الميزة قيد التطوير حالياً", show_alert=True)
    
    elif data == "analyze_tiktok":
        await query.answer("🎵 هذه الميزة قيد التطوير حالياً", show_alert=True)
    
    elif data == "analyze_facebook":
        await query.answer("📘 هذه الميزة قيد التطوير حالياً", show_alert=True)
    
    elif data == "main_menu":
        user_id = query.from_user.id
        user_info = get_user_info(user_id)
        is_premium = user_info['status'] == 'premium' if user_info else False
        await query.edit_message_text(
            "🏠 **القائمة الرئيسية**\n\nاختر ما تريد:",
            parse_mode='Markdown',
            reply_markup=get_main_keyboard(is_premium)
        )
    
    elif data.startswith("ai_recommendations"):
        await ai_recommendations(update, context)
    
    elif data.startswith("edit_"):
        platform = data.split('_')[1]
        context.user_data['editing_platform'] = platform
        await query.edit_message_text(
            f"✏️ **تعديل حساب {platform.capitalize()}**\n\n"
            f"أرسل المعرف الجديد أو الرابط:",
            parse_mode='Markdown'
        )


async def handle_edit_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة تعديل الحساب"""
    platform = context.user_data.get('editing_platform')
    if not platform:
        return
    
    user_id = update.effective_user.id
    new_identifier = update.message.text.strip()
    
    # حذف الحساب القديم وإضافة الجديد
    delete_user_account(user_id, platform)
    save_user_account(user_id, platform, new_identifier)
    
    context.user_data.pop('editing_platform', None)
    
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    
    await update.message.reply_text(
        f"✅ تم تحديث حساب {platform.capitalize()} إلى: {escape_html(new_identifier)}",
        parse_mode='HTML',
        reply_markup=get_main_keyboard(is_premium)
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة الرسائل النصية"""
    text = update.message.text.strip()
    user_id = update.effective_user.id
    
    # معالجة الأزرار
    if text == "🎯 تحليل حساباتي":
        await analyze_command(update, context)
        return
    
    elif text == "📊 إحصائياتي":
        await my_stats_command(update, context)
        return
    
    elif text == "📝 بياناتي":
        await my_data_command(update, context)
        return
    
    elif text == "✏️ تعديل بياناتي":
        await edit_data_command(update, context)
        return
    
    elif text == "💎 اشتراك مميز":
        await premium_command(update, context)
        return
    
    elif text == "ℹ️ المساعدة":
        await help_command(update, context)
        return
    
    elif text == "📄 صفحة البايو":
        await bio_page_command(update, context)
        return
    
    elif text == "🔍 فحص يوزرنيم":
        await username_check_command(update, context)
        return
    
    # معالجة تعديل الحساب
    if context.user_data.get('editing_platform'):
        await handle_edit_account(update, context)
        return
    
    # معالجة فحص اليوزرنيم
    if context.user_data.get('awaiting_username'):
        await handle_username_check(update, context)
        return
    
    # رسالة افتراضية
    user_info = get_user_info(user_id)
    is_premium = user_info['status'] == 'premium' if user_info else False
    await update.message.reply_text(
        "❓ عذراً، لم أتعرف على طلبك.\n\n"
        "📌 يمكنك استخدام الأزرار أدناه أو إرسال /help للمساعدة.",
        reply_markup=get_main_keyboard(is_premium)
    )


# ========== Flask Routes ==========

@app.route('/payment')
def payment_page():
    """صفحة الدفع"""
    return render_template('payment.html', free_limit=FREE_LIMIT)


@app.route('/bio/<page_url>')
def bio_page(page_url):
    """صفحة البايو الشخصية"""
    try:
        response = supabase.table('bio_pages').select('*').eq('page_url', page_url).eq('is_enabled', True).execute()
        if not response.data:
            return "Page not found", 404
        
        bio = response.data[0]
        user_info = get_user_info(bio['user_id'])
        
        if not user_info:
            return "User not found", 404
        
        html = f"""
        <!DOCTYPE html>
        <html dir="rtl" lang="ar">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{escape_html(bio['display_name'])} - صفحة البايو</title>
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    padding: 20px;
                }}
                .container {{
                    max-width: 500px;
                    margin: 0 auto;
                }}
                .card {{
                    background: white;
                    border-radius: 20px;
                    padding: 30px;
                    text-align: center;
                    box-shadow: 0 20px 40px rgba(0,0,0,0.2);
                }}
                .name {{
                    font-size: 24px;
                    font-weight: bold;
                    margin-bottom: 10px;
                }}
                .username {{
                    color: #666;
                    margin-bottom: 20px;
                }}
                .button {{
                    display: block;
                    background: #f0f0f0;
                    padding: 12px 20px;
                    margin: 10px 0;
                    border-radius: 10px;
                    text-decoration: none;
                    color: #333;
                    transition: all 0.3s;
                }}
                .button:hover {{
                    background: #e0e0e0;
                    transform: scale(1.02);
                }}
                .youtube {{ background: #ff0000; color: white; }}
                .instagram {{ background: #e4405f; color: white; }}
                .tiktok {{ background: #000000; color: white; }}
                .facebook {{ background: #1877f2; color: white; }}
                .footer {{
                    text-align: center;
                    margin-top: 20px;
                    color: white;
                    font-size: 12px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="card">
                    <div class="name">{escape_html(bio['display_name'])}</div>
                    <div class="username">@{user_info.get('username', '')}</div>
        """
        
        accounts = bio.get('accounts', {})
        for platform, acc in accounts.items():
            icon = get_platform_icon(platform)
            html += f'<a href="https://{platform}.com/{acc["account_identifier"]}" class="button {platform}" target="_blank">{icon} {platform.capitalize()}</a>'
        
        html += f"""
                    <div class="footer">
                        تم الإنشاء عبر @Social_Media_tools_bot
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
        
    except Exception as e:
        logger.error(f"Error in bio_page: {e}")
        return "Internal error", 500


# ========== الدالة الرئيسية ==========

def main():
    """تشغيل البوت"""
    application = Application.builder().token(TOKEN).build()
    
    # معالج التسجيل (ConversationHandler)
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start_command)],
        states={
            ASK_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_name)],
            ASK_YOUTUBE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex('^/skip$'), ask_youtube),
                CommandHandler("skip", skip_youtube)
            ],
            ASK_INSTAGRAM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex('^/skip$'), ask_instagram),
                CommandHandler("skip", skip_instagram)
            ],
            ASK_TIKTOK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex('^/skip$'), ask_tiktok),
                CommandHandler("skip", skip_tiktok)
            ],
            ASK_FACEBOOK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex('^/skip$'), ask_facebook),
                CommandHandler("skip", skip_facebook)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_registration)]
    )
    
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("mystats", my_stats_command))
    application.add_handler(CommandHandler("premium", premium_command))
    application.add_handler(CommandHandler("mydata", my_data_command))
    application.add_handler(CommandHandler("edit", edit_data_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    print("="*60)
    print("📊 Social Media Analyzer Bot - النسخة المميزة")
    print("🤖 @Social_Media_tools_bot")
    print("✅ أوامر: /start /help /mystats /premium /mydata")
    print(f"✅ نظام المدفوعات: مجاني {FREE_LIMIT} تحليل - مميز غير محدود")
    print("✅ قاعدة بيانات: Supabase (متكاملة مع النظام الموحد)")
    print("✅ الذكاء الاصطناعي: Gemini API")
    print("="*60)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
