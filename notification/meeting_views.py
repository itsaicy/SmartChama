from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.contrib import messages

from .models import Meeting, MeetingAttendance
from chama.models import Membership
from notification.models import Notification
from notification.forms import MeetingForm

from common.utils import set_active_chama, create_child_record, send_to_members, update_status

# -----------------------------------------------------
# 1. Meetings List Page (/meetings/)
# -----------------------------------------------------
@login_required
def meeting_list(request):
    active_chama_id = request.session.get("active_chama_id")
    meetings = Meeting.objects.filter(meeting_chama_id=active_chama_id)

    filter_type = request.GET.get("filter")
    if filter_type == "upcoming":
        meetings = meetings.filter(meeting_date__gte=timezone.now())
    elif filter_type == "past":
        meetings = meetings.filter(meeting_date__lt=timezone.now())
    elif filter_type in ["online", "physical"]:
        meetings = meetings.filter(meeting_type=filter_type)

    return render(request, "notification/meeting/meeting_list.html", {"meetings": meetings})

# -----------------------------------------------------
# 2. Meeting Detail Page (/meetings/<id>/)
# -----------------------------------------------------
@login_required
def meeting_detail(request, pk):
    active_chama_id = request.session.get("active_chama_id")
    meeting = get_object_or_404(Meeting, pk=pk, meeting_chama_id=active_chama_id)

    attendance = MeetingAttendance.objects.filter(
        attendance_meeting=meeting,
        attendance_user=request.user
    ).first()

    return render(request, "notification/meeting/meeting_detail.html", {
        "meeting": meeting,
        "attendance": attendance
    })

# -----------------------------------------------------
# 3. Member Attendance Status Page (/attendance/my/)
# -----------------------------------------------------
@login_required
def my_attendance(request):
    active_chama_id = request.session.get("active_chama_id")
    records = MeetingAttendance.objects.filter(
        attendance_user=request.user,
        attendance_meeting__meeting_chama_id=active_chama_id
    )
    return render(request, "notification/meeting/my_attendance.html", {"records": records})

# -----------------------------------------------------
# 4. Admin Meeting List (/official/meetings/)
# -----------------------------------------------------
@login_required
def admin_meeting_list(request):
    active_chama_id = request.session.get("active_chama_id")
    meetings = Meeting.objects.filter(meeting_chama_id=active_chama_id).order_by("meeting_date")
    return render(request, "notification/meeting/admin_meeting_list.html", {"meetings": meetings})

# -----------------------------------------------------
# 5. Create Meeting Page (/official/meetings/create/)
# -----------------------------------------------------
@login_required
def create_meeting(request):
    if request.method == "POST":
        form = MeetingForm(request.POST)
        if form.is_valid():
            meeting = form.save(commit=False)
            meeting.meeting_created_by = request.user
            meeting.meeting_chama_id = request.session.get("active_chama_id")
            meeting.save()

            # Notify all members of the chama
            members = Membership.objects.filter(membership_chama_id=meeting.meeting_chama_id)

            def notify_member(member):
                return Notification.objects.create(
                    notification_user=member.membership_user,
                    notification_chama_id=meeting.meeting_chama_id,
                    notification_message=f"New meeting scheduled: {meeting.meeting_title}",
                    notification_type="meeting"
                )

            send_to_members(members, notify_member)

            messages.success(request, "Meeting created and members notified.")
            return redirect("meeting_detail", pk=meeting.pk)
    else:
        form = MeetingForm()

    return render(request, "notification/meeting/create_meeting.html", {"form": form})

# -----------------------------------------------------
# 6. Update Meeting Page (editing must notify members)
# -----------------------------------------------------
@login_required
def update_meeting(request, pk):
    active_chama_id = request.session.get("active_chama_id")
    meeting = get_object_or_404(Meeting, pk=pk, meeting_chama_id=active_chama_id)

    if request.method == "POST":
        for field in ["meeting_title", "meeting_date", "meeting_type", "meeting_venue", "meeting_online_link", "meeting_agenda"]:
            setattr(meeting, field, request.POST.get(field))
        meeting.save()

        members = Membership.objects.filter(membership_chama_id=meeting.meeting_chama_id)

        def notify_member(member):
            return Notification.objects.create(
                notification_user=member.membership_user,
                notification_chama_id=meeting.meeting_chama_id,
                notification_message=f"Meeting updated: {meeting.meeting_title}",
                notification_type="meeting"
            )

        send_to_members(members, notify_member)

        messages.success(request, "Meeting updated and members notified.")
        return redirect("meeting_detail", pk=meeting.pk)

    return render(request, "notification/meeting/create_meeting.html", {"meeting": meeting})

# -----------------------------------------------------
# 7. Confirm Attendance
# -----------------------------------------------------
@login_required
def confirm_attendance(request, pk, status):
    active_chama_id = request.session.get("active_chama_id")
    meeting = get_object_or_404(Meeting, pk=pk, meeting_chama_id=active_chama_id)
    attendance, created = MeetingAttendance.objects.get_or_create(
        attendance_user=request.user,
        attendance_meeting=meeting
    )
    update_status(attendance, "attendance_status", status)
    messages.success(request, f"Attendance marked as {status}.")
    return redirect("meeting_detail", pk=pk)

# -----------------------------------------------------
# 8. Delete Meeting
# -----------------------------------------------------
@login_required
def delete_meeting(request, pk):
    active_chama_id = request.session.get("active_chama_id")
    meeting = get_object_or_404(Meeting, pk=pk, meeting_chama_id=active_chama_id)

    if request.method == "POST":
        members = Membership.objects.filter(membership_chama_id=active_chama_id)

        def notify_member(member):
            return Notification.objects.create(
                notification_user=member.membership_user,
                notification_chama_id=active_chama_id,
                notification_message=f"Meeting cancelled: {meeting.meeting_title}",
                notification_type="meeting"
            )

        send_to_members(members, notify_member)
        meeting.delete()
        messages.success(request, "Meeting deleted and members notified.")
        return redirect("admin_meeting_list")

    return redirect("admin_meeting_list")
