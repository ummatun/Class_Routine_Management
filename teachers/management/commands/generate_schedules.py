from django.core.management.base import BaseCommand
from routine.models import Routine
from teachers.models import ClassSchedule
from datetime import timedelta, datetime
from django.db import IntegrityError

class Command(BaseCommand):
    help = 'Generate ClassSchedule entries from Routine between start_date and end_date'

    def add_arguments(self, parser):
        parser.add_argument('start_date', type=str, help='Semester start date in YYYY-MM-DD format')
        parser.add_argument('end_date', type=str, help='Semester end date in YYYY-MM-DD format')

    def handle(self, *args, **options):
        start_date = datetime.strptime(options['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(options['end_date'], '%Y-%m-%d').date()

        day_name_to_num = {
            'Monday': 0, 'Tuesday': 1, 'Wednesday': 2,
            'Thursday': 3, 'Friday': 4, 'Saturday': 5, 'Sunday': 6,
        }

        routines = Routine.objects.all()

        # Optional: define vacation dates here or fetch from model if available
        vacation_dates = []  # e.g., [date(2025, 8, 15), date(2025, 9, 10)]

        # Delete previously generated schedules for the date range
        deleted_count, _ = ClassSchedule.objects.filter(date__range=(start_date, end_date)).delete()

        created_count = 0
        skipped_conflicts = 0
        conflict_logs = []

        current_date = start_date
        while current_date <= end_date:
            if current_date in vacation_dates:
                current_date += timedelta(days=1)
                continue

            weekday_num = current_date.weekday()

            for routine in routines:
                routine_day_num = day_name_to_num.get(routine.slot.day)
                if routine_day_num == weekday_num:
                    conflict = ClassSchedule.objects.filter(
                        room=routine.room,
                        date=current_date,
                        start_time=routine.slot.start_time
                    ).exists()

                    if conflict:
                        skipped_conflicts += 1
                        conflict_logs.append(
                            f"{routine.course.code} ({routine.room.number}) at {routine.slot.start_time} on {current_date}"
                        )
                        continue

                    try:
                        ClassSchedule.objects.create(
                            course=routine.course,
                            teacher=routine.teacher,
                            room=routine.room,
                            date=current_date,
                            original_date=current_date,
                            semester=routine.batch,
                            start_time=routine.slot.start_time,
                            end_time=routine.slot.end_time,
                            status='pending',
                            class_type='offline',
                        )
                        created_count += 1
                    except IntegrityError:
                        skipped_conflicts += 1

            current_date += timedelta(days=1)

        self.stdout.write(self.style.SUCCESS(
            f"✅ {created_count} ClassSchedules created.\n🗑️ {deleted_count} old entries deleted.\n❌ {skipped_conflicts} skipped due to room conflicts."
        ))

        if conflict_logs:
            self.stdout.write(self.style.WARNING("\n🔁 Room conflicts log:"))
            for log in conflict_logs:
                self.stdout.write(f" - {log}")
