import streamlit as st
import sqlite3
import folium
from streamlit_folium import st_folium
import requests
import base64
import os
from streamlit_js_eval import streamlit_js_eval

# OSRM API URL (No API Key Required)
OSRM_URL = "http://router.project-osrm.org/route/v1/driving"

# --- Database Connection ---
conn = sqlite3.connect("accident_reporting.db", check_same_thread=False, timeout=5)
c = conn.cursor()

# Create a table for Ambulance Driver 
c.execute('''
    CREATE TABLE IF NOT EXISTS ambulance_drivers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT UNIQUE,
        name TEXT,
        pin TEXT,
        status TEXT,
        latitude REAL,
        longitude REAL
    )
''')

# Create a table for Upload details of the victim after reached the spot
c.execute('''
    CREATE TABLE IF NOT EXISTS patient_medical_info (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        accident_id INTEGER,  -- Foreign key to link with accident report
        driver_id INTEGER,   -- Foreign key to link with ambulance driver
        pulse_rate INTEGER,
        oxygen_saturation INTEGER,
        bp TEXT,
        fractures_detected TEXT,
        blood_clotting_rate INTEGER,
        head_injury INTEGER,
        burns_external_wounds TEXT,
        remarks TEXT,
        photos BLOB,  -- Store photos as binary data
        videos BLOB,  -- Store videos as binary data
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (accident_id) REFERENCES reports (id),
        FOREIGN KEY (driver_id) REFERENCES ambulance_drivers (id)
    )
''')

# Create a table for link ambulance and hospital
c.execute('''
    CREATE TABLE IF NOT EXISTS ambulance_hospital_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ambulance_id INTEGER,
        hospital_id INTEGER,
        FOREIGN KEY (ambulance_id) REFERENCES ambulance_drivers (id),
        FOREIGN KEY (hospital_id) REFERENCES hospitals (id)
    )
''')

conn.commit()

# --- Initialize Session State ---
if "logged_in_driver" not in st.session_state:
    st.session_state.logged_in_driver = None

# --- Function to Play Sound ---
def play_sound():
    # HTML audio element to play a sound
    audio_path = "notification/notification.mp3"  # Replace with the path to your sound file
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

# --- Driver Authentication ---
if st.session_state.logged_in_driver is None:
    st.title("🚑 Ambulance Driver System")
    choice = st.radio("Choose an option", ["Login", "Register"], index=None)

    # Register the new ambulance driver
    if choice == "Register":
        with st.form("register_form"):
            name = st.text_input("Full Name")
            phone = st.text_input("Phone Number")
            pin = st.text_input("4-digit PIN", type="password")
            submitted = st.form_submit_button("Register")

            if submitted:
                # Check if the phone number already exists
                c.execute("SELECT * FROM ambulance_drivers WHERE phone = ?", (phone,))
                existing_user = c.fetchone()

                if existing_user:
                    st.error("User already exists! Try logging in.")
                else:
                    # Insert new user into the database
                    c.execute(
                        "INSERT INTO ambulance_drivers (phone, name, pin, status) VALUES (?, ?, ?, ?)",
                        (phone, name, pin, "Not Ready"),
                    )
                    conn.commit()
                    st.success("Registration successful! Please log in.")
    
    # Based on the login the driver
    elif choice == "Login":
        with st.form("login_form"):
            phone = st.text_input("Phone Number")
            pin = st.text_input("4-digit PIN", type="password")
            submitted = st.form_submit_button("Login")

            if submitted:
                # Fetch the driver with the given phone number and PIN
                c.execute("SELECT * FROM ambulance_drivers WHERE phone = ? AND pin = ?", (phone, pin))
                driver = c.fetchone()

                if driver:
                    # Update session state with the driver's ID
                    st.session_state.logged_in_driver = driver[0]  # Store driver ID in session state
                    st.toast(f"Welcome back, {driver[2]}!", icon="🚑")  # Notification for login success
                    play_sound()  # Play sound on login
                    st.rerun()  # Refresh the page to show the dashboard
                else:
                    st.error("Invalid credentials! Try again.")

# --- Driver Dashboard ---
if st.session_state.logged_in_driver:
    # Define driver_id here so it's accessible throughout the block
    driver_id = st.session_state.logged_in_driver

    # Sidebar
    if st.sidebar.button("Logout", key="logout_button"):
        st.session_state.update({"logged_in_driver": None})
        st.rerun()

    st.title("🚑 Ambulance Dashboard")

    # Fetch details from the Database of the current ambulance details
    c.execute("SELECT * FROM ambulance_drivers WHERE id = ?", (driver_id,))
    driver = c.fetchone()

    # Update the status of the ambulance 
    st.write(f"**Status:** {driver[4]}")
    status = st.radio("Update Status", ["Ready", "Not Ready"], index=0 if driver[4] == "Ready" else 1)

    if st.button("Update Status", key="update_status_button"):
        c.execute("UPDATE ambulance_drivers SET status = ? WHERE id = ?", (status, driver_id))
        conn.commit()

        st.success("Status updated successfully!")
        st.rerun()

    # --- Location Update ---
    st.subheader("Update Location")
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
        default_lat, default_lon = location["latitude"], location["longitude"]
        

    # Create a map centered at the default location
    m = folium.Map(location=[default_lat, default_lon], zoom_start=14)

    # Add a draggable marker for ambulance location selection
    marker = folium.Marker(
        [default_lat, default_lon],
        tooltip="Drag to set location",
        draggable=True,
        icon=folium.Icon(icon="ambulance", prefix="fa", color="red"),
    )
    m.add_child(marker)

    # Display the map
    map_data = st_folium(m, height=400, width=700)

    # Extract the latest selected coordinates
    if map_data and map_data.get("last_clicked"):
        lat, lon = map_data["last_clicked"]["lat"], map_data["last_clicked"]["lng"]
        st.success(f"Selected Location: {get_place_name(lat, lon)}")
    else:
        lat, lon = default_lat, default_lon
        st.info("Click on the map to select your location.")

    # Save updated location to database when the button is clicked
    if st.button("Update Location", key="update_location_button"):
        c.execute("UPDATE ambulance_drivers SET latitude = ?, longitude = ? WHERE id = ?", (lat, lon, driver_id))
        conn.commit()
        st.success("Location updated successfully!")

    # --- Assign Nearest Accident ---
    st.subheader("Assigned Accident Location")
    c.execute("""SELECT id, location FROM reports WHERE (ambulance_status = ? 
              AND assigned_to IS NULL) OR (ambulance_status = ? AND assigned_to = ?) 
              ORDER BY timestamp DESC LIMIT 1 """, ("Waiting", "Waiting", driver_id))
    accident = c.fetchone()
    

    if accident and driver[4] == "Ready":
        acc_lat, acc_lon = map(float, accident[1].split(", "))

        # Assign the accident to this driver
        c.execute("UPDATE reports SET assigned_to = ? WHERE id = ?", (driver_id, accident[0]))
        conn.commit()

        # Fetch route from OSRM (OpenStreetMap)
        response = requests.get(f"{OSRM_URL}/{lon},{lat};{acc_lon},{acc_lat}?overview=full&geometries=geojson")
        route_data = response.json()
        route_coords = [(point[1], point[0]) for point in route_data["routes"][0]["geometry"]["coordinates"]]
        eta = route_data["routes"][0]["duration"] / 60  # Convert seconds to minutes
        eta_with_delay = eta * 1.2  # Adding a 20% delay factor

        st.write(f"**Accident Location:** {get_place_name(acc_lat, acc_lon)}")
        st.write(f"**Estimated Time of Arrival (ETA):** {eta_with_delay:.2f} minutes (including possible delays)")

        # Notification for accident assignment
        st.toast(f"🚨 Accident assigned! ETA: {eta_with_delay:.2f} minutes.", icon="🚨")
        play_sound()  # Play sound on accident assignment

        accident_map = folium.Map(location=[acc_lat, acc_lon], zoom_start=14)
        folium.Marker([acc_lat, acc_lon], tooltip="Accident", icon=folium.Icon(icon="exclamation-triangle", prefix="fa", color="orange")).add_to(accident_map)
        folium.Marker([lat, lon], tooltip="Ambulance", icon=folium.Icon(icon="ambulance", prefix="fa", color="red")).add_to(accident_map)

        # Draw actual road path
        folium.PolyLine(route_coords, color="blue", weight=5, opacity=0.8).add_to(accident_map)

        st_folium(accident_map, height=400, width=700)

        current_ambulance_status = st.radio("Accident location: ", ["Reached", "Not Reached"], index=1)

        if current_ambulance_status == "Reached":
            # --- Add Medical Information Form (Only after accident is assigned) ---
            st.subheader("Patient Medical Information")

            with st.form("medical_info_form"):
                pulse_rate = st.number_input("Pulse Rate (bpm)", min_value=0, max_value=200, value=80)
                oxygen_saturation = st.number_input("Oxygen Saturation (%)", min_value=0, max_value=100, value=95)
                bp = st.text_input("Blood Pressure (e.g., 120/80)")
                fractures_detected = st.radio("Fractures Detected?", ["Yes", "No"], index=1)
                blood_clotting_rate = st.number_input("Blood Clotting Rate (seconds)", min_value=0, max_value=600, value=120)
                head_injury = st.selectbox("Head Injury Severity (1 to 5)", options=[1, 2, 3, 4, 5], index=0)
                burns_external_wounds = st.text_area("Burns/External Wounds Description")
                remarks = st.text_area("Any Other Remarks")

                # Add file uploaders for photos and videos
                uploaded_photos = st.file_uploader("Upload Photos of the Victim", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
                uploaded_videos = st.file_uploader("Upload Videos of the Victim", type=["mp4", "avi"])

                submitted = st.form_submit_button("Submit Medical Information")

                #c.execute("""SELECT * FROM hospitals""")

                # Identify the nearest hospital
                c.execute("""SELECT h.id, h.latitude, h.longitude
                        FROM hospitals h JOIN reports r ON 1=1
                        WHERE h.status = 'Ready' ORDER BY 
                        ((h.latitude - CAST(SUBSTR(r.location, 1, INSTR(r.location, ',') - 1) AS REAL)) * 
                        (h.latitude - CAST(SUBSTR(r.location, 1, INSTR(r.location, ',') - 1) AS REAL)) +
                        (h.longitude - CAST(SUBSTR(r.location, INSTR(r.location, ',') + 1, LENGTH(r.location)) AS REAL)) * 
                        (h.longitude - CAST(SUBSTR(r.location, INSTR(r.location, ',') + 1, LENGTH(r.location)) AS REAL))) ASC
                        LIMIT 1""")
                
                hospital = c.fetchone()
                if hospital is None:
                    print("Sorry Can't find hospital")
                else:
                    hospital_id = hospital[0]

                print("Hospital ID:", hospital_id)
                

            if hospital:
                c.execute("UPDATE reports SET hospital_assigned_to = ? WHERE id = ?", (hospital[0], accident[0]))
                c.execute("INSERT INTO ambulance_hospital_links (ambulance_id, hospital_id) VALUES (?, ?)", (driver_id, hospital_id))
                conn.commit()


            if submitted:

                c.execute("UPDATE reports SET ambulance_status = ? WHERE id = ?", ("Done", accident[0]))
                conn.commit()

                # Convert uploaded files to binary data
                
                photos_data = [photo.read() for photo in uploaded_photos] if uploaded_photos else None
                videos_data = uploaded_videos.read() if uploaded_videos else None

                # Save the medical information to the database
                c.execute(
                    '''
                    INSERT INTO patient_medical_info (
                        accident_id, driver_id, pulse_rate, oxygen_saturation, bp, fractures_detected,
                        blood_clotting_rate, head_injury, burns_external_wounds, remarks,
                        photos, videos
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        accident[0],
                        driver_id,
                        pulse_rate,
                        oxygen_saturation,
                        bp,
                        fractures_detected,
                        blood_clotting_rate,
                        head_injury,
                        burns_external_wounds,
                        remarks,
                        sqlite3.Binary(b"".join(photos_data)) if photos_data else None,
                        sqlite3.Binary(videos_data) if videos_data else None,
                    ),
                )
                conn.commit()
                st.success("Medical information submitted successfully!")
                play_sound()  # Play sound on successful submission

                with st.form("data"):

                    # Fetch route from OSRM (OpenStreetMap)
                    response = requests.get(f"{OSRM_URL}/{acc_lon},{acc_lat};{hospital[2]},{hospital[1]}?overview=full&geometries=geojson")
                    route_data = response.json()
                    route_coords = [(point[1], point[0]) for point in route_data["routes"][0]["geometry"]["coordinates"]]
                    eta = route_data["routes"][0]["duration"] / 60  # Convert seconds to minutes
                    eta_with_delay = eta * 1.2  # Adding a 20% delay factor

                    st.write(f"**Estimated Time of Reach Hospital (ETA):** {eta_with_delay:.2f} minutes (including possible delays)")
                    accident_map = folium.Map(location=[acc_lat, acc_lon], zoom_start=14)
                    folium.Marker([acc_lat, acc_lon], tooltip="Ambulance", icon=folium.Icon(icon="ambulance", prefix="fa", color="red")).add_to(accident_map)
                    folium.Marker([hospital[1], hospital[2]], tooltip="Hospital", icon=folium.Icon(icon="hospital", prefix="fa", color="blue")).add_to(accident_map)

                    # Draw actual road path
                    folium.PolyLine(route_coords, color="green", weight=5, opacity=0.8).add_to(accident_map)

                    st_folium(accident_map, height=400, width=700)

                    hospital_status = st.form_submit_button("Reached Hospital")
                 

    else:
        st.info("No accident assigned or you're not ready.")

    # --- Show Previously Assigned Accidents ---
    if st.button("Show Previously Assigned Accidents", key="show_previous_accidents"):
        c.execute(
            '''
            SELECT r.id, SUBSTR(r.location, 1, INSTR(r.location, ',') - 1) AS latitude,  
            SUBSTR(r.location, INSTR(r.location, ',') + 1) AS longitude, r.timestamp, 
            p.pulse_rate, p.oxygen_saturation, p.bp FROM reports r
            LEFT JOIN patient_medical_info p ON r.id = p.accident_id
            WHERE r.assigned_to = ? ''',(driver_id,),
        )
        previous_accidents = c.fetchall()

        if previous_accidents:
            st.subheader("Previously Assigned Accidents")
            for accident in previous_accidents:
                st.write(f"**Accident ID:** {accident[0]}")
                st.write(f"**Location:** {get_place_name(accident[1], accident[2])}")
                st.write(f"**Timestamp:** {accident[3]}")
                st.write(f"**Pulse Rate:** {accident[4]}")
                st.write(f"**Oxygen Saturation:** {accident[5]}")
                st.write(f"**Blood Pressure:** {accident[6]}")
                st.write("---")
        else:
            st.info("No previously assigned accidents found.")

# --- Close Database Connection ---
conn.close()