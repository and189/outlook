import subprocess
import sys
import time
import random
import string
import xml.etree.ElementTree as ET
import re
import os
import yaml
import json # Added for JSON handling
import requests # Added for sending Discord messages

def load_config(config_path):
    """Loads configuration from a YAML file."""
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        return config
    except FileNotFoundError:
        print(f"Error: Config file not found at {config_path}", file=sys.stderr)
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing config file: {e}", file=sys.stderr)
        sys.exit(1)

# --- CONFIGURATION ---
# The text of the element to be pressed (corrected according to your specification)
ELEMENT_TEXT_TO_FIND = "HUMAN Iframe Page"

# Duration of the click in milliseconds (10 seconds = 10000 ms)
HOLD_DURATION_MS = 15000

# Discord Webhook URL
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1383790260500168715/QA2QdWol0XpuxZAG07aKjNG_J2yt4DeyreDa8Qv3MBmE3NAo0r1Z2SxD03fyHfytn4t_"

# The IP of your device - Using existing device_ip instead
# DEVICE_ADDRESS = "192.168.0.33"

# Mapping of lowercase characters and numbers to ADB key event codes
# Based on the existing key codes in the script and common Android key codes
KEY_CODE_MAP = {
    'a': 29, 'b': 30, 'c': 31, 'd': 32, 'e': 33, 'f': 34, 'g': 35, 'h': 36,
    'i': 37, 'j': 38, 'k': 39, 'l': 40, 'm': 41, 'n': 42, 'o': 43, 'p': 44,
    'q': 45, 'r': 46, 's': 47, 't': 48, 'u': 49, 'v': 50, 'w': 51, 'x': 52,
    'y': 53, 'z': 54,
    '0': 7, '1': 8, '2': 9, '3': 10, '4': 11, '5': 12, '6': 13, '7': 14,
    '8': 15, '9': 16,
    '.': 56, '@': 77 # Added common email characters
}

def string_to_keycodes(text):
    """Converts a string to a list of ADB key event codes (lowercase), transliterating umlauts."""
    key_codes = []
    # Transliterate common German umlauts
    transliterated_text = text.lower().replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss')
    
    for char in transliterated_text:
        if char in KEY_CODE_MAP:
            key_codes.append(KEY_CODE_MAP[char])
        else:
            print(f"Warning: No key code found for character '{char}' after transliteration", file=sys.stderr)
    return key_codes

# Lists of common German names for more human-like generation
FIRST_NAMES = [
    "Thomas", "Michael", "Andreas", "Stefan", "Christian", "Daniel", "Martin", "Peter", "Frank", "Jürgen",
    "Maria", "Andrea", "Sabine", "Claudia", "Petra", "Nicole", "Tanja", "Sandra", "Susanne", "Martina"
]

LAST_NAMES = [
    "Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker", "Schulz", "Hofmann",
    "Schäfer", "Koch", "Bauer", "Richter", "Klein", "Wolf", "Schröder", "Neumann", "Schwarz", "Zimmermann"
]

def generate_random_string(length):
    """Generates a random lowercase string of a given length."""
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(length))

def generate_random_email_details():
    """Generates a more unique email name along with the chosen first and last names."""
    first_name = random.choice(FIRST_NAMES) # Keep original casing for form input
    last_name = random.choice(LAST_NAMES)   # Keep original casing for form input
    
    # Generate email name parts in lowercase and transliterate umlauts
    first_lower = first_name.lower().replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss')
    last_lower = last_name.lower().replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss')
    separator = random.choice(['.']) # Use only '.' as a separator
    number = str(random.randint(100, 9999)) # Always add a larger number

    # Combine parts in a few common formats for the email name
    formats = [
        f"{first_lower}{separator}{last_lower}{number}",
        f"{first_lower}{number}{separator}{last_lower}",
        f"{first_lower}{last_lower}{number}",
        f"{last_lower}{separator}{first_lower}{number}",
        f"{first_lower[0]}{last_lower}{number}", # e.g., jdoe1234
        f"{first_lower}{last_lower}{separator}{number}", # e.g., janedoe_1234
        f"{last_lower}{first_lower}{number}" # e.g., doejane1234
    ]
    # Ensure the generated name is not empty and remove extra separators if number is empty
    generated_name = random.choice(formats).replace('..', '.').replace('__', '_').strip('._')
    
    # Regenerate if empty, otherwise return all details
    if not generated_name:
        return generate_random_email_details()
    else:
        return generated_name, first_name, last_name


def generate_random_password():
    """Generates a random password."""
    letter_part = generate_random_string(random.randint(8, 12))
    number_part = str(random.randint(100, 999))
    return f"{letter_part}{number_part}"

def generate_random_month():
    """Generates a random month name."""
    months = ["Januar", "Februar", "Maerz", "April", "Mai", "Juni",
              "Juli", "August", "September", "Oktober", "November", "Dezember"]
    return random.choice(months)

def generate_random_day():
    """Generates a random day number (1-28)."""
    return str(random.randint(1, 28))

def generate_random_year():
    """Generates a random year number (1950-2000)."""
    return str(random.randint(1950, 2000))

def generate_random_first_name():
    """Generates a random first name from a list."""
    return random.choice(FIRST_NAMES)

def generate_random_last_name():
    """Generates a random last name from a list."""
    return random.choice(LAST_NAMES)


def get_ui_dump_tree(device_ip, max_retries=5, retry_delay_sec=2):
    """Creates a UI dump, pulls it, and parses the XML tree."""
    xml_file_device_path = "/sdcard/window_dump.xml"
    xml_file_local_path = "window_dump.xml"

    for attempt in range(1, max_retries + 1):
        print(f"\n[Attempt {attempt}/{max_retries}] Creating and downloading UI dump...")
        if run_adb_command(f"shell uiautomator dump {xml_file_device_path}") is None:
            print(f"Error creating UI dump on attempt {attempt}. Waiting {retry_delay_sec} seconds...")
            time.sleep(retry_delay_sec)
            continue
        if run_adb_command(f"pull {xml_file_device_path} {xml_file_local_path}") is None:
            print(f"Error downloading UI dump on attempt {attempt}. Waiting {retry_delay_sec} seconds...")
            time.sleep(retry_delay_sec)
            continue

        try:
            tree = ET.parse(xml_file_local_path)
            root = tree.getroot()
            print("  [+] UI dump successfully retrieved and parsed.")
            return root
        except ET.ParseError as e:
            print(f"!!! ERROR: Could not read the XML file on attempt {attempt}. {e}")
            if attempt < max_retries:
                print(f"Waiting {retry_delay_sec} seconds before next attempt...")
                time.sleep(retry_delay_sec)
            continue # Try again

    print(f"\n!!! ERROR: Could not retrieve/read UI dump after {max_retries} attempts. Aborting.")
    return None

def find_element_bounds(root, text_to_find):
    """Finds the bounds of an element by its text or content-desc in the XML tree."""
    if root is None:
        return None

    found_node = None
    for node in root.iter('node'):
        # We check text and also the description (content-desc)
        if node.attrib.get('text') == text_to_find or node.attrib.get('content-desc') == text_to_find:
            found_node = node
            break

    if found_node is None:
        print(f"!!! ERROR: Could not find element with text '{text_to_find}'.")
        return None

    bounds_str = found_node.attrib.get('bounds')
    print(f"  [+] Element found! Bounds: {bounds_str}")
    return bounds_str

def click_element_at_bounds(bounds_str, device_ip):
    """Performs a click at the center of the given bounds."""
    if bounds_str is None:
        print("!!! ERROR: No bounds specified for clicking.")
        return False

    coords = re.findall(r'\d+', bounds_str)
    if len(coords) != 4:
        print("!!! ERROR: Invalid bounds format.")
        return False

    x1, y1, x2, y2 = map(int, coords)
    center_x = (x1 + x2) // 2
    center_y = (y1 + y2) // 2

    print(f"  Clicking at point (X={center_x}, Y={center_y})...")
    run_adb_command(f"shell input tap {center_x} {center_y}")
    time.sleep(1) # Short pause after the action
    return True

def find_and_click_element(text_to_find, device_ip, max_retries=5, retry_delay_sec=2):
    """Finds an element by text and clicks it, with retries."""
    print(f"\n[Action] Searching and clicking element with text: '{text_to_find}'...")
    for attempt in range(1, max_retries + 1):
        print(f"\n[Attempt {attempt}/{max_retries}] Searching for element with text: '{text_to_find}'...")

        # Get UI dump and parse XML
        root = get_ui_dump_tree(device_ip, max_retries=1, retry_delay_sec=retry_delay_sec) # Use 1 retry here
        if root is None:
            print(f"Error retrieving/reading UI dump on attempt {attempt}. Waiting {retry_delay_sec} seconds...")
            time.sleep(retry_delay_sec)
            continue

        # Find element bounds
        bounds_str = find_element_bounds(root, text_to_find)
        if bounds_str is None:
            print(f"Element '{text_to_find}' not found on attempt {attempt}. Waiting {retry_delay_sec} seconds...")
            if attempt < max_retries:
                 # Log the full content of the XML file when the element is not found
                xml_file_local_path = "window_dump.xml" # Need to define path again to read it
                if os.path.exists(xml_file_local_path):
                    try:
                        with open(xml_file_local_path, 'r', encoding='utf-8') as f:
                            full_content = f.read()
                            print(f"  [Debug] Full content of UI dump:\n{full_content}")
                    except Exception as e:
                        print(f"  [Debug] Error reading local XML file for debug log: {e}")
                time.sleep(retry_delay_sec)
            continue # Try again

        # Element found, now click it
        if click_element_at_bounds(bounds_str, device_ip):
            print(f"\n--- SUCCESS! Element '{text_to_find}' was clicked. ---")
            return True # Success, exit function
        else:
            print(f"!!! ERROR clicking element '{text_to_find}' on attempt {attempt}. Waiting {retry_delay_sec} seconds...")
            time.sleep(retry_delay_sec)
            continue # Try again

    print(f"\n!!! ERROR: Element '{text_to_find}' not found or clicked after {max_retries} attempts. Aborting.")
    return False # Failure


def run_adb_command(command):
    """Executes an ADB command and returns the output."""
    # Corrected f-string formatting
    full_command = f"adb -s {device_ip} {command}" # Use device_ip from main block
    print(f"  > Executing: {full_command}")
    try:
        result = subprocess.run(full_command, shell=True, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"!!! ERROR executing ADB !!!")
        print(f"Command: {e.cmd}")
        print(f"Error message: {e.stderr}")
        return None

def find_and_long_press_element(text_to_find, duration_ms, device_ip, max_retries=5, retry_delay_sec=2):
    """Finds an element by its text and performs a long click, with retries."""

    for attempt in range(1, max_retries + 1):
        print(f"\n[Attempt {attempt}/{max_retries}] Searching for element with text: '{text_to_find}' for long click...")

        # Get UI dump and parse XML
        root = get_ui_dump_tree(device_ip, max_retries=1, retry_delay_sec=retry_delay_sec) # Use 1 retry here
        if root is None:
            print(f"Error retrieving/reading UI dump on attempt {attempt}. Waiting {retry_delay_sec} seconds...")
            time.sleep(retry_delay_sec)
            continue

        # Find element bounds
        bounds_str = find_element_bounds(root, text_to_find)
        if bounds_str is None:
            print(f"Element '{text_to_find}' not found on attempt {attempt}. Waiting {retry_delay_sec} seconds...")
            if attempt < max_retries:
                 # Log the full content of the XML file when the element is not found
                xml_file_local_path = "window_dump.xml" # Need to define path again to read it
                if os.path.exists(xml_file_local_path):
                    try:
                        with open(xml_file_local_path, 'r', encoding='utf-8') as f:
                            full_content = f.read()
                            print(f"  [Debug] Full content of UI dump:\n{full_content}")
                    except Exception as e:
                        print(f"  [Debug] Error reading local XML file for debug log: {e}")
                time.sleep(retry_delay_sec)
            continue # Try again

        # Element found, now perform long press
        print("\n[Action] Calculating center point and performing long click...")
        coords = re.findall(r'\d+', bounds_str)
        if len(coords) != 4:
            print("!!! ERROR: Invalid bounds format.")
            return False # Exit if bounds format is wrong

        x1, y1, x2, y2 = map(int, coords)
        center_x = (x1 + x2) // 2
        center_y = (y1 + y2) // 2

        print(f"  Holding point (X={center_x}, Y={center_y}) for {duration_ms / 1000} seconds...")

        # This is the command for the long click (a swipe without movement)
        run_adb_command(f"shell input swipe {center_x} {center_y} {center_x} {center_y} {duration_ms}")

        print("\n--- SUCCESS! Long click was performed. ---")
        time.sleep(1) # Short pause after the action
        return True # Success, exit function

    print(f"\n!!! ERROR: Element '{text_to_find}' not found for long click after {max_retries} attempts. Aborting.")
    return False # Failure


while True:
    if __name__ == "__main__":
        # Check for device_ip command-line argument
        if len(sys.argv) > 1:
            device_ip = sys.argv[1]
            print(f"Using device IP from command line: {device_ip}")
        else:
            print("Error: No device IP provided as a command-line argument.", file=sys.stderr)
            # Removed sys.exit(1) to allow the loop to continue
            pass # Or add logging/error handling if needed

        # config is still needed for other settings like URLs and API keys
        config = load_config('config.yaml')

        url_to_open = "https://go.microsoft.com/fwlink/p/?linkid=2125440&clcid=0x409&culture=en-us&country=us" # Replace with the URL you want to open
        log_file = "account_logs.txt" # Define log file name

        print(f"Attempting to connect to device at {device_ip}...")
        # Corrected command: remove "adb" prefix
        run_adb_command(f"connect {device_ip}")

        # Clear Chrome cache
        print("Attempting to clear Chrome cache...")
        # Corrected command: remove "adb shell" prefix
        run_adb_command("shell pm clear com.android.chrome")

        # Open the target URL directly after clearing cache
        print(f"Attempting to open browser with URL: {url_to_open}...")
        # Corrected command: use double quotes for the URL and escape any existing double quotes
        escaped_url = url_to_open.replace('"', '\\"')
        run_adb_command(f'shell am start -a android.intent.action.VIEW -d "{escaped_url}"')

        # Wait for the page to load
        time.sleep(10)

        # Attempt to click "Use without an account"
        print("\nAttempting to click 'Use without an account'...")
        find_and_click_element("Use without an account", device_ip)

        # Wait after attempting to click "Use without an account"
        time.sleep(5) # Add a short wait after clicking

        # Wait after initial input commands
        time.sleep(25) # Increased wait time before typing email name by an additional 10 seconds

        # Generate email details and password
        email_name, first_name, last_name = generate_random_email_details()
        email_full = f"{email_name}@outlook.com"
        password = generate_random_password()

        # Type email name using key events
        print(f"Attempting to type email name: {email_name} using key events...")
        email_key_events = string_to_keycodes(email_name)

        for key_code in email_key_events:
            # Corrected command: remove "adb shell" prefix
            run_adb_command(f"shell input keyevent {key_code}")
            time.sleep(0.1) # Small delay between key events

        # Send 3x Tab and Enter after typing email name
        print("Attempting to send 2x Tab and Enter after typing email name with delays...")
        # Corrected commands: remove "adb shell" prefix
        run_adb_command("shell input keyevent 61") # KEYCODE_TAB
        time.sleep(0.1) # Small delay
        run_adb_command("shell input keyevent 61") # KEYCODE_TAB
        time.sleep(0.1) # Small delay
        run_adb_command("shell input keyevent 66") # KEYCODE_ENTER
        time.sleep(0.1) # Small delay after Enter

        # Wait after email entry sequence
        time.sleep(5)

        # Type password
        print(f"Attempting to type password: {password} using key events...")
        password_key_events = string_to_keycodes(password)
        for key_code in password_key_events:
            # Corrected command: remove "adb shell" prefix
            run_adb_command(f"shell input keyevent {key_code}")
            time.sleep(0.1) # Small delay between key events

        # Send Tab, Tab, Enter after typing password
        print("Attempting to send Tab, Tab, Enter after typing password...")
        # Corrected commands: remove "adb shell" prefix
        run_adb_command("shell input keyevent 61") # KEYCODE_TAB
        time.sleep(0.1)
        run_adb_command("shell input keyevent 61") # KEYCODE_TAB
        time.sleep(0.1)
        run_adb_command("shell input keyevent 66") # KEYCODE_ENTER
        time.sleep(10) # Wait after password entry

        # Send "ger" + Enter + Tab before month
        print("Attempting to send 'ger' + Enter + Tab...")
        ger_key_events = string_to_keycodes("ger")
        for key_code in ger_key_events:
            run_adb_command(f"shell input keyevent {key_code}")
            time.sleep(0.1) # Small delay between key events

        run_adb_command("shell input keyevent 66") # KEYCODE_ENTER
        time.sleep(1) # 1 second pause after Enter
        run_adb_command("shell input keyevent 61") # KEYCODE_TAB
        time.sleep(1) # 1 second pause after Tab
        time.sleep(5) # Wait after "ger" sequence

        # Generate and send key events for month
        month = generate_random_month()
        print(f"Attempting to type first 2 letters of month: {month[:2]} using key events...")
        month_key_events = string_to_keycodes(month[:2]) # Send only the first 2 letters
        for key_code in month_key_events:
            run_adb_command(f"shell input keyevent {key_code}")
            time.sleep(0.1) # Small delay between key events

        # Send Enter, Tab after typing month
        print("Attempting to send Enter, Tab after typing month...")
        # Corrected commands: remove "adb shell" prefix
        run_adb_command("shell input keyevent 66") # KEYCODE_ENTER
        time.sleep(0.1)
        run_adb_command("shell input keyevent 61") # KEYCODE_TAB
        time.sleep(5) # Wait after month entry

        # Generate and type number for day
        day = generate_random_day()
        print(f"Attempting to type day: {day} using key events...")
        day_key_events = string_to_keycodes(day)
        for key_code in day_key_events:
            # Corrected command: remove "adb shell" prefix
            run_adb_command(f"shell input keyevent {key_code}")
            time.sleep(0.1) # Small delay between key events

        # Send Enter, Tab after typing day
        print("Attempting to send Enter, Tab after typing day...")
        # Corrected commands: remove "adb shell" prefix
        run_adb_command("shell input keyevent 66") # KEYCODE_ENTER
        time.sleep(0.1)
        run_adb_command("shell input keyevent 61") # KEYCODE_TAB
        time.sleep(5) # Wait after day entry

        # Generate and type year in numbers
        year = generate_random_year()
        print(f"Attempting to type year: {year} using key events...")
        year_key_events = string_to_keycodes(year)
        for key_code in year_key_events:
            # Corrected command: remove "adb shell" prefix
            run_adb_command(f"shell input keyevent {key_code}")
            time.sleep(0.1) # Small delay between key events

        # Send Tab, Tab, Enter after typing year
        print("Attempting to send Tab, Tab, Enter after typing year...")
        # Corrected commands: remove "adb shell" prefix
        run_adb_command("shell input keyevent 61") # KEYCODE_TAB
        time.sleep(0.1)
        run_adb_command("shell input keyevent 61") # KEYCODE_TAB
        time.sleep(0.1)
        run_adb_command("shell input keyevent 66") # KEYCODE_ENTER
        time.sleep(10) # Wait after year entry

        # Type first name
        print(f"Attempting to type first name: {first_name} using key events...")
        first_name_key_events = string_to_keycodes(first_name)
        for key_code in first_name_key_events:
            run_adb_command(f"shell input keyevent {key_code}")
            time.sleep(0.1) # Small delay between key events

        # Send Tab after typing first name
        print("Attempting to send Tab after typing first name...")
        run_adb_command("shell input keyevent 61") # KEYCODE_TAB
        time.sleep(5) # Wait after Tab

        # Type last name
        print(f"Attempting to type last name: {last_name} using key events...")
        last_name_key_events = string_to_keycodes(last_name)
        for key_code in last_name_key_events:
            run_adb_command(f"shell input keyevent {key_code}")
            time.sleep(0.1) # Small delay between key events

        # Send 4x Tab, Enter after typing last name
        print("Attempting to send 4x Tab, Enter after typing last name...")
        # Corrected commands: remove "adb shell" prefix
        run_adb_command("shell input keyevent 61") # KEYCODE_TAB
        time.sleep(0.1)
        run_adb_command("shell input keyevent 61") # KEYCODE_TAB
        time.sleep(0.1)
        run_adb_command("shell input keyevent 61") # KEYCODE_TAB
        time.sleep(0.1)
        run_adb_command("shell input keyevent 61") # KEYCODE_TAB
        time.sleep(0.1)
        run_adb_command("shell input keyevent 66") # KEYCODE_ENTER
        time.sleep(5) # Wait after last name entry

        # Call the function to find and long press the element
        long_press_success = find_and_long_press_element(ELEMENT_TEXT_TO_FIND, HOLD_DURATION_MS, device_ip)

        if long_press_success:
            # Wait 10 seconds after the long press
            print("\nWaiting 10 seconds after the long click...")
            time.sleep(20)

            # Check if the element is still present after the long press
            print(f"\nChecking if element '{ELEMENT_TEXT_TO_FIND}' is still present after long click...")
            root_after_long_press = get_ui_dump_tree(device_ip, max_retries=1, retry_delay_sec=2)
            bounds_after_long_press = find_element_bounds(root_after_long_press, ELEMENT_TEXT_TO_FIND)

            if bounds_after_long_press is not None:
                print(f"  [!] Element '{ELEMENT_TEXT_TO_FIND}' is still present after long click. Performing long click again.")
                # Perform another long press if the element is still present
                find_and_long_press_element(ELEMENT_TEXT_TO_FIND, HOLD_DURATION_MS, device_ip)
                # After the second long press, the script will continue to the check below
                # to see if the element is finally gone.

                # Re-check after the second long press
                print(f"\nRe-checking if element '{ELEMENT_TEXT_TO_FIND}' is still present after second long click...")
                root_after_second_long_press = get_ui_dump_tree(device_ip, max_retries=1, retry_delay_sec=2)
                bounds_after_second_long_press = find_element_bounds(root_after_second_long_press, ELEMENT_TEXT_TO_FIND)

                if bounds_after_second_long_press is not None:
                     print(f"  [!] Element '{ELEMENT_TEXT_TO_FIND}' is still present after second long click. Restarting script.")
                else:
                     print(f"  [+] Element '{ELEMENT_TEXT_TO_FIND}' is no longer present after second long click. Continuing.")


            else:
                print(f"  [+] Element '{ELEMENT_TEXT_TO_FIND}' is no longer present after long click. Continuing.")

            # Attempt to click "Skip" (first time)
            print("\nAttempting to click 'Skip for now' (1st time)...")
            find_and_click_element("Skip for now", device_ip)

            # Wait 5 seconds
            print("\nWaiting 5 seconds...")
            time.sleep(5)

            # Attempt to click "Skip" (second time)
            print("\nAttempting to click 'Skip for now' (2nd time)...")
            find_and_click_element("Skip for now", device_ip)

            # Wait 15 seconds
            print("\nWaiting 15 seconds...")
            time.sleep(15)

            # Attempt to click "Reject all" for up to 5 minutes (150 retries * 2 sec delay)
            print("\nAttempting to click 'Reject all' (up to 5 minutes)...")
            reject_all_success = find_and_click_element("Reject all", device_ip, max_retries=150)

            # If "Reject all" was clicked successfully, log the account
            if reject_all_success:
                print(f"\n--- SUCCESS! 'Reject all' was clicked. Logging account details. ---")
                # Log the generated account details
                with open(log_file, "a") as f:
                    f.write(f"Attempt: {time.strftime('%Y-%m-%m %H:%M:%S')}\n")
                    f.write(f"Email: {email_full}\n")
                    f.write(f"First Name: {first_name}\n")
                    f.write(f"Last Name: {last_name}\n")
                    f.write(f"Password: {password}\n")
                    f.write("-" * 20 + "\n")
                print(f"Logged account details to {log_file}")

                # Send success message to Discord webhook
                discord_message = f"Account created: Email: {email_full}"
                payload = {
                    "content": discord_message
                }
                try:
                    response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
                    response.raise_for_status() # Raise an exception for bad status codes
                    print("Sent success message to Discord webhook.")
                except requests.exceptions.RequestException as e:
                    print(f"Error sending message to Discord webhook: {e}", file=sys.stderr)

                # Add email and password to email.json
                email_json_path = 'email.json'
                email_entry = f"{email_full};{password}"
                email_data = {"emails": []}

                if os.path.exists(email_json_path):
                    try:
                        with open(email_json_path, 'r') as f:
                            email_data = json.load(f)
                    except (json.JSONDecodeError, FileNotFoundError):
                        print(f"Warning: Could not read or parse existing {email_json_path}. Starting with an empty list.", file=sys.stderr)

                email_list = email_data.get("emails", [])
                email_list.append(email_entry)
                email_data["emails"] = email_list

                try:
                    with open(email_json_path, 'w') as f:
                        json.dump(email_data, f, indent=2)
                    print(f"Added '{email_entry}' to {email_json_path}")
                except Exception as e:
                    print(f"Error writing to {email_json_path}: {e}", file=sys.stderr)

            else:
                print(f"\n!!! ERROR: 'Reject all' was not found or clicked after 4 attempts. Account will not be marked as successful. !!!")
                # Removed sys.exit(1) to allow the loop to continue
                pass # Or add logging/error handling if needed

        else:
            print("\n!!! Long click was not successful. Skipping further steps. !!!")
            # Removed sys.exit(1) to allow the loop to continue
            pass # Or add logging/error handling if needed

        # Print the generated email and password to standard output for the orchestrator script
        print(f"GENERATED_ACCOUNT:{email_full};{password}")

        print("Script finished successfully.")
        # Removed sys.exit(0) to allow the loop to continue
        # The loop will automatically restart
