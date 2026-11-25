from django import forms
from django.contrib.auth import get_user_model


# autocomplete lets browsers fill in the user's own details (WCAG 1.3.5, NFR 5)
class RegisterForm(forms.Form):
    full_name = forms.CharField(max_length=150, label="Full name",
                                widget=forms.TextInput(attrs={"autocomplete": "name"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    phone = forms.CharField(max_length=30, widget=forms.TextInput(attrs={"autocomplete": "tel", "type": "tel"}))
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="At least 12 characters.", min_length=12,
    )
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


class LoginForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))
