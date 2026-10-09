import cv2
import numpy as np
import re
import torch
import os
import time
from PIL import Image
from ultralytics import YOLO
import easyocr
from transformers import AutoProcessor, AutoModelForCausalLM

# ==========================================
# 1. INITIALIZATION & DIRECTORY SETUP
# ==========================================
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DEBUG_DIR = os.path.join(os.path.dirname(BASE_DIR), "src", "debug_analytics")
os.makedirs(DEBUG_DIR, exist_ok=True)

vehicle_model = YOLO(os.path.join(BASE_DIR, "yolo11n.pt"))
plate_model = YOLO(os.path.join(BASE_DIR, "license_weight", "indian_plates_best.pt"))

easy_ocr = easyocr.Reader(['en'], gpu=True, verbose=False)

try:
    from paddleocr import PaddleOCR
    paddle_ocr = PaddleOCR(lang="en", device="cpu", use_mkldnn=False, show_log=False)
    PADDLE_AVAILABLE = True
except Exception as e:
    PADDLE_AVAILABLE = False

FLORENCE_ID = "multimodalart/Florence-2-large-no-flash-attn"
florence_processor = AutoProcessor.from_pretrained(FLORENCE_ID, trust_remote_code=True)
florence_model = AutoModelForCausalLM.from_pretrained(
    FLORENCE_ID, torch_dtype=torch.float16, trust_remote_code=True
).to(DEVICE)

VALID_STATES = [
    "AN", "AP", "AR", "AS", "BR", "CH", "CG", "DD", "DL", "DN", "GA", "GJ",
    "HR", "HP", "JH", "JK", "KA", "KL", "LA", "LD", "MP", "MH", "MN", "ML",
    "MZ", "NL", "OD", "PB", "PY", "RJ", "SK", "TN", "TR", "TS", "UK", "UP", 
    "WB", "BH"
]

CHAR_TO_NUM = {"O": "0", "I": "1", "Z": "2", "S": "5", "G": "6", "B": "8", "D": "0", "Q": "0", "T": "1"}
NUM_TO_CHAR = {"0": "O", "1": "I", "2": "Z", "5": "S", "6": "G", "8": "B", "7": "T"}

# ==========================================
# 2. IMAGE ENHANCEMENT
# ==========================================
def add_padding(img, bbox, pad_pct=0.06):
    h, w = img.shape[:2]
    x1, y1, x2, y2 = bbox
    pad_w = int((x2 - x1) * pad_pct)
    pad_h = int((y2 - y1) * pad_pct)
    return [max(0, x1 - pad_w), max(0, y1 - pad_h), min(w, x2 + pad_w), min(h, y2 + pad_h)]

def denoise_and_enhance(crop):
    h, w = crop.shape[:2]
    scaling = max(3.0, 150.0 / h) 
    upscaled = cv2.resize(crop, None, fx=scaling, fy=scaling, interpolation=cv2.INTER_LANCZOS4)
    
    gray = cv2.cvtColor(upscaled, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    contrast = clahe.apply(gray)
    
    smooth = cv2.bilateralFilter(contrast, d=7, sigmaColor=75, sigmaSpace=75)
    return cv2.cvtColor(smooth, cv2.COLOR_GRAY2BGR)

# ==========================================
# 3. OCR EXTRACTION
# ==========================================
def extract_easyocr_text(crop, is_full_image=False):
    try:
        results = easy_ocr.readtext(crop, allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
        if not results: return "", 0.0
    except Exception: return "", 0.0

    img_h = crop.shape[0]
    valid_boxes = []
    total_conf = 0.0
    
    for bbox, text, conf in results:
        y_coords = [pt[1] for pt in bbox]
        box_h = max(y_coords) - min(y_coords)
        
        if not is_full_image and box_h < (img_h * 0.05):
            continue
            
        x_center = sum([pt[0] for pt in bbox]) / 4.0
        y_center = sum(y_coords) / 4.0
        valid_boxes.append({"text": text, "conf": float(conf), "x": x_center, "y": y_center, "h": box_h})
        total_conf += float(conf)

    if not valid_boxes: return "", 0.0

    avg_conf = total_conf / len(valid_boxes)
    valid_boxes = sorted(valid_boxes, key=lambda b: b["y"])
    lines, current_line = [], []
    
    line_variance = valid_boxes[0]["h"] * 0.6 if valid_boxes else img_h * 0.15
    for b in valid_boxes:
        if not current_line: current_line.append(b)
        else:
            if abs(b["y"] - current_line[0]["y"]) < line_variance:
                current_line.append(b)
            else:
                lines.append(sorted(current_line, key=lambda x: x["x"]))
                current_line = [b]
    if current_line: lines.append(sorted(current_line, key=lambda x: x["x"]))

    raw_text = "".join([box["text"] for line in lines for box in line])
    return raw_text, avg_conf

def extract_paddle_text(crop, is_full_image=False):
    if not PADDLE_AVAILABLE: return "", 0.0
    try:
        results = list(paddle_ocr.predict(crop))
        if not results or not results[0]['rec_texts']: return "", 0.0
        page = results[0]
    except Exception: return "", 0.0

    img_h = crop.shape[0]
    valid_boxes = []
    total_conf = 0.0
    for text, conf, box in zip(page['rec_texts'], page['rec_scores'], page['rec_polys']):
        y_coords = [pt[1] for pt in box]
        box_h = max(y_coords) - min(y_coords)
        if not is_full_image and box_h < (img_h * 0.05): continue
            
        x_center = sum([pt[0] for pt in box]) / 4.0
        y_center = sum(y_coords) / 4.0
        valid_boxes.append({"text": text, "conf": float(conf), "x": x_center, "y": y_center, "h": box_h})
        total_conf += float(conf)

    if not valid_boxes: return "", 0.0

    avg_conf = total_conf / len(valid_boxes)
    valid_boxes = sorted(valid_boxes, key=lambda b: b["y"])
    lines, current_line = [], []
    
    line_variance = valid_boxes[0]["h"] * 0.6 if valid_boxes else img_h * 0.15
    for b in valid_boxes:
        if not current_line: current_line.append(b)
        else:
            if abs(b["y"] - current_line[0]["y"]) < line_variance:
                current_line.append(b)
            else:
                lines.append(sorted(current_line, key=lambda x: x["x"]))
                current_line = [b]
    if current_line: lines.append(sorted(current_line, key=lambda x: x["x"]))

    raw_text = "".join([box["text"] for line in lines for box in line])
    return raw_text, avg_conf

def run_florence_fallback(crop_cv2):
    rgb = cv2.cvtColor(crop_cv2, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)
    task_prompt = "<OCR>"
    
    inputs = florence_processor(text=task_prompt, images=pil_img, return_tensors="pt").to(DEVICE, torch.float16)

    with torch.no_grad():
        generated_ids = florence_model.generate(
            input_ids=inputs["input_ids"], pixel_values=inputs["pixel_values"], max_new_tokens=128, num_beams=5
        )
    prediction = florence_processor.batch_decode(generated_ids, skip_special_tokens=False)[0]
    parsed = florence_processor.post_process_generation(prediction, task=task_prompt, image_size=(pil_img.width, pil_img.height))
    return parsed.get(task_prompt, "")

# ==========================================
# 4. STRUCTURAL BLOCK SCANNER
# ==========================================
def validate_indian_format(plate):
    if re.match(r"^([A-Z]{2})([0-9]{2})([A-Z]{1,3})([0-9]{4})$", plate) and plate[:2] in VALID_STATES:
        return True, "STANDARD"
    if re.match(r"^([0-9]{2})(BH)([0-9]{4})([A-Z]{2})$", plate): return True, "BH_SERIES"
    return False, None

def correct_heuristics(raw_text):
    clean = re.sub(r'[^A-Z0-9\s]', '', raw_text.upper())
    clean = re.sub(r'I[NM][D0O]|1[NM][D0O]|IND|1ND', '', clean)
    
    if re.search(r'^\s*IN', clean) and len(clean.replace(' ', '')) >= 8: clean = re.sub(r'^\s*IN', 'TN', clean)
    elif not re.search(r'^\s*MH', clean) and re.search(r'^\s*NH', clean) and len(clean.replace(' ', '')) >= 8: clean = re.sub(r'^\s*NH', 'MH', clean)
    elif re.search(r'^\s*HA', clean) and len(clean.replace(' ', '')) >= 8: clean = re.sub(r'^\s*HA', 'HR', clean)
    elif not re.search(r'^\s*KA', clean) and re.search(r'^\s*K4', clean) and len(clean.replace(' ', '')) >= 8: clean = re.sub(r'^\s*K4', 'KA', clean)

    match = re.search(r'([A-Z]{2})\s*([0-9OIZSGBQ]{2})\s*(.*?)\s*([0-9OIZSGBQ]{4})(?!\d)', clean)
    if match:
        state, rto, series, num = match.groups()
        rto = ''.join([CHAR_TO_NUM.get(c, c) for c in rto])
        series = ''.join([NUM_TO_CHAR.get(c, c) for c in series])
        series = re.sub(r'[^A-Z]', '', series)
        if len(series) > 3: series = series[-2:]
        num = ''.join([CHAR_TO_NUM.get(c, c) for c in num])
        return state + rto + series + num

    clean = clean.replace(' ', '')
    if len(clean) > 10: clean = clean[-10:]
    if len(clean) < 9 or len(clean) > 10: return clean

    chars = list(clean)
    for i in range(2): chars[i] = NUM_TO_CHAR.get(chars[i], chars[i])
    for i in range(2, 4): chars[i] = CHAR_TO_NUM.get(chars[i], chars[i])
    for i in range(len(chars) - 4, len(chars)): chars[i] = CHAR_TO_NUM.get(chars[i], chars[i])
    for i in range(4, len(chars) - 4): chars[i] = NUM_TO_CHAR.get(chars[i], chars[i])
    return ''.join(chars)

# ==========================================
# 5. MAIN ANPR INFERENCE LOOP
# ==========================================
def extract_license_plate(image_path, timeout=15.0):
    start_time = time.time()
    img = cv2.imread(image_path)
    if img is None: return [{"error": "Image not found"}]
    
    vehicle_results = vehicle_model(img, classes=[2, 3, 5, 7], conf=0.5, verbose=False)[0]
    detections = []
    
    rois = []
    if len(vehicle_results.boxes) > 0:
        for v_box in vehicle_results.boxes.xyxy.cpu().numpy():
            v_coords = add_padding(img, list(map(int, v_box)))
            rois.append((img[v_coords[1]:v_coords[3], v_coords[0]:v_coords[2]], False))
    else:
        rois.append((img, True))

    for v_crop, is_full_image in rois:
        plate_results = plate_model(v_crop, conf=0.15, verbose=False)[0]
        
        plate_crops = []
        if len(plate_results.boxes) == 0:
            plate_crops.append((v_crop, True))
        else:
            for p_box in plate_results.boxes.xyxy.cpu().numpy():
                p_coords = add_padding(v_crop, list(map(int, p_box)))
                plate_crops.append((v_crop[p_coords[1]:p_coords[3], p_coords[0]:p_coords[2]], False))

        for raw_plate_crop, is_fallback_crop in plate_crops:
            if time.time() - start_time > timeout:
                print("Custom OCR timed out!")
                break
                
            if is_fallback_crop and raw_plate_crop.shape[0] > 600:
                prep_crop = raw_plate_crop 
            else:
                prep_crop = denoise_and_enhance(raw_plate_crop)

            raw_text_unprep, conf_unprep = extract_easyocr_text(raw_plate_crop, is_fallback_crop)
            raw_text_prep, conf_prep = extract_easyocr_text(prep_crop, is_fallback_crop)
            if conf_unprep > conf_prep:
                primary_raw, conf = raw_text_unprep, conf_unprep
            else:
                primary_raw, conf = raw_text_prep, conf_prep
            candidate_text = correct_heuristics(primary_raw)
            is_valid, plate_type = validate_indian_format(candidate_text)
            engine_source = f"EasyOCR ({plate_type})"
            
            if not is_valid and PADDLE_AVAILABLE:
                p_raw, p_conf = extract_paddle_text(prep_crop, is_fallback_crop)
                p_candidate = correct_heuristics(p_raw)
                p_valid, p_type = validate_indian_format(p_candidate)
                
                if p_valid:
                    candidate_text, conf, is_valid, engine_source = p_candidate, p_conf, p_valid, f"PaddleOCR ({p_type})"

            if not is_valid or conf < 0.65:
                if time.time() - start_time > timeout:
                    print("Skipping Florence-2 due to timeout!")
                    final_plate, source = candidate_text, engine_source
                else:
                    florence_raw = run_florence_fallback(prep_crop)
                    florence_candidate = correct_heuristics(florence_raw)
                    florence_valid, f_type = validate_indian_format(florence_candidate)

                if florence_valid:
                    final_plate, source = florence_candidate, "Florence-2 (Recovered)"
                else:
                    final_plate = candidate_text if len(candidate_text) >= len(florence_candidate) else florence_candidate
                    source = "Ensemble Guess (Unvalidated)"
            else:
                final_plate, source = candidate_text, engine_source

            if len(final_plate) >= 8:
                detections.append({"plate_number": final_plate, "confidence": round(float(conf), 2), "source": source})

    import gc
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    if not detections:
        return []
    
    validated = [d for d in detections if "Unvalidated" not in d["source"]]
    if validated:
        return [max(validated, key=lambda x: x["confidence"])]
    return [max(detections, key=lambda x: x["confidence"])]

def get_plate_crops(image_path):
    """Uses YOLO to find the license plate and returns it as a base64 encoded JPEG string. 
    If no plate is found, returns the original image base64."""
    img = cv2.imread(image_path)
    if img is None: return []
    
    vehicle_results = vehicle_model(img, classes=[2, 3, 5, 7], conf=0.5, verbose=False)[0]
    
    rois = []
    if len(vehicle_results.boxes) > 0:
        for v_box in vehicle_results.boxes.xyxy.cpu().numpy():
            v_coords = add_padding(img, list(map(int, v_box)))
            rois.append((img[v_coords[1]:v_coords[3], v_coords[0]:v_coords[2]], False))
    else:
        rois.append((img, True))

    plate_crops_b64 = []
    for v_crop, is_full_image in rois:
        plate_results = plate_model(v_crop, conf=0.15, verbose=False)[0]
        
        if len(plate_results.boxes) == 0:
            # No plate found in this vehicle, fallback to the vehicle crop itself
            final_crop = v_crop
        else:
            # Take the highest confidence plate
            best_box = plate_results.boxes.xyxy.cpu().numpy()[0]
            p_coords = add_padding(v_crop, list(map(int, best_box)))
            final_crop = v_crop[p_coords[1]:p_coords[3], p_coords[0]:p_coords[2]]
            
            # Fallback if crop is invalid
            if final_crop.size == 0:
                final_crop = v_crop
            
        # Convert to Base64
        _, buffer = cv2.imencode('.jpg', final_crop)
        import base64
        b64_str = base64.b64encode(buffer).decode('utf-8')
        plate_crops_b64.append(b64_str)
        
    import gc
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        
    return plate_crops_b64

if __name__ == '__main__':
    import argparse
    import os

    parser = argparse.ArgumentParser(description='ALPR Pipeline Tester')
    parser.add_argument('image_path', nargs='?', help='Path to the image to process. If omitted, runs a test on all test images in the images/ directory')
    args = parser.parse_args()

    if args.image_path:
        test_images = [args.image_path]
    else:
        img_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'images')
        test_images = [os.path.join(img_dir, f) for f in os.listdir(img_dir) if f.startswith('test') and f.endswith('.jpg')]
        test_images.sort()

    for img in test_images:
        print(f'\n--- Processing {os.path.basename(img)} ---')
        try:
            results = extract_license_plate(img)
            if results:
                for r in results:
                    print(f'Plate: {r["plate_number"]} | Engine: {r["source"]} | Confidence: {r["confidence"]}')
            else:
                print('No plates found.')
        except Exception as e:
            print('Error:', e)
