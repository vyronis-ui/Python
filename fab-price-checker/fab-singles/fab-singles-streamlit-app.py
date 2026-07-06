import streamlit as st
import pandas as pd
import requests
import json
import os
import streamlit.components.v1 as components

# Set up page configuration
st.set_page_config(page_title="Flesh and Blood Singles Finder", layout="wide")

# Automatically determine the absolute path of the directory containing this script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_FILENAME = "master-fab-singles-links.csv"
CSV_PATH = os.path.join(BASE_DIR, CSV_FILENAME)

@st.cache_data
def load_data():
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"Could not find '{CSV_FILENAME}' at path: {CSV_PATH}")
    return pd.read_csv(CSV_PATH)

try:
    df = load_data()
except Exception as e:
    st.error(f"⚠️ Error loading CSV file: {e}")
    st.stop()


# ----------------------------------------------------
# SIDEBAR: STORE LISTING
# ----------------------------------------------------
with st.sidebar:
    st.header("🏪 Tracked Store Listing")
    st.write("The app is currently pulling live data from the following shops:")
    
    # Calculate how many links exist per store for a helpful metric breakdown
    store_counts = df["Store Name"].value_counts()
    
    # Render stores as a clean bulleted list with their database count
    for store, count in store_counts.items():
        st.markdown(f"• **{store}** ({count:,} card links indexed)")
        
    st.divider()
    st.caption("Note: Shops are automatically indexed from your attached database CSV file.")


# Helper function to fetch ONLY available variants
def fetch_card_variants(url):
    try:
        json_url = url if url.endswith(".js") else f"{url}.js"
        response = requests.get(json_url, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            variants = data.get("variants", [])
            
            if variants:
                available_variants = []
                
                for variant in variants:
                    is_available = variant.get("available", False)
                    
                    # Only collect variants that are actively available
                    if is_available:
                        title = variant.get("title", "").strip()
                        price_raw = variant.get("price", 0)
                        price = f"${price_raw / 100:.2f}"
                        
                        available_variants.append({
                            "Condition": title,
                            "Price": price,
                            "Availability": "Available"
                        })
                
                return available_variants
                
            else:
                # Fallback if the store layout doesn't use standard multi-variant tracking lists
                available = data.get("available", False)
                if available:
                    price_raw = data.get("price", 0)
                    return [{
                        "Condition": "Standard",
                        "Price": f"${price_raw / 100:.2f}",
                        "Availability": "Available"
                    }]
                
    except Exception:
        pass
    
    return []

# ----------------------------------------------------
# MAIN APP UI LAYOUT
# ----------------------------------------------------
st.title("🃏 Flesh and Blood Singles Finder")
st.write("Type a card name below, filter your target stores, and search live prices.")

# Get unique values for both select boxes
unique_cards = sorted(df["Base Card Name"].dropna().unique())
unique_stores = sorted(df["Store Name"].dropna().unique())

# Dropdown search for the Card Name
selected_card = st.selectbox(
    "Search for a card name:",
    options=unique_cards,
    index=None,
    placeholder="Type to search..."
)

# NEW FILTER: Multi-select filter for limiting store selection (All selected by default)
selected_stores = st.multiselect(
    "Filter by Stores:",
    options=unique_stores,
    default=unique_stores,
    placeholder="Select stores to include..."
)

if st.button("Search", type="primary") and selected_card:
    if not selected_stores:
        st.warning("Please select at least one store to perform a search.")
    else:
        st.subheader(f"Results for: {selected_card}")
        
        # Filter dataset by chosen card name AND chosen stores
        matching_rows = df[
            (df["Base Card Name"] == selected_card) & 
            (df["Store Name"].isin(selected_stores))
        ]
        
        results = []
        
        progress_bar = st.progress(0)
        total_rows = len(matching_rows)
        
        if total_rows > 0:
            for idx, (_, row) in enumerate(matching_rows.iterrows()):
                store = row.get("Store Name", "Unknown Store")
                title_unmodified = row.get("Product Title Unmodified", "Link")
                url = row.get("Product Link", "")
                
                if url:
                    variants_data = fetch_card_variants(url)
                    for v in variants_data:
                        results.append({
                            "Store Name": store,
                            "Product": title_unmodified,
                            "Condition": v["Condition"],
                            "Price": v["Price"],
                            "Availability": v["Availability"],
                            "URL": url
                        })
                
                progress_bar.progress((idx + 1) / total_rows)
        
        progress_bar.empty()
        
        # Only render table if we found items that are actively in stock
        if results:
            table_html = """
            <table style="width:100%; border-collapse: collapse; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px;">
                <thead>
                    <tr style="background-color: #f0f2f6; text-align: left;">
                        <th style="padding: 12px 10px; border-bottom: 2px solid #ddd; color: #31333F;">Store Name</th>
                        <th style="padding: 12px 10px; border-bottom: 2px solid #ddd; color: #31333F;">Product Title</th>
                        <th style="padding: 12px 10px; border-bottom: 2px solid #ddd; color: #31333F;">Condition</th>
                        <th style="padding: 12px 10px; border-bottom: 2px solid #ddd; color: #31333F;">Price</th>
                        <th style="padding: 12px 10px; border-bottom: 2px solid #ddd; color: #31333F;">Availability</th>
                    </tr>
                </thead>
                <tbody>
            """
            
            for item in results:
                avail_style = "color: #28a745; font-weight: bold;"
                    
                table_html += f"""
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #eee; color: #31333F;">{item['Store Name']}</td>
                        <td style="padding: 10px; border-bottom: 1px solid #eee;">
                            <a href="{item['URL']}" target="_blank" style="color: #ff4b4b; text-decoration: none; font-weight: 500;">{item['Product']}</a>
                        </td>
                        <td style="padding: 10px; border-bottom: 1px solid #eee; color: #31333F; font-weight: 500;">{item['Condition']}</td>
                        <td style="padding: 10px; border-bottom: 1px solid #eee; color: #31333F;">{item['Price']}</td>
                        <td style="padding: 10px; border-bottom: 1px solid #eee; {avail_style}">{item['Availability']}</td>
                    </tr>
                """
                
            table_html += "</tbody></table>"
            
            calculated_height = max(180, (len(results) * 42) + 60)
            components.html(table_html, height=calculated_height, scrolling=True)
        else:
            st.warning("❌ This card is currently out of stock across the selected stores.")
            
elif not selected_card:
    st.info("Please select a card from the dropdown to begin.")