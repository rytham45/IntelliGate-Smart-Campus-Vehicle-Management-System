from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import Vehicle, AccessLog

@csrf_exempt
@api_view(['POST', 'GET'])
def check_if_exists(request):
    plate_number = request.data.get('plate_number') or request.GET.get('plate_number')
    if not plate_number:
        return Response({"error": "No plate_number provided"}, status=status.HTTP_400_BAD_REQUEST)
    
    exists = Vehicle.objects.filter(plate_number=plate_number).exists()
    return Response({"exists": exists, "plate_number": plate_number}, status=status.HTTP_200_OK)

@csrf_exempt
@api_view(['POST', 'GET'])
def check_if_has_pass(request):
    plate_number = request.data.get('plate_number') or request.GET.get('plate_number')
    if not plate_number:
        return Response({"error": "No plate_number provided"}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        vehicle = Vehicle.objects.get(plate_number=plate_number)
        has_pass = True
        return Response({
            "has_pass": has_pass, 
            "plate_number": plate_number, 
            "role": vehicle.role
        }, status=status.HTTP_200_OK)
    except Vehicle.DoesNotExist:
        return Response({
            "has_pass": False, 
            "plate_number": plate_number
        }, status=status.HTTP_200_OK)

@csrf_exempt
@api_view(['POST', 'GET'])
def check_if_pass_is_valid(request):
    plate_number = request.data.get('plate_number') or request.GET.get('plate_number')
    if not plate_number:
        return Response({"error": "No plate_number provided"}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        vehicle = Vehicle.objects.get(plate_number=plate_number)
        
        import pytz
        kolkata = pytz.timezone('Asia/Kolkata')
        today = timezone.now().astimezone(kolkata).date()
        
        if vehicle.start_date <= today <= vehicle.expiry_date:
            is_valid = True
            reason = "Pass is within valid dates"
        else:
            is_valid = False
            reason = "Pass expired or not started"
            
        return Response({
            "is_valid": is_valid, 
            "plate_number": plate_number, 
            "role": vehicle.role,
            "name": vehicle.owner_name,
            "reason": reason
        }, status=status.HTTP_200_OK)
    except Vehicle.DoesNotExist:
        return Response({"is_valid": False, "error": "Vehicle not found"}, status=status.HTTP_404_NOT_FOUND)