from django.db import models

class Vehicle(models.Model):
    ROLE_CHOICES = [
        ('STUDENT', 'Student'),
        ('FACULTY', 'Faculty'),
        ('STAFF', 'Staff'),
        ('VISITOR', 'Visitor'),
    ]

    plate_number = models.CharField(max_length=20, unique=True, help_text="No spaces, e.g., PB02AB1234")
    owner_name = models.CharField(max_length=100)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='STUDENT')
    start_date = models.DateField()
    expiry_date = models.DateField()

    def __str__(self):
        return f"{self.plate_number} ({self.owner_name})"

class AccessLog(models.Model):
    STATUS_CHOICES = [
        ('AUTHORIZED', 'Authorized'),
        ('DENIED_EXPIRED', 'Denied - Pass Expired or Not Started'),
        ('DENIED_UNREGISTERED', 'Denied - Not in System'),
        ('ERROR', 'Error - OCR Failed')
    ]

    # Only the text is saved here! No image field.
    plate_number = models.CharField(max_length=20)
    timestamp = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES)

    def __str__(self):
        return f"[{self.status}] {self.plate_number} at {self.timestamp.strftime('%H:%M:%S')}"