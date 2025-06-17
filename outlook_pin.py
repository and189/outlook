import pychrome
import time
import traceback
import json
import argparse
import subprocess
import xml.etree.ElementTree as ET
import re
import os
import yaml # Importiere die PyYAML-Bibliothek

# --- KONFIGURATION LADEN ---
def load_config(config_path='config.yaml'):
    """Lädt die Konfiguration aus einer YAML-Datei."""
    try:
        with open(config_path, 'r') as file:
            config = yaml.safe_load(file)
        return config
    except FileNotFoundError:
        print(f"FEHLER: Die Konfigurationsdatei '{config_path}' wurde nicht gefunden.")
        print("Bitte stelle sicher, dass 'config.yaml' existiert und die Geräte-IP enthält.")
        exit(1)
    except yaml.YAMLError as e:
        print(f"FEHLER beim Lesen der Konfigurationsdatei: {e}")
        exit(1)

config = load_config()
# Zugriff auf die device_ip innerhalb der adb_config Sektion
DEVICE_IP = config.get('adb_config', {}).get('device_ip')

if not DEVICE_IP:
    print("FEHLER: 'device_ip' nicht unter 'adb_config' in 'config.yaml' gefunden.")
    print("Bitte stelle sicher, dass deine 'config.yaml' einen Eintrag wie 'adb_config: { device_ip: \"192.168.1.100\" }' enthält.")
    exit(1)

# --- ADB PORT FORWARDING ---
# Dieser Befehl muss ausgeführt werden, BEVOR das Skript versucht, eine Verbindung herzustellen.
# Er leitet den lokalen TCP-Port 9222 an den abstrakten Socket 'chrome_devtools_remote' auf dem Gerät weiter.
print("Einrichtung der ADB Port-Weiterleitung für Chrome DevTools...")
try:
    # Verwende die aus der Konfigurationsdatei gelesene Geräte-IP
    subprocess.run(f"adb -s {DEVICE_IP} forward tcp:9222 localabstract:chrome_devtools_remote", shell=True, check=True)
    print("ADB Port-Weiterleitung erfolgreich eingerichtet.")
except subprocess.CalledProcessError as e:
    print(f"FEHLER: ADB Port-Weiterleitung fehlgeschlagen: {e}")
    print("Stellen Sie sicher, dass ADB installiert ist, Ihr Gerät unter der angegebenen IP erreichbar und korrekt verbunden sowie debug-fähig ist.")
    exit(1) # Skript beenden, wenn die Portweiterleitung fehlschlägt

DEBUGGING_URL = 'http://127.0.0.1:9222'
MAX_PIN_RETRIES = 5
RETRY_DELAY_S = 3
KEEP_XML_FOR_DEBUG = True

# --- HELFERFUNKTIONEN ---

def find_and_click(tab, selector, element_name, timeout=5):
    print(f"\nSuche '{element_name}' zum Klicken (CSS): '{selector}'")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            js_function = 'function() { this.scrollIntoView({block: "center", inline: "center"}); this.click(); }'
            find_script = f"document.querySelector('{selector}')"
            result = tab.call_method("Runtime.evaluate", expression=find_script, returnByValue=False, awaitPromise=True)
            if 'result' in result and result['result'].get('objectId'):
                element_object_id = result['result']['objectId']
                print(f"'{element_name}' gefunden. Führe Klick aus...")
                tab.call_method("Runtime.callFunctionOn", functionDeclaration=js_function, objectId=element_object_id)
                print(f"-> Klick auf '{element_name}' erfolgreich.")
                return True
            time.sleep(0.5)
        except pychrome.exceptions.CallMethodException:
            pass
    print(f"FEHLER: '{element_name}' nicht gefunden nach {timeout} Sekunden.")
    return False

def find_and_click_by_xpath(tab, xpath_expression, element_name, timeout=5):
    """
    Findet ein Element anhand eines XPath-Ausdrucks und klickt darauf.
    """
    print(f"\nSuche '{element_name}' zum Klicken (XPath): '{xpath_expression}'")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            safe_xpath = json.dumps(xpath_expression)

            js_find_script = f"""
                document.evaluate(
                    {safe_xpath},
                    document,
                    null,
                    XPathResult.FIRST_ORDERED_NODE_TYPE,
                    null
                ).singleNodeValue
            """
            result = tab.call_method("Runtime.evaluate", expression=js_find_script, returnByValue=False)
            if 'result' in result and result['result'].get('objectId'):
                element_object_id = result['result']['objectId']
                print(f"'{element_name}' gefunden. Führe Klick aus...")
                js_click_function = 'function() { this.click(); }'
                tab.call_method("Runtime.callFunctionOn", functionDeclaration=js_click_function, objectId=element_object_id)
                print(f"-> Klick auf '{element_name}' erfolgreich.")
                return True
            time.sleep(0.5)
        except pychrome.exceptions.CallMethodException:
            pass
    print(f"FEHLER: '{element_name}' nicht gefunden nach {timeout} Sekunden.")
    return False

def find_and_click_by_text(tab, text_to_find, element_name):
    print(f"\nPrüfe optional, ob '{element_name}' vorhanden ist (Text: '{text_to_find}')...")
    try:
        xpath_expression = f"//*[contains(text(), '{text_to_find}')]"
        js_find_script = f'document.evaluate("{xpath_expression}", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue'
        result = tab.call_method("Runtime.evaluate", expression=js_find_script, returnByValue=False)
        if 'result' in result and result['result'].get('objectId'):
            element_object_id = result['result']['objectId']
            print(f"-> '{element_name}' gefunden. Klicke darauf...")
            js_click_function = 'function() { this.click(); }'
            tab.call_method("Runtime.callFunctionOn", functionDeclaration=js_click_function, objectId=element_object_id)
            print(f"-> Klick auf '{element_name}' erfolgreich.")
            return True
        else:
            print(f"-> '{element_name}' nicht gefunden, fahre fort.")
            return False
    except pychrome.exceptions.CallMethodException:
        print(f"-> Fehler bei der optionalen Prüfung auf '{element_name}', fahre fort.")
        return False

def find_and_get_href(tab, selector, element_name):
    print(f"\nLese URL von '{element_name}': '{selector}'")
    get_href_script = f"document.querySelector('{selector}').href"
    try:
        result = tab.call_method("Runtime.evaluate", expression=get_href_script, returnByValue=True)
        if 'result' in result and result['result'].get('value'):
            url = result['result']['value']
            print(f"-> URL gefunden: {url}")
            return url
        else:
            print(f"FEHLER: Konnte keine URL für '{element_name}' finden.")
            return None
    except pychrome.exceptions.CallMethodException as e:
        print(f"FEHLER beim Auslesen der URL von '{element_name}': {e}")
        return None

def find_and_type(tab, selector, text, element_name):
    print(f"\nSuche '{element_name}' zum Tippen: '{selector}'")
    if not find_and_click(tab, selector, f"{element_name} (Fokus)"): return False
    print(f"Tippe Text in '{element_name}'...")
    try:
        for char in text:
            tab.call_method("Input.dispatchKeyEvent", type="char", text=char)
            time.sleep(0.05)
        print(f"-> Eingabe für '{element_name}' abgeschlossen.")
        return True
    except pychrome.exceptions.CallMethodException as e:
        print(f"FEHLER beim Tippen in '{element_name}': {e}")
        return False

def press_key(tab, key_name, count=1):
    print(f"\nDrücke Taste '{key_name}' {count}-mal...")
    key_map = {'Enter': {'key': 'Enter', 'keyCode': 13, 'windowsVirtualKeyCode': 13}, 'Tab': {'key': 'Tab', 'keyCode': 9, 'windowsVirtualKeyCode': 9}}
    if key_name not in key_map: return False
    key_params = key_map[key_name]
    try:
        for _ in range(count):
            tab.call_method("Input.dispatchKeyEvent", type="keyDown", **key_params)
            time.sleep(0.05)
            tab.call_method("Input.dispatchKeyEvent", type="keyUp", **key_params)
            time.sleep(0.1)
        print(f"-> Taste '{key_name}' erfolgreich gedrückt.")
        return True
    except pychrome.exceptions.CallMethodException as e:
        print(f"FEHLER beim Drücken der Taste '{key_name}': {e}")
        return False


# --- HELFERFUNKTIONEN ---

def run_adb_command(command):
    # Ensure DEVICE_IP is accessible here, it's a global variable set at the top
    if not DEVICE_IP:
        print("FEHLER: DEVICE_IP ist nicht gesetzt. ADB-Befehl kann nicht ausgeführt werden.")
        return None

    # Construct the full command including -s DEVICE_IP
    full_command = f"adb -s {DEVICE_IP} {command}"
    print(f"    > Führe ADB-Befehl aus: {full_command}")
    try:
        result = subprocess.run(full_command, shell=True, capture_output=True, text=True, check=True, encoding='utf-8')
        # Check for specific ADB errors in stderr even if check=True is used
        # Sometimes ADB outputs warnings to stderr but still exits with 0
        if "more than one device/emulator" in result.stderr.lower():
            print(f"!!! ADB-Fehler: Es sind zu viele Geräte/Emulatoren verbunden. Stellen Sie sicher, dass nur das Zielgerät ({DEVICE_IP}) verbunden ist oder die Geräte-ID eindeutig ist.")
            return None
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"!!! FEHLER bei der Ausführung von ADB: {e.stderr}")
        return None
    except FileNotFoundError:
        print("!!! FEHLER: ADB-Befehl nicht gefunden. Stellen Sie sicher, dass ADB installiert ist und sich in Ihrem PATH befindet.")
        return None


def extract_pin_from_screen():
    print("\n--- STARTE PIN-EXTRAKTION (ADB) ---")
    xml_file_device_path = "/sdcard/window_dump.xml"
    xml_file_local_path = "window_dump.xml"
    pin_code = None
    try:
        for attempt in range(MAX_PIN_RETRIES):
            print(f"\n--- Versuch {attempt + 1} von {MAX_PIN_RETRIES} ---")
            if run_adb_command(f"shell uiautomator dump {xml_file_device_path}") is None or \
               run_adb_command(f"pull {xml_file_device_path} {xml_file_local_path}") is None:
                time.sleep(RETRY_DELAY_S)
                continue

            print("[Schritt 2] Suche nach einem 6-stelligen PIN-Code...")
            try:
                tree = ET.parse(xml_file_local_path)
                root = tree.getroot()
                pin_pattern = re.compile(r'\b\d{6}\b')
                for node in root.iter('node'):
                    for attr in ['text', 'content-desc']:
                        node_text = node.attrib.get(attr, '')
                        match = pin_pattern.search(node_text)
                        if match:
                            pin_code = match.group(0)
                            print(f"   [+] PIN-Code gefunden: {pin_code}")
                            return pin_code
                print(f"   -> Kein PIN-Code gefunden. Warte {RETRY_DELAY_S} Sekunden...")
                time.sleep(RETRY_DELAY_S)
            except ET.ParseError as e:
                print(f"!!! FEHLER: Konnte XML nicht lesen. {e}")
                time.sleep(RETRY_DELAY_S)
        print(f"\n!!! Konnte PIN nach {MAX_PIN_RETRIES} Versuchen nicht finden.")
        return None
    finally:
        if os.path.exists(xml_file_local_path) and not KEEP_XML_FOR_DEBUG:
            os.remove(xml_file_local_path)


# --- HAUPTSKRIPT ---
def perform_actions(email, password): # Funktion nimmt nun E-Mail und Passwort entgegen
    browser = None
    tab = None
    try:
        print("Verbinde mit dem via ADB weitergeleiteten Browser...")
        browser = pychrome.Browser(url=DEBUGGING_URL)
        tab = browser.list_tab()[0]
        tab.start()
        print("Erfolgreich mit dem aktiven Tab verbunden.")
        time.sleep(2)

        # Zuerst zur Start-URL navigieren, auf der sich der "Haupt-Button" befindet
        initial_landing_url = "https://www.microsoft.com/en-us/microsoft-365/outlook/email-and-calendar-software-microsoft-outlook?deeplink=%2fowa%2f%3frealm%3doutlook.com&sdf=0"
        print(f"Navigiere zur Startseite mit dem Haupt-Button: {initial_landing_url}")
        tab.call_method("Page.navigate", url=initial_landing_url, _timeout=30)
        print("Warte 10 Sekunden, damit die Startseite vollständig laden kann...")
        time.sleep(10)

        # Schritt 1: Link vom Haupt-Button lesen und dann zur Login-Seite navigieren
        link_selector = "#action-oc5b26"
        target_url = find_and_get_href(tab, link_selector, "Haupt-Button Link")
        if not target_url:
            raise Exception("Konnte die Ziel-URL des Haupt-Buttons nicht finden.")

        print(f"Navigiere zur extrahierten Login-URL: {target_url}")
        tab.call_method("Page.navigate", url=target_url, _timeout=30)
        print("Warte 10 Sekunden, damit die Login-Seite vollständig laden kann...")
        time.sleep(10)

        # Schritt 2: E-Mail eingeben und auf "Weiter" klicken
        email_selector = 'input[type="email"]'
        if not find_and_type(tab, email_selector, email, "E-Mail-Feld"): # Verwende den übergebenen E-Mail-Parameter
            raise Exception("E-Mail-Eingabe fehlgeschlagen.")
        if not find_and_click(tab, "#idSIButton9", "Weiter-Button nach E-Mail"):
            raise Exception("Klick auf 'Weiter' nach E-Mail fehlgeschlagen.")
        print("Warte 3 Sekunden, damit die nächste Seite laden kann...")
        time.sleep(3)

        # Optionaler Schritt: Auf "Use your password" klicken
        find_and_click_by_text(tab, "Use your password", "Passwort-Option Button")

        # Schritt 3: Passwort eingeben
        print("\nWarte 5 Sekunden auf das Passwortfeld...")
        time.sleep(5)
        password_selector = 'input[type="password"]'
        if not find_and_type(tab, password_selector, password, "Passwort-Feld"): # Verwende den übergebenen Passwort-Parameter
            raise Exception("Passwort-Eingabe fehlgeschlagen.")

        # Klick auf den Anmelden-Button per XPath
        signin_button_xpath = '//*[@id="view"]/div/div[5]/button'
        if not find_and_click_by_xpath(tab, signin_button_xpath, "Anmelden-Button (per XPath)"):
             raise Exception("Klick auf den Anmelden-Button (per XPath) ist fehlgeschlagen.")
        print("Warte 5 Sekunden vor dem ersten Skip-Versuch...")
        time.sleep(5)
        # HIER WURDE DER FEHLER BEHOBEN
        if not find_and_click_by_xpath(tab, '//*[@id="iShowSkip"]', "Skip-Button (erster Versuch)"):
             print("Erster Skip-Versuch fehlgeschlagen, warte 5 Sekunden vor dem zweiten Versuch...")
             time.sleep(5)
             find_and_click_by_xpath(tab, '//*[@id="iShowSkip"]', "Skip-Button (zweiter Versuch)")
        time.sleep(5)
        # HIER WURDE DER FEHLER BEHOBEN (wiederholt sich, daher beide Instanzen korrigiert)
        if not find_and_click_by_xpath(tab, '//*[@id="iShowSkip"]', "Skip-Button (erster Versuch)"):
             print("Erster Skip-Versuch fehlgeschlagen, warte 5 Sekunden vor dem zweiten Versuch...")
             time.sleep(5)
             find_and_click_by_xpath(tab, '//*[@id="iShowSkip"]', "Skip-Button (zweiter Versuch)")

        print("Warte 10 Sekunden auf die 'Angemeldet bleiben?'-Seite...")
        time.sleep(10)

        # Schritt 4: Aktionen auf der "Angemeldet bleiben?"-Seite
        target_button_xpath = '//*[@id="view"]/div/div[5]/button[2]'
        print(f"Warte 5 Sekunden vor dem ersten Versuch, '{target_button_xpath}' zu klicken...")
        time.sleep(5)
        if not find_and_click_by_xpath(tab, target_button_xpath, "Spezifischer Button nach Login (erster Versuch)"):
             print(f"Erster Versuch, '{target_button_xpath}' zu klicken, fehlgeschlagen. Warte 5 Sekunden vor dem zweiten Versuch...")
             time.sleep(5)
             find_and_click_by_xpath(tab, target_button_xpath, "Spezifischer Button nach Login (zweiter Versuch)")

        print("\nLogin-Flow scheint erfolgreich. Warte auf die finale Seite...")
        time.sleep(20)

        # Schritt 5: Finaler Klick
        find_and_click(tab, "#id__316", "Finaler Button nach Login")

        # Send ADB click
        run_adb_command("shell input tap 330 585")

        print("\n✅ Skript erfolgreich bis zum Ende durchgelaufen!")
        return True

    except Exception as e:
        print(f"\n❌ Ein Fehler hat den Ablauf unterbrochen: {e}")
        # traceback.print_exc()
        return False
    finally:
        if tab:
            tab.stop()
            print("\nVerbindung zum Tab getrennt.")

        # Start PIN extraction after login attempt
        print("\nStarte PIN-Extraktion.")
        extracted_pin = extract_pin_from_screen()

        if extracted_pin:
            print(f"\n✅ ENDERGEBNIS: Extrahierter PIN-Code: {extracted_pin}")
        else:
            print("\n❌ ENDERGEBNIS: Es konnte kein PIN extrahiert werden.")

        print("Skript beendet.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Führt einen Login-Flow mit E-Mail und Passwort aus.")
    parser.add_argument("-e", "--email", required=True, help="Die E-Mail-Adresse für den Login.")
    parser.add_argument("-p", "--password", required=True, help="Das Passwort für den Login.")
    args = parser.parse_args()

    perform_actions(args.email, args.password)
