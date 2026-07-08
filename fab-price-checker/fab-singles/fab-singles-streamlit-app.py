import streamlit as st
import pandas as pd
import requests
import json
import os
import urllib.parse

# Set up page configuration
st.set_page_config(page_title="Flesh and Blood Singles Finder", layout="wide")

# Determine paths for both datasets
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MASTER_CSV_FILENAME = "master-fab-singles-links.csv"
PRINTINGS_CSV_FILENAME = "cards_printings_unique.csv"

MASTER_CSV_PATH = os.path.join(BASE_DIR, MASTER_CSV_FILENAME)
PRINTINGS_CSV_PATH = os.path.join(BASE_DIR, PRINTINGS_CSV_FILENAME)

@st.cache_data
def load_and_prepare_data():
    if not os.path.exists(MASTER_CSV_PATH):
        raise FileNotFoundError(f"Could not find '{MASTER_CSV_FILENAME}' at path: {MASTER_CSV_PATH}")
    if not os.path.exists(PRINTINGS_CSV_PATH):
        raise FileNotFoundError(f"Could not find '{PRINTINGS_CSV_FILENAME}' at path: {PRINTINGS_CSV_PATH}")
        
    # Load files with low_memory=False to suppress DtypeWarnings
    df_master = pd.read_csv(MASTER_CSV_PATH, low_memory=False)
    df_printings = pd.read_csv(PRINTINGS_CSV_PATH, low_memory=False)
    
    # Pre-extract unique card names and unique stores within the cache to keep UI responsive
    unique_card_names = sorted(df_printings["name"].dropna().unique())
    unique_stores = sorted(df_master["Store Name"].dropna().unique())
    
    return df_master, df_printings, unique_card_names, unique_stores

try:
    df_master, df_printings, unique_card_names, unique_stores = load_and_prepare_data()
except Exception as e:
    st.error(f"⚠️ Error loading CSV files: {e}")
    st.stop()


# ----------------------------------------------------
# SIDEBAR: STORE LISTING ONLY
# ----------------------------------------------------
with st.sidebar:
    st.header("🏪 Tracked Store Listing")
    st.write("The app is currently pulling live data from the following shops:")
    
    store_counts = df_master["Store Name"].value_counts()
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
st.write("Type a card name to filter options, select your card, and search live prices.")

# Initialize session state variables if they don't exist yet
if "search_term_value" not in st.session_state:
    st.session_state.search_term_value = ""

if "search_history" not in st.session_state:
    st.session_state.search_history = []

# Callback function to handle the clear button click
def clear_search():
    st.session_state.search_term_value = ""

# Callback function to load a card from recent history
def load_historical_card(card_name):
    st.session_state.search_term_value = card_name

# Create two columns with vertical alignment fixed at the bottom row boundary
col1, col2 = st.columns([5, 1], vertical_alignment="bottom")

with col1:
    search_term = st.text_input(
        "Type card name to search:", 
        placeholder="Type at least 3 letters... e.g., Fyendal",
        key="search_term_value"
    )

with col2:
    if st.button("Clear ✖", on_click=clear_search, use_container_width=True):
        st.rerun()

# NEW: We reserve an empty UI container slot here. 
# This lets us inject the history layout block *after* the search history state updates down below!
history_container = st.container()

selected_card_name = None

# Step 2: Dynamically inject the dropdown selection ONLY when criteria met
if len(search_term) >= 3:
    filtered_options = [
        card for card in unique_card_names 
        if search_term.lower() in card.lower()
    ]
    
    if filtered_options:
        default_index = 0
        if search_term in filtered_options:
            default_index = filtered_options.index(search_term)
            
        selected_card_name = st.selectbox(
            f"Select exact card matching '{search_term}':",
            options=filtered_options,
            index=default_index
        )
    else:
        st.warning("No cards found matching that search term. Check your spelling!")
else:
    st.info("💡 Please type at least 3 characters to display matching card options.")

# --- STORE FILTER HIDDEN FOR NOW ---
selected_stores = unique_stores

# Step 3: Action search button execution
if st.button("Search Live Prices", type="primary"):
    if not selected_card_name:
        st.error("Please filter and select a valid card from the dropdown first.")
    elif not selected_stores:
        st.warning("Please select at least one store to perform a search.")
    else:
        st.subheader(f"Results for: {selected_card_name}")
        
        # --- UPDATE SEARCH HISTORY IMMEDIATELY ---
        updated_history = [item for item in st.session_state.search_history if item != selected_card_name]
        updated_history.insert(0, selected_card_name)
        st.session_state.search_history = updated_history[:3]
        
        # 1. Retrieve all unique printings_identifiers for the chosen card name
        matched_identifiers = df_printings[df_printings["name"] == selected_card_name]["printings_identifier"].dropna().unique()
        
        if len(matched_identifiers) == 0:
            st.error("No valid card numbers found for this card in the printing database.")
        else:
            # 2. Case-insensitive string matching across the single Card Number column
            str_identifiers = [str(x).strip().lower() for x in matched_identifiers]
            
            matching_rows = df_master[
                (df_master["Card Number"].astype(str).str.strip().str.lower().isin(str_identifiers)) & 
                (df_master["Store Name"].isin(selected_stores))
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
                                "URL": url
                            })
                    progress_bar.progress((idx + 1) / total_rows)
            
            progress_bar.empty()
            
            # Render HTML results table
            if results:
                table_html = """
                <style>
                    :root {
                        --bg-color: #ffffff;
                        --text-color: #31333F;
                        --header-bg: #f0f2f6;
                        --border-color: #eeeeee;
                        --link-color: #ff4b4b;
                    }
                    @media (prefers-color-scheme: dark) {
                        :root {
                            --bg-color: #0e1117;
                            --text-color: #fafafa;
                            --header-bg: #1d2430;
                            --border-color: #31333f;
                            --link-color: #ff6c6c;
                        }
                    }
                    body { background-color: var(--bg-color); margin: 0; padding: 0; }
                    table { width: 100%; border-collapse: collapse; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 14px; background-color: var(--bg-color); }
                    th { padding: 12px 10px; border-bottom: 2px solid var(--border-color); background-color: var(--header-bg); color: var(--text-color); text-align: left; }
                    td { padding: 10px; border-bottom: 1px solid var(--border-color); color: var(--text-color); }
                    a { color: var(--link-color); text-decoration: none; font-weight: 500; }
                    a:hover { text-decoration: underline; }
                </style>
                <table>
                    <thead>
                        <tr>
                            <th>Store Name</th>
                            <th>Product Title</th>
                            <th>Condition</th>
                            <th>Price</th>
                        </tr>
                    </thead>
                    <tbody>
                """
                for item in results:
                    table_html += f"""
                        <tr>
                            <td>{item['Store Name']}</td>
                            <td><a href="{item['URL']}" target="_blank">{item['Product']}</a></td>
                            <td style="font-weight: 500;">{item['Condition']}</td>
                            <td>{item['Price']}</td>
                        </tr>
                    """
                table_html += "</tbody></table>"
                
                calculated_height = max(180, (len(results) * 42) + 60)
                
                safe_html = urllib.parse.quote(table_html)
                st.iframe(f"data:text/html;charset=utf-8,{safe_html}", height=calculated_height)
            else:
                st.warning("❌ This card printing is currently out of stock across the tracked stores.")

# ----------------------------------------------------
# DYNAMIC HISTORY RENDERING
# ----------------------------------------------------
# By rendering the history content inside our pre-allocated container block, 
# it will accurately include the search you *just* executed instantly.
if st.session_state.search_history:
    with history_container:
        st.write("🕒 **Recent Searches:**")
        history_cols = st.columns(len(st.session_state.search_history))
        for i, hist_card in enumerate(st.session_state.search_history):
            with history_cols[i]:
                st.button(
                    f"🔗 {hist_card}", 
                    key=f"hist_{i}", 
                    on_click=load_historical_card, 
                    args=(hist_card,), 
                    use_container_width=True
                )