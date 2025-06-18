import yaml
import subprocess
import os
import xml.etree.ElementTree as ET
import re
import random
import datetime
import json
import string
import time
import urllib.parse
import requests
import logging
import pytesseract
from PIL import Image

# Konfiguration des Loggings, um auch DEBUG-Ausgaben zu sehen
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


def load_config(config_path='config.yaml'):
    """Loads configuration from a YAML file."""
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        return config
    except FileNotFoundError:
        logging.error(f"Error: Config file not found at {config_path}")
        return None
    except yaml.YAMLError as e:
        logging.error(f"Error parsing config file: {e}")
        return None

def run_adb_command(device_ip2, command):
    """Runs an ADB command for a specific device IP."""
    adb_command = ["adb", "-s", device_ip2] + command
    try:
        result = subprocess.run(adb_command, capture_output=True, text=True, check=True)
        logging.debug("ADB Command Output:")
        logging.debug(result.stdout)
        if result.stderr:
            logging.debug("ADB Command Error:")
            logging.debug(result.stderr)
        return result.stdout
    except subprocess.CalledProcessError as e:
        logging.error(f"Error executing ADB command: {e}")
        logging.error(f"Stderr: {e.stderr}")
        return None
    except FileNotFoundError:
        logging.error("Error: ADB command not found. Make sure ADB is installed and in your PATH.")
        return None

def dump_ui(device_ip2, output_file="dump.xml"):
    """
    Performs a UI dump by saving it to a temporary file on the device
    and then pulling the file to the local machine.
    """
    logging.info(f"Dumping UI for device {device_ip2}...")
    device_temp_file = "/data/local/tmp/window_dump.xml"

    # Dump UI to a temporary file on the device
    dump_command = ["shell", "uiautomator dump", device_temp_file]
    dump_result = run_adb_command(device_ip2, dump_command)

    if dump_result is None:
        logging.error("Error performing UI dump on device.")
        return None

    # Pull the temporary file from the device
    pull_command = ["pull", device_temp_file, output_file]
    pull_result = run_adb_command(device_ip2, pull_command)

    if pull_result is None:
        logging.error(f"Error pulling UI dump file from device to {output_file}.")
        # Attempt to remove the screenshot from the device even if pull failed
        run_adb_command(device_ip2, ["shell", "rm", device_temp_file])
        return None

    # Optional: Remove the temporary file from the device
    run_adb_command(device_ip2, ["shell", "rm", device_temp_file]) # No need to check result for removal

    logging.info(f"UI dump saved to {output_file}")
    return output_file

def parse_ui_dump(xml_file):
    """Parses the UI dump XML file."""
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
        logging.info(f"Successfully parsed UI dump from {xml_file}")
        return root
    except FileNotFoundError:
        logging.error(f"Error: UI dump file not found at {xml_file}")
        return None
    except ET.ParseError as e:
        logging.error(f"Error parsing XML file: {e}")
        return None

def find_element(root, attribute, value):
    """Finds the first element in the UI dump with a matching attribute and value."""
    if root is None:
        return None

    for elem in root.iter():
        # Check both 'text' and 'content-desc' attributes
        elem_text = elem.attrib.get('text', '').strip().lower()
        elem_content_desc = elem.attrib.get('content-desc', '').strip().lower()
        search_value = value.strip().lower()
        logging.debug(f"Checking element: text='{elem_text}', content-desc='{elem_content_desc}'")

        if elem_text == search_value or elem_content_desc == search_value:
            bounds = elem.attrib.get('bounds')
            if bounds:
                # Bounds are in format [left,top][right,bottom]
                match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                if match:
                    x1, y1, x2, y2 = map(int, match.groups())
                    # Calculate center coordinates
                    center_x = (x1 + x2) // 2
                    center_y = (y1 + y2) // 2
                    # Only return coordinates if they are not (0, 0)
                    if center_x != 0 or center_y != 0:
                        logging.info(f"Found element with {attribute}='{value}' at coordinates ({center_x}, {center_y})")
                        return {'x': center_x, 'y': center_y}
    logging.info(f"Element with {attribute}='{value}' not found.")
    return None

def tap(device_ip2, x, y):
    """Performs a tap action on the device screen at the given coordinates."""
    logging.info(f"Tapping on device {device_ip2} at coordinates ({x}, {y})...")
    command = ["shell", "input", "tap", str(x), str(y)]
    run_adb_command(device_ip2, command)

def clear_chrome_cache(device_ip2):
    """Clears the cache for the Chrome browser app."""
    logging.info(f"Clearing Chrome cache on device {device_ip2}...")
    # This command force stops the app and clears its cache
    command = ["shell", "pm clear com.android.chrome"]
    run_adb_command(device_ip2, command)

def start_chrome(device_ip2, url=None):
    """Starts the Chrome browser."""
    logging.info(f"Starting Chrome on device {device_ip2}...")
    command = ["shell", "am start -n com.android.chrome/com.google.android.apps.chrome.Main"]
    if url:
        # Use ACTION_VIEW to open a URL, potentially in a new tab depending on Chrome's state
        command = ["shell", f"am start -a android.intent.action.VIEW -d \"{url}\" com.android.chrome"]
    run_adb_command(device_ip2, command)

def open_new_tab_with_url(device_ip2, url):
    """Opens a new tab in Chrome with the specified URL."""
    logging.info(f"Opening new tab with URL {url} on device {device_ip2}...")
    # Using ACTION_VIEW with FLAG_ACTIVITY_NEW_TASK might open in a new tab or bring to front and navigate
    command = ["shell", f"am start -a android.intent.action.VIEW -f 0x10200000 -d \"{url}\" com.android.chrome"]
    run_adb_command(device_ip2, command)


def get_unused_email_and_password(email_file='email.json'):
    """Reads email.json, finds an unused email (without ' X'), and returns email and password."""
    try:
        with open(email_file, 'r') as f:
            data = json.load(f)
            emails = data.get("emails", [])

        for i, entry in enumerate(emails): # Use enumerate to get index
            if not entry.endswith(" X"):
                parts = entry.split(';')
                if len(parts) == 2:
                    email = parts[0].strip()
                    password = parts[1].strip()
                    logging.info(f"Found unused email: {email}")
                    # Mark the email as used by appending " X"
                    data["emails"][i] = entry + " X"
                    # Write the updated data back to email.json
                    with open(email_file, 'w') as f:
                        json.dump(data, f, indent=4) # Use indent for readability
                    logging.info(f"Marked email '{email}' as used in {email_file}")
                    return email, password
        logging.warning("No unused emails found in email.json")
        return None, None

    except FileNotFoundError:
        logging.error(f"Error: Email file not found at {email_file}")
        return None, None
    except json.JSONDecodeError as e:
        logging.error(f"Error parsing email JSON file: {e}")
        return None, None
    except Exception as e:
        logging.error(f"An error occurred while reading email file: {e}")
        return None, None



def generate_random_username():
    """Generates a more human-like random username."""
    adjectives = ["happy", "lucky", "swift", "brave", "clever", "gentle", "mighty", "sunny", "quiet", "wild"]
    nouns = ["tiger", "eagle", "river", "mountain", "ocean", "forest", "star", "moon", "fire", "wind"]

    # Choose a random adjective and noun
    part1 = random.choice(adjectives)
    part2 = random.choice(nouns)

    # Optionally add some digits at the end
    digits = str(random.randint(10, 999))

    # Combine parts, ensuring total length is reasonable (e.g., < 20 chars)
    username = f"{part1}{part2}{digits}"

    # Ensure username starts with a letter
    if not username[0].isalpha():
        username = random.choice(string.ascii_letters) + username[1:]

    # Keep length reasonable
    if len(username) > 18:
        username = username[:18]

    return username.lower() # Use lowercase for consistency

def generate_random_password():
    """Generates a random password (>= 8 chars, uppercase, lowercase, special, digit)."""
    special_characters = '!@?'
    # Ensure at least one of each required type
    password = [
        random.choice(string.ascii_uppercase),
        random.choice(string.ascii_lowercase),
        random.choice(special_characters),
        random.choice(string.digits)
    ]
    # Generate remaining characters to reach at least 8
    all_characters = string.ascii_letters + string.digits + '!@?'
    for _ in range(random.randint(4, 10)): # Total length >= 8
        password.append(random.choice(all_characters))
    # Shuffle to mix characters
    random.shuffle(password)
    return "".join(password)


# Constants for PIN extraction in THIS SCRIPT (not outlook_pin_extractor.py)
MAX_RETRIES = 5
RETRY_DELAY_S = 2
KEEP_XML_FOR_DEBUG = True # Set to False to remove dump.xml after extraction

def extract_pin_from_ui(device_ip2):
    """
    Dumps the UI, parses it, and searches for a 6-digit PIN code.
    Retries multiple times if the PIN is not found immediately.
    This function is intended for extracting PINs within the main ADB workflow,
    if outlook_pin_extractor.py is not used or provides a partial flow.
    Given the new approach, this function might be less critical but is kept for robustness.
    """
    pin_code = None
    xml_file_local_path = "dump.xml" # Reuse the default dump file name

    for attempt in range(MAX_RETRIES):
        logging.info(f"\n--- PIN Extraction Attempt {attempt + 1} of {MAX_RETRIES} (via ADB dump) ---")

        # Step 1: Dump UI
        dump_file = dump_ui(device_ip2, xml_file_local_path)
        if dump_file is None:
            logging.warning("Error dumping UI. Retrying...")
            time.sleep(RETRY_DELAY_S)
            continue

        # Step 2: Parse UI dump
        ui_root = parse_ui_dump(dump_file)
        if ui_root is None:
            logging.warning("Error parsing UI dump. Retrying...")
            # Clean up the local dump file if parsing failed
            if os.path.exists(xml_file_local_path) and not KEEP_XML_FOR_DEBUG:
                   os.remove(xml_file_local_path)
            time.sleep(RETRY_DELAY_S)
            continue

        logging.info(f"[Schritt 2] Suche nach einem 6-stelligen PIN-Code in der UI...")
        pin_pattern = re.compile(r'\b\d{6}\b')

        for node in ui_root.iter('node'):
            node_text = node.attrib.get('text', '')
            match = pin_pattern.search(node_text)
            if match:
                pin_code = match.group(0)
                logging.info(f"  [+] PIN-Code gefunden: {pin_code}")
                # Clean up the local dump file after successful extraction
                if os.path.exists(xml_file_local_path) and not KEEP_XML_FOR_DEBUG:
                    os.remove(xml_file_local_path)
                return pin_code

        if pin_code is None:
            logging.info(f"  -> Kein PIN-Code gefunden. Warte {RETRY_DELAY_S} Sekunden...")
            # Clean up the local dump file if PIN not found and not keeping for debug
            if os.path.exists(xml_file_local_path) and not KEEP_XML_FOR_DEBUG:
                   os.remove(xml_file_local_path)
            time.sleep(RETRY_DELAY_S)
            continue

    logging.error(f"\n!!! FEHLER: Konnte den PIN-Code nach {MAX_RETRIES} Versuchen nicht finden.")
    # Clean up the local dump file if PIN not found after all retries and not keeping for debug
    if os.path.exists(xml_file_local_path) and not KEEP_XML_FOR_DEBUG:
           os.remove(xml_file_local_path)
    return None # Explicitly return None if PIN is not found after all retries


def analyze_screenshot_for_errors(device_ip2):
    """
    Takes a screenshot, pulls it, performs OCR, and checks for specific error texts.
    Returns True if an error text is found, False otherwise.
    """
    logging.info("Taking screenshot for error analysis...")
    screenshot_filename = f"screenshot_error_{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
    device_screenshot_path = f"/sdcard/{screenshot_filename}"
    local_screenshot_path = screenshot_filename

    # Take screenshot
    screenshot_command = ["shell", "screencap", "-p", device_screenshot_path]
    screenshot_result = run_adb_command(device_ip2, screenshot_command)

    if screenshot_result is None:
        logging.error("Error taking screenshot.")
        return False

    # Pull screenshot
    pull_command = ["pull", device_screenshot_path, local_screenshot_path]
    pull_result = run_adb_command(device_ip2, pull_command)

    if pull_result is None:
        logging.error(f"Error pulling screenshot to {local_screenshot_path}.")
        # Attempt to remove the screenshot from the device even if pull failed
        run_adb_command(device_ip2, ["shell", "rm", device_screenshot_path])
        return False

    # Optional: Remove the temporary file from the device
    run_adb_command(device_ip2, ["shell", "rm", device_screenshot_path])

    logging.info(f"Screenshot saved to {local_screenshot_path}. Performing OCR...")

    try:
        # Load config to get tesseract path
        config = load_config()
        if config and 'ocr_config' in config and 'tesseract_path' in config['ocr_config']:
            pytesseract.tesseract_cmd = config['ocr_config']['tesseract_path']
            logging.info(f"Using Tesseract executable at: {pytesseract.tesseract_cmd}")
        else:
            logging.warning("Tesseract path not found in config.yaml. Ensure 'ocr_config' and 'tesseract_path' are set.")
            pass

        # Perform OCR
        img = Image.open(local_screenshot_path)
        text = pytesseract.image_to_string(img)
        logging.debug("OCR Text:")
        logging.debug(text)

        # Check for error texts (case-insensitive and strip whitespace)
        error_texts = ["We are unable to creat", "Oops!", "Error", "Something went wrong"] # Added more common error terms
        found_error = False
        for error in error_texts:
            if error.lower().strip() in text.lower().strip():
                logging.warning(f"Found error text: '{error}'")
                found_error = True
                break
        return found_error

    except FileNotFoundError:
        logging.error("Error: pytesseract or Tesseract executable not found. Make sure Tesseract is installed and in your PATH.")
        return False
    except Exception as e:
        logging.error(f"An unexpected error occurred during screenshot analysis: {e}")
        import traceback
        traceback.print_exc()
        return False

def verify_success_with_ocr(device_ip2):
    """
    Takes a screenshot, pulls it, performs OCR, and checks for specific success texts.
    Returns True if a success text is found, False otherwise.
    """
    logging.info("Taking screenshot for success verification with OCR...")
    screenshot_filename = f"screenshot_success_{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
    device_screenshot_path = f"/sdcard/{screenshot_filename}"
    local_screenshot_path = screenshot_filename

    # Take screenshot
    screenshot_command = ["shell", "screencap", "-p", device_screenshot_path]
    screenshot_result = run_adb_command(device_ip2, screenshot_command)

    if screenshot_result is None:
        logging.error("Error taking screenshot for success verification.")
        return False

    # Pull screenshot
    pull_command = ["pull", device_screenshot_path, local_screenshot_path]
    pull_result = run_adb_command(device_ip2, pull_command)

    if pull_result is None:
        logging.error(f"Error pulling screenshot to {local_screenshot_path} for success verification.")
        run_adb_command(device_ip2, ["shell", "rm", device_screenshot_path])
        return False

    # Optional: Remove the temporary file from the device
    run_adb_command(device_ip2, ["shell", "rm", device_screenshot_path])

    logging.info(f"Screenshot saved to {local_screenshot_path}. Performing OCR for success verification...")

    try:
        config = load_config()
        if config and 'ocr_config' in config and 'tesseract_path' in config['ocr_config']:
            pytesseract.tesseract_cmd = config['ocr_config']['tesseract_path']
            logging.info(f"Using Tesseract executable at: {pytesseract.tesseract_cmd}")
        else:
            logging.warning("Tesseract path not found in config.yaml. Ensure 'ocr_config' and 'tesseract_path' are set.")
            pass

        img = Image.open(local_screenshot_path)
        text = pytesseract.image_to_string(img)
        logging.debug("OCR Text for Success Verification:")
        logging.debug(text)

        # Define success keywords
        # Consider variations and common phrases like "Welcome", "Account created", "You're all set"
        success_keywords = ["Success", "erfolgreich", "completed", "Account Created", "You're all set", "Welcome", "Ready to play"]
        found_success = False
        for keyword in success_keywords:
            if keyword.lower().strip() in text.lower().strip():
                logging.info(f"Found success keyword via OCR: '{keyword}'")
                found_success = True
                break
        
        if not found_success:
            logging.warning("No success keywords found via OCR.")

        # Optionally remove the local screenshot file after processing
        # os.remove(local_screenshot_path)
        # logging.info(f"Removed local screenshot file: {local_screenshot_path}")

        return found_success

    except FileNotFoundError:
        logging.error("Error: pytesseract or Tesseract executable not found. Make sure Tesseract is installed and in your PATH.")
        return False
    except Exception as e:
        logging.error(f"An unexpected error occurred during OCR success verification: {e}")
        import traceback
        traceback.print_exc()
        return False


def send_ptc_data_to_api(config, username, password, email, worker_status):
    """Sends PTC account data to the specified API endpoint."""
    if not config or 'api_config' not in config or 'ptc_webhook_url' not in config['api_config']:
        logging.error("Error: API configuration not found in config.yaml")
        return

    url = config['api_config']['ptc_webhook_url']

    data = {
        "ptc_name": username,
        "ptc_pass": password,
        "ptc_mail": email,
        "worker_name": "AdbUiHelperWorker", # Use a specific worker name
        "worker_status": worker_status
    }

    try:
        headers = {'Content-Type': 'application/json; charset=UTF-8'}
        response = requests.post(url, json=data, headers=headers, timeout=10)

        if response.status_code == 200:
            logging.info("API: Data sent successfully")
        else:
            logging.error(f"API: Error sending data: Status code {response.status_code}. Response: {response.text}")
        response.close()
    except Exception as e:
        logging.error(f"API: Error sending data: {e}")

def perform_ptc_workflow(device_ip2, email, username, ptc_password):
    """Performs the sequence of actions for the PTC workflow."""
    # Add the new sequence of actions (Year, Month, Day)
    logging.info("Performing requested sequence of actions (Year, Month, Day)...")
    time.sleep(5) # 5s pause

    # Send two Tab key presses
    logging.info("Sending two Tab key presses...")
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "61"])
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "61"])
    time.sleep(1) # Short pause between key events

    # Send "ger" text
    logging.info("Typing 'ger'...")
    run_adb_command(device_ip2, ["shell", "input", "text", "ger"])
    time.sleep(1) # Short pause after typing

    # Send Tab key press
    logging.info("Sending Tab key press...")
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "61"])
    time.sleep(1) # Short pause after tab

    # Type random year (18-50 years ago)
    current_year = datetime.date.today().year
    random_age = random.randint(18, 50)
    birth_year = current_year - random_age
    logging.info(f"Typing year: {birth_year} (random age: {random_age})")
    run_adb_command(device_ip2, ["shell", "input", "text", str(birth_year)])
    time.sleep(1) # Short pause after typing year

    # Send Tab key press
    logging.info("Sending Tab key press...")
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "61"])
    time.sleep(1) # Short pause after tab

    # Type month "ja"
    logging.info("Typing month 'ja'...")
    run_adb_command(device_ip2, ["shell", "input", "text", "ja"])
    time.sleep(1) # Short pause after typing month

    # Send Tab key press
    logging.info("Sending Tab key press...")
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "61"])
    time.sleep(1) # Short pause after tab

    # Type day "15"
    logging.info("Typing day '15'...")
    run_adb_command(device_ip2, ["shell", "input", "text", "15"])
    time.sleep(1) # Short pause after typing day

    # Send Tab key press
    logging.info("Sending Tab key press...")
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "61"])
    time.sleep(1) # Short pause after tab

    # Send Enter key press
    logging.info("Sending Enter key press...")
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "66"])

    time.sleep(5) # Final 5s pause
    logging.info("Sequence of actions completed.")

    # Add the next sequence of actions (Email, Username, Password)
    logging.info("Performing next sequence of actions (Email, Username, Password)...")
    time.sleep(4) # 4s pause

    # Send two Tab key presses
    logging.info("Sending two Tab key presses...")
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "61"])
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "61"])
    time.sleep(1) # Short pause

    # Send Enter key press
    logging.info("Sending Enter key press...")
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "66"])
    time.sleep(5) # 5s pause

    # Send two Tab key presses
    logging.info("Sending two Tab key presses...")
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "61"])
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "61"])
    time.sleep(1) # Short pause

    # Type email
    logging.info(f"Typing email: {email}")
    run_adb_command(device_ip2, ["shell", "input", "text", email])
    time.sleep(1) # Short pause

    # Send Tab key press
    logging.info("Sending Tab key press...")
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "61"])
    time.sleep(1) # Short pause

    # Type email again (assuming confirmation or second field)
    logging.info(f"Typing email again: {email}")
    run_adb_command(device_ip2, ["shell", "input", "text", email])
    time.sleep(1) # Short pause

    # Send two Tab key presses
    logging.info("Sending two Tab key presses...")
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "61"])
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "61"])
    time.sleep(1) # Short pause

    # Send Enter key press
    logging.info("Sending Enter key press...")
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "66"])
    time.sleep(15) # 10s pause

    # Check for errors after the previous steps
    if analyze_screenshot_for_errors(device_ip2):
        logging.warning("Error detected in screenshot. Restarting workflow...")
        return # Exit the current perform_ptc_workflow call

    # Send three Tab key presses
    logging.info("Sending three Tab key presses...")
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "61"])
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "61"])
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "61"])
    time.sleep(1) # Short pause

    # Send Enter key press
    logging.info("Sending Enter key press...")
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "66"])
    time.sleep(5) # 5s pause

    # Send Enter key press
    logging.info("Sending Enter key press...")
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "66"])
    time.sleep(1) # Short pause

    # Send two Tab key presses
    logging.info("Sending two Tab key presses...")
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "61"])
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "61"])
    time.sleep(1) # Short pause

    # Send Enter key press
    logging.info("Sending Enter key press...")
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "66"])
    time.sleep(5) # 5s pause

    # Send Tab key press
    logging.info("Sending Tab key press...")
    result = run_adb_command(device_ip2, ["shell", "input", "keyevent", "61"])
    if result is None:
        logging.error("Error sending Tab key press before username input.")
        # Optionally, add more robust error handling or exit here
    time.sleep(1) # Short pause

    # Type username
    logging.info(f"Typing username: {username}")
    run_adb_command(device_ip2, ["shell", "input", "text", username])
    time.sleep(1) # Short pause

    # Send Tab key press
    logging.info("Sending Tab key press...")
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "61"])
    time.sleep(1) # Short pause

    # Type password character by character
    logging.info(f"Attempting to type PTC password: {ptc_password}")
    run_adb_command(device_ip2, ["shell", "input", "text", ptc_password])
    logging.info(f"Finished typing PTC password.")
    time.sleep(1) # Short pause after typing password

    # Send two Tab key presses
    logging.info("Sending two Tab key presses...")
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "61"])
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "61"])
    time.sleep(1) # Short pause

    # Send Enter key press
    logging.info("Sending Enter key press...")
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "66"])
    time.sleep(10) # 10s pause

    # Add extra steps requested by user after password entry
    logging.info("Sending two Tab key presses (extra steps)...")
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "61"])
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "61"])
    time.sleep(2) # 2s pause
    logging.info("Sending Enter key press (extra steps)...")
    run_adb_command(device_ip2, ["shell", "input", "keyevent", "66"])
    time.sleep(7) # 7s pause

def get_pin_from_external_script(email, password, script_path="outlook_pin.py"):
    """
    Calls the external script outlook_pin.py to get the PIN.
    Args:
        email (str): The email address to pass to the external script.
        password (str): The password to pass to the external script.
        script_path (str): The path to the outlook_pin.py script.
    Returns:
        str or None: The extracted PIN code if successful, None otherwise.
    """
    logging.info(f"\n--- Calling external PIN extraction script: {script_path} ---")
    logging.info(f"Passing email: {email} and password (hidden) to external script.")
    try:
        command = ["python3", script_path, "--email", email, "--password", password]

        result = subprocess.run(command, capture_output=True, text=True, check=True)

        pin_pattern = re.compile(r'ENDERGEBNIS: Extrahierter PIN-Code: (\d{6})')
        match = pin_pattern.search(result.stdout)

        if match:
            pin_code = match.group(1)
            logging.info(f"✅ Successfully extracted PIN from external script: {pin_code}")
            return pin_code
        else:
            logging.error(f"❌ Failed to find PIN in external script's output.")
            logging.debug("External script stdout:\n" + result.stdout)
            logging.debug("External script stderr:\n" + result.stderr)
            return None

    except FileNotFoundError:
        logging.error(f"Error: External script '{script_path}' not found. Make sure it's in your PATH or current directory.")
        return None
    except subprocess.CalledProcessError as e:
        logging.error(f"Error executing external script '{script_path}':")
        logging.error(f"Return code: {e.returncode}")
        logging.error(f"Stdout:\n" + e.stdout)
        logging.error(f"Stderr:\n" + e.stderr)
        return None
    except Exception as e:
        logging.error(f"An unexpected error occurred while calling the external script: {e}")
        traceback.print_exc()
        return None


if __name__ == "__main__":
    while True: # Start of the infinite loop
        config = load_config()
        # Changed 'device_ip' to 'device_ip2' consistently
        if config and 'adb_config' in config and 'device_ip2' in config['adb_config']:
            device_ip2 = config['adb_config']['device_ip2']
            logging.info(f"Using device IP: {device_ip2}")

            # Get unused email and password from email.json
            email, email_password = get_unused_email_and_password() # Get email and password from file

            if email is None or email_password is None:
                logging.warning("Could not retrieve unused email or password. Exiting loop.")
                time.sleep(60) # Wait before retrying if no email is found
                continue # Continue to the next iteration if no email is found

            logging.info(f"Using email: {email}")
            # email_password is now explicitly used for the external script call

            # Generate random username and password for PTC
            username = generate_random_username()
            ptc_password = generate_random_password() # Generate password using the function
            logging.info(f"Generated username for PTC: {username}")
            logging.info(f"Generated password for PTC: {ptc_password}")

            # Initial VPN app start and connect tap
            logging.info("Force stopping ProtonVPN app before initial connection...")
            run_adb_command(device_ip2, ["shell", "am", "force-stop", "ch.protonvpn.android"])
            time.sleep(1) # Give it a moment to stop
            logging.info("ProtonVPN app force stopped.")
            logging.info("Starting ProtonVPN app for initial connection...")
            run_adb_command(device_ip2, ["shell", "am", "start", "-n", "ch.protonvpn.android/.RoutingActivity"])
            time.sleep(7) # Wait for app to open
            logging.info("ProtonVPN app started.")
            run_adb_command(device_ip2, ["shell", "input", "tap", "640", "550"])
            time.sleep(5) # Wait for connection
            logging.info("VPN connect tap sent.")

            # Step 1: Clear Chrome cache
            clear_chrome_cache(device_ip2)
            time.sleep(5) # Add delay after clearing cache

            # Step 2: Start Chrome with the Pokemon signup URL directly
            initial_url = "https://join.pokemon.com/"

            logging.info(f"Attempting to open browser with URL: {initial_url}...")
            command = ["shell", f"am start -a android.intent.action.VIEW -d \"{initial_url}\" com.android.chrome"]
            run_adb_command(device_ip2, command)
            time.sleep(15) # Add delay for the page to load

            # Step 3: Handle initial prompts (cookie banner, privacy prompt)
            dump_file = dump_ui(device_ip2)

            if dump_file:
                ui_root = parse_ui_dump(dump_file)

                # Check for "Accept" button (cookie banner)
                accept_button_coords = find_element(ui_root, "text", "Accept")
                if accept_button_coords:
                    logging.info("Found 'Accept' button (cookie banner). Tapping.")
                    tap(device_ip2, accept_button_coords['x'], accept_button_coords['y'])
                    time.sleep(2) # Give time after tapping Accept

                # Check for "Use without an account" first
                use_without_account_coords = find_element(ui_root, "text", "Use without an account")
                if use_without_account_coords:
                    logging.info("Found 'Use without an account'. Tapping.")
                    tap(device_ip2, use_without_account_coords['x'], use_without_account_coords['y'])
                    time.sleep(2) # Give time after tap
                else:
                    # If "Use without an account" is not found, check for "No thanks" (privacy prompt)
                    no_thanks_coords = find_element(ui_root, "text", "No thanks")
                    if no_thanks_coords:
                        logging.info("Privacy prompt found. Clicking 'No thanks'.")
                        tap(device_ip2, no_thanks_coords['x'], no_thanks_coords['y'])
                        time.sleep(2) # Give time after tapping "No thanks"
                    else:
                        logging.info("Neither 'Use without an account' nor privacy prompt 'No thanks' found.")

            # Step 4: Perform the PTC workflow (starts directly now)
            perform_ptc_workflow(device_ip2, email, username, ptc_password)
            time.sleep(5) # Add a pause after the PTC workflow

            # Step 5: Abrufen des PINs über das separate Skript (outlook_pin_extractor.py)
            logging.info("\n--- Abrufen des PINs vom externen Skript ---")
            pin_code = get_pin_from_external_script(email, email_password, "outlook_pin.py")

            if pin_code:
                logging.info(f"Extracted PIN: {pin_code}")
                # --- New sequence after PIN extraction ---
                logging.info("Performing sequence after PIN extraction...")
                # Assuming these clicks are needed to navigate back to the PIN input field in the Pokemon app
                tap(device_ip2, 552, 50) # Example coordinate, adjust as needed
                time.sleep(5)
                tap(device_ip2, 390, 461) # Example coordinate, adjust as needed
                time.sleep(2)
                # PIN typing and Enter
                logging.info(f"Entering extracted PIN: {pin_code}")
                run_adb_command(device_ip2, ["shell", "input", "text", pin_code])
                time.sleep(2) # Give time after typing PIN
                logging.info("Sending Enter key after PIN...")
                run_adb_command(device_ip2, ["shell", "input", "keyevent", "66"])
                time.sleep(10) # 10s pause after entering PIN

                tap(device_ip2, 493, 343) # Example coordinate, adjust as needed
                time.sleep(2) # Short pause after tapping before select all

                # Select all (Ctrl+A)
                logging.info("Sending Select All (Ctrl+A)...")
                run_adb_command(device_ip2, ["shell", "input", "keyevent", "--longpress", "113", "29"]) # KEYCODE_CTRL_LEFT, KEYCODE_A
                time.sleep(1) # Short pause after select all

                # Copy (Ctrl+C)
                logging.info("Sending Copy (Ctrl+C)...")
                run_adb_command(device_ip2, ["shell", "input", "keyevent", "--longpress", "113", "31"]) # KEYCODE_CTRL_LEFT, KEYCODE_C
                time.sleep(1) # Short pause after copy

                # --- Verify "Success" message using OCR ---
                logging.info("Verifying 'Success' message using OCR...")
                success_found = verify_success_with_ocr(device_ip2)

                if success_found:
                    logging.info("Verification of 'Success' message completed successfully.")
                    # Send data to API
                    logging.info("Sending account data to API...")
                    send_ptc_data_to_api(config, username, ptc_password, email, "success")
                else:
                    logging.warning("Verification of 'Success' message failed via OCR. Sending 'failed_pin_verification' status.")
                    send_ptc_data_to_api(config, username, ptc_password, email, "failed_pin_verification") # Beispielstatus bei Fehlschlag

                # --- End of new sequence ---
            else:
                logging.warning("PIN could not be retrieved from external script. Sending 'failed_pin_retrieval' status.")
                send_ptc_data_to_api(config, username, ptc_password, email, "failed_pin_retrieval") # Beispielstatus bei Fehlschlag

            logging.info("\nOverall workflow completed.")

        else:
            logging.error("ADB device IP not found in config.yaml. Please ensure 'adb_config' and 'device_ip2' are set.")

        # Add a delay before the next iteration
        logging.info("Waiting 2 seconds before next run...")
        time.sleep(2) # Wait for 2 seconds before restarting the loop
