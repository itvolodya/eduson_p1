# appstore_reviews.py (исправленная версия)
import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
import re
import json

# Конфигурация
st.set_page_config(page_title="App Store Reviews Collector", layout="wide")

# Константы
RSS_HOST = "https://itunes.apple.com"
PAGE_URL = "https://apps.apple.com/{storefront}/app/id{app_id}?see-all=reviews"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
}

PERIOD_OPTIONS = {
    "1": ("Last 24 hours", 1),
    "2": ("Last 30 days", 30), 
    "3": ("Last 90 days", 90),
    "6": ("All time", None)
}

def extract_app_id(url):
    """Извлекает app_id из URL приложения"""
    match = re.search(r"/id(\d+)", url) or re.search(r"[?&]id=(\d+)", url)
    if not match:
        st.error("🔍 Invalid App Store URL. Expected format: .../id123456789")
        return None
    return match.group(1)

def get_storefront(url, user_input):
    """Определяет витрину с учетом пользовательского ввода"""
    parts = [p for p in urlparse(url).path.split("/") if p]
    from_url = next((p for p in parts if len(p) == 2 and p.isalpha()), "us")
    return user_input.lower() if user_input else from_url

def fetch_rss_reviews(session, app_id, storefront):
    """Получает отзывы через RSS API"""
    url = f"{RSS_HOST}/{storefront}/rss/customerreviews/id={app_id}/sortBy=mostRecent/json"
    try:
        response = session.get(url, timeout=20)
        response.raise_for_status()
        data = response.json()
        return data.get("feed", {}).get("entry", [])
    except Exception as e:
        st.warning(f"⚠️ RSS feed unavailable: {str(e)}")
        return []

def fetch_page_reviews(session, app_id, storefront):
    """Резервный метод: парсит страницу приложения"""
    url = PAGE_URL.format(storefront=storefront, app_id=app_id)
    try:
        response = session.get(url, timeout=20)
        response.encoding = "utf-8"  # Важно для корректного отображения символов
        
        # Ищем JSON-данные в HTML
        match = re.search(r'<script[^>]*id="serialized-server-data"[^>]*>(.*?)</script>', response.text, re.S)
        if not match:
            return []
            
        data = json.loads(match.group(1))
        shelf = data['data'][0]['data']['shelfMapping']['allProductReviews']
        return [item['review'] for item in shelf.get('items', []) if 'review' in item]
        
    except Exception as e:
        st.error(f"❌ Failed to parse page: {str(e)}")
        return []

def process_reviews(raw_reviews, app_id, storefront, days_limit=None):
    """Обрабатывает сырые отзывы в DataFrame"""
    reviews = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_limit) if days_limit else None
    
    for item in raw_reviews:
        try:
            date_str = item.get('updated', {}).get('label', '') or item.get('date', '')
            date = datetime.fromisoformat(date_str.replace('Z', '+00:00')) if date_str else None
            
            if cutoff and date and date < cutoff:
                continue
                
            reviews.append({
                'app_id': app_id,
                'storefront': storefront,
                'review_id': item.get('id', {}).get('label', '') or str(item.get('id', '')),
                'author': item.get('author', {}).get('name', {}).get('label', '') or item.get('reviewerName', ''),
                'rating': item.get('im:rating', {}).get('label', '') or str(item.get('rating', '')),
                'title': item.get('title', {}).get('label', '') or item.get('title', ''),
                'content': item.get('content', {}).get('label', '') or item.get('contents', ''),
                'date': date_str,
                'date_parsed': date,
                'source': 'RSS' if 'im:rating' in item else 'Page'
            })
        except Exception as e:
            st.warning(f"Skipping malformed review: {str(e)}")
    
    return pd.DataFrame(reviews).sort_values('date_parsed', ascending=False)

# Интерфейс
def main():
    st.title("📱 App Store Reviews Collector")
    st.markdown("""
    Collect public reviews from any iOS app.  
    Works even when official RSS feed is empty (most cases).
    """)
    
    with st.sidebar:
        st.header("Settings")
        app_url = st.text_input("App Store URL", 
            placeholder="https://apps.apple.com/us/app/telegram-messenger/id686449807",
            help="Paste any App Store app URL containing '/id123456789'")
        
        custom_storefront = st.text_input("Custom Storefront (optional)", 
            placeholder="us, ru, gb, etc.",
            help="Override country storefront from URL")
        
        period = st.selectbox("Time period", 
            options=list(PERIOD_OPTIONS.keys()),
            format_func=lambda x: PERIOD_OPTIONS[x][0],
            index=3)  # Default to "All time"
    
    if st.button("🚀 Collect Reviews", type="primary"):
        if not app_url:
            st.warning("Please enter an App Store URL")
            return
            
        with st.spinner("Processing..."):
            # Извлекаем параметры
            app_id = extract_app_id(app_url)
            if not app_id:
                return
                
            storefront = get_storefront(app_url, custom_storefront)
            days_limit = PERIOD_OPTIONS[period][1]
            
            # Собираем данные
            session = requests.Session()
            session.headers.update(HEADERS)
            
            st.info(f"🔎 Checking app ID: {app_id} (storefront: {storefront})")
            
            # Пробуем оба источника
            rss_reviews = fetch_rss_reviews(session, app_id, storefront)
            page_reviews = [] if rss_reviews else fetch_page_reviews(session, app_id, storefront)
            
            # Обрабатываем результат
            df = process_reviews(rss_reviews + page_reviews, app_id, storefront, days_limit)
            
            if not df.empty:
                st.success(f"✅ Collected {len(df)} reviews ({len(rss_reviews)} from RSS, {len(page_reviews)} from page)")
                
                # Показываем таблицу
                st.dataframe(df[['author', 'rating', 'title', 'date', 'source']], 
                            height=400,
                            column_config={
                                'rating': st.column_config.NumberColumn(format="%d ⭐"),
                                'date': st.column_config.DatetimeColumn()
                            })
                
                # Кнопка скачивания
                csv = df.to_csv(index=False).encode('utf-8-sig')  # Для Excel
                st.download_button(
                    label="📥 Download CSV",
                    data=csv,
                    file_name=f"appstore_reviews_{app_id}_{datetime.now().date()}.csv",
                    mime="text/csv"
                )
                
                # Дополнительная аналитика
                with st.expander("📊 Statistics"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Total reviews", len(df))
                        st.metric("Average rating", round(df['rating'].astype(float).mean(), 2))
                    with col2:
                        st.metric("From RSS feed", len(rss_reviews))
                        st.metric("From app page", len(page_reviews))
                    
                    st.bar_chart(df['rating'].value_counts().sort_index(), height=200)
            else:
                st.error("No reviews found. Possible reasons:")
                st.markdown("""
                - The app has no reviews in selected region
                - Apple's RSS feed is temporarily unavailable
                - The app ID is incorrect
                - You're being rate-limited (try again later)
                """)

if __name__ == "__main__":
    main()