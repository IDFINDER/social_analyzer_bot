# -*- coding: utf-8 -*-
"""
دوال تحليل قنوات يوتيوب
"""

import os
import logging
from datetime import datetime
from googleapiclient.discovery import build
from .helpers import format_number, format_duration, escape_html

logger = logging.getLogger(__name__)

YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY')
youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY) if YOUTUBE_API_KEY else None


def extract_channel_info(channel_input):
    """
    استخراج معلومات القناة من الإدخال
    """
    channel_input = channel_input.strip()
    
    # إزالة @ إذا كانت موجودة
    if channel_input.startswith('@'):
        channel_input = channel_input[1:]
    
    # إزالة الروابط
    if 'youtube.com' in channel_input:
        if '/@' in channel_input:
            channel_input = channel_input.split('/@')[-1].split('?')[0]
        elif '/channel/' in channel_input:
            channel_input = channel_input.split('/channel/')[-1].split('?')[0]
        elif '/c/' in channel_input:
            channel_input = channel_input.split('/c/')[-1].split('?')[0]
    
    return channel_input


async def get_channel_details(channel_identifier):
    """
    تحليل قناة يوتيوب
    """
    if not youtube:
        return None, "YouTube API key not configured"
    
    try:
        channel_identifier = extract_channel_info(channel_identifier)
        channel_id = None
        
        # البحث عن القناة
        search_response = youtube.search().list(
            part='snippet',
            q=channel_identifier,
            type='channel',
            maxResults=1
        ).execute()
        
        if not search_response.get('items'):
            return None, "لم يتم العثور على القناة"
        
        channel_id = search_response['items'][0]['snippet']['channelId']
        
        # جلب تفاصيل القناة
        channel_response = youtube.channels().list(
            part='snippet,statistics,contentDetails,status',
            id=channel_id
        ).execute()
        
        if not channel_response.get('items'):
            return None, "لم يتم العثور على القناة"
        
        channel_data = channel_response['items'][0]
        snippet = channel_data['snippet']
        statistics = channel_data.get('statistics', {})
        status = channel_data.get('status', {})
        
        # جلب أحدث الفيديوهات
        uploads_playlist_id = channel_data.get('contentDetails', {}).get('relatedPlaylists', {}).get('uploads')
        latest_videos = []
        
        if uploads_playlist_id:
            playlist_response = youtube.playlistItems().list(
                part='snippet',
                playlistId=uploads_playlist_id,
                maxResults=5
            ).execute()
            
            for item in playlist_response.get('items', []):
                video_snippet = item['snippet']
                latest_videos.append({
                    'title': video_snippet['title'],
                    'video_id': video_snippet['resourceId']['videoId'],
                    'published_at': video_snippet['publishedAt'][:10]
                })
        
        # حساب المتوسطات
        total_views = int(statistics.get('viewCount', 0))
        total_videos = int(statistics.get('videoCount', 1))
        avg_views = total_views / total_videos if total_videos > 0 else 0
        
        channel_details = {
            'title': snippet['title'],
            'description': snippet.get('description', 'لا يوجد وصف')[:200],
            'custom_url': snippet.get('customUrl', 'N/A'),
            'published_at': snippet['publishedAt'][:10],
            'country': snippet.get('country', 'غير محدد'),
            'subscribers': format_number(statistics.get('subscriberCount', 0)),
            'total_views': format_number(total_views),
            'total_videos': format_number(total_videos),
            'hidden_subscribers': statistics.get('hiddenSubscriberCount', False),
            'privacy_status': status.get('privacyStatus', 'غير معروف'),
            'avg_views': format_number(avg_views),
            'latest_videos': latest_videos,
            'channel_id': channel_id
        }
        
        return channel_details, None
        
    except Exception as e:
        logger.error(f"Error getting channel details: {e}")
        return None, str(e)


def format_channel_report(channel_details, user_id=None, is_premium=False, remaining_analyses=None):
    """
    تنسيق تقرير تحليل القناة
    """
    if not channel_details:
        return None, None
    
    from .helpers import clean_filename, escape_html
    
    # بناء الرسالة النصية
    message = f"✅ <b>تم تحليل القناة بنجاح!</b>\n\n"
    message += f"📺 <b>القناة:</b> {escape_html(channel_details['title'])}\n"
    message += f"🆔 **اليوزر:** @{escape_html(channel_details['custom_url'])}\n"
    message += f"📅 **الإنشاء:** {channel_details['published_at']}\n"
    message += f"🌍 **البلد:** {channel_details['country']}\n\n"
    
    message += f"📊 **الإحصائيات:**\n"
    subs_text = "🔒 مخفي" if channel_details['hidden_subscribers'] else channel_details['subscribers']
    message += f"👥 **المشتركين:** {subs_text}\n"
    message += f"📹 **عدد الفيديوهات:** {channel_details['total_videos']}\n"
    message += f"👁️ **إجمالي المشاهدات:** {channel_details['total_views']}\n"
    message += f"📊 **متوسط المشاهدات/فيديو:** {channel_details['avg_views']}\n\n"
    
    message += f"🆕 **أحدث 5 فيديوهات:**\n"
    for i, v in enumerate(channel_details['latest_videos'][:5], 1):
        message += f"{i}. [{escape_html(v['title'][:50])}](https://www.youtube.com/watch?v={v['video_id']})\n"
    
    if not is_premium:
        message += f"\n📊 **المتبقي اليوم:** {remaining_analyses}/{FREE_LIMIT}"
    
    # بناء الملف النصي
    file_content = build_text_file(channel_details, is_premium)
    
    # اسم الملف
    filename = f"تحليل_يوتيوب_{datetime.now().strftime('%Y_%m_%d')}.txt"
    
    return message, (file_content, filename)


def build_text_file(channel_details, is_premium):
    """
    بناء محتوى الملف النصي
    """
    now = datetime.now()
    
    content = "=" * 60 + "\n"
    content += f"          تقرير حساب يوتيوب @{channel_details['custom_url']}\n"
    content += "=" * 60 + "\n\n"
    
    content += f"📅 التاريخ: {now.strftime('%Y-%m-%d')}\n"
    content += f"⏰ الوقت: {now.strftime('%H:%M')}\n\n"
    
    content += f"📺 القناة: {channel_details['title']}\n"
    content += f"🆔 اليوزر: @{channel_details['custom_url']}\n"
    content += f"📅 الإنشاء: {channel_details['published_at']}\n"
    content += f"🌍 البلد: {channel_details['country']}\n\n"
    
    content += "📊 الإحصائيات:\n"
    subs_text = "🔒 مخفي" if channel_details['hidden_subscribers'] else channel_details['subscribers']
    content += f"👥 المشتركين: {subs_text}\n"
    content += f"📹 عدد الفيديوهات: {channel_details['total_videos']}\n"
    content += f"👁️ المشاهدات: {channel_details['total_views']}\n"
    content += f"📊 المتوسط: {channel_details['avg_views']}\n\n"
    
    content += "🔥 أفضل 5 فيديوهات:\n"
    for i, v in enumerate(channel_details['latest_videos'][:5], 1):
        content += f"{i}. {v['title']}\n"
        content += f"   https://www.youtube.com/watch?v={v['video_id']}\n"
    
    content += "\n" + "=" * 60 + "\n"
    
    if not is_premium:
        content += "⬅️ تم التحليل عبر بوت تحليل حسابات السوشل ميديا\n"
        content += "تطوير Ebrahim Alshabany\n"
        content += "@E_Alshabany\n"
    
    content += "=" * 60 + "\n"
    
    return content
