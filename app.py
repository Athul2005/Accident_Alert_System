import streamlit as st
import pandas as pd
from datetime import datetime
import sqlite3
import os
from streamlit_js_eval import streamlit_js_eval
from streamlit_folium import folium_static, st_folium
import folium
from geopy.distance import geodesic  # To calculate distance
import requests

# --- Initialize SQLite Database ---
conn = sqlite3.connect('accident_reporting.db', check_same_thread=False)
c = conn.cursor()

# Create tables if they don't exist
c.execute('''CREATE TABLE IF NOT EXISTS users (
                phone TEXT PRIMARY KEY,
                name TEXT,
                email TEXT,
                pin TEXT
            )''')

c.execute('''CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_phone TEXT,
                name TEXT,
                location TEXT,
                media TEXT,
                place TEXT,
                description TEXT,
                timestamp TEXT,
                ambulance_status TEXT,
                assigned_to INTEGER DEFAULT NULL,
                hospital_assigned_to INTEGER DEFAULT NULL,
                hospital_status TEXT,
                FOREIGN KEY (assigned_to) REFERENCES ambulance_drivers (id)
                FOREIGN KEY(user_phone) REFERENCES users(phone)
            )''')
conn.commit()

# --- Initialize Session State ---
if "logged_in_user" not in st.session_state:
    st.session_state.logged_in_user = None

# Initialize session state for lat and lon
if "lat" not in st.session_state:
    st.session_state.lat = 8.5241  # Default latitude for Thiruvananthapuram
if "lon" not in st.session_state:
    st.session_state.lon = 76.9366  # Default longitude for Thiruvananthapuram

# --- Function to Display Chat Messages ---
def display_chat(messages):
    for msg in messages:
        with st.chat_message("assistant" if msg["sender"] == "bot" else "user"):
            st.markdown(msg["text"])

# --- Function to Convert latitude and longitude into place name            
def get_place_name(lat, lon): 
    """Convert latitude and longitude to a human-readable place name.""" 
    url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json" 
    headers = {"User-Agent": "AccidentReportApp/1.0"} 
    response = requests.get(url, headers=headers).json() 
    return response.get("display_name", "Location not found") 

# --- User Authentication (Login / Register) ---
if st.session_state.logged_in_user is None:
    st.title("🚨 Accident Reporting Chatbot")
    messages = [{"sender": "bot", "text": "Hi, what would you like to do?"}]
    display_chat(messages)

    choice = st.radio("Choose an option", ["Login", "Register"], index=None, key="auth_choice")

    if choice == "Register":
        with st.form("register_form"):
            name = st.text_input("Full Name")
            phone = st.text_input("Phone Number")
            email = st.text_input("Email")
            pin = st.text_input("4-digit PIN", type="password")
            submitted = st.form_submit_button("Register")

            if submitted:
                c.execute("SELECT * FROM users WHERE phone = ?", (phone,))
                if c.fetchone():
                    st.error("User already exists! Try logging in.")
                else:
                    c.execute("INSERT INTO users (phone, name, email, pin) VALUES (?, ?, ?, ?)", 
                              (phone, name, email, pin))
                    conn.commit()
                    st.success("Registration successful! Please log in.")

    elif choice == "Login":
        with st.form("login_form"):
            phone = st.text_input("Phone Number")
            pin = st.text_input("4-digit PIN", type="password")
            submitted = st.form_submit_button("Login")

            if submitted:
                c.execute("SELECT * FROM users WHERE phone = ? AND pin = ?", (phone, pin))
                user = c.fetchone()
                if user:
                    st.session_state.logged_in_user = phone
                    st.session_state.username = user[1]  # Store name in session
                    st.success(f"Welcome back, {user[1]}!")
                    st.session_state.page = "dashboard"
                    st.rerun()
                else:
                    st.error("Invalid credentials! Try again.")

# --- Dashboard (After Login) ---
if st.session_state.logged_in_user:
    st.sidebar.button("Logout", on_click=lambda: st.session_state.update({"logged_in_user": None, "page": "login"}))
    st.title("🚨 Accident Reporting Chatbot")

    user_phone = st.session_state.logged_in_user
    c.execute("SELECT * FROM users WHERE phone = ?", (user_phone,))
    user = c.fetchone()
    
    messages = [{"sender": "bot", "text": f"Hi {user[1]}, what would you like to do?"}]
    display_chat(messages)

    choice = st.radio("Choose an option", ["Report an Accident", "View Previous Reports"], index=None, key="main_choice")

    if choice == "Report an Accident":
        st.subheader("Auto-Detect & Manually Select Location")

        # Default location: Thiruvananthapuram
        default_lat, default_lon = 8.5241, 76.9366
        tvm_coords = (default_lat, default_lon)

        # Request high-accuracy GPS location
        location = streamlit_js_eval(
            js_expressions="""
            new Promise((resolve, reject) => 
                navigator.geolocation.getCurrentPosition(
                    (pos) => resolve({latitude: pos.coords.latitude, longitude: pos.coords.longitude, accuracy: pos.coords.accuracy}),
                    (err) => reject(err),
                    { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
                )
            )
            """,
            key="get_location"
        )

        # Process location data
        if location and "latitude" in location and "longitude" in location:
            lat, lon, accuracy = location["latitude"], location["longitude"], location["accuracy"]
            user_coords = (lat, lon)
            place = get_place_name(lat, lon)

            if geodesic(user_coords, tvm_coords).km > 50:
                st.warning(f"Detected location ({lat}, {lon}) and Corresponding place is {place} is too far from Thiruvananthapuram. Using default location.")
                lat, lon = default_lat, default_lon
            else:
                st.success(f"Detected Location: {lat}, {lon} and Corresponding place is {place} (Accuracy: ±{accuracy} meters)")
        else:
            st.warning("Unable to detect location. Using default: Thiruvananthapuram.")
            lat, lon = default_lat, default_lon

        # Update session state with detected or default location
        st.session_state.lat = lat
        st.session_state.lon = lon

        # Display map with marker
        map_ = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=15)
        marker = folium.Marker([st.session_state.lat, st.session_state.lon], tooltip="Move me!", draggable=True, icon=folium.Icon(color="red", icon="map-marker", prefix="fa"))
        map_.add_child(marker)

        # Use st_folium to render the map and get updated data
        map_data = st_folium(map_, height=400, width=700)

        # Update lat and lon if marker is moved or clicked
        if map_data and map_data.get("last_clicked"):
            st.session_state.lat = map_data["last_clicked"]["lat"]
            st.session_state.lon = map_data["last_clicked"]["lng"]
            place = get_place_name(st.session_state.lat, st.session_state.lon)
            st.success(f"Selected Location: {st.session_state.lat}, {st.session_state.lon} and Corresponding place is {place}")

        # Report form
        with st.form("report_form"):
            media = st.file_uploader("Upload Photos/Videos (Optional)", accept_multiple_files=True)
            description = st.text_area("Describe the Accident")
            submit = st.form_submit_button("Submit Report")
            
            if submit:
                # Debugging: Print the location before inserting into the database
                #st.write(f"Debug: Location to be inserted into the database - Latitude: {st.session_state.lat}, Longitude: {st.session_state.lon}")

                media_filenames = []
                if media:
                    for file in media:
                        file_path = os.path.join("uploads", file.name)
                        with open(file_path, "wb") as f:
                            f.write(file.getbuffer())
                        media_filenames.append(file.name)

                # Insert report into the database
                c.execute("INSERT INTO reports (user_phone, name, location, media, place, description, timestamp, ambulance_status, hospital_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (user_phone, user[1], f"{st.session_state.lat}, {st.session_state.lon}", ",".join(media_filenames), place, description, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "Waiting", "Waiting"))
                conn.commit()
                st.success("Report submitted successfully!")
    
    elif choice == "View Previous Reports":
        c.execute("SELECT * FROM reports WHERE user_phone = ?", (user_phone,))
        user_reports = c.fetchall()
        
        if not user_reports:
            st.info("No previous reports found.")
        else:
            for report in user_reports:
                with st.expander(f"📍 {report[5]} ({report[7]})"):
                    st.write(f"**Description:** {report[6]}")
                    if report[4]:
                        media_files = report[4].split(',')
                        for media in media_files:
                            if media.lower().endswith(('png', 'jpg', 'jpeg')):
                                st.image(os.path.join("uploads", media), caption=media)
                            elif media.lower().endswith(('mp4', 'mov', 'avi')):
                                st.video(os.path.join("uploads", media))
                            else:
                                st.write(f"File: {media}")

# --- Close Database Connection ---
conn.close()