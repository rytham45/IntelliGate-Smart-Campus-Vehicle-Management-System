import os
import django
from datetime import date, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from Main.models import Vehicle

def run_seed():
    Vehicle.objects.all().delete() # Clear existing

    today = date.today()

    vehicles = [
        # 1. Valid Student (Authorized)
        {"plate_number": "PB02AB1234", "owner_name": "Aarav Sharma", "role": "STUDENT", "start_date": today - timedelta(days=30), "expiry_date": today + timedelta(days=180)},

        # 2. Valid Faculty (Authorized)
        {"plate_number": "DL01XY9999", "owner_name": "Dr. Ramesh Verma", "role": "FACULTY", "start_date": today - timedelta(days=60), "expiry_date": today + timedelta(days=365)},

        # 3. Expired Pass (Denied)
        {"plate_number": "HR26DK5555", "owner_name": "Vikram Singh", "role": "STUDENT", "start_date": today - timedelta(days=120), "expiry_date": today - timedelta(days=5)},
    ]

    for v in vehicles:
        Vehicle.objects.create(**v)
        print(f"Created: {v['plate_number']} ({v['owner_name']})")

    print("Database seeding completed successfully.")

if __name__ == '__main__':
    run_seed()