import os
import time
import base64
import requests
import threading
import re
import firebase_admin
from firebase_admin import credentials, db
from django.core.management.base import BaseCommand
from django.utils import timezone
import pytz
from Main.models import Vehicle
import sys
import os
import threading
from pathlib import Path

# Calculate project root dynamically using __file__
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../../../"))

# Add the extractor folder to the Python path FIRST before importing from it
extractor_path = os.path.join(PROJECT_ROOT, "license_extractor")
if extractor_path not in sys.path:
    sys.path.append(extractor_path)

from license_plate_11 import extract_license_plate as custom_extract_license_plate
from heyroute_ocr import extract_plate_with_heyroute

# Configuration Toggle
USE_HEYROUTE_PRIMARY = True

request_lock = threading.Lock()
active_heyroute_requests = 0

CLEANUP_INTERVAL_SECONDS = 5
ABANDONED_RECORD_AGE_SECONDS = 60

def clean_plate_text(raw_text: str) -> str:
    clean_text = re.sub(r'[^A-Z0-9]', '', raw_text.upper())
    bh_match = re.search(r'\d{2}BH\d{4}[A-Z]{1,2}', clean_text)
    if bh_match: return bh_match.group(0)
    std_match = re.search(r'[A-Z]{2}\d{1,2}[A-Z]{1,3}\d{4}', clean_text)
    if std_match: return std_match.group(0)
    return clean_text[:10]

def online_extract_license_plate(image_path: str) -> str:
    try:
        api_key = os.getenv("OCR_SPACE_API_KEY", "helloworld")
        with open(image_path, 'rb') as f:
            image_bytes = f.read()
        response = requests.post(
            "https://api.ocr.space/parse/image",
            files={"file": ("plate.jpg", image_bytes, "image/jpeg")},
            data={"apikey": api_key, "language": "eng", "OCREngine": 2},
            timeout=15
        )
        result = response.json()
        if result.get("ParsedResults"):
            detected_text = result["ParsedResults"][0].get("ParsedText", "")
            return clean_plate_text(detected_text.replace("\r", "").replace("\n", "").strip())
        return ""
    except Exception as e:
        print(f"OCR Error: {e}")
        return ""

def verify_vehicle(plate_number: str) -> dict:
    result = {
        "status": "complete",
        "plate_number": plate_number,
        "name": "Unknown",
        "role": "Unknown",
        "is_valid": False
    }
    
    if not plate_number or len(plate_number) < 4:
        result["status"] = "review"
        return result
        
    try:
        vehicle = Vehicle.objects.get(plate_number=plate_number)
        result["name"] = vehicle.owner_name
        result["role"] = vehicle.role
        
        # All roles follow Asia/Kolkata date
        kolkata = pytz.timezone('Asia/Kolkata')
        today = timezone.now().astimezone(kolkata).date()
        
        if vehicle.start_date <= today <= vehicle.expiry_date:
            result["is_valid"] = True
        else:
            result["is_valid"] = False
            
    except Vehicle.DoesNotExist:
        result["is_valid"] = False
        
    return result

class Command(BaseCommand):
    help = 'Runs the Firebase scan worker matching Android contract'

    def handle(self, *args, **options):
        default_cred = os.path.join(PROJECT_ROOT, "keys", "serviceAccountKey.json")
        cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", default_cred)
        db_url = os.getenv("FIREBASE_DATABASE_URL", "https://intelli-gate-default-rtdb.asia-southeast1.firebasedatabase.app/")

        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred, {"databaseURL": db_url})
            
        threading.Thread(target=self.cleanup_worker, daemon=True).start()
        
        db.reference("scan_images").listen(self.listen_images)
        db.reference("scan_plates").listen(self.listen_plates)
        
        self.stdout.write(self.style.SUCCESS('Listening on /scan_images and /scan_plates...'))
        self.stdout.write(self.style.WARNING('Type "toggle" and hit Enter to switch between HeyRoute and Local OCR. Type "quit" to exit.'))
        try:
            while True:
                user_cmd = input().strip().lower()
                if user_cmd == "toggle":
                    global USE_HEYROUTE_PRIMARY
                    USE_HEYROUTE_PRIMARY = not USE_HEYROUTE_PRIMARY
                    state = "ON (HeyRoute API)" if USE_HEYROUTE_PRIMARY else "OFF (Local Custom OCR)"
                    self.stdout.write(self.style.SUCCESS(f"HeyRoute Primary is now {state}"))
                elif user_cmd in ["quit", "exit"]:
                    self.stdout.write(self.style.WARNING('\nShutting down Firebase worker...'))
                    import sys
                    sys.exit(0)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\nShutting down Firebase worker...'))
            import sys
            sys.exit(0)

    def listen_images(self, event):
        self.handle_event(event, "image", "scan_images")

    def listen_plates(self, event):
        self.handle_event(event, "plate", "scan_plates")

    def handle_event(self, event, request_type, base_path):
        if not event.data or not isinstance(event.data, dict):
            return
        path_parts = [p for p in event.path.split("/") if p]
        
        if len(path_parts) == 0:
            for uid, user_data in event.data.items():
                if isinstance(user_data, dict):
                    for sid, sdata in user_data.items():
                        if isinstance(sdata, dict):
                            self.process_scan(uid, sid, sdata, request_type, base_path)
        elif len(path_parts) >= 2:
            uid, sid = path_parts[0], path_parts[1]
            if len(path_parts) > 2:
                full_data = db.reference(f"{base_path}/{uid}/{sid}").get()
                if isinstance(full_data, dict):
                    self.process_scan(uid, sid, full_data, request_type, base_path)
            else:
                self.process_scan(uid, sid, event.data, request_type, base_path)

    def process_scan(self, user_id, scan_id, data, request_type, base_path):
        created_at = data.get("created_at")
        if not created_at:
            return
            
        now = int(time.time() * 1000)
        # Check if older than 60 seconds before processing
        if (now - created_at) > 60000:
            return

        plate_number = ""
        result_payload = {"created_at": created_at}
        
        if request_type == "image":
            b64_data = data.get("image")
            if not b64_data: return
            
            heyroute_failed = False
            
            import tempfile
            try:
                image_bytes = base64.b64decode(b64_data, validate=True)
                filename = os.path.join(tempfile.gettempdir(), f"scan_{scan_id}.jpg")
                with open(filename, "wb") as f:
                    f.write(image_bytes)
            except Exception as e:
                self.stdout.write(f"Image Decode Error: {e}")
                result_payload.update({"status": "error", "is_valid": False, "plate_number": "ERROR"})
                self.write_result(base_path, user_id, scan_id, result_payload)
                return
            
            # --- PRIMARY: HeyRoute (Gemini) ---
            if USE_HEYROUTE_PRIMARY:
                global active_heyroute_requests
                
                with request_lock:
                    current_load = active_heyroute_requests
                
                if current_load >= 3:
                    self.stdout.write("High load (>= 3 requests). Bypassing HeyRoute, falling back to Custom OCR.")
                    heyroute_failed = True
                else:
                    with request_lock:
                        active_heyroute_requests += 1
                    try:
                        self.stdout.write(f"Sending to HeyRoute API... (Active Requests: {current_load + 1})")
                        
                        # Use YOLO to get the cropped plate first
                        from license_plate_11 import get_plate_crops
                        self.stdout.write("Running YOLO to crop plate...")
                        crops = get_plate_crops(filename)
                        if crops and len(crops) > 0:
                            target_b64 = crops[0] # Use the first/best crop
                        else:
                            target_b64 = b64_data # Fallback to original image
                            
                        hr_result = extract_plate_with_heyroute(target_b64)
                        
                        if hr_result["success"]:
                            plate_number = hr_result["plate_number"]
                            self.stdout.write(f"HeyRoute OCR success: {plate_number}")
                        elif hr_result["error_message"] == "REVIEW":
                            self.stdout.write("HeyRoute returned REVIEW (Unreadable plate).")
                            plate_number = "" # Will trigger "review" status below
                        else:
                            self.stdout.write(f"HeyRoute API Error (Status {hr_result['status_code']}): {hr_result['error_message']}")
                            heyroute_failed = True
                    except Exception as e:
                        self.stdout.write(f"HeyRoute Exception: {e}")
                        heyroute_failed = True
                    finally:
                        with request_lock:
                            active_heyroute_requests -= 1
            else:
                heyroute_failed = True # Act as if it failed so we drop into fallback
                
            # --- SECONDARY: Custom Local OCR (Fallback) ---
            if heyroute_failed or (not USE_HEYROUTE_PRIMARY):
                try:
                    self.stdout.write("Running Custom OCR fallback...")
                    # Enforce a 12-second timeout so the overall process stays within 15s
                    custom_results = custom_extract_license_plate(filename, timeout=12.0)
                    if custom_results and len(custom_results) > 0:
                        best_match = custom_results[0]
                        conf = best_match.get("confidence", 0.0)
                        source = best_match.get("source", "")
                        
                        if conf >= 0.5 and "error" not in best_match and "Unvalidated" not in source:
                            plate_number = best_match.get("plate_number", "")
                            self.stdout.write(f"Custom OCR success: {plate_number} ({conf})")
                    
                    if os.path.exists(filename):
                        os.remove(filename)
                except Exception as e:
                    self.stdout.write(f"Custom OCR Error: {e}")
                    if os.path.exists(filename):
                        os.remove(filename)
                    result_payload.update({"status": "error", "is_valid": False, "plate_number": "ERROR"})
                    self.write_result(base_path, user_id, scan_id, result_payload)
                    return
            else:
                if os.path.exists(filename):
                    os.remove(filename)
        else:
            plate_number = data.get("plate_number")

        verification_result = verify_vehicle(plate_number)
        result_payload.update(verification_result)
        
        self.write_result(base_path, user_id, scan_id, result_payload)

    def write_result(self, base_path, user_id, scan_id, result_payload):
        # Atomic update: write to scan_results and delete from scan_images/scan_plates
        updates = {
            f"scan_results/{user_id}/{scan_id}": result_payload,
            f"{base_path}/{user_id}/{scan_id}": None
        }
        db.reference().update(updates)
        self.stdout.write(f"Processed scan {scan_id}. Status: {result_payload.get('status')} Valid: {result_payload.get('is_valid')}")

    def cleanup_worker(self):
        while True:
            try:
                now = int(time.time() * 1000)
                threshold = now - (ABANDONED_RECORD_AGE_SECONDS * 1000)
                
                def clean_node(node_name):
                    users_data = db.reference(node_name).get()
                    if users_data:
                        updates = {}
                        for uid, user_dict in users_data.items():
                            if isinstance(user_dict, dict):
                                for sid, sdata in user_dict.items():
                                    if isinstance(sdata, dict):
                                        created = sdata.get("created_at", now)
                                        if created < threshold:
                                            updates[f"{node_name}/{uid}/{sid}"] = None
                        if updates:
                            db.reference().update(updates)

                clean_node("scan_images")
                clean_node("scan_plates")
                clean_node("scan_results")
            except Exception:
                pass
            time.sleep(CLEANUP_INTERVAL_SECONDS)
