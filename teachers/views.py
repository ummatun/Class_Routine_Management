from datetime import datetime, timedelta
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.conf import settings
from .models import ClassSchedule, Reschedule, Teacher
from .forms import RescheduleForm, TeacherForm
from routine.models import Routine, Notification



# @login_required
# def teacher_dashboard(request):
#     teacher = Teacher.objects.get(user=request.user)
#     schedules = ClassSchedule.objects.filter(teacher=teacher).order_by('date', 'start_time')
#     return render(request, 'teachers/teacher_dashboard.html', {
#         'teacher': teacher,
#         'schedules': schedules,
#     })


@login_required
def teacher_dashboard(request):
    teacher = Teacher.objects.get(user=request.user)
    today = timezone.now().date()
    
    schedules = ClassSchedule.objects.filter(
        teacher=teacher,
        date__gte=today  # Only upcoming classes including today
    ).exclude(status='cancelled').order_by('date', 'start_time')

    return render(request, 'teachers/teacher_dashboard.html', {
        'teacher': teacher,
        'schedules': schedules,
    })


def teacher_list(request):
    teachers = Teacher.objects.all()
    return render(request, 'teachers/teacher_list.html', {'teachers': teachers})



def teacher_detail(request, teacher_id):
    teacher = get_object_or_404(Teacher, pk=teacher_id)
    today = timezone.now().date()

    # Show only non-cancelled, upcoming classes
    schedules = ClassSchedule.objects.filter(
        teacher=teacher,
        date__gte=today
    ).exclude(status='cancelled').order_by('date', 'start_time')

    if request.method == "POST":
        action = request.POST.get("action")
        schedule_id = request.POST.get("schedule_id")

        if action == "cancel" and schedule_id:
            schedule = get_object_or_404(ClassSchedule, pk=schedule_id)

            # Delete related Reschedule objects (optional: cascade handles it too)
            Reschedule.objects.filter(class_schedule=schedule).delete()

            # Delete the class schedule
            schedule.delete()

            messages.success(request, "Class and its reschedule(s) canceled successfully.")
            return redirect('teacher_detail', teacher_id=teacher.id)

        elif action == "extra_class":
            messages.info(request, "Extra Class functionality not implemented yet.")
            return redirect('teacher_detail', teacher_id=teacher.id)

    context = {
        "teacher": teacher,
        "schedules": schedules,
    }
    return render(request, "teachers/teacher_detail.html", context)

# def teacher_detail(request, teacher_id):
#     teacher = get_object_or_404(Teacher, pk=teacher_id)
#     schedules = ClassSchedule.objects.filter(teacher=teacher).exclude(status='cancelled').order_by('date', 'start_time')

#     if request.method == "POST":
#         action = request.POST.get("action")
#         schedule_id = request.POST.get("schedule_id")

#         if action == "cancel" and schedule_id:
#             schedule = get_object_or_404(ClassSchedule, pk=schedule_id)

#             # Delete related Reschedule objects (optional, cascade will handle anyway)
#             Reschedule.objects.filter(class_schedule=schedule).delete()

#             # Delete the class schedule itself
#             schedule.delete()

#             messages.success(request, "Class and its reschedule(s) canceled successfully.")
#             return redirect('teacher_detail', teacher_id=teacher.id)

#         elif action == "extra_class":
#             # TODO: Implement extra class creation or redirect logic here
#             messages.info(request, "Extra Class functionality not implemented yet.")
#             return redirect('teacher_detail', teacher_id=teacher.id)

#     context = {
#         "teacher": teacher,
#         "schedules": schedules,
#     }
#     return render(request, "teachers/teacher_detail.html", context)


# teachers/views.py
from datetime import datetime
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from .models import ClassSchedule, Reschedule
from .forms import RescheduleForm
from routine.models import Slot, Room
from courses.models import Course

from datetime import datetime
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from .forms import RescheduleForm
from .models import ClassSchedule, Reschedule
from routine.models import Room
#from routine.utils import get_available_slots  # if your get_available_slots is in utils

def reschedule_class(request, schedule_id):
    class_schedule = get_object_or_404(ClassSchedule, id=schedule_id)
    existing_reschedule = Reschedule.objects.filter(class_schedule=class_schedule).first()

    if request.method == "POST":
        form = RescheduleForm(request.POST, instance=existing_reschedule, class_schedule=class_schedule)

        date_str = request.POST.get('reschedule_date')
        is_online_str = request.POST.get('is_online')
        is_online = (is_online_str == 'True') if is_online_str is not None else None

        if date_str and is_online is not None:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            form.fields['selected_slot'].choices = get_available_slots(class_schedule, date_obj, is_online)
        else:
            form.fields['selected_slot'].choices = []

        if form.is_valid():
            reschedule = form.save(commit=False)
            reschedule.class_schedule = class_schedule  # for reference
            original_date = class_schedule.date

            # Determine new time, room and type
            if reschedule.is_online:
                class_type = 'online'
                start_time = reschedule.new_start_time
                end_time = reschedule.new_end_time
                room = None
            else:
                try:
                    selected_slot = form.cleaned_data.get('selected_slot')
                    parts = selected_slot.strip().split()
                    if len(parts) != 2:
                        raise ValueError("Slot format incorrect. Use 'RoomNumber HH:MM-HH:MM'")
                    room_number = parts[0]
                    time_range = parts[1]
                    start_str, end_str = time_range.split('-')

                    start_time = datetime.strptime(start_str, '%H:%M').time()
                    end_time = datetime.strptime(end_str, '%H:%M').time()
                    room = Room.objects.get(number=room_number)

                    # Update reschedule fields
                    reschedule.new_start_time = start_time
                    reschedule.new_end_time = end_time
                    reschedule.room = room_number
                    class_type = 'offline'

                except Exception as e:
                    messages.error(request, f"Error parsing slot: {e}")
                    return render(request, 'teachers/reschedule_class.html', {
                        'form': form,
                        'class_schedule': class_schedule,
                    })

            # 1️⃣ Cancel original class
            class_schedule.status = 'cancelled'
            class_schedule.save()

            # 2️⃣ Create new ClassSchedule instance
            new_class = ClassSchedule.objects.create(
                course=class_schedule.course,
                teacher=class_schedule.teacher,
                room=room,
                date=reschedule.reschedule_date,
                original_date=original_date,
                start_time=start_time,
                end_time=end_time,
                semester=class_schedule.semester,
                status='rescheduled',
                class_type=class_type
            )

            # 3️⃣ Link Reschedule to new class
            reschedule.class_schedule = new_class
            reschedule.save()

            messages.success(request, "Class rescheduled successfully.")
            return redirect('teacher_detail', teacher_id=new_class.teacher.id)
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = RescheduleForm(instance=existing_reschedule, class_schedule=class_schedule)
        form.fields['selected_slot'].choices = []

    return render(request, 'teachers/reschedule_class.html', {
        'form': form,
        'class_schedule': class_schedule,
    })


# def reschedule_class(request, schedule_id):
#     class_schedule = get_object_or_404(ClassSchedule, id=schedule_id)
#     existing_reschedule = Reschedule.objects.filter(class_schedule=class_schedule).first()

#     if request.method == "POST":
#         form = RescheduleForm(request.POST, instance=existing_reschedule, class_schedule=class_schedule)

#         date_str = request.POST.get('reschedule_date')
#         is_online_str = request.POST.get('is_online')
#         is_online = (is_online_str == 'True') if is_online_str is not None else None

#         if date_str and is_online is not None:
#             date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
#             form.fields['selected_slot'].choices = get_available_slots(class_schedule, date_obj, is_online)
#         else:
#             form.fields['selected_slot'].choices = []

#         if form.is_valid():
#             reschedule = form.save(commit=False)
#             reschedule.class_schedule = class_schedule
            
#             # Store original info
#             original_date = class_schedule.date

#             if reschedule.is_online:
#                 # Online: use start/end from form
#                 class_schedule.class_type = 'online'
#                 class_schedule.start_time = reschedule.new_start_time
#                 class_schedule.end_time = reschedule.new_end_time
#                 class_schedule.room = None

#             else:
#                 try:
#                     selected_slot = form.cleaned_data.get('selected_slot')
#                     print(f"Selected slot: {selected_slot}")
#                     parts = selected_slot.strip().split()
#                     if len(parts) != 2:
#                         raise ValueError("Slot format is incorrect. Expected 'RoomNumber HH:MM-HH:MM'")

#                     room_number = parts[0]
#                     time_range = parts[1]
#                     start_str, end_str = time_range.split('-')

#                     start_time = datetime.strptime(start_str, '%H:%M').time()
#                     end_time = datetime.strptime(end_str, '%H:%M').time()

#                     # ✅ Assign values to both models
#                     reschedule.new_start_time = start_time
#                     reschedule.new_end_time = end_time
#                     reschedule.room = room_number

#                     class_schedule.start_time = start_time
#                     class_schedule.end_time = end_time
#                     class_schedule.room = Room.objects.get(number=room_number)
#                     class_schedule.class_type = 'offline'

#                     print(f"[DEBUG] Parsed times: {start_time} to {end_time}")

#                 except Exception as e:
#                     messages.error(request, f"Error parsing slot: {e}")
#                     return render(request, 'teachers/reschedule_class.html', {
#                         'form': form,
#                         'class_schedule': class_schedule,
#                     })

#             class_schedule.date = reschedule.reschedule_date
#             class_schedule.status = 'rescheduled'

#             # ✅ Save only after everything is valid
#             reschedule.save()
#             class_schedule.save()

#             messages.success(request, "Class rescheduled successfully.")
#             return redirect('teacher_detail', teacher_id=class_schedule.teacher.id)

#         else:
#             messages.error(request, "Please fix the errors below.")

#     else:
#         form = RescheduleForm(instance=existing_reschedule, class_schedule=class_schedule)
#         form.fields['selected_slot'].choices = []

#     return render(request, 'teachers/reschedule_class.html', {
#         'form': form,
#         'class_schedule': class_schedule,
#     })


def get_available_slots(class_schedule, date, is_online):
    """
    Returns a list of available slots tuples (value, label) based on:
    1) teacher's schedule on that date,
    2) batch's schedule (via semester from course),
    3) room availability for offline classes,
    with these constraints:

    - No offline classes on Friday (weekday=4) or Saturday (weekday=5).
    - Online classes allowed all days.
    - Online time:
        * Friday & Saturday: 9:00 AM - 10:00 PM
        * Other days: 7:00 PM - 10:00 PM
    """

    weekday = date.weekday()  # Monday=0 ... Sunday=6
    teacher = class_schedule.teacher
    semester = class_schedule.semester

    available = []

    if is_online:
        # Online class time limits
        if weekday in [4, 5]:  # Friday or Saturday
            valid_slots = Slot.objects.filter(start_time__gte='09:00', end_time__lte='22:00')
        else:
            valid_slots = Slot.objects.filter(start_time__gte='19:00', end_time__lte='22:00')

        for slot in valid_slots:
            # Check if teacher is free at this slot on that date using overlap logic
            conflict = ClassSchedule.objects.filter(
                teacher=teacher,
                date=date,
                start_time__lt=slot.end_time,
                end_time__gt=slot.start_time,
                status__in=['pending', 'conducted', 'rescheduled']
            ).exists()
            if not conflict:
                label = f"Online {slot.start_time.strftime('%I:%M %p')}–{slot.end_time.strftime('%I:%M %p')}"
                value = f"Online {slot.start_time.strftime('%H:%M')}-{slot.end_time.strftime('%H:%M')}"
                available.append((value, label))

    else:
        # Offline classes NOT allowed Friday/Saturday
        if weekday in [4, 5]:
            return []

        seen_combinations = set()

        for room in Room.objects.all():
            for slot in Slot.objects.all():
                time_key = (room.number, slot.start_time, slot.end_time)

                if time_key in seen_combinations:
                    continue

                # Check teacher free (overlap)
                if ClassSchedule.objects.filter(
                    teacher=teacher,
                    date=date,
                    start_time__lt=slot.end_time,
                    end_time__gt=slot.start_time,
                    status__in=['pending', 'conducted', 'rescheduled']
                ).exists():
                    continue

                # Check batch (semester) free (overlap)
                if ClassSchedule.objects.filter(
                    semester=semester,
                    date=date,
                    start_time__lt=slot.end_time,
                    end_time__gt=slot.start_time,
                    status__in=['pending', 'conducted', 'rescheduled']
                ).exists():
                    continue

                # Check room free (overlap)
                if ClassSchedule.objects.filter(
                    room=room,
                    date=date,
                    start_time__lt=slot.end_time,
                    end_time__gt=slot.start_time,
                    status__in=['pending', 'conducted', 'rescheduled']
                ).exists():
                    continue

                seen_combinations.add(time_key)

                label = f"Room {room.number} {slot.start_time.strftime('%I:%M %p')}–{slot.end_time.strftime('%I:%M %p')}"
                value = f"{room.number} {slot.start_time.strftime('%H:%M')}-{slot.end_time.strftime('%H:%M')}"
                available.append((value, label))

    return available

from django.http import JsonResponse
from datetime import datetime

def ajax_get_available_slots(request):
    date_str = request.GET.get('date')
    is_online_str = request.GET.get('is_online')

    if not date_str or is_online_str is None:
        return JsonResponse({'slots': []})

    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        is_online = is_online_str.lower() == 'true'
    except:
        return JsonResponse({'slots': []})

    # You need class_schedule object here, but since it's AJAX, pass teacher_id and semester_id via GET
    teacher_id = request.GET.get('teacher_id')
    semester = request.GET.get('semester')

    # Minimal check for required params
    if not teacher_id or not semester:
        return JsonResponse({'slots': []})

    # Get teacher and create dummy class_schedule-like object
    from teachers.models import Teacher
    try:
        teacher = Teacher.objects.get(id=teacher_id)
    except Teacher.DoesNotExist:
        return JsonResponse({'slots': []})

    # Create a dummy class_schedule object with teacher and semester for get_available_slots
    class DummySchedule:
        def __init__(self, teacher, semester):
            self.teacher = teacher
            self.semester = semester

    dummy_schedule = DummySchedule(teacher, semester)

    from .views import get_available_slots  # import your existing function
    slots = get_available_slots(dummy_schedule, date_obj, is_online)

    # Format slots as list of dicts for frontend
    slot_list = [{'value': val, 'label': label} for val, label in slots]

    return JsonResponse({'slots': slot_list})


def add_teacher(request):
    if request.method == 'POST':
        form = TeacherForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            username = email.split('@')[0]

            # Create associated User
            user = User.objects.create_user(
                username=username,
                email=email,
                password='cse1234'
            )

            teacher = form.save(commit=False)
            teacher.user = user
            teacher.save()

            messages.success(
                request,
                f'✅ Teacher "{teacher.name}" added.\nUsername: {username}, Password: cse1234'
            )
            return redirect('teacher_list')
    else:
        form = TeacherForm()

    return render(request, 'teachers/add_teacher.html', {'form': form})

def edit_teacher(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)
    if request.method == 'POST':
        form = TeacherForm(request.POST, instance=teacher)
        if form.is_valid():
            form.save()
            messages.success(request, '✅ Teacher updated successfully.')
            return redirect('teacher_list')
    else:
        form = TeacherForm(instance=teacher)
    return render(request, 'teachers/edit_teacher.html', {'form': form})

def delete_teacher(request, pk):
    teacher = get_object_or_404(Teacher, pk=pk)
    if request.method == 'POST':
        teacher.delete()
        messages.success(request, '🗑️ Teacher deleted successfully.')
        return redirect('teacher_list')
    return render(request, 'teachers/delete_teacher.html', {'teacher': teacher})
import re

def get_semester_from_subject(subject):
    # Extract the first 3-digit code from the subject string
    match = re.search(r'\b(\d{3})\b', subject)
    if match:
        code = int(match.group(1))
        if 100 <= code <= 149:
            return '1-1'
        elif 150 <= code <= 199:
            return '1-2'
        elif 200 <= code <= 249:
            return '2-1'
        elif 250 <= code <= 299:
            return '2-2'
        elif 300 <= code <= 349:
            return '3-1'
        elif 350 <= code <= 399:
            return '3-2'
        elif 400 <= code <= 449:
            return '4-1'
        elif 450 <= code <= 499:
            return '4-2'
    return 'Unknown'

@login_required
def online_rescheduled_classes(request):
    rescheduled_classes = Reschedule.objects.filter(is_online=True).select_related('class_schedule__teacher').order_by('-reschedule_date')

    # Annotate semester info on each reschedule object
    for reschedule in rescheduled_classes:
        subject = reschedule.class_schedule.subject
        reschedule.semester = get_semester_from_subject(subject)

    return render(request, 'teachers/online_rescheduled_list.html', {
        'rescheduled_classes': rescheduled_classes
    })





