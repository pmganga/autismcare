from django import forms
from django.contrib.auth import get_user_model

from .models import Learner, LearningSession


class TeacherRegisterForm(forms.Form):
    full_name = forms.CharField(max_length=150, label="Full name",
                                widget=forms.TextInput(attrs={"autocomplete": "name"}))
    school_name = forms.CharField(max_length=200, label="School",
                                  widget=forms.TextInput(attrs={"autocomplete": "organization"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                               min_length=12, help_text="At least 12 characters.")
    password_confirm = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                                       label="Confirm password")

    def clean_email(self):
        email = self.cleaned_data["email"]
        if get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        data = super().clean()
        if data.get("password") and data.get("password") != data.get("password_confirm"):
            self.add_error("password_confirm", "The passwords do not match.")
        return data


class LearnerForm(forms.ModelForm):
    class Meta:
        model = Learner
        fields = ["nickname", "current_level"]
        labels = {"current_level": "Starting level (1 = easiest, 5 = hardest)"}

    def __init__(self, *args, teacher=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.teacher = teacher

    def clean_nickname(self):
        nickname = self.cleaned_data["nickname"].strip()
        if self.teacher and self.teacher.learners.filter(nickname__iexact=nickname).exists():
            raise forms.ValidationError("You already have a learner with this nickname.")
        return nickname


class SessionSettingsForm(forms.Form):
    """Activity diagram: 'Configure sensory settings (audio on/off, colour mode)'."""

    audio_enabled = forms.BooleanField(required=False, initial=True, label="Audio: speak words and play calm sounds")
    sensory_mode = forms.ChoiceField(
        choices=LearningSession.SensoryMode.choices, initial=LearningSession.SensoryMode.SOFT,
        widget=forms.RadioSelect, label="Colour mode",
    )
    planned_cards = forms.TypedChoiceField(
        choices=[(n, f"{n} cards") for n in (6, 9, 12, 15)], coerce=int, initial=9, label="Session length",
        help_text="The level is checked after every 3 cards.",
    )
