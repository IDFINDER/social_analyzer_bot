import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Any
import openai
from collections import Counter
import re
from openai import OpenAI
from config import Config
from database import db_manager

# Configure logging
logger = logging.getLogger(__name__)


class TelegramAnalytics:
    def __init__(self):
        self.df = None

        if not Config.OPENAI_API_KEY:
            raise ValueError("OpenAI API key not configured")

        # создаем клиент один раз
        self.client = OpenAI(api_key=Config.OPENAI_API_KEY)
        
    def load_channel_data(self, username: str, days_back: int = 30) -> bool:
        """Load channel data from database"""
        try:
            channel = db_manager.get_channel_by_username(username)
            if not channel:
                logger.error(f"Channel {username} not found")
                return False
            
            posts = db_manager.get_channel_posts(channel.id, limit=1000, days_back=days_back)
            
            if not posts:
                logger.warning(f"No posts found for channel {username}")
                return False
            
            # Convert to DataFrame
            data = []
            for post in posts:
                data.append({
                    'message_id': post.message_id,
                    'text': post.text,
                    'date': post.date,
                    'views': post.views,
                    'forwards': post.forwards,
                    'replies': post.replies,
                    'reactions_count': post.reactions_count,
                    'reactions_data': post.reactions_data,
                    'media_type': post.media_type,
                    'links': post.links,
                    'engagement_rate': post.engagement_rate
                })
            
            self.df = pd.DataFrame(data)
            self.df['date'] = pd.to_datetime(self.df['date'])
            self.df = self.df.sort_values('date')
            
            logger.info(f"Loaded {len(self.df)} posts for channel {username}")
            return True
            
        except Exception as e:
            logger.error(f"Error loading channel data: {e}")
            return False
    
    def calculate_engagement_rate(self, subscribers_count: int) -> pd.DataFrame:
        """Calculate engagement rate for all posts"""
        if self.df is None or self.df.empty:
            return pd.DataFrame()
        
        df = self.df.copy()
        
        # Calculate total engagement
        df['total_engagement'] = (df['reactions_count'] + 
                                df['replies'] + 
                                df['forwards'])
        
        # Calculate engagement rate
        df['engagement_rate'] = (df['total_engagement'] / subscribers_count) * 100
        
        # Update database
        for _, row in df.iterrows():
            # Update engagement rate in database
            pass  # This would require updating the database
        
        return df
    
    def get_basic_metrics(self, subscribers_count: int) -> Dict[str, Any]:
        """Calculate basic channel metrics"""
        if self.df is None or self.df.empty:
            return {}
        
        df = self.calculate_engagement_rate(subscribers_count)
        
        metrics = {
            'total_posts': len(df),
            'avg_views': df['views'].mean(),
            'avg_engagement_rate': df['engagement_rate'].mean(),
            'total_reactions': df['reactions_count'].sum(),
            'total_forwards': df['forwards'].sum(),
            'total_replies': df['replies'].sum(),
            'best_post_views': df['views'].max(),
            'best_post_engagement': df['engagement_rate'].max(),
            'posts_with_media': len(df[df['media_type'].notna()]),
            'posts_with_links': len(df[df['links'].notna()])
        }
        
        return metrics
    
    def get_best_posts(self, subscribers_count: int, top_n: int = 5) -> List[Dict[str, Any]]:
        """Get best performing posts"""
        if self.df is None or self.df.empty:
            return []
        
        df = self.calculate_engagement_rate(subscribers_count)
        
        # Sort by engagement rate
        best_posts = df.nlargest(top_n, 'engagement_rate')
        
        posts_data = []
        for _, post in best_posts.iterrows():
            posts_data.append({
                'message_id': post['message_id'],
                'text': post['text'][:100] + "..." if len(post['text']) > 100 else post['text'],
                'date': post['date'].strftime('%Y-%m-%d %H:%M'),
                'views': post['views'],
                'engagement_rate': round(post['engagement_rate'], 2),
                'reactions': post['reactions_count'],
                'forwards': post['forwards'],
                'replies': post['replies']
            })
        
        return posts_data
    
    def get_trends_analysis(self, subscribers_count: int) -> Dict[str, Any]:
        """Analyze trends over time"""
        if self.df is None or self.df.empty:
            return {}
        
        df = self.calculate_engagement_rate(subscribers_count)
        
        # Resample by day
        daily_stats = df.set_index('date').resample('D').agg({
            'views': 'mean',
            'engagement_rate': 'mean',
            'reactions_count': 'sum',
            'forwards': 'sum',
            'replies': 'sum'
        }).fillna(0)
        
        # Calculate trends
        trends = {
            'views_trend': self._calculate_trend(daily_stats['views']),
            'engagement_trend': self._calculate_trend(daily_stats['engagement_rate']),
            'reactions_trend': self._calculate_trend(daily_stats['reactions_count']),
            'forwards_trend': self._calculate_trend(daily_stats['forwards']),
            'replies_trend': self._calculate_trend(daily_stats['replies'])
        }
        
        return trends
    
    def _calculate_trend(self, series: pd.Series) -> str:
        """Calculate trend direction"""
        if len(series) < 2:
            return "stable"
        
        # Calculate slope
        x = np.arange(len(series))
        slope = np.polyfit(x, series, 1)[0]
        
        if slope > 0.1:
            return "increasing"
        elif slope < -0.1:
            return "decreasing"
        else:
            return "stable"
    
    def get_content_analysis(self) -> Dict[str, Any]:
        """Analyze content patterns"""
        if self.df is None or self.df.empty:
            return {}
        
        df = self.df.copy()
        
        # Media analysis
        media_counts = df['media_type'].value_counts().to_dict()
        
        # Link analysis
        posts_with_links = df[df['links'].notna()]
        link_posts_engagement = posts_with_links['engagement_rate'].mean() if not posts_with_links.empty else 0
        
        # Text length analysis
        df['text_length'] = df['text'].str.len()
        avg_text_length = df['text_length'].mean()
        
        # Best performing content types
        content_performance = {}
        for media_type in df['media_type'].unique():
            if pd.notna(media_type):
                media_posts = df[df['media_type'] == media_type]
                content_performance[media_type] = {
                    'count': len(media_posts),
                    'avg_engagement': media_posts['engagement_rate'].mean(),
                    'avg_views': media_posts['views'].mean()
                }
        
        return {
            'media_distribution': media_counts,
            'link_posts_engagement': link_posts_engagement,
            'avg_text_length': avg_text_length,
            'content_performance': content_performance
        }

    def generate_ai_insights(self, channel_name: str, subscribers_count: int) -> str:
        """Generate AI-powered insights using OpenAI (new API)"""
        if not Config.OPENAI_API_KEY:
            return "OpenAI API key not configured"

        if self.df is None or self.df.empty:
            return "No data available for analysis"

        try:
            # Подготавливаем данные
            metrics = self.get_basic_metrics(subscribers_count)
            best_posts = self.get_best_posts(subscribers_count, top_n=3)
            trends = self.get_trends_analysis(subscribers_count)
            content_analysis = self.get_content_analysis()

            # Формируем промпт
            prompt = f"""
            Analyze this Telegram channel data and provide insights:

            Channel: {channel_name}
            Subscribers: {subscribers_count:,}

            Key Metrics:
            - Total posts: {metrics.get('total_posts', 0)}
            - Average views: {metrics.get('avg_views', 0):.0f}
            - Average engagement rate: {metrics.get('avg_engagement_rate', 0):.2f}%
            - Total reactions: {metrics.get('total_reactions', 0):,}

            Trends:
            - Views trend: {trends.get('views_trend', 'unknown')}
            - Engagement trend: {trends.get('engagement_trend', 'unknown')}

            Content Analysis:
            - Media distribution: {content_analysis.get('media_distribution', {})}
            - Average text length: {content_analysis.get('avg_text_length', 0):.0f} characters

            Best performing posts:
            {json.dumps(best_posts, indent=2)}

            Please provide:
            1. Key insights about channel performance
            2. Recommendations for improvement
            3. Content strategy suggestions
            4. Engagement optimization tips

            Keep the response concise and actionable.
            """

            # Новый вызов API
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",  # или "gpt-4o", "gpt-3.5-turbo"
                messages=[
                    {"role": "system",
                     "content": "Ты эксперт по аналитике Telegram-каналов. Отвечай строго на русском языке, давай конкретные и полезные рекомендации для владельца канала."}
,
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=0.7
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"Error generating AI insights: {e}")
            return f"Error generating AI insights: {str(e)}"


    def create_engagement_chart(self, subscribers_count: int, save_path: str = None) -> str:
        """Create engagement rate chart"""
        if self.df is None or self.df.empty:
            return ""
        
        df = self.calculate_engagement_rate(subscribers_count)
        
        # Create figure with subplots
        fig = make_subplots(
            rows=2, cols=2,
            subplot_titles=('Engagement Rate Over Time', 'Views Over Time', 
                          'Reactions Distribution', 'Post Performance'),
            specs=[[{"secondary_y": False}, {"secondary_y": False}],
                   [{"secondary_y": False}, {"secondary_y": False}]]
        )
        
        # Engagement rate over time
        fig.add_trace(
            go.Scatter(x=df['date'], y=df['engagement_rate'], 
                      mode='lines+markers', name='Engagement Rate'),
            row=1, col=1
        )
        
        # Views over time
        fig.add_trace(
            go.Scatter(x=df['date'], y=df['views'], 
                      mode='lines+markers', name='Views'),
            row=1, col=2
        )
        
        # Reactions distribution
        fig.add_trace(
            go.Histogram(x=df['reactions_count'], name='Reactions Distribution'),
            row=2, col=1
        )
        
        # Post performance scatter
        fig.add_trace(
            go.Scatter(x=df['views'], y=df['engagement_rate'], 
                      mode='markers', name='Views vs Engagement'),
            row=2, col=2
        )
        
        fig.update_layout(
            title=f'Telegram Channel Analytics',
            height=800,
            showlegend=True
        )
        
        if save_path:
            fig.write_html(save_path)
            return save_path
        else:
            return fig.to_html()
    
    def generate_comprehensive_report(self, username: str, subscribers_count: int) -> Dict[str, Any]:
        """Generate comprehensive analytics report"""
        if not self.load_channel_data(username):
            return {"error": "Failed to load channel data"}
        
        report = {
            'channel_name': username,
            'subscribers_count': subscribers_count,
            'analysis_date': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'basic_metrics': self.get_basic_metrics(subscribers_count),
            'best_posts': self.get_best_posts(subscribers_count),
            'trends': self.get_trends_analysis(subscribers_count),
            'content_analysis': self.get_content_analysis(),
            'ai_insights': self.generate_ai_insights(username, subscribers_count)
        }
        
        return report

# Example usage
def main():
    """Example usage of analytics"""
    analytics = TelegramAnalytics()
    
    # Load data for a channel
    if analytics.load_channel_data("example_channel", days_back=30):
        # Generate report
        report = analytics.generate_comprehensive_report("example_channel", 10000)
        print(json.dumps(report, indent=2, default=str))
        
        # Create chart
        analytics.create_engagement_chart(10000, "reports/engagement_chart.html")

if __name__ == "__main__":
    main()
