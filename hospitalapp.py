import streamlit as st
import sqlite3
import folium
from streamlit_folium import st_folium
from streamlit_js_eval import streamlit_js_eval
import requests
import base64
import os
from datetime import datetime
import face_recognition
import cv2
import numpy as np
from PIL import Image
import io

# OSRM API URL (No API Key Required)
OSRM_URL = "http://router.project-osrm.org/route/v1/driving"

# Telegram Bot Token (Replace with your actual bot token)
BOT_TOKEN = "7661586372:AAGtwV2fksGTl6kuS5h9mdr2SDCBqsoD50U"

# --- Database Connection ---
conn = sqlite3.connect("accident_reporting.db", check_same_thread=False)
c = conn.cursor()

# Create hospitals table if it doesn't exist
c.execute('''CREATE TABLE IF NOT EXISTS hospitals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT UNIQUE,
                name TEXT,
                pin TEXT,
                status TEXT,
                latitude REAL,
                longitude REAL
            )''')

# Create old_patient_records table if it doesn't exist
c.execute('''CREATE TABLE IF NOT EXISTS old_patient_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                age INTEGER,
                gender TEXT,
                place TEXT,
                phone TEXT,
                emergency_phone TEXT,
                tele_id TEXT,
                medical_history TEXT,
                treatment TEXT,
                lab_reports TEXT,
                doctor_notes TEXT,
                medical_info TEXT,
                image BLOB,
                face_encodings BLOB NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )''')
conn.commit()

# --- Initialize Session State ---
if "logged_in_hospital" not in st.session_state:
    st.session_state.logged_in_hospital = None
if "selected_accident" not in st.session_state:
    st.session_state.selected_accident = None
if "show_add_patient" not in st.session_state:
    st.session_state.show_add_patient = False
if "show_find_patient" not in st.session_state:
    st.session_state.show_find_patient = False

# --- Function to Play Sound ---
def play_sound():
    # HTML audio element to play a sound
    audio_path = "notification.mp3"  # Replace with the path to your sound file
    if os.path.exists(audio_path):
        audio_bytes = open(audio_path, "rb").read()
        audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
        audio_html = f"""
            <audio autoplay="true">
                <source src="data:audio/mp3;base64,{audio_base64}" type="audio/mp3">
            </audio>
        """
        st.components.v1.html(audio_html, height=0)
    else:
        st.warning("Notification sound file not found!")

# --- Funtion to Convert latitude and longitude into place name            
def get_place_name(lat, lon): 
    """Convert latitude and longitude to a human-readable place name.""" 
    url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json" 
    headers = {"User-Agent": "AccidentReportApp/1.0"} 
    response = requests.get(url, headers=headers).json() 
    return response.get("display_name", "Location not found") 
    
# Function to compare face encodings
def compare_faces(uploaded_encoding, stored_encoding):
    if uploaded_encoding is None or stored_encoding is None:
        return False
    
    stored_encoding = np.frombuffer(stored_encoding, dtype=np.float64)
    return face_recognition.compare_faces([stored_encoding], np.frombuffer(uploaded_encoding, dtype=np.float64))[0]
    
# Function to extract face encoding
def recognize_face(image_bytes):
    image = np.array(Image.open(io.BytesIO(image_bytes)))
    rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    
    face_locations = face_recognition.face_locations(rgb_image)
    face_encodings = face_recognition.face_encodings(rgb_image, face_locations)
    
    if face_encodings:
        return face_encodings[0].tobytes()  # Store as binary
    else:
        return None

# --- Function to Fetch Old Patient Images ---
def fetch_old_patient_images():
    c.execute("SELECT image FROM old_patient_records")
    return [row[0] for row in c.fetchall()]

# Function to send a Telegram message
def send_telegram_message(chat_id, message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": message}
    response = requests.post(url, data=data)
    
    if response.status_code == 200:
        print("Message sent successfully!")
        return True
    else:
        print("Failed to send message:", response.text)
        return False

# --- Hospital Authentication ---
if st.session_state.logged_in_hospital is None:
    st.title("🏥 Hospital System")
    choice = st.radio("Choose an option", ["Login", "Register"], index=None)
    if choice == "Register":
        with st.form("register_form"):
            name = st.text_input("Hospital Name")
            phone = st.text_input("Phone Number")
            pin = st.text_input("4-digit PIN", type="password")

            submitted = st.form_submit_button("Register")
            if submitted:
                # Check if the phone number already exists
                c.execute("SELECT * FROM hospitals WHERE phone = ?", (phone,))
                existing_user = c.fetchone()
                if existing_user:
                    st.error("Hospital already exists! Try logging in.")
                else:
                    # Insert new hospital into the database
                    c.execute(
                        "INSERT INTO hospitals (phone, name, pin, status) VALUES (?, ?, ?, ?)",
                        (phone, name, pin, "Not Ready"),
                    )
                    conn.commit()
                    st.success("Registration successful! Please log in.")
            
            # Default location: Thiruvananthapuram
            default_lat, default_lon = 8.5241, 76.9366

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

            # --- Current Location is fetched ---
            if location:
                default_lat, default_lon, accuracy = location["latitude"], location["longitude"], location["accuracy"]
        
        # Create a map for location selection
        st.subheader("Select Hospital Location")
        m = folium.Map(location=[default_lat, default_lon], zoom_start=14)
        marker = folium.Marker(
            [default_lat, default_lon],
            tooltip="Drag to set location",
            draggable=True,
            icon=folium.Icon(icon="map-marker", prefix="fa", color="green"),
        )
        m.add_child(marker)
        map_data = st_folium(m, height=400, width=700)
        
        # Extract the latest selected coordinates
        if map_data and map_data.get("last_clicked"):
            lat, lon = map_data["last_clicked"]["lat"], map_data["last_clicked"]["lng"]
            st.success(f"Selected Location: {get_place_name(lat, lon)}")
        else:
            lat, lon = default_lat, default_lon
            st.info("Click on the map to select your location.")
        if st.button("Update Location"):
            c.execute("UPDATE hospitals SET latitude = ?, longitude = ? WHERE phone = ?", (lat, lon, phone))
            conn.commit()
            st.success("Location updated successfully!!!")


    elif choice == "Login":
        with st.form("login_form"):
            phone = st.text_input("Phone Number")
            pin = st.text_input("4-digit PIN", type="password")
            submitted = st.form_submit_button("Login")
            if submitted:
                # Fetch the hospital with the given phone number and PIN
                c.execute("SELECT * FROM hospitals WHERE phone = ? AND pin = ?", (phone, pin))
                hospital = c.fetchone()
                if hospital:
                    # Update session state with the hospital's ID
                    st.session_state.logged_in_hospital = hospital[0]  # Store hospital ID in session state
                    st.toast(f"Welcome back, {hospital[2]}!", icon="🏥")  # Notification for login success
                    play_sound()  # Play sound on login
                    st.rerun()  # Refresh the page to show the dashboard
                else:
                    st.error("Invalid credentials! Try again.")

# --- Hospital Dashboard ---
if st.session_state.logged_in_hospital:
    hospital_id = st.session_state.logged_in_hospital
    if st.sidebar.button("Logout", key="logout_button"):
        st.session_state.update({"logged_in_hospital": None})
        st.rerun()
    
    # Fetch hospital details
    c.execute("SELECT * FROM hospitals WHERE id = ?", (hospital_id,))
    hospital = c.fetchone()

    # --- Sidebar Buttons for Old Patient Records ---
    if st.sidebar.button("Add Old Patient Details"):
        st.session_state.show_add_patient = True
        st.session_state.show_find_patient = False
        st.session_state.selected_accident = None
        st.rerun()

    if st.sidebar.button("Find Old Patient Details"):
        st.session_state.show_find_patient = True
        st.session_state.show_add_patient = False
        st.session_state.selected_accident = None
        st.rerun()

    if st.sidebar.button("Home"):
        st.session_state.logged_in_hospital = hospital[0]
        st.session_state.show_add_patient = False
        st.session_state.show_find_patient = False
        st.session_state.selected_accident = None

    # --- Add Old Patient Details Page ---
    if st.session_state.show_add_patient:
        st.title("📝 Add Old Patient Details")
        with st.form("add_patient_form"):
            # Patient Details
            name = st.text_input("Patient Name")
            age = st.number_input("Age", min_value=0, max_value=120, step=1)
            gender = st.selectbox("Gender", ["Male", "Female", "Other"])
            place = st.text_input("Place")
            phone = st.text_input("Contact Number")
            emergency_contact = st.text_input("Emergency Contact")
            telegram_id = st.text_input("Telegram ID")

            # Medical History & Treatment    
            medical_history = st.text_area("Medical History")
            treatment = st.text_area("Treatment Plan")
            lab_reports = st.text_area("Lab Reports & Diagnostics")
            doctor_notes = st.text_area("Doctor's Notes")
            medical_info = st.text_area("Remark")

            # Face photo Capture
            image = st.file_uploader("Upload Patient Image", type=["jpg", "jpeg", "png"])
            
            submitted = st.form_submit_button("Add Patient")
            if submitted:
                if name and phone and medical_info and image:
                    # Convert image to binary data
                    image_bytes = image.read()
                    image_encoding = recognize_face(image_bytes)
                    # Insert into old_patient_records table
                    c.execute(
                        """INSERT INTO old_patient_records (name, age, gender, place, phone, emergency_phone, tele_id, 
                            medical_history, treatment, lab_reports, doctor_notes, medical_info,
                            image, face_encodings) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (name, age, gender, place, phone, emergency_contact, telegram_id, medical_history, treatment, 
                          lab_reports, doctor_notes, medical_info, image_bytes, image_encoding),
                    )
                    conn.commit()
                    st.success("Patient details added successfully!")
                else:
                    st.error("Please upload data properly.")

    # --- Find Old Patient Details Page ---
    elif st.session_state.show_find_patient:
        st.title("🔍 Find Old Patient Details")
        uploaded_image = st.file_uploader("Upload Patient Image", type=["jpg", "jpeg", "png"])

        if st.button("Search in Records"):
            if uploaded_image:
                uploaded_image_bytes = uploaded_image.read()
                uploaded_image_encoding = recognize_face(uploaded_image_bytes)
                
                if uploaded_image_encoding:
                    c.execute("SELECT name, age, gender, place, phone, emergency_phone, tele_id, medical_history, treatment, lab_reports, doctor_notes, medical_info, image, face_encodings FROM old_patient_records")
                    old_patient_details = c.fetchall()
                    found = False

                    for patient in old_patient_details:
                        if compare_faces(uploaded_image_encoding, patient[13]):  # Matching face_encodings
                            st.image(patient[12], caption="Patient Image", width=200)  # Display patient image
                            
                            # Display details in left-aligned format
                            st.write("### Patient Details")
                            st.write(f"**Name:** {patient[0]}")
                            st.write(f"**Age:** {patient[1]}")
                            st.write(f"**Gender:** {patient[2]}")
                            st.write(f"**Place:** {patient[3]}")
                            st.write(f"**Phone:** {patient[4]}")
                            st.write(f"**Emergency Contact:** {patient[5]}")
                            st.write(f"**Telegram ID:** {patient[6]}")
                            st.write(f"**Medical History:** {patient[7]}")
                            st.write(f"**Treatment:** {patient[8]}")
                            st.write(f"**Lab Reports:** {patient[9]}")
                            st.write(f"**Doctor Notes:** {patient[10]}")
                            st.write(f"**Remarks:** {patient[11]}")
                            
                            found = True
                            break
                    
                    if not found:
                        st.warning("No matching face found in the database.")
                else:
                    st.warning("No face detected in the uploaded image.")
            else:
                st.warning("Please upload a photo to search.")
            
        
    # --- Accident List ---
    elif st.session_state.selected_accident is None:
        st.title("🏥 Hospital Dashboard")
        st.write(f"**Hospital Name:** {hospital[2]}")
        st.write(f"**Status:** {hospital[4]}")

        # Update Hospital Status
        status = st.radio("Update Status", ["Ready", "Not Ready"], index=0 if hospital[4] == "Ready" else 1)
        if st.button("Update Status", key="update_status_button"):
            c.execute("UPDATE hospitals SET status = ? WHERE id = ?", (status, hospital_id))
            conn.commit()
            st.success("Status updated successfully!")
            st.rerun()

        # --- Accident List with Date Selection ---
        st.subheader("Accidents Assigned to This Hospital")
        selected_date = st.date_input("Select Date", datetime.today())
        c.execute("SELECT id, user_phone, name, location, timestamp FROM reports WHERE DATE(timestamp) = ? AND hospital_assigned_to = ?", (selected_date, hospital_id))
        accidents = c.fetchall()
        if accidents:
            for accident in accidents:
                lat, lon = accident[3].split(', ')
                if st.button(f"Accident ID: {accident[0]} - Reported by: {accident[2]} - Location: {get_place_name(lat, lon)}"):
                    st.session_state.selected_accident = accident[0]
                    st.rerun()
        else:
            st.info("No accidents assigned to this hospital on this date.")

    # --- Accident Details Page ---
    else:
        st.title("🚨 Accident Details")
        c.execute("SELECT * FROM reports WHERE id = ?", (st.session_state.selected_accident,))
        accident_details = c.fetchone()
        if accident_details:
            st.write(f"**Accident ID:** {accident_details[0]}")
            st.write(f"**User Phone:** {accident_details[1]}")
            st.write(f"**Name:** {accident_details[2]}")
            st.write(f"**Place:** {accident_details[5]}")
            st.write(f"**Description:** {accident_details[6]}")
            st.write(f"**Timestamp:** {accident_details[7]}")

            # Fetch ambulance driver details
            if accident_details[9]:  # If an ambulance driver is assigned
                c.execute("SELECT * FROM ambulance_drivers WHERE id = ?", (accident_details[9],))
                ambulance_driver = c.fetchone()
                if ambulance_driver:
                    st.subheader("Ambulance Driver Details")
                    st.write(f"**Driver Name:** {ambulance_driver[2]}")
                    st.write(f"**Driver Phone:** {ambulance_driver[1]}")
                    st.write(f"**Driver Location:** {get_place_name(ambulance_driver[5],ambulance_driver[6])}")

            # Fetch patient medical information
            c.execute("SELECT * FROM patient_medical_info WHERE accident_id = ?", (st.session_state.selected_accident,))
            patient_medical_info = c.fetchone()
            if patient_medical_info:
                st.subheader("Patient Medical Information")
                st.write(f"**Pulse Rate:** {patient_medical_info[3]}")
                st.write(f"**Oxygen Saturation:** {patient_medical_info[4]}")
                st.write(f"**Blood Pressure:** {patient_medical_info[5]}")
                st.write(f"**Fractures Detected:** {patient_medical_info[6]}")
                st.write(f"**Blood Clotting Rate:** {patient_medical_info[7]}")
                st.write(f"**Head Injury:** {patient_medical_info[8]}")
                st.write(f"**Burns/External Wounds:** {patient_medical_info[9]}")
                st.write(f"**Remarks:** {patient_medical_info[10]}")
                if patient_medical_info[11]:
                    st.image(patient_medical_info[11], caption="Uploaded Photo", width=200)
                if patient_medical_info[12]:
                    st.subheader("Uploaded Video")
                    st.video(patient_medical_info[12])

                # --- Face Recognition for Previous Records ---
                if patient_medical_info[11]:  # Check if an image is uploaded
                    st.subheader("Face Recognition for Previous Records")

                    uploaded_image = patient_medical_info[11]
                    if uploaded_image:
                        uploaded_image_bytes = uploaded_image
                        uploaded_image_encoding = recognize_face(uploaded_image_bytes)
                        
                        if uploaded_image_encoding:
                            c.execute("""SELECT name, age, gender,  medical_history, treatment, lab_reports, doctor_notes,
                                         medical_info, image, face_encodings, tele_id FROM old_patient_records""")
                            
                            # Fetch all images from old patient records
                            old_patient_detials = c.fetchall()
                            found = False
                            for patient in old_patient_detials:
                                if compare_faces(uploaded_image_encoding, patient[9]):
                                    st.write(f"**Name:** {patient[0]}")
                                    st.write(f"**Age:** {patient[1]}")
                                    st.write(f"**Gender:** {patient[2]}")
                                    st.write(f"**Medical History:** {patient[3]}")
                                    st.write(f"**Treatment:** {patient[4]}")
                                    st.write(f"**Lab Reports:** {patient[5]}")
                                    st.write(f"**Doctor Notes:** {patient[6]}")
                                    st.write(f"**Remarks:** {patient[7]}")
                                    st.image(patient[8], caption="Patient Image", width=200)
                                    found = True
                                    break
                            if not found:
                                st.warning("No matching face found in the database.")
                            if found:
                                if st.button("Send Message to relative"):
                                    message = f"Dear family member, {patient[0]} has been admitted to {hospital[2]} due to an accident and is under medical care. Please visit the hospital or contact us at {hospital[1]} for details."
                                    if send_telegram_message(patient[10], message):
                                        st.success("Message send successfully!!!")
                                    else:
                                        st.error("Message send failed.")
                        else:
                            st.warning("No face detected in the uploaded image.")
                    


            # Display the map with the route
            acc_lat, acc_lon = map(float, accident_details[3].split(", "))
            response = requests.get(f"{OSRM_URL}/{hospital[6]},{hospital[5]};{acc_lon},{acc_lat}?overview=full&geometries=geojson")
            route_data = response.json()
            route_coords = [(point[1], point[0]) for point in route_data["routes"][0]["geometry"]["coordinates"]]
            eta = route_data["routes"][0]["duration"] / 60  # Convert seconds to minutes
            eta_with_delay = eta * 2  # Adding a 20% delay factor
            st.write(f"**Estimated Time of Arrival (ETA):** {eta_with_delay:.2f} minutes (including possible delays)")

            # Display the route on the map
            route_map = folium.Map(location=[(hospital[5] + acc_lat) / 2, (hospital[6] + acc_lon) / 2], zoom_start=14)
            folium.PolyLine(route_coords, color="blue", weight=2.5, opacity=1).add_to(route_map)
            folium.Marker([hospital[5], hospital[6]], tooltip="Hospital", icon=folium.Icon(icon="hospital", prefix="fa", color="blue")).add_to(route_map)
            folium.Marker([acc_lat, acc_lon], tooltip="Accident", icon=folium.Icon(icon="ambulance", prefix="fa", color="red")).add_to(route_map)
            st_folium(route_map, height=400, width=700)

            # Back to Accident List
            if st.button("Back to Accident List"):
                st.session_state.selected_accident = None
                st.rerun()

# --- Close Database Connection ---
conn.close()
