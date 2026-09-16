# appstore_reviews.py
import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
import re
import time

# Конфигурация Streamlit
st.set_page_config(
    page_title="App Store Reviews Collector",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Константы
RSS_HOST = "https://itunes.apple.com"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
MAX_RETRIES = 3
REQUEST_TIMEOUT = 20

PERIODS = {
    "1": ("Last 24 hours", 1),
    "2": ("Last 30 days", 30),
    "3": ("Last 90 days", 90),
    "4": ("Last 180 days", 180),
    "5": ("Last 365 days", 365),
    "6": ("All available time", None)
}

# Функции обработки
def extract_app_id(url):
    """Извлекает app_id из URL App Store"""
    match = re.search(r"/id(\d+)", url) or re.search(r"[?&]id=(\d+)", url)
    if not match:
        st.error("Invalid App Store URL. Expected format: .../id123456789")
        return None
    return match.group(1)

def extract_storefront(url, default="us"):
    """Определяет код витрины из URL"""
    parts = [p for p in urlparse(url).path.split("/") if p]
    for part in parts:
        if len(part) == 2 and part.isalpha():
            return part.lower()
    return default

def build_session():
    """Создает HTTP сессию с настройками"""
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/xml, text/html;q=0.9, */*;q=0.8"
    })
    return session

def fetch_reviews(session, app_id, storefront, days=None):
    """Основная функция сбора отзывов"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days else None
    url = f"{RSS_HOST}/{storefront}/rss/customerreviews/id={app_id}/sortBy=mostRecent/json"
    
    try:
        response = session.get(url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        
        reviews = []
        entries = data.get("feed", {}).get("entry", [])
        
        for entry in entries:
            if not entry.get("im:rating"):
                continue  # Пропускаем технические записи
            
            review = {
                "app_id": app_id,
                "storefront": storefront,
                "review_id": entry.get("id", {}).get("label", ""),
                "author": entry.get("author", {}).get("name", {}).get("label", ""),
                "rating": entry.get("im:rating", {}).get("label", ""),
                "title": entry.get("title", {}).get("label", ""),
                "content": entry.get("content", {}).get("label", ""),
                "date": entry.get("updated", {}).get("label", ""),
            }
            
            if not cutoff or datetime.fromisoformat(review["date"]) >= cutoff:
                reviews.append(review)
                
        return reviews
        
    except Exception as e:
        st.error(f"Error fetching reviews: {str(e)}")
        return []

# Интерфейс Streamlit
def main():
    st.title("📱 App Store Reviews Collector")
    st.markdown("Collect public reviews from any App Store app by URL")
    
    with st.sidebar:
        st.header("Settings")
        app_url = st.text_input("App Store URL", 
                               placeholder="https://apps.apple.com/us/app/telegram-messenger/id686449807")
        custom_storefront = st.text_input("Custom Storefront (optional)", 
                                        placeholder="us, ru, gb, etc.")
        period = st.selectbox("Review period", 
                            options=list(PERIODS.keys()),
                            format_func=lambda x: PERIODS[x][0])
    
    if st.button("Collect Reviews"):
        if not app_url:
            st.warning("Please enter an App Store URL")
            return
            
        app_id = extract_app_id(app_url)
        if not app_id:
            return
            
        default_storefront = extract_storefront(app_url)
        storefront = custom_storefront.lower() if custom_storefront else default_storefront
        
        with st.spinner(f"Collecting reviews for app {app_id} from {storefront}..."):
            session = build_session()
            days = PERIODS[period][1]
            reviews = fetch_reviews(session, app_id, storefront, days)
            
            if reviews:
                df = pd.DataFrame(reviews)
                st.success(f"✅ Collected {len(df)} reviews")
                
                st.dataframe(df)
                
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name=f"appstore_reviews_{app_id}_{datetime.now().date()}.csv",
                    mime="text/csv"
                )
            else:
                st.warning("No reviews found for the selected period")

if __name__ == "__main__":
    main()