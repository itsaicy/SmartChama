from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.contrib import messages
from django.db import transaction
from django.db.models import Q

from .models import Meeting, MeetingAttendance, Notification
from chama.models import Membership, Chama
from .forms import MeetingForm

# --- Helper: Get Active Chama (Safety Net) ---
def get_active_chama_id(request):
    """
    Helper to ensure we always have a valid Chama ID.
    Prioritizes Session > User Membership > First DB Record (Fallback).
    """
    active_chama_id = request.session.get("active_chama_id")
    
    if not active_chama_id:
        # Attempt 1: Check if user is a member of any chama
        membership = Membership.objects.filter(membership_user=request.user).first()
        if membership:
            active_chama_id = membership.membership_chama.id
        else:
            # Attempt 2 (FALLBACK for Admin/Testing): Grab first available Chama
            first_chama = Chama.objects.first()
            if first_chama:
                active_chama_id = first_chama.id
    
    # Update session if we found one
    if active_chama_id:
        request.session["active_chama_id"] = active_chama_id
        
    return active_chama_id

# --- Helper: Send Notification ---
def create_notification_for_group(chama_id, message, type, related_meeting=None):
    """Creates a notification for all members of a chama."""
    if not chama_id: return
    members = Membership.objects.filter(membership_chama_id=chama_id)
    notifications = []
    for member in members:
        notifications.append(Notification(
            notification_user=member.membership_user,
            notification_chama_id=chama_id,
            notification_message=message,
            notification_type=type,
            notification_related_meeting=related_meeting
        ))
    Notification.objects.bulk_create(notifications)

# -----------------------------------------------------
# 1. Meetings List Page (User)
# -----------------------------------------------------
@login_required
def meeting_list(request):
    active_chama_id = get_active_chama_id(request)
    now = timezone.now()
    
    # Base Query
    meetings = Meeting.objects.filter(meeting_chama_id=active_chama_id).order_by('meeting_date')

    # Filtering Logic
    filter_type = request.GET.get("filter", "all")
    
    if filter_type == "upcoming":
        meetings = meetings.filter(meeting_date__gte=now)
    elif filter_type == "past":
        meetings = meetings.filter(meeting_date__lt=now).order_by('-meeting_date')
    elif filter_type == "online":
        meetings = meetings.filter(meeting_type='online')
    elif filter_type == "physical":
        meetings = meetings.filter(meeting_type='physical')

    return render(request, "notification/meeting/meeting_list.html", {
        "meetings": meetings, 
        "filter_type": filter_type,
        "is_root_view": True
    })

# -----------------------------------------------------
# 2. Meeting Detail Page
# -----------------------------------------------------
@login_required
def meeting_detail(request, pk):
    active_chama_id = get_active_chama_id(request)
    meeting = get_object_or_404(Meeting, pk=pk, meeting_chama_id=active_chama_id)

    # Get User's attendance
    attendance, created = MeetingAttendance.objects.get_or_create(
        attendance_meeting=meeting,
        attendance_user=request.user
    )

    # Admin View: Get all attendees for "Who's Going"
    all_attendees = None
    is_official = False 
    
    # Check if user is an official (Admin/Secretary/Treasurer)
    try:
        membership = Membership.objects.filter(
            membership_user=request.user, 
            membership_chama_id=active_chama_id
        ).first()
        
        # Adjust these roles based on your exact Membership model choices
        if membership and membership.membership_role in ['admin', 'secretary', 'treasurer', 'chairperson']:
            is_official = True
            all_attendees = MeetingAttendance.objects.filter(attendance_meeting=meeting).select_related('attendance_user')
        elif request.user.is_staff or request.user.is_superuser:
            # Fallback for superusers
            is_official = True
            all_attendees = MeetingAttendance.objects.filter(attendance_meeting=meeting).select_related('attendance_user')
            
    except Exception as e:
        print(f"Error checking official status: {e}")

    return render(request, "notification/meeting/meeting_detail.html", {
        "meeting": meeting,
        "attendance": attendance,
        "is_official": is_official,
        "all_attendees": all_attendees
    })

# -----------------------------------------------------
# 3. Confirm Attendance (User Action)
# -----------------------------------------------------
@login_required
def confirm_attendance(request, pk, status):
    active_chama_id = get_active_chama_id(request)
    meeting = get_object_or_404(Meeting, pk=pk, meeting_chama_id=active_chama_id)
    
    attendance, created = MeetingAttendance.objects.get_or_create(
        attendance_user=request.user,
        attendance_meeting=meeting
    )
    
    attendance.attendance_status = status 
    attendance.save()
    
    messages.success(request, f"You have confirmed you are {status}.")
    return redirect("notification:meeting_detail", pk=pk)

# -----------------------------------------------------
# 4. Admin: Create Meeting
# -----------------------------------------------------
@login_required
def create_meeting(request):
    active_chama_id = get_active_chama_id(request)
    
    if not active_chama_id:
        messages.error(request, "System Error: No Chama groups found. Please create a Chama first.")
        return redirect("notification:meeting_list")

    if request.method == "POST":
        form = MeetingForm(request.POST)
        if form.is_valid():
            meeting = form.save(commit=False)
            meeting.meeting_created_by = request.user
            meeting.meeting_chama_id = active_chama_id
            meeting.save()

            # Notify Members
            create_notification_for_group(
                active_chama_id,
                f"New Meeting: {meeting.meeting_title}",
                "meeting",
                related_meeting=meeting
            )
            
            messages.success(request, "Meeting scheduled successfully.")
            return redirect("notification:admin_meeting_list")
    else:
        form = MeetingForm()

    return render(request, "notification/meeting/create_meeting.html", {"form": form})

# -----------------------------------------------------
# 5. Admin: Update Meeting
# -----------------------------------------------------
@login_required
def update_meeting(request, pk):
    active_chama_id = get_active_chama_id(request)
    meeting = get_object_or_404(Meeting, pk=pk, meeting_chama_id=active_chama_id)

    if request.method == "POST":
        form = MeetingForm(request.POST, instance=meeting)
        if form.is_valid():
            meeting = form.save()

            create_notification_for_group(
                active_chama_id,
                f"Meeting Updated: {meeting.meeting_title}",
                "meeting",
                related_meeting=meeting
            )

            messages.success(request, "Meeting updated.")
            return redirect("notification:admin_meeting_list")
    else:
        form = MeetingForm(instance=meeting)

    return render(request, "notification/meeting/create_meeting.html", {"form": form, "meeting": meeting})

# -----------------------------------------------------
# 6. Admin: Delete Meeting
# -----------------------------------------------------
@login_required
def delete_meeting(request, pk):
    active_chama_id = get_active_chama_id(request)
    meeting = get_object_or_404(Meeting, pk=pk, meeting_chama_id=active_chama_id)

    if request.method == "POST":
        title = meeting.meeting_title
        create_notification_for_group(
            active_chama_id,
            f"Meeting Cancelled: {title}",
            "meeting"
        )
        
        meeting.delete()
        messages.success(request, "Meeting deleted.")
        return redirect("notification:admin_meeting_list")
    
    return redirect("notification:admin_meeting_list")

# -----------------------------------------------------
# 7. Admin: Manage Meeting List
# -----------------------------------------------------
@login_required
def admin_meeting_list(request):
    active_chama_id = get_active_chama_id(request)
    now = timezone.now()
    
    meetings = Meeting.objects.filter(meeting_chama_id=active_chama_id).order_by('meeting_date')
    
    # Filter Logic
    filter_type = request.GET.get("filter", "all")
    if filter_type == "upcoming":
        meetings = meetings.filter(meeting_date__gte=now)
    elif filter_type == "past": # Matches the UI pill 'Past'
        meetings = meetings.filter(meeting_date__lt=now).order_by('-meeting_date')

    return render(request, "notification/meeting/admin_meeting_list.html", {
        "meetings": meetings,
        "filter_type": filter_type,
        "is_root_view": False,
        "now": now # Pass 'now' to template for badge logic
    })

# -----------------------------------------------------
# 8. User: My Attendance List
# -----------------------------------------------------
@login_required
def my_attendance(request):
    active_chama_id = get_active_chama_id(request)
    now = timezone.now()
    
    # Get all attendance records
    records = MeetingAttendance.objects.filter(
        attendance_user=request.user,
        attendance_meeting__meeting_chama_id=active_chama_id
    ).select_related('attendance_meeting')

    # Filter Logic
    filter_type = request.GET.get("filter", "upcoming") # Default to upcoming
    
    if filter_type == "upcoming":
        records = records.filter(attendance_meeting__meeting_date__gte=now).order_by('attendance_meeting__meeting_date')
    elif filter_type == "past":
        records = records.filter(attendance_meeting__meeting_date__lt=now).order_by('-attendance_meeting__meeting_date')

    return render(request, "notification/meeting/my_attendance.html", {
        "records": records,
        "filter_type": filter_type,
        "is_root_view": False
    })

# -----------------------------------------------------
# 9. Admin Action: Trigger Confirmation (Fixes NoReverseMatch)
# -----------------------------------------------------
@login_required
def trigger_attendance_confirmation(request, meeting_id, user_id, status):
    """
    Called when Admin clicks Check/X on 'Who's Going' list.
    Marks status and sends notification.
    """
    # 1. Permission Check
    if not (request.user.is_staff or request.user.is_superuser):
        # Add additional role checks here if needed
        pass

    meeting = get_object_or_404(Meeting, pk=meeting_id)
    
    # 2. Get or Create the attendance record
    target_user_attendance, created = MeetingAttendance.objects.get_or_create(
        attendance_meeting=meeting, 
        attendance_user_id=user_id
    )
    
    # 3. Create Notification
    Notification.objects.create(
        notification_user_id=user_id,
        notification_chama=meeting.meeting_chama,
        notification_title="Attendance Update",
        notification_message=f"Admin has marked you as {status} for {meeting.meeting_title}. Please confirm if this is incorrect.",
        notification_type="meeting",
        notification_related_meeting=meeting
    )
    
    # 4. Update Status
    target_user_attendance.attendance_status = status
    target_user_attendance.save()
    
    messages.success(request, f"Member marked as {status} and notified.")
    return redirect('notification:meeting_detail', pk=meeting_id)