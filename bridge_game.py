import random
import re
import threading
from tkinter import *
from tkinter import messagebox
from PIL import Image, ImageTk
import os # Import os module for file operations
import mysql.connector # Import mysql.connector for database operations
from mysql.connector import Error as MySQLConnectionError # Specific error for connection issues
import json # Import json for serializing data to store in database
import datetime # Import datetime for timestamps

# --- Panda3D Imports ---
from panda3d.core import *
from direct.showbase.ShowBase import ShowBase
from panda3d.core import TransparencyAttrib, Vec4, Material, LVector3, LPoint3, GeomVertexFormat, GeomVertexData, GeomTriangles, GeomNode, NodePath, VBase4, AmbientLight, DirectionalLight, Geom, GeomVertexWriter, TextNode
from direct.gui.OnscreenText import OnscreenText
from direct.interval.IntervalGlobal import Sequence, Parallel, Func
from collections import deque # Importing deque for efficient player queue management


# --- Global variable for login status file ---
LOGIN_STATUS_FILE = "login_status.txt"

# !!! IMPORTANT: CONFIGURE YOUR MYSQL DATABASE DETAILS HERE !!!
DB_CONFIG = {
    'host': '127.0.0.1', # Or 'localhost' or your MySQL server IP
    'user': 'root', # The user you created in MySQL
    'password': 'admin123', # The password for 'game_user'
    'database': 'squid_game_db' # The database name you created
}
# !!! END CONFIGURATION !!!

# Global database connection and cursor
db_connection = None
db_cursor = None

# --- Utility functions for login persistence ---
def save_login_status(logged_in=True):
    """
    Saves the login status to a file.
    """
    try:
        with open(LOGIN_STATUS_FILE, "w") as f:
            f.write(f"logged_in={logged_in}\n")
        print(f"DEBUG: Login status saved: logged_in={logged_in}")
    except IOError as e:
        print(f"ERROR: Could not save login status to {LOGIN_STATUS_FILE}: {e}")

def check_login_status():
    """
    Checks the login status from the file.
    Returns True if logged in, False otherwise.
    """
    if not os.path.exists(LOGIN_STATUS_FILE):
        return False
    try:
        with open(LOGIN_STATUS_FILE, "r") as f:
            content = f.read()
            if "logged_in=True" in content:
                print("DEBUG: Login status found: logged_in=True")
                return True
        print("DEBUG: Login status found: logged_in=False or file empty.")
        return False
    except IOError as e:
        print(f"ERROR: Could not read login status from {LOGIN_STATUS_FILE}: {e}")
        return False

# --- Database Setup Functions (moved outside GlassBridgeScene) ---
def connect_db():
    """Establishes a connection to the MySQL database and sets global db_connection and db_cursor."""
    global db_connection, db_cursor
    try:
        db_connection = mysql.connector.connect(**DB_CONFIG)
        db_cursor = db_connection.cursor()
        print(f"DEBUG: Connected to MySQL database: {DB_CONFIG['database']}")
    except MySQLConnectionError as e:
        print(f"ERROR: MySQL database connection failed: {e}")
        print("WARNING: Game will run without session logging due to database connection issue.")
        db_connection = None
        db_cursor = None
    except Exception as e:
        print(f"ERROR: An unexpected error occurred during database connection: {e}")
        print("WARNING: Game will run without session logging due to unexpected database issue.")
        db_connection = None
        db_cursor = None

def create_tables():
    """
    Creates the game_sessions, staff, bridge_info, and users tables if they don't exist.
    Uses the global db_connection and db_cursor.
    """
    global db_connection, db_cursor
    if not db_cursor:
        print("WARNING: No database cursor available to create table. Skipping table creation.")
        return

    try:
        # Create game_sessions table
        db_cursor.execute('''
            CREATE TABLE IF NOT EXISTS game_sessions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                start_time DATETIME NOT NULL,
                end_time DATETIME,
                duration_seconds DECIMAL(10, 2),
                players_selected_json TEXT,
                players_crossed_json TEXT,
                players_fallen_json TEXT,
                time_limit_reached BOOLEAN,
                bridge_layout_json TEXT
            )
        ''')
        print("DEBUG: Table 'game_sessions' checked/created in MySQL.")

        # Create staff table
        db_cursor.execute('''
            CREATE TABLE IF NOT EXISTS staff (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                role VARCHAR(255),
                staff_id VARCHAR(50) UNIQUE
            )
        ''')
        print("DEBUG: Table 'staff' checked/created in MySQL.")

        # Create bridge_info table
        db_cursor.execute('''
            CREATE TABLE IF NOT EXISTS bridge_info (
                id INT AUTO_INCREMENT PRIMARY KEY,
                game_session_id INT NOT NULL,
                row_index INT NOT NULL,
                column_index INT NOT NULL,
                is_safe BOOLEAN NOT NULL,
                FOREIGN KEY (game_session_id) REFERENCES game_sessions(id)
            )
        ''')
        print("DEBUG: Table 'bridge_info' checked/created in MySQL.")

        # Create users table
        db_cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL
            )
        ''')
        print("DEBUG: Table 'users' checked/created in MySQL.")

        db_connection.commit()
        print("DEBUG: All tables checked/created in MySQL.")
    except MySQLConnectionError as e:
        print(f"ERROR: Could not create tables in MySQL: {e}. Ensure user has privileges.")
    except Exception as e:
        print(f"ERROR: An unexpected error occurred during table creation: {e}")

# --- Tkinter UI Functions and Classes ---

# Global variables for screen dimensions, initialized after root
screen_width = None
screen_height = None

def load_image(image_path, width, height):
    """
    Loads and resizes an image for Tkinter.
    Handles potential errors during image loading.
    """
    try:
        img = Image.open(image_path)
        img = img.resize((width, height), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(img)
    except Exception as e:
        # Using print for errors instead of messagebox to avoid issues if root is not yet fully initialized
        print(f"Error: Failed to load image from {image_path}: {e}")
        return None

def is_valid_email(email):
    """
    Validates an email address using a regular expression.
    """
    return re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", email)

def _handle_user_login_or_registration(username, email, password):
    """
    Handles user login or registration by interacting with the 'users' table.
    If the user does not exist, it inserts them.
    For this demo, it assumes successful login if user exists.
    Uses the global db_connection and db_cursor.
    """
    global db_connection, db_cursor
    if not db_cursor or not db_connection or not db_connection.is_connected():
        messagebox.showerror("Database Error", "Database connection not established. Please check your MySQL server.")
        return False

    try:
        print(f"DEBUG: Attempting to check for user '{username}' (email: {email}).")
        # Check if user already exists by email or username
        db_cursor.execute("SELECT id FROM users WHERE email = %s OR username = %s", (email, username))
        user_exists = db_cursor.fetchone()

        if user_exists:
            print(f"DEBUG: User '{username}' (email: {email}) already exists. Proceeding with login.")
            messagebox.showinfo("Login Successful", "You are already registered. Logging in.")
            return True
        else:
            print(f"DEBUG: User '{username}' (email: {email}) not found. Attempting to register new user.")
            # User does not exist, insert new user
            db_cursor.execute("INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
                           (username, email, password))
            db_connection.commit()
            print(f"DEBUG: New user '{username}' (email: {email}) registered successfully and changes committed.")
            messagebox.showinfo("Registration Successful", "New account created and logged in!")
            return True
    except MySQLConnectionError as e:
        print(f"ERROR: Database operation failed for user login/registration: {e}")
        messagebox.showerror("Database Error", f"Could not connect to or interact with the user database: {e}")
        return False
    except Exception as e:
        print(f"ERROR: An unexpected error occurred during user login/registration: {e}")
        messagebox.showerror("Error", f"An unexpected error occurred: {e}")
        return False

def show_welcome_screen():
    """
    Displays the initial welcome screen with game title and a login button.
    Checks for persistent login.
    """
    # Check if already logged in
    if check_login_status():
        print("DEBUG: User already logged in, skipping to player selection.")
        show_player_selection()
        return

    for widget in root.winfo_children():
        widget.destroy()

    # Use a placeholder image if the actual path is not found or image fails to load
    global bg_photo_welcome # Keep a reference to prevent garbage collection
    # NOTE: Absolute path used for image. Consider changing to a relative path or providing images in the same directory.
    bg_image_path_welcome = "C:\\Users\\DELL\\OneDrive\\Desktop\\Downloads\\GBG\\Images\\Welcome GBG.jpg"
    bg_photo_welcome = load_image(bg_image_path_welcome, screen_width, screen_height)
    if bg_photo_welcome:
        bg_label_welcome = Label(root, image=bg_photo_welcome)
        bg_label_welcome.place(x=0, y=0, relwidth=1, relheight=1)
        bg_label_welcome.image = bg_photo_welcome
    else:
        # Fallback if image fails to load
        bg_label_welcome = Label(root, bg='lightblue')
        bg_label_welcome.place(x=0, y=0, relwidth=1, relheight=1)
        print("Warning: Using fallback background for welcome screen.")


    title1_font = ("Helvetica", 36, "bold")
    title1 = Label(root, text="WELCOME TO SQUID GAME", font=title1_font, fg="black", bg='white')
    title1.place(relx=0.5, rely=0.4, anchor='center')

    title2_font = ("Helvetica", 28, "bold")
    title2 = Label(root, text="GLASS BRIDGE GAME", font=title2_font, fg="black", bg='white')
    title2.place(relx=0.5, rely=0.5, anchor='center')

    login_button_font = ("Helvetica", 18, "bold")
    login_button = Button(root, text="LOGIN", font=login_button_font, bg="#FF3E3E", fg="white", command=show_login_form)
    login_button.place(relx=0.5, rely=0.6, anchor='center')

def show_login_form():
    """
    Displays the login form with username, email, and password fields.
    """
    for widget in root.winfo_children():
        widget.destroy()

    # Use a placeholder image if the actual path is not found or image fails to load
    global bg_photo_login # Keep a reference to prevent garbage collection
    # NOTE: Absolute path used for image. Consider changing to a relative path or providing images in the same directory.
    bg_image_path_login = "C:\\Users\\DELL\\OneDrive\\Desktop\\Downloads\\GBG\\Images\\Login GBG.jpg"
    bg_photo_login = load_image(bg_image_path_login, screen_width, screen_height)

    if bg_photo_login:
        bg_label_login = Label(root, image=bg_photo_login)
        bg_label_login.place(x=0, y=0, relwidth=1, relheight=1)
        bg_label_login.image = bg_photo_login
    else:
        bg_label_login = Label(root, bg='darkgrey')
        bg_label_login.place(x=0, y=0, relwidth=1, relheight=1)
        print("Warning: Using fallback background for login screen.")

    login_frame = Frame(root, bg='#333333', highlightthickness=0, relief='ridge', bd=0)
    login_frame.place(relx=0.5, rely=0.5, anchor='center')

    login_label_font = ("Helvetica", 24, "bold")
    login_label = Label(login_frame, text="LOGIN", font=login_label_font, fg="white", bg='#333333')
    login_label.pack(pady=(20, 10))

    username_label = Label(login_frame, text="Username:", font=("Helvetica", 14), fg="white", bg='#333333', anchor='w')
    username_label.pack(pady=(10, 0), padx=20, fill='x')
    username_entry = Entry(login_frame, font=("Helvetica", 14), width=30, relief='solid', bd=1, bg='white', fg='black')
    username_entry.pack(pady=5, padx=20, fill='x')

    email_label = Label(login_frame, text="Email:", font=("Helvetica", 14), fg="white", bg='#333333', anchor='w')
    email_label.pack(pady=(10, 0), padx=20, fill='x')
    email_entry = Entry(login_frame, font=("Helvetica", 14), width=30, relief='solid', bd=1, bg='white', fg='black')
    email_entry.pack(pady=5, padx=20, fill='x')

    password_label = Label(login_frame, text="Password:", font=("Helvetica", 14), fg="white", bg='#333333', anchor='w')
    password_label.pack(pady=(10, 0), padx=20, fill='x')
    password_entry = Entry(login_frame, font=("Helvetica", 14), show="*", width=30, relief='solid', bd=1, bg='white', fg='black')
    password_entry.pack(pady=5, padx=20, fill='x')

    def submit_login():
        """
        Handles the submission of the login form.
        Validates input and proceeds to player selection if valid.
        """
        username = username_entry.get().strip()
        email = email_entry.get().strip()
        password = password_entry.get().strip()

        if not username or not email or not password:
            messagebox.showerror("Error", "Please fill in all fields.")
            return
        if not is_valid_email(email):
            messagebox.showerror("Invalid Email", "Please enter a valid email address.")
            return

        # Attempt to handle user login/registration in the database
        print(f"DEBUG: Calling _handle_user_login_or_registration for user: {username}")
        if _handle_user_login_or_registration(username, email, password):
            print("DEBUG: _handle_user_login_or_registration returned True. Proceeding to player selection.")
            save_login_status(True) # Save login status on successful login
            show_player_selection()
        else:
            # If _handle_user_login_or_registration returns False, it means an error occurred
            # but perhaps a specific messagebox was not shown by that function for this case.
            # This ensures some feedback is always given.
            print("DEBUG: _handle_user_login_or_registration returned False. Displaying generic error.")
            messagebox.showerror("Login/Registration Failed", "An error occurred during login or registration. Please check the console for details or try again.")

    submit_button = Button(login_frame, text="Submit", font=("Helvetica", 14, "bold"), bg="red", fg="white", command=submit_login, relief='raised', bd=1)
    submit_button.pack(pady=20, padx=20, fill='x')

    back_button = Button(root, text="Back", font=("Helvetica", 14), command=show_welcome_screen)
    back_button.place(relx=0.01, rely=0.95, anchor='sw')
def show_player_selection():
    for widget in root.winfo_children():
        widget.destroy()

    player_bg_path =  "C:\\Users\\DELL\\OneDrive\\Desktop\\Downloads\\GBG\\Images\\playerSelection GBG.jpg"
    bg_photo = load_image(player_bg_path, screen_width // 2, screen_height)

    left_frame = Frame(root, width=screen_width // 2, height=screen_height)
    left_frame.pack(side="left", fill="both")

    if bg_photo:
        bg_label = Label(left_frame, image=bg_photo)
        bg_label.place(x=0, y=0, relwidth=1, relheight=1)
        bg_label.image = bg_photo
    else:
        bg_label = Label(root, bg='darkgrey')
        bg_label.place(x=0, y=0, relwidth=1, relheight=1)
        print("Warning: Using fallback background for player selection screen.")


    right_frame = Frame(root, bg="#B22222", width=screen_width // 2)
    right_frame.pack(side="right", fill="both", expand=True)

    Label(right_frame, text="Character Information", font=("Helvetica", 24, "bold"), fg="white", bg="#B22222").pack(pady=20)

    info_frame = Frame(right_frame, bg="#B22222")
    info_frame.pack(padx=20, pady=5, fill="both", expand=True)

    char_data = [
        ("Joon-ho", "P1", "player"), ("Sang-woo", "P2", "player"),
        ("Sae-byeok", "P3", "player"), ("Il-nam", "P4", "player"),
        ("Ali", "P5", "player"), ("Mi-nyeo", "P6", "player"),
        ("Gi-hun", "P7", "player"), ("Front Man", "S1", "staff"),
        ("Square Guard", "SG", "staff"), ("Triangle Guard", "TG", "staff"),
        ("Circle Guard", "CG", "staff"),
    ]

    player_vars, staff_vars = {}, {}

    def create_checkboxes(data, label_text, vars_dict):
        Label(info_frame, text=label_text, font=("Helvetica", 16), fg="white", bg="#B22222").pack(anchor="w")
        for name, char_id, _ in data:
            var = BooleanVar()
            vars_dict[name] = var
            f = Frame(info_frame, bg="#444444")
            f.pack(fill="x", pady=1)
            Checkbutton(f, text=name, font=("Helvetica", 14), variable=var, fg="white", bg="#444444", selectcolor="black").pack(side="left")
            Label(f, text=f"ID: {char_id}", font=("Helvetica", 14), fg="white", bg="#444444").pack(side="right")

    create_checkboxes([c for c in char_data if c[2] == "player"], "Players:", player_vars)
    create_checkboxes([c for c in char_data if c[2] == "staff"], "Staff:", staff_vars)
    
    def proceed_to_game():
        """
        Collects selected players/staff and proceeds to the final rules screen.
        """
        global selected_players, selected_staff
        selected_players = [name for name, var in player_vars.items() if var.get()]
        selected_staff = [name for name, var in staff_vars.items() if var.get()]
        
        if not selected_players:
            messagebox.showwarning("No Players Selected", "Please select at least one player to proceed.")
            return

        # Corrected: Call show_final_screen() to stay within the Tkinter flow
        show_final_screen()

    # Frame for buttons at the bottom of the right_frame
    btn_frame = Frame(right_frame, bg="#B22222")
    btn_frame.pack(side="bottom", fill="x", pady=20, padx=20) # Pack to bottom

    Button(btn_frame, text="Back", font=("Helvetica", 14), command=show_welcome_screen, bg="#444444", fg="white", width=10).pack(side="left")
    Button(btn_frame, text="Proceed", font=("Helvetica", 14, "bold"), command=proceed_to_game, bg="#444444", fg="white", width=10).pack(side="right")

def show_final_screen():
    """
    Displays the game rules and a button to start the Panda3D game.
    """
    for widget in root.winfo_children():
        widget.destroy()

    global final_bg # Keep a reference
    # NOTE: Absolute path used for image. Consider changing to a relative path or providing images in the same directory.
    final_bg_path =  "C:\\Users\\DELL\\OneDrive\\Desktop\\Downloads\\GBG\\Images\\Rules_GBG.jpg"
    final_bg = load_image(final_bg_path, screen_width, screen_height)
    if final_bg:
        bg_label = Label(root, image=final_bg) # Corrected: Use final_bg instead of bg_photo
        bg_label.place(x=0, y=0, relwidth=1, relheight=1)
        bg_label.image = final_bg
    else:
        bg_label = Label(root, bg='darkblue')
        bg_label.place(x=0, y=0, relwidth=1, relheight=1)
        print("Warning: Using fallback background for rules screen.")

    rules_text = """Glass Bridge Rules

● Two Glass Panels Each Step:
    ○ At each step, there are two glass panels - one strong and one weak.

● Only One is Safe:
    ○ The strong glass holds your weight.
    ○ The weak glass breaks and you fall.

● Go in Order:
    ○ Players take turns to cross the bridge, one at a time.

● Falling Means You're Out:
    ○  If you step on weak glass, you fall and are eliminated.

● Be Quick:
    ○ There's a time limit to reach the other side.
    ○ If you're too slow, you're out.

● No Going Back:
    ○ Once you're on the bridge, you can't go back or swap turns."""

    final_label = Label(root, text="", font=("Helvetica", 18, "bold"), fg="black", bg="#F4C2C2", justify="left", wraplength=1000)
    final_label.place(relx=0.5, rely=0.5, anchor='center')

    def animate_text(index):
        """
        Animates the display of the rules text character by character.
        """
        if index < len(rules_text):
            final_label.config(text=rules_text[:index+1])
            root.after(10, animate_text, index + 1) 
        elif index == len(rules_text):
            # Show the "Play Game" button after text animation
            play_button = Button(
                root,
                text="Play Game",
                font=("Helvetica", 14),
                bg="#444444",
                fg="white",
                command=start_game,
                relief='raised',
                bd=1,
                width=10
            )
            play_button.place(relx=0.99, rely=0.95, anchor='se') # Right bottom corner

    animate_text(0)

    back_button = Button(
        root,
        text="Back",
        font=("Helvetica", 14),
        command=show_player_selection,
        bg="#444444",
        fg="white",
        relief='raised',
        bd=1,
        width=10
    )
    back_button.place(relx=0.01, rely=0.95, anchor='sw')


def start_game():
    """
    Initiates the Panda3D game.
    This function will destroy the Tkinter window and then launch the 3D game.
    """
    print("DEBUG: Tkinter 'Play Game' button clicked. Destroying Tkinter window and starting Panda3D game.")
    root.destroy() # Close the Tkinter window

    # Now, initialize and run the Panda3D game
    global selected_players, selected_staff, db_connection, db_cursor # Access the global list populated by Tkinter and db connection
    game = GlassBridgeScene(list(selected_players), list(selected_staff), db_connection, db_cursor) # Pass a copy of selected players and DB connection to the game
    game.run()


# --- Panda3D Game Classes and Logic ---

class Player:
    """
    Represents a single player character in the Glass Bridge game.
    Handles player model creation, movement, and status.
    """
    def __init__(self, name, start_pos, game_instance, head_color, body_color):
        self.name = name
        self.game = game_instance
        self.current_tile_row = -1  # Starts before the first bridge tile (on the starting platform)
        self.current_tile_col = -1  # Column doesn't matter until they are on the bridge
        self.fallen = False
        self.crossed = False
        self.turn_active = False # True only when it's this player's turn to make a choice
        self.original_color = body_color # Store original color for resetting highlight
        self.is_on_bridge = False # True if player is on any tile of the bridge
        # Create the player's segmented model
        self.np = self._create_character_model(start_pos, head_color=head_color, body_color=body_color)
        self.np.reparentTo(self.game.render) # <--- ADDED: Reparent player model to the scene
        print(f"DEBUG: Player {self.name} initialized at start_pos: {start_pos}")

    @staticmethod
    def _create_character_model(pos, head_size=0.6, torso_width=0.8, torso_depth=0.5, torso_height=1.0,
                             limb_width=0.3, limb_depth=0.3, arm_length=0.7, leg_length=0.8,
                             head_color=VBase4(1, 0.8, 0, 1), body_color=VBase4(0, 0.5, 1, 1)):
        """
        Creates a segmented character model (head, torso, arms, legs) from cubes.
        The character_root's Z=0 is designed to be the bottom of the character's feet.
        This is a static method to be reused for both Players and Staff.
        """
        character_root = NodePath("character_root")
        # Legs (base at Z=0 of the character_root)
        left_leg = Player._create_cube(limb_width, limb_depth, leg_length, body_color)
        left_leg.setPos(-(torso_width / 4), 0, leg_length / 2)
        left_leg.reparentTo(character_root)
        right_leg = Player._create_cube(limb_width, limb_depth, leg_length, body_color)
        right_leg.setPos(torso_width / 4, 0, leg_length / 2)
        right_leg.reparentTo(character_root)
        # Torso (base at Z=leg_length)
        torso = Player._create_cube(torso_width, torso_depth, torso_height, body_color)
        torso.setPos(0, 0, leg_length + torso_height / 2)
        torso.reparentTo(character_root)
        # Arms (attached to torso, positioned relative to character_root's Z=0)
        left_arm = Player._create_cube(limb_width, limb_depth, arm_length, body_color)
        left_arm.setPos(-(torso_width / 2 + limb_width / 2), 0, leg_length + torso_height * 0.7)
        left_arm.reparentTo(character_root)
        right_arm = Player._create_cube(limb_width, limb_depth, arm_length, body_color)
        right_arm.setPos(torso_width / 2 + limb_width / 2, 0, leg_length + torso_height * 0.7)
        right_arm.reparentTo(character_root)
        # Head (base at Z=leg_length + torso_height)
        head = Player._create_cube(head_size, head_size, head_size, head_color)
        head.setPos(0, 0, leg_length + torso_height + head_size / 2)
        head.reparentTo(character_root)
        character_root.setPos(pos)
        character_root.setScale(0.8) # Overall scale for the entire character model
        
        material = Material()
        material.setDiffuse(VBase4(0.8, 0.8, 0.8, 1))
        material.setSpecular(VBase4(0.5, 0.5, 0.5, 1))
        material.setShininess(50.0)
        character_root.setMaterial(material)
        return character_root

    @staticmethod
    def _create_cube(sx, sy, sz, color):
        """
        Helper method to create a single cube GeomNodePath.
        The cube is centered at (0,0,0) and has dimensions sx, sy, sz.
        Made static to be callable by both Player and Staff.
        """
        format = GeomVertexFormat.getV3n3cpt2()
        vdata = GeomVertexData('cube', format, Geom.UHDynamic)
        vertex = GeomVertexWriter(vdata, 'vertex')
        normal = GeomVertexWriter(vdata, 'normal')
        color_writer = GeomVertexWriter(vdata, 'color')
        texcoord = GeomVertexWriter(vdata, 'texcoord')

        half_sx, half_sy, half_sz = sx / 2, sy / 2, sz / 2

        # Front face (Y-negative)
        vertex.addData3f(-half_sx, -half_sy, -half_sz); normal.addData3f(0,-1,0); color_writer.addData4f(color); texcoord.addData2f(0,0)
        vertex.addData3f( half_sx, -half_sy, -half_sz); normal.addData3f(0,-1,0); color_writer.addData4f(color); texcoord.addData2f(1,0)
        vertex.addData3f( half_sx, -half_sy,  half_sz); normal.addData3f(0,-1,0); color_writer.addData4f(color); texcoord.addData2f(1,1)
        vertex.addData3f(-half_sx, -half_sy,  half_sz); normal.addData3f(0,-1,0); color_writer.addData4f(color); texcoord.addData2f(0,1)
        # Back face (Y-positive)
        vertex.addData3f( half_sx,  half_sy, -half_sz); normal.addData3f(0,1,0); color_writer.addData4f(color); texcoord.addData2f(0,0)
        vertex.addData3f(-half_sx,  half_sy, -half_sz); normal.addData3f(0,1,0); color_writer.addData4f(color); texcoord.addData2f(1,0)
        vertex.addData3f(-half_sx,  half_sy,  half_sz); normal.addData3f(0,1,0); color_writer.addData4f(color); texcoord.addData2f(1,1)
        vertex.addData3f( half_sx,  half_sy,  half_sz); normal.addData3f(0,1,0); color_writer.addData4f(color); texcoord.addData2f(0,1)
        # Right face (X-positive)
        vertex.addData3f( half_sx, -half_sy, -half_sz); normal.addData3f(1,0,0); color_writer.addData4f(color); texcoord.addData2f(0,0)
        vertex.addData3f( half_sx,  half_sy, -half_sz); normal.addData3f(1,0,0); color_writer.addData4f(color); texcoord.addData2f(1,0)
        vertex.addData3f( half_sx,  half_sy,  half_sz); normal.addData3f(1,0,0); color_writer.addData4f(color); texcoord.addData2f(1,1)
        vertex.addData3f( half_sx, -half_sy,  half_sz); normal.addData3f(1,0,0); color_writer.addData4f(color); texcoord.addData2f(0,1)
        # Left face (X-negative)
        vertex.addData3f(-half_sx,  half_sy, -half_sz); normal.addData3f(-1,0,0); color_writer.addData4f(color); texcoord.addData2f(0,0)
        vertex.addData3f(-half_sx, -half_sy, -half_sz); normal.addData3f(-1,0,0); color_writer.addData4f(color); texcoord.addData2f(1,0)
        vertex.addData3f(-half_sx, -half_sy,  half_sz); normal.addData3f(-1,0,0); color_writer.addData4f(color); texcoord.addData2f(1,1)
        vertex.addData3f(-half_sx,  half_sy,  half_sz); normal.addData3f(-1,0,0); color_writer.addData4f(color); texcoord.addData2f(0,1) # Corrected normal
        # Top face (Z-positive)
        vertex.addData3f(-half_sx,  half_sy,  half_sz); normal.addData3f(0,0,1); color_writer.addData4f(color); texcoord.addData2f(0,0)
        vertex.addData3f(-half_sx, -half_sy,  half_sz); normal.addData3f(0,0,1); color_writer.addData4f(color); texcoord.addData2f(1,0)
        vertex.addData3f( half_sx, -half_sy,  half_sz); normal.addData3f(0,0,1); color_writer.addData4f(color); texcoord.addData2f(1,1)
        vertex.addData3f( half_sx,  half_sy,  half_sz); normal.addData3f(0,0,1); color_writer.addData4f(color); texcoord.addData2f(0,1)
        # Bottom face (Z-negative)
        vertex.addData3f(-half_sx, -half_sy, -half_sz); normal.addData3f(0,0,-1); color_writer.addData4f(color); texcoord.addData2f(0,0)
        vertex.addData3f(-half_sx,  half_sy, -half_sz); normal.addData3f(0,0,-1); color_writer.addData4f(color); texcoord.addData2f(1,0)
        vertex.addData3f( half_sx,  half_sy, -half_sz); normal.addData3f(0,0,-1); color_writer.addData4f(color); texcoord.addData2f(1,1)
        vertex.addData3f( half_sx, -half_sy, -half_sz); normal.addData3f(0,0,-1); color_writer.addData4f(color); texcoord.addData2f(0,1)

        tris = GeomTriangles(Geom.UHDynamic)
        tris.addVertices(0,1,2); tris.addVertices(0,2,3) # Front
        tris.addVertices(4,5,6); tris.addVertices(4,6,7) # Back
        tris.addVertices(8,9,10); tris.addVertices(8,10,11) # Right
        tris.addVertices(12,13,14); tris.addVertices(12,14,15) # Left
        tris.addVertices(16,17,18); tris.addVertices(16,18,19) # Top
        tris.addVertices(20,21,22); tris.addVertices(20,22,23) # Bottom

        geom = Geom(vdata)
        geom.addPrimitive(tris)
        node = GeomNode('cube_model')
        node.addGeom(geom)
        np = NodePath(node)
        return np

    def move_to_tile(self, row, col):
        """
        Moves the player to the specified tile on the bridge.
        This function handles the actual movement animation and updates player/tile state.
        """
        print(f"DEBUG: Player {self.name} (current_tile_row={self.current_tile_row}, current_tile_col={self.current_tile_col}) called to move to ({row}, {col}).")

        if self.fallen or self.crossed:
            print(f"DEBUG: {self.name} is already out of the game. Cannot move.")
            return

        # Start the global timer if this is the very first move of the game
        # This condition ensures the timer starts only once, when the first player makes their very first step onto the bridge.
        if not self.game.timer_active and self.game.current_player == self:
            self.game.timer_active = True
            print("DEBUG: Global game timer activated!")
        target_tile = self.game.bridge_tiles[row][col]
        target_pos = target_tile['np'].getPos()
        
        # Player stands on top of the tile, so Z is tile's Z + tile_depth
        player_z_on_tile = target_pos.getZ() + self.game.tile_depth
        
        # Update player's position before animation
        self.current_tile_row = row
        self.current_tile_col = col
        self.is_on_bridge = True # Player is now on the bridge
        print(f"DEBUG: {self.name} moving to tile ({row}, {col}) at Y: {target_pos.getY()}, Z: {player_z_on_tile}")

        # Use posInterval to animate the existing player model
        move_interval = Sequence(
            self.np.posInterval(0.5, LPoint3(target_pos.getX(), target_pos.getY(), player_z_on_tile)),
            Func(self.check_tile, row, col)
        )
        move_interval.start()

    def check_tile(self, row, col):
        """
        Checks if the tile the player landed on is safe or broken.
        This is called after the player's movement animation completes.
        """
        if self.fallen or self.crossed:
            return

        tile_info = self.game.bridge_tiles[row][col]
        
        print(f"DEBUG (Check Tile): {self.name} landed on ({row}, {col}). Is safe: {tile_info['is_safe']}.")

        if tile_info['is_safe']:
            print(f"DEBUG: {self.name} landed safely on tile ({row}, {col}).")
            # Mark this tile as safe for observation
            self.game.revealed_safe_path[row] = col 

            # Change color of the safe tile to indicate it's proven
            tile_info['np'].setColorScale(VBase4(0.5, 1.0, 0.5, 0.6)) # Light green for safe tile
            tile_info['np'].setTransparency(TransparencyAttrib.M_alpha) # Ensure transparency is still active

            self.game.player_status_text[self.name].setText(f"{self.name}: On tile {row+1}/{self.game.bridge_length}")

            if row == self.game.bridge_length - 1:
                print(f"DEBUG: {self.name} has crossed the bridge!")
                self.crossed = True
                self.game.player_status_text[self.name].setText(f"{self.name}: Crossed!")
                # Move player to a safe "crossed" area off the bridge
                # Offset slightly to prevent stacking at the end if multiple cross
                self.np.setPos(self.np.getPos().getX() + (self.game.players.index(self) - (len(self.game.players) - 1) / 2) * 0.5, 
                                 self.np.getPos().getY() + 2, self.game.tile_depth)
                
                # Player crossed, their turn ends, next player's turn starts
                self.turn_active = False 
                self.game.next_player_turn() 
            else:
                # Player landed safely and has not crossed, their turn continues
                self.turn_active = True 
                print(f"DEBUG: {self.name}'s turn continues. Choose next tile (1 for Left, 2 for Right)")
                self.game.game_status_text.setText(f"{self.name}: Choose next tile (1 for Left, 2 for Right)")
        else: # Player landed on a broken tile
            print(f"DEBUG: {self.name} landed on a broken tile ({row}, {col}).")
            # Mark this tile as broken for observation
            self.game.revealed_broken_path[row] = col
            self._fall(broken_tile_info=tile_info)
            self.game.player_status_text[self.name].setText(f"{self.name}: Fallen!")
            # Player fell, their turn ends, next player's turn starts
            self.turn_active = False 
            self.game.next_player_turn() 

    def _fall(self, broken_tile_info=None):
        """
        Animates the player falling and removes their model.
        Also animates the broken tile falling.
        """
        print(f"DEBUG: {self.name} is falling. Current tile: ({self.current_tile_row}, {self.current_tile_col})")
        self.fallen = True
        self.is_on_bridge = False

        if broken_tile_info:
            # Animate the broken tile falling
            broken_tile_info['np'].setTransparency(TransparencyAttrib.M_alpha)
            broken_tile_info['np'].setColor(Vec4(0.2, 0.2, 0.2, 0.3)) # Make it look broken/darker
            fall_tile_interval = broken_tile_info['np'].posInterval(0.5, LPoint3(broken_tile_info['x'], broken_tile_info['y'], -5),
                                                                     startPos=broken_tile_info['np'].getPos())
            fall_tile_interval.start()

        fall_interval = Sequence(
            self.np.posInterval(0.5, LPoint3(self.np.getPos().getX(), self.np.getPos().getY(), -5)),
            Func(self.np.detachNode) # Remove player model after falling
        )
        fall_interval.start()

class Staff:
    """
    Represents a staff character in the Glass Bridge game.
    Handles staff model creation, positioning, and patrolling behavior.
    """
    def __init__(self, name, role, start_pos, game_instance, color):
        self.name = name
        self.role = role
        self.game = game_instance
        self.color = color
        # Create staff model using the shared static method
        self.np = Player._create_character_model(start_pos, head_color=color, body_color=color)
        self.np.reparentTo(self.game.render) # Add staff to the scene
        print(f"DEBUG: Staff {self.name} ({self.role}) initialized at start_pos: {start_pos}")

        if self.role == "Guard":
            self.patrol_interval = None
            self.start_patrol() # Start patrolling immediately for guards

    def start_patrol(self):
        """
        Sets up and starts the patrolling animation for guards.
        """
        # Patrol path along the side of the bridge
        # Assuming guards patrol along the Y-axis parallel to the bridge
        patrol_y_start = self.game.bridge_start_y - self.game.tile_width * 0.5
        patrol_y_end = self.game.bridge_start_y + (self.game.bridge_length - 1) * (self.game.tile_width + self.game.tile_gap) + self.game.tile_width * 0.5
        
        # X-position depends on which side the guard is on (left or right of bridge)
        # For simplicity, let's alternate guards between left and right side patrol
        # This will need to be decided when setting up staff.
        # For now, let's assume they are placed on one side and patrol it.
        current_x = self.np.getPos().getX() # Keep their assigned X position

        # Define patrol points (start at current Y, move to end Y, then back)
        point1 = LPoint3(current_x, patrol_y_start, self.game.tile_depth)
        point2 = LPoint3(current_x, patrol_y_end, self.game.tile_depth)
        
        # Calculate duration based on distance to make speed somewhat consistent
        patrol_distance = (patrol_y_end - patrol_y_start)
        patrol_duration = patrol_distance / 2.0 # Adjust this value for speed (e.g., 2.0 units per second)

        # Create the patrol sequence
        # Move to point 2, then to point 1, looping indefinitely
        self.patrol_interval = Sequence(
            self.np.posInterval(patrol_duration, point2),
            self.np.posInterval(patrol_duration, point1)
        )
        self.patrol_interval.loop() # Loop the patrol animation
        print(f"DEBUG: Staff {self.name} started patrolling between Y={patrol_y_start:.2f} and Y={patrol_y_end:.2f}.")


class GlassBridgeScene(ShowBase):
    """
    Main game class for the Glass Bridge game, implementing Squid Game rules.
    Manages the scene, bridge, players, and game flow.
    """
    def __init__(self, selected_players_from_tkinter, selected_staff_from_tkinter, conn, cursor):
        ShowBase.__init__(self)
        print("DEBUG: Initializing GlassBridgeScene.")
        self.disableMouse()

        # --- Database Setup (using passed connection) ---
        self.conn = conn
        self.cursor = cursor
        self.game_session_id = None # To store the ID of the current game session in the DB
        self.session_start_time = datetime.datetime.now() # Record start time for DB
        self.selected_players_names = selected_players_from_tkinter # Store players from Tkinter selection
        self.selected_staff_names = selected_staff_from_tkinter # Store selected staff from Tkinter

        # --- Camera Setup for 3D Perspective ---
        self.camera.setPos(0, -10, 15) # Closer to the action
        self.camera.lookAt(0, -5, 0) # Look at the start of the bridge/platform
        self.set_background_color(0.1, 0.1, 0.1)  # Dark grey background

        # --- Lighting ---
        dlight = DirectionalLight('dlight')
        dlight.setColor(Vec4(0.9, 0.9, 0.9, 1))
        dlightNP = self.render.attachNewNode(dlight)
        dlightNP.setHpr(30, -60, 0)
        self.render.setLight(dlightNP)

        alight = AmbientLight('alight')
        alight.setColor(Vec4(0.3, 0.3, 0.3, 1))
        alightNP = self.render.attachNewNode(alight)
        self.render.setLight(alightNP)
        # --- Game Parameters ---
        self.bridge_length = 10 # Number of rows of tiles
        self.tile_width = 3.0
        self.tile_gap = 0.5
        self.tile_depth = 0.2
        self.bridge_start_y = 0
        self.revealed_safe_path = {} # Stores {row: safe_column} for proven safe tiles
        self.revealed_broken_path = {} # NEW: Stores {row: broken_column} for tiles that broke
        self.pulse_interval = None # Initialize pulse_interval here

        # --- Time Limit for the game ---
        self.time_limit = 40.0 # Total seconds for all players to cross
        self.time_left = self.time_limit
        self.timer_active = False # Becomes True when the first player steps on the bridge
        self.game_over_flag = False # Flag to indicate if the game has concluded

        # --- Bridge Generation ---
        self.bridge_tiles = [] # Stores tile NodePaths and their properties
        self.actual_bridge_layout = [] # Stores the true safe/broken configuration for DB
        self.end_platform_y = 0 # Will be set during bridge generation
        self.create_bridge_and_platforms() # Renamed and refactored
        print("DEBUG: Initial bridge_tiles after generation:")
        for r_idx, row_tiles in enumerate(self.bridge_tiles):
            for c_idx, tile_info in enumerate(row_tiles):
                print(f"   Tile ({r_idx},{c_idx}): is_safe={tile_info['is_safe']}")

        # Initialize players and staff
        self.players = [] # All player objects (Player 1, Player 2, etc.)
        self.staff_members = [] # All staff objects
        # DSA Concept: Using a deque for active_players_queue for efficient player queue management (O(1) rotations)
        self.active_players_queue = deque() # Deque of players still in the game, in turn order (for manual choices)
        
        self.current_player = None # The Player object whose turn it currently is
        self.setup_characters() # New method to set up both players and staff

        # Set initial current player and activate their turn
        if self.active_players_queue:
            self.current_player = self.active_players_queue[0] # First player in the deque
            self.current_player.turn_active = True
            self.camera_follow_player = self.current_player.np
            print(f"DEBUG: Initial current player set to {self.current_player.name}. Turn active: {self.current_player.turn_active}")
        else:
            print("ERROR: No players created. Game cannot start.")
            self.current_player = None 

        # --- Save initial game session data to DB (only if connection exists) ---
        if self.conn:
            self._save_initial_game_session()


        # --- UI Elements ---
        self.player_info_text = OnscreenText(text="", pos=(0.0, 0.9), scale=0.07, fg=(1,1,1,1), align=TextNode.ACenter, mayChange=True)
        self.instructions_text = OnscreenText(text="Press '1' for Left, '2' for Right", pos=(0, -0.9), scale=0.07, fg=(1,1,1,1), align=TextNode.ACenter, mayChange=True)
        self.game_status_text = OnscreenText(text="Game Start!", pos=(0, 0.8), scale=0.08, fg=(1,1,1,1), align=TextNode.ACenter, mayChange=True)
        self.timer_text = OnscreenText(text=f"Time Left: {self.time_limit:.0f}", pos=(1.0, 0.9), scale=0.06, fg=(1,1,1,1), align=TextNode.ARight, mayChange=True) # Timer display
        self.player_status_text = {} # To display individual player status
        self.display_player_status_ui()

        # --- Input Handling ---
        self.accept("1", self.attempt_move, [0]) # Left tile
        self.accept("2", self.attempt_move, [1]) # Right tile
        self.accept("escape", self.userExit) # Allow ESC to exit

        # --- Game Loop/Task ---
        self.taskMgr.add(self.update_game_state, "update_game_state")
        self.taskMgr.add(self.update_camera, "update_camera")
        self.taskMgr.add(self.update_timer, "update_game_timer") # Add timer update task
        
        self.update_player_info_display()
        # Initial highlight for the first player
        self.highlight_current_player()

    def _save_initial_game_session(self):
        """Saves initial game session data to the database."""
        if not self.cursor or not self.conn:
            print("WARNING: No database cursor or connection available to save initial session. Skipping.")
            return

        try:
            # Use %s as placeholder for MySQL connector
            self.cursor.execute('''
                INSERT INTO game_sessions (start_time, players_selected_json, bridge_layout_json)
                VALUES (%s, %s, %s)
            ''', (
                self.session_start_time.isoformat(sep=' ', timespec='seconds'), # Format for MySQL DATETIME
                json.dumps(self.selected_players_names),
                json.dumps(self.actual_bridge_layout)
            ))
            self.game_session_id = self.cursor.lastrowid # Get the ID of the newly inserted row
            self.conn.commit()
            print(f"DEBUG: Initial game session saved with ID: {self.game_session_id}")

            # Insert staff data (example, you might want to fetch this from char_data)
            staff_data = [
                ("Front Man", "S1"), ("Square Guard", "SG"), ("Triangle Guard", "TG"), ("Circle Guard", "CG")
            ]
            for name, staff_id in staff_data:
                self.cursor.execute('''
                    INSERT IGNORE INTO staff (name, role, staff_id) VALUES (%s, %s, %s)
                ''', (name, "Guard", staff_id)) # Assuming 'Guard' role for simplicity
            self.conn.commit()
            print("DEBUG: Staff data inserted/checked.")

            # Insert bridge_info for this session
            for r_idx, row_config in enumerate(self.actual_bridge_layout):
                for c_idx, is_safe in enumerate(row_config):
                    self.cursor.execute('''
                        INSERT INTO bridge_info (game_session_id, row_index, column_index, is_safe)
                        VALUES (%s, %s, %s, %s)
                    ''', (self.game_session_id, r_idx, c_idx, is_safe))
            self.conn.commit()
            print("DEBUG: Bridge info for current session inserted.")

        except MySQLConnectionError as e:
            print(f"ERROR: Could not save initial game session or related data to MySQL: {e}")
        except Exception as e:
            print(f"ERROR: An unexpected error occurred while saving initial session or related data: {e}")

    def _update_game_session_results(self, time_limit_reached_flag=False):
        """Updates the game session with final results."""
        if not self.cursor or not self.conn or self.game_session_id is None:
            print("WARNING: No database cursor, connection, or session ID to update results. Skipping.")
            return

        end_time = datetime.datetime.now()
        duration = (end_time - self.session_start_time).total_seconds()
        
        players_crossed = [player.name for player in self.players if player.crossed]
        players_fallen = [player.name for player in self.players if player.fallen]

        try:
            # Use %s as placeholder for MySQL connector
            self.cursor.execute('''
                UPDATE game_sessions
                SET end_time = %s,
                    duration_seconds = %s,
                    players_crossed_json = %s,
                    players_fallen_json = %s,
                    time_limit_reached = %s
                WHERE id = %s
            ''', (
                end_time.isoformat(sep=' ', timespec='seconds'), # Format for MySQL DATETIME
                duration,
                json.dumps(players_crossed),
                json.dumps(players_fallen),
                1 if time_limit_reached_flag else 0, # MySQL BOOLEAN is often stored as TINYINT(1) or 0/1
                self.game_session_id
            ))
            self.conn.commit()
            print(f"DEBUG: Game session {self.game_session_id} updated with final results.")
        except MySQLConnectionError as e:
            print(f"ERROR: Could not update game session results in MySQL: {e}")
        except Exception as e:
            print(f"ERROR: An unexpected error occurred while updating session results: {e}")

    def create_bridge_and_platforms(self):
        """
        Generates the starting platform, bridge tiles, and end platform.
        Also records the actual safe/broken layout for database storage.
        """
        # Create start platform
        self.create_platform(LPoint3(0, self.bridge_start_y - self.tile_width * 1.5, 0), self.tile_width * 3, self.tile_width * 2)

        self.actual_bridge_layout = [] # Reset for each new bridge generation
        for row in range(self.bridge_length):
            row_tiles = []
            safe_column = random.randint(0, 1) # 0 for left, 1 for right
            
            # Record the safe column for this row in the actual_bridge_layout
            row_config = [False, False] # [is_left_safe, is_right_safe]
            row_config[safe_column] = True
            self.actual_bridge_layout.append(row_config)

            for col in range(2): # Two columns for the bridge
                x_pos = (col - 0.5) * (self.tile_width + self.tile_gap)
                y_pos = self.bridge_start_y + row * (self.tile_width + self.tile_gap)
                is_safe = (col == safe_column)
                tile_color = VBase4(0.7, 0.7, 0.9, 0.6) # Default glass color
                
                tile_np = self.create_tile(LPoint3(x_pos, y_pos, 0), self.tile_width, self.tile_width, self.tile_depth, tile_color)
                row_tiles.append({'np': tile_np, 'is_safe': is_safe, 'x': x_pos, 'y': y_pos})
            self.bridge_tiles.append(row_tiles)

        # Create end platform
        self.end_platform_y = self.bridge_start_y + self.bridge_length * (self.tile_width + self.tile_gap) + self.tile_width * 1.5
        self.create_platform(LPoint3(0, self.end_platform_y, 0), self.tile_width * 3, self.tile_width * 2)

    def create_tile(self, pos, width, length, depth, color=VBase4(0.7, 0.7, 0.9, 0.6)):
        """
        Creates a single tile model for the bridge.
        The tile's bottom surface will be at pos.z.
        """
        format = GeomVertexFormat.getV3n3cpt2()
        vdata = GeomVertexData('tile', format, Geom.UHDynamic)
        vertex = GeomVertexWriter(vdata, 'vertex')
        normal = GeomVertexWriter(vdata, 'normal')
        color_writer = GeomVertexWriter(vdata, 'color')
        texcoord = GeomVertexWriter(vdata, 'texcoord')

        half_width, half_length = width / 2, length / 2

        # Define vertices for a cuboid, with Z from 0 to depth (bottom at 0)
        vertices = [
            # Front face (Y-negative)
            (-half_width, -half_length, 0), (half_width, -half_length, 0), (half_width, -half_length, depth), (-half_width, -half_length, depth),
            # Back face (along +Y)
            (half_width, half_length, 0), (-half_width, half_length, 0), (-half_width, half_length, depth), (half_width, half_length, depth),
            # Right face (along +X)
            (half_width, -half_length, 0), (half_width, half_length, 0), (half_width, half_length, depth), (half_width, -half_length, depth),
            # Left face (along -X)
            (-half_width, half_length, 0), (-half_width, -half_length, 0), (-half_width, -half_length, depth), (-half_width, half_length, depth),
            # Top face (along +Z)
            (-half_width, -half_length, depth), (half_width, -half_length, depth), (half_width, half_length, depth), (-half_width, half_length, depth),
            # Bottom face (along -Z)
            (-half_width, half_length, 0), (half_width, half_length, 0), (half_width, -half_length, 0), (-half_width, -half_length, 0)
        ]
        
        normals = [
            (0,-1,0), (0,-1,0), (0,-1,0), (0,-1,0), # Front
            (0,1,0), (0,1,0), (0,1,0), (0,1,0),     # Back
            (1,0,0), (1,0,0), (1,0,0), (1,0,0),     # Right
            (-1,0,0), (-1,0,0), (-1,0,0), (-1,0,0), # Left
            (0,0,1), (0,0,1), (0,0,1), (0,0,1),     # Top
            (0,0,-1), (0,0,-1), (0,0,-1), (0,0,-1) # Bottom
        ]

        texcoords = [
            (0,0), (1,0), (1,1), (0,1),
            (0,0), (1,0), (1,1), (0,1),
            (0,0), (1,0), (1,1), (0,1),
            (0,0), (1,0), (1,1), (0,1),
            (0,0), (1,0), (1,1), (0,1),
            (0,0), (1,0), (1,1), (0,1)
        ]
        
        for i in range(len(vertices)):
            vertex.addData3f(*vertices[i])
            normal.addData3f(*normals[i])
            color_writer.addData4f(color)
            texcoord.addData2f(*texcoords[i])

        tris = GeomTriangles(Geom.UHDynamic)
        indices = [
            0,1,2, 0,2,3,   # Front
            4,5,6, 4,6,7,   # Back
            8,9,10, 8,10,11, # Right
            12,13,14, 12,14,15, # Left
            16,17,18, 16,18,19, # Top
            20,21,22, 20,22,23  # Bottom
        ]
        for i in range(0, len(indices), 3):
            tris.addVertices(indices[i], indices[i+1], indices[i+2])
        
        geom = Geom(vdata)
        geom.addPrimitive(tris)
        node = GeomNode('tile_model')
        node.addGeom(geom)
        np = NodePath(node)
        np.setPos(pos)
        np.reparentTo(self.render)

        material = Material()
        material.setDiffuse(color)
        material.setAmbient(VBase4(0.5, 0.5, 0.5, 1))
        material.setSpecular(VBase4(1, 1, 1, 1))
        material.setShininess(96.0)
        np.setMaterial(material)
        np.setTransparency(TransparencyAttrib.M_alpha)
        return np

    def create_platform(self, pos, width, length):
        """
        Creates a solid cuboid platform model.
        The platform's top surface will be at pos.z.
        """
        format = GeomVertexFormat.getV3n3cpt2()
        vdata = GeomVertexData('platform', format, Geom.UHDynamic)
        vertex = GeomVertexWriter(vdata, 'vertex')
        normal = GeomVertexWriter(vdata, 'normal')
        color_writer = GeomVertexWriter(vdata, 'color')
        texcoord = GeomVertexWriter(vdata, 'texcoord')
        
        platform_color = VBase4(1.0, 0.0, 0.0, 1.0) # Solid platform color (Red)
        
        half_width, half_length, half_depth = width / 2, length / 2, self.tile_depth / 2 # Use tile_depth for platform thickness

        # Define vertices for a cuboid, with Z from -half_depth to half_depth (centered at 0)
        vertices = [
            # Front face (along -Y)
            (-half_width, -half_length, -half_depth), (half_width, -half_length, -half_depth), (half_width, -half_length, half_depth), (-half_width, -half_length, half_depth),
            # Back face (along +Y)
            (half_width, half_length, -half_depth), (-half_width, half_length, -half_depth), (-half_width, half_length, half_depth), (half_width, half_length, half_depth),
            # Right face (along +X)
            (half_width, -half_length, -half_depth), (half_width, half_length, -half_depth), (half_width, half_length, half_depth), (half_width, -half_length, half_depth),
            # Left face (along -X)
            (-half_width, half_length, -half_depth), (-half_width, -half_length, -half_depth), (-half_width, -half_length, half_depth), (-half_width, half_length, half_depth),
            # Top face (along +Z)
            (-half_width, -half_length, half_depth), (half_width, -half_length, half_depth), (half_width, half_length, half_depth), (-half_width, half_length, half_depth),
            # Bottom face (along -Z)
            (-half_width, half_length, -half_depth), (half_width, half_length, -half_depth), (half_width, -half_length, -half_depth), (-half_width, -half_length, -half_depth)
        ]
        
        normals = [
            (0,-1,0), (0,-1,0), (0,-1,0), (0,-1,0), # Front
            (0,1,0), (0,1,0), (0,1,0), (0,1,0),     # Back
            (1,0,0), (1,0,0), (1,0,0), (1,0,0),     # Right
            (-1,0,0), (-1,0,0), (-1,0,0), (-1,0,0), # Left
            (0,0,1), (0,0,1), (0,0,1), (0,0,1),     # Top
            (0,0,-1), (0,0,-1), (0,0,-1), (0,0,-1) # Bottom
        ]

        texcoords = [
            (0,0), (1,0), (1,1), (0,1),
            (0,0), (1,0), (1,1), (0,1),
            (0,0), (1,0), (1,1), (0,1),
            (0,0), (1,0), (1,1), (0,1),
            (0,0), (1,0), (1,1), (0,1),
            (0,0), (1,0), (1,1), (0,1)
        ]
        for i in range(len(vertices)):
            vertex.addData3f(*vertices[i])
            normal.addData3f(*normals[i])
            color_writer.addData4f(platform_color)
            texcoord.addData2f(*texcoords[i])

        tris = GeomTriangles(Geom.UHDynamic)
        indices = [
            0,1,2, 0,2,3,   # Front
            4,5,6, 4,6,7,   # Back
            8,9,10, 8,10,11, # Right
            12,13,14, 12,14,15, # Left
            16,17,18, 16,18,19, # Top
            20,21,22, 20,22,23  # Bottom
        ]
        for i in range(0, len(indices), 3):
            tris.addVertices(indices[i], indices[i+1], indices[i+2])
        
        geom = Geom(vdata)
        geom.addPrimitive(tris)
        node = GeomNode('platform_model')
        node.addGeom(geom)
        np = NodePath(node)
        # Adjust position so the top of the platform is at pos.z
        np.setPos(pos.getX(), pos.getY(), pos.getZ() + half_depth) 
        np.reparentTo(self.render)

        material = Material()
        material.setDiffuse(platform_color)
        material.setSpecular(VBase4(0.5, 0.5, 0.5, 1))
        material.setShininess(50.0)
        np.setMaterial(material)
        return np

    def setup_characters(self):
        """
        Creates player and staff objects and positions them.
        Initializes the active_players_queue.
        """
        player_colors = [
            VBase4(1.0, 0.8, 0.0, 1.0), # Yellow
            VBase4(0.0, 0.5, 1.0, 1.0), # Blue
            VBase4(0.5, 0.8, 0.2, 1.0), # Green
            VBase4(0.8, 0.2, 0.8, 1.0), # Purple
            VBase4(1.0, 0.5, 0.0, 1.0), # Orange
            VBase4(0.0, 0.8, 0.8, 1.0), # Cyan
            VBase4(0.8, 0.0, 0.8, 1.0)  # Magenta
        ]
        
        # --- Setup Players ---
        player_names_for_game = self.selected_players_names if self.selected_players_names else [f"Player {i+1}" for i in range(7)] # Default to 7 players
        self.num_players = len(player_names_for_game) # Update num_players based on selection or default to 7

        player_start_y = self.bridge_start_y - (self.tile_width * 1.5)
        player_z_on_platform = self.tile_depth # Players stand on top of the platform

        # Calculate player starting positions to spread them out on the platform
        num_players_per_row = 4 # Max players per row on the starting platform
        player_spacing_x = self.tile_width / (num_players_per_row + 1)
        player_spacing_y = self.tile_width / 2

        for i, player_name in enumerate(player_names_for_game):
            row_idx = i // num_players_per_row
            col_idx = i % num_players_per_row
            
            x_offset = (col_idx - (num_players_per_row - 1) / 2) * player_spacing_x
            y_offset = row_idx * player_spacing_y 

            body_color = player_colors[i % len(player_colors)] # Cycle through the defined colors
            head_color = body_color 

            start_pos = LPoint3(x_offset, player_start_y + y_offset, player_z_on_platform)
            
            player = Player(player_name, start_pos, self, head_color=head_color, body_color=body_color)
            self.players.append(player)
            self.active_players_queue.append(player) # All players are active initially (added to deque)
            print(f"DEBUG (setup_characters): Player {player.name} added to active_players_queue.")

        # --- Setup Staff ---
        staff_colors = {
            "Front Man": VBase4(0.2, 0.2, 0.2, 1.0), # Dark Grey/Black for Front Man
            "Square Guard": VBase4(0.7, 0.0, 0.0, 1.0), # Red for Square Guard
            "Triangle Guard": VBase4(0.0, 0.7, 0.0, 1.0), # Green for Triangle Guard
            "Circle Guard": VBase4(0.0, 0.0, 0.7, 1.0)  # Blue for Circle Guard
        }
        
        guard_patrol_x_offsets = [-self.tile_width * 2, self.tile_width * 2] # Left and Right sides of bridge
        guard_index = 0 # To alternate guards between left and right patrol paths

        for staff_name in self.selected_staff_names:
            staff_color = staff_colors.get(staff_name, VBase4(0.5, 0.5, 0.5, 1.0)) # Default grey if not found
            if staff_name == "Front Man":
                # Position Front Man on the end platform
                front_man_pos = LPoint3(0, self.end_platform_y, self.tile_depth) # On top of the end platform
                front_man = Staff(staff_name, "Front Man", front_man_pos, self, staff_color)
                self.staff_members.append(front_man)
                print(f"DEBUG (setup_characters): Front Man placed at {front_man_pos}.")
            elif staff_name in ["Square Guard", "Triangle Guard", "Circle Guard"]:
                # Position guards on patrolling paths on the sides of the bridge
                patrol_x = guard_patrol_x_offsets[guard_index % len(guard_patrol_x_offsets)]
                guard_start_y = self.bridge_start_y - self.tile_width * 0.5 # Start near beginning of bridge
                guard_pos = LPoint3(patrol_x, guard_start_y, self.tile_depth)
                
                guard = Staff(staff_name, "Guard", guard_pos, self, staff_color)
                self.staff_members.append(guard)
                guard_index += 1
                print(f"DEBUG (setup_characters): Guard {staff_name} placed at {guard_pos} for patrol.")
            else:
                print(f"WARNING: Unrecognized staff member '{staff_name}'. Skipping.")


    def display_player_status_ui(self):
        """
        Creates OnscreenText elements for each player's status.
        Adjusts Y offset for more players.
        """
        y_offset = 0.7 # Start Y for status text
        if self.num_players > 5:
            y_offset = 0.8 - (self.num_players * 0.03) 

        for player in self.players:
            text_node = OnscreenText(text=f"{player.name}: Ready", pos=(-1.2, y_offset), scale=0.04, fg=(1,1,1,1), align=TextNode.ALeft, mayChange=True)
            self.player_status_text[player.name] = text_node
            y_offset -= 0.05 # Smaller step for more players

    def update_player_info_display(self):
        """
        Updates the UI text showing the current player and instructions.
        """
        if self.current_player and not self.current_player.fallen and not self.current_player.crossed:
            self.player_info_text.setText(f"Current Player: {self.current_player.name}")
            self.instructions_text.setText("Press '1' for Left, '2' for Right")
        elif self.game_over_flag: # Check this flag to ensure game is truly over
            self.player_info_text.setText("Game Over!")
            self.instructions_text.setText("Press ESC to exit.")
        else: # Likely a transition state or all players finished but game_over hasn't been called yet
            self.player_info_text.setText("Waiting for next turn...")
            self.instructions_text.setText("")

    def highlight_current_player(self):
        """
        Highlights the current player and resets the highlight for others.
        """
        # Stop any existing pulse interval before resetting colors/scales
        if self.pulse_interval and self.pulse_interval.isPlaying():
            self.pulse_interval.finish()
            self.pulse_interval = None

        # Reset color and scale of all players to their original state
        for player in self.players:
            player.np.setColorScale(1, 1, 1, 1) # Reset color scale to normal (no tint)
            player.np.setScale(0.8) # Reset scale

        # Apply highlight to the current player
        if self.current_player and not self.current_player.fallen and not self.current_player.crossed:
            # Apply a yellowish tint for highlight
            self.current_player.np.setColorScale(1.5, 1.5, 0.5, 1) 
            # Simple pulse animation: grow from 0.8 to 0.9 and shrink back to 0.8
            self.pulse_interval = Sequence(
                self.current_player.np.scaleInterval(0.2, 0.9), # Grow slightly to 0.9
                self.current_player.np.scaleInterval(0.2, 0.8) # Shrink back to 0.8
            )
            self.pulse_interval.loop() # Use loop for continuous pulsing

    def attempt_move(self, chosen_col):
        """
        Handles player input for choosing a tile to move to.
        Only the current active player can make a choice.
        """
        if self.game_over_flag: # If game is over, ignore input
            print("DEBUG: Game is over. Ignoring input.")
            return

        if not self.current_player or not self.current_player.turn_active:
            print("DEBUG: Not current player's turn or no active player. Ignoring input.")
            self.game_status_text.setText("Not your turn or game ended!")
            return
        
        if self.current_player.fallen or self.current_player.crossed:
            print("DEBUG: Current player already finished. Ignoring input.")
            self.game_status_text.setText(f"{self.current_player.name} already finished!")
            return

        next_row = self.current_player.current_tile_row + 1

        if next_row >= self.bridge_length:
            print(f"DEBUG: {self.current_player.name} is at the end of the bridge or crossed. No more moves needed.")
            self.game_status_text.setText(f"{self.current_player.name} already at the end!")
            return

        # Check if the chosen tile exists and is valid
        if 0 <= next_row < self.bridge_length and 0 <= chosen_col < 2:
            # In Squid Game rules, we don't check if the tile is "occupied" by another player,
            # only if it's a valid tile to step on based on the game's rules.
            # The "observation" comes from knowing which tiles broke.
            
            print(f"DEBUG: {self.current_player.name} attempting to move to row {next_row}, col {chosen_col}")
            self.game_status_text.setText(f"{self.current_player.name}'s turn: Moving...")
            self.current_player.turn_active = False # Deactivate turn while move is in progress
            self.current_player.move_to_tile(next_row, chosen_col)
        else:
            print("Invalid move. Please choose '1' for Left or '2' for Right for the current tile.")
            self.game_status_text.setText("Invalid move! Try again.")
            self.current_player.turn_active = True # Keep turn active for invalid input

    def next_player_turn(self):
        """
        Advances the game to the next active player's turn for making a choice.
        This is called when the current player falls or crosses.
        """
        if self.game_over_flag:
            print("DEBUG (next_player_turn): Game is over. Not processing next turn.")
            return

        print(f"DEBUG (next_player_turn): Called. Current player before change: {self.current_player.name if self.current_player else 'None'}. Active queue size: {len(self.active_players_queue)}")

        # Ensure previous player's turn is properly ended and highlight removed
        if self.current_player:
            self.current_player.turn_active = False
            self.current_player.np.setColorScale(1, 1, 1, 1) # Reset color scale to normal
            self.current_player.np.setScale(0.8)

            # Remove the current player (who just fell or crossed) from the active queue
            # Only remove if they are still at the front of the queue (meaning their turn just finished)
            if self.active_players_queue and self.active_players_queue[0] == self.current_player:
                removed_player = self.active_players_queue.popleft()
                print(f"DEBUG (next_player_turn): Removed {removed_player.name} from active queue.")

        # Re-evaluate active players for game over condition
        if not self.active_players_queue:
            self.game_over()
            return

        # The new current player is now at the front of the deque
        self.current_player = self.active_players_queue[0]
        self.current_player.turn_active = True
        
        # ONLY reset player's *visual* position to the start platform if they haven't stepped on the bridge yet (current_tile_row == -1)
        # This ensures players who haven't started yet appear at the start,
        # but players who are midway through stay where they are.
        if self.current_player.current_tile_row == -1: # Only reset visual position for players who haven't started
            player_start_y = self.bridge_start_y - (self.tile_width * 1.5)
            player_z_on_platform = self.tile_depth
            num_players_per_row = 4
            player_spacing_x = self.tile_width / (num_players_per_row + 1)
            player_spacing_y = self.tile_width / 2
            
            player_idx_in_all_players = self.players.index(self.current_player)
            row_idx = player_idx_in_all_players // num_players_per_row
            col_idx = player_idx_in_all_players % num_players_per_row
            x_offset = (col_idx - (num_players_per_row - 1) / 2) * player_spacing_x
            y_offset = row_idx * player_spacing_y 
            start_pos = LPoint3(x_offset, player_start_y + y_offset, player_z_on_platform)
            self.current_player.np.setPos(start_pos)
            print(f"DEBUG: {self.current_player.name} (new turn) reset to start platform position ({start_pos.getX():.2f}, {start_pos.getY():.2f}).")
        else:
            print(f"DEBUG: {self.current_player.name} (new turn) is already on tile ({self.current_player.current_tile_row}, {self.current_player.current_tile_col}). No position reset.")


        self.camera_follow_player = self.current_player.np
        self.update_player_info_display()
        self.highlight_current_player() # Highlight the new current player
        self.game_status_text.setText(f"It's {self.current_player.name}'s turn! Choose next tile (1 for Left, 2 for Right).")

    def handle_time_up(self):
        """
        Called when the game timer runs out.
        All remaining active players are considered to have timed out.
        All unrevealed bridge tiles will fall.
        """
        if self.game_over_flag: # Prevent multiple calls to game_over
            return

        print("DEBUG: Time has run out! All remaining players are eliminated and bridge breaks.")
        self.game_status_text.setText("TIME OUT! Bridge breaks and players eliminated!")
        self.timer_active = False # Stop the timer

        # Mark all active players as fallen (timed out)
        players_timed_out = list(self.active_players_queue) # Create a copy to iterate
        for player in players_timed_out:
            if not player.fallen and not player.crossed:
                player.fallen = True
                player.is_on_bridge = False
                player.turn_active = False
                self.player_status_text[player.name].setText(f"{player.name}: Timed Out!")
                if player.np: # Detach their model if it's still there
                    player.np.detachNode()
        
        self.active_players_queue.clear() # Clear the queue as all are out

        # Make all unrevealed bridge tiles fall
        for r_idx, row_tiles in enumerate(self.bridge_tiles):
            for c_idx, tile_info in enumerate(row_tiles):
                # Check if this tile has NOT been revealed as safe or broken yet
                if r_idx not in self.revealed_safe_path and r_idx not in self.revealed_broken_path:
                    # Animate the tile falling
                    fall_tile_interval = tile_info['np'].posInterval(0.5, LPoint3(tile_info['x'], tile_info['y'], -5),
                                                                    startPos=tile_info['np'].getPos())
                    # Also make it look broken/darker and transparent as it falls
                    tile_info['np'].setTransparency(TransparencyAttrib.M_alpha)
                    tile_info['np'].setColor(Vec4(0.2, 0.2, 0.2, 0.3)) 
                    fall_tile_interval.start()
                elif r_idx in self.revealed_safe_path and self.revealed_safe_path[r_idx] != c_idx:
                    # If the other tile in this row was safe, but this one wasn't revealed, it must be the broken one
                    # This handles cases where a player stepped on the safe one, leaving the other unrevealed.
                    fall_tile_interval = tile_info['np'].posInterval(0.5, LPoint3(tile_info['x'], tile_info['y'], -5),
                                                                    startPos=tile_info['np'].getPos())
                    tile_info['np'].setTransparency(TransparencyAttrib.M_alpha)
                    tile_info['np'].setColor(Vec4(0.2, 0.2, 0.2, 0.3)) 
                    fall_tile_interval.start()


        self.game_over(time_limit_reached_flag=True) # Call game over to finalize state, indicating time limit was reached

    def game_over(self, time_limit_reached_flag=False):
        """
        Ends the game, displays results, and disables further input.
        Also updates the database with final game results.
        """
        if self.game_over_flag:
            return # Already handled game over

        print("DEBUG: All players have finished their attempt (either fallen or crossed). Game Over!")
        self.game_over_flag = True
        self.timer_active = False # Ensure timer stops

        self.game_status_text.setText("Game Over!")
        winners = [player.name for player in self.players if player.crossed]
        if winners:
            self.player_info_text.setText(f"Winners: {', '.join(winners)}")
        else:
            self.player_info_text.setText("No one crossed the bridge.")
        self.instructions_text.setText("Press ESC to exit.")
        self.ignore_all() # Ignore all previous inputs
        self.accept("escape", self.userExit) # Re-enable ESC to exit
        self.current_player = None # Clear current player as game is over
        self.camera_follow_player = None # Stop camera following a specific player

        # --- Save final game results to database ---
        self._update_game_session_results(time_limit_reached_flag)
        # We no longer close the connection here, it's closed by on_closing
        print("DEBUG: Database connection will be closed on application exit.")


    def update_game_state(self, task):
        """
        Main game loop task to check for game over condition and manage turn progression.
        """
        if self.game_over_flag:
            return task.done # Stop this task if game is over

        # If no active players left, game is over.
        if not self.active_players_queue and not self.game_over_flag: # Added game_over_flag check
            self.game_over()
            return task.done
        
        # This task loop mainly ensures that if a player somehow becomes inactive without
        # next_player_turn being called, it will be triggered.
        if self.current_player is None or (self.current_player.fallen or self.current_player.crossed):
            self.next_player_turn()
        # If the current player is active and waiting for input, do nothing in this task loop.
        # Their turn will progress via attempt_move -> check_tile.
        elif self.current_player and self.current_player.turn_active:
            pass # Current player is active, waiting for input.

        return task.cont

    def update_timer(self, task):
        """
        Updates the global game timer.
        """
        if self.game_over_flag:
            self.timer_text.setText(f"Time Left: 0") # Ensure timer shows 0 at end
            return task.done # Stop the timer task

        if self.timer_active:
            self.time_left -= globalClock.getDt() # type: ignore
            if self.time_left <= 0:
                self.time_left = 0
                self.timer_text.setText(f"Time Left: 0")
                self.handle_time_up()
                return task.done # Stop the timer task

            self.timer_text.setText(f"Time Left: {self.time_left:.0f}") # Display as whole seconds
        
        return task.cont

    def update_camera(self, task):
        """
        Smoothly moves the camera to follow the current lead player.
        """
        target_follow_node = None
        
        # Always follow the current player if they are active
        if self.current_player and not self.current_player.fallen and not self.current_player.crossed:
            target_follow_node = self.current_player.np
        
        self.camera_follow_player = target_follow_node # Update the camera_follow_player reference

        if self.camera_follow_player:
            # Adjust camera position relative to the target player
            target_pos = self.camera_follow_player.getPos() + LVector3(0, -15, 10) 
            current_pos = self.camera.getPos()
            
            # Smooth interpolation for camera movement
            new_pos = current_pos + (target_pos - current_pos) * 0.05
            self.camera.setPos(new_pos)
            self.camera.lookAt(self.camera_follow_player.getPos() + LVector3(0, 0, 0.5)) 
        return task.cont


# --- Main Tkinter Application Setup ---
def on_closing():
    """
    Handles the closing of the Tkinter window.
    Closes the database connection.
    """
    global db_connection, db_cursor
    if db_cursor:
        db_cursor.close()
        print("DEBUG: Database cursor closed.")
    if db_connection and db_connection.is_connected():
        db_connection.close()
        print("DEBUG: Database connection closed on application exit.")
    root.destroy()


if __name__ == '__main__':
    root = Tk()
    root.title("Squid Game - Glass Bridge")
    root.state('zoomed') # Maximize the window
    root.resizable(True, True)

    # Initialize screen_width and screen_height globally after root is created
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()

    # Set up database connection and tables immediately
    connect_db()
    create_tables()

    # Global variables to store selected players/staff from Tkinter
    selected_players = []
    selected_staff = []

    # Handle window closing to ensure DB connection is closed
    root.protocol("WM_DELETE_WINDOW", on_closing)

    show_welcome_screen() # Call this to start the application
    root.mainloop()
