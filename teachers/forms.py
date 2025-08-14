from django import forms
from django.utils import timezone
from datetime import datetime, timedelta
from django.core.exceptions import ValidationError
from .models import Reschedule, Teacher



class RescheduleForm(forms.ModelForm):
    is_online = forms.TypedChoiceField(
        choices=[(True, 'Online'), (False, 'Offline')],
        coerce=lambda x: x == 'True',
        widget=forms.RadioSelect
    )

    selected_slot = forms.ChoiceField(
        choices=[],  # filled dynamically
        required=False
    )

    new_start_time = forms.TimeField(required=False, widget=forms.TimeInput(attrs={'type': 'time'}))
    new_end_time = forms.TimeField(required=False, widget=forms.TimeInput(attrs={'type': 'time'}))

    class Meta:
        model = Reschedule
        fields = ['reschedule_date', 'is_online', 'selected_slot', 'new_start_time', 'new_end_time']
        widgets = {
            'reschedule_date': forms.DateInput(attrs={'type': 'date'}),
            'new_start_time': forms.TimeInput(attrs={'type': 'time'}),
            'new_end_time': forms.TimeInput(attrs={'type': 'time'}),
        }

    def __init__(self, *args, **kwargs):
        self.class_schedule = kwargs.pop('class_schedule', None)
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        is_online = cleaned_data.get('is_online')
        reschedule_date = cleaned_data.get('reschedule_date')

        if not reschedule_date:
            raise forms.ValidationError("Please select a reschedule date.")

        # Friday=4, Saturday=5
        weekday = reschedule_date.weekday()

        if is_online:
            if not cleaned_data.get('new_start_time') or not cleaned_data.get('new_end_time'):
                raise forms.ValidationError("Online class requires start and end times.")
        else:
            if weekday in [4, 5]:
                raise forms.ValidationError("Offline classes are NOT allowed on Friday or Saturday.")

            if not cleaned_data.get('selected_slot'):
                raise forms.ValidationError("Offline class requires selecting a slot.")

        return cleaned_data

class TeacherForm(forms.ModelForm):
    class Meta:
        model = Teacher
        fields = ['name', 'email', 'designation', 'department']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'designation': forms.TextInput(attrs={'class': 'form-control'}),
            'department': forms.TextInput(attrs={'class': 'form-control'}),
        }
