from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


class StudentRegistrationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, label="Password")
    confirm_password = forms.CharField(widget=forms.PasswordInput, label="Confirm password")

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "phone"]
        widgets = {
            "first_name": forms.TextInput(attrs={"autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"autocomplete": "family-name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "phone": forms.TextInput(attrs={"autocomplete": "tel"}),
        }

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data["email"]).lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        password, confirm = cleaned.get("password"), cleaned.get("confirm_password")
        if password and confirm and password != confirm:
            self.add_error("confirm_password", "Passwords do not match.")
        if password:
            try:
                validate_password(password)
            except forms.ValidationError as error:
                self.add_error("password", error)
        return cleaned

    def save(self):
        data = self.cleaned_data
        return User.objects.create_user(
            email=data["email"],
            password=data["password"],
            first_name=data["first_name"].strip(),
            last_name=data["last_name"].strip(),
            phone=data["phone"].strip(),
            role=User.Roles.STUDENT,
            is_active=False,
            is_email_verified=False,
        )


class StudentProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone"]
        widgets = {
            "first_name": forms.TextInput(attrs={"autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"autocomplete": "family-name"}),
            "phone": forms.TextInput(attrs={"autocomplete": "tel"}),
        }


class InstituteEnrollmentForm(forms.Form):
    registration_code = forms.CharField(max_length=36, label="Institute registration code")

    def __init__(self, *args, student, **kwargs):
        self.student = student
        super().__init__(*args, **kwargs)

    def clean_registration_code(self):
        from institutes.models import Institute, InstituteMembership
        code = self.cleaned_data["registration_code"].strip()
        try:
            institute = Institute.objects.get(
                registration_code__iexact=code,
                status=Institute.Status.APPROVED,
            )
        except Institute.DoesNotExist:
            raise forms.ValidationError("No approved institute was found for this registration code.")
        if InstituteMembership.objects.filter(institute=institute, user=self.student).exists():
            raise forms.ValidationError("You already have a membership with this institute.")
        self.institute = institute
        return code

    def save(self):
        from institutes.models import InstituteMembership
        return InstituteMembership.objects.create(
            institute=self.institute,
            user=self.student,
            role=InstituteMembership.Role.STUDENT,
            is_active=True,
        )
