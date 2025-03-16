import streamlit as st
import sqlite3
from datetime import datetime
import requests

# --- Database Connection ---
conn = sqlite3.connect("accident_reporting.db", check_same_thread=False)
c = conn.cursor()

# --- Funtion to Convert latitude and longitude into place name            
def get_place_name(lat, lon): 
    """Convert latitude and longitude to a human-readable place name.""" 
    url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json" 
    headers = {"User-Agent": "AccidentReportApp/1.0"} 
    response = requests.get(url, headers=headers).json() 
    return response.get("display_name", "Location not found") 

# Configure Page
st.set_page_config(page_title="Kerala Police Login", page_icon="🚔")

# Initialize session state variables
if "logged_in_user" not in st.session_state:
    st.session_state["logged_in_user"] = None
if "page" not in st.session_state:
    st.session_state["page"] = "login"
if "selected_accident" not in st.session_state:
    st.session_state["selected_accident"] = None  # Store selected accident ID

# Hide Streamlit default sidebar initially
if not st.session_state["logged_in_user"]:
    st.markdown("""
        <style>
            [data-testid="stSidebar"] { display: none; }
        </style>
    """, unsafe_allow_html=True)

# --- Login Page ---
if st.session_state["page"] == "login":
    st.image("https://keralapolice.gov.in/storage/headers/logo/q9mh5i5Hyy3X3vXvVaJZOuPkY.png", width=200)
    st.title("Kerala Police Admin Login")
    st.markdown("Please enter your administrator credentials to proceed.")

    with st.form("login_form"):
        admin_id = st.text_input("Administrator ID:", placeholder="Enter your admin ID")
        password = st.text_input("Password:", type="password", placeholder="Enter your password")
        submit_button = st.form_submit_button("Login")

    if submit_button:
        if admin_id == "administrator" and password == "password":  # Replace with real authentication
            st.session_state["logged_in_user"] = admin_id
            st.session_state["page"] = "dashboard"
            st.rerun()
        else:
            st.error("Invalid credentials. Please try again.")

# --- Dashboard Page ---
elif st.session_state["page"] == "dashboard":
    st.sidebar.title(f"Welcome, Kerala Police")
    if st.sidebar.button("Logout"):
        st.session_state["logged_in_user"] = None
        st.session_state["page"] = "login"
        st.session_state["selected_accident"] = None
        st.rerun()

    st.subheader("Police Dashboard")
    selected_date = st.date_input("Select Date", datetime.today())

    # Query accidents for the selected date
    c.execute("SELECT id, user_phone, name, location, timestamp FROM reports WHERE DATE(timestamp) = ?", (selected_date,))
    accidents = c.fetchall()

    if accidents:
        for accident in accidents:
            accident_id = accident[0]
            lat, lon = accident[3].split(', ')
            accident_label = f"Accident ID: {accident_id} - Reported by: {accident[2]} - Location: {get_place_name(lat, lon)}"
            if st.button(accident_label, key=f"accident_{accident_id}"):
                st.session_state["selected_accident"] = accident_id
                st.session_state["page"] = "details"
                st.rerun()
    else:
        st.info("No accidents reported on this date.")

# --- Accident Details Page ---
elif st.session_state["page"] == "details":
    st.title("🚨 Accident Details")
    
    if st.session_state["selected_accident"] is not None:
        c.execute("SELECT * FROM reports WHERE id = ?", (st.session_state["selected_accident"],))
        accident_details = c.fetchone()

        if accident_details:
            st.write(f"**Accident ID:** {accident_details[0]}")
            st.write(f"**User Phone:** {accident_details[1]}")
            st.write(f"**Name:** {accident_details[2]}")
            st.write(f"**Place:** {accident_details[5]}")
            st.write(f"**Description:** {accident_details[6]}")
            st.write(f"**Timestamp:** {accident_details[7]}")

            # Fetch and display ambulance driver details
            if accident_details[9]:
                c.execute("SELECT * FROM ambulance_drivers WHERE id = ?", (accident_details[9],))
                ambulance_driver = c.fetchone()
                if ambulance_driver:
                    st.subheader("Ambulance Driver Details")
                    st.write(f"**Driver Name:** {ambulance_driver[2]}")
                    st.write(f"**Driver Phone:** {ambulance_driver[1]}")

            # Fetch and display patient medical information
            c.execute("SELECT * FROM patient_medical_info WHERE accident_id = ?", (st.session_state["selected_accident"],))
            patient_medical_info = c.fetchone()

            if patient_medical_info:
                if patient_medical_info[11]:
                    st.image(patient_medical_info[11], caption="Ambulance Driver Uploaded Photo", width=200)
                if patient_medical_info[12]:
                    st.subheader("Uploaded Video")
                    st.video(patient_medical_info[12])

            # Fetch and display details of the assigned hospital
            c.execute("SELECT * FROM hospitals WHERE id = ?",(accident_details[10],))
            hospital_details = c.fetchone()

            if hospital_details:
                st.subheader("Hospital Details")
                st.write(f"**Hospital Name:** {hospital_details[2]}")
                st.write(f"**Hospital Phone:** {hospital_details[1]}")
                st.write(f"**Hospital Place:** {get_place_name(hospital_details[5],hospital_details[6])}")

        # Back button to return to the accident list
        if st.button("Back to Dashboard"):
            st.session_state["selected_accident"] = None
            st.session_state["page"] = "dashboard"
            st.rerun()

# --- Close Database Connection ---
conn.close()
