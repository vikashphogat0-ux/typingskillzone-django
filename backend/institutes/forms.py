from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction

from .models import Institute

User = get_user_model()


class InstituteRegistrationForm(forms.ModelForm):
    owner_name = forms.CharField(max_length=150, label="Owner's full name")
    owner_email = forms.EmailField(label="Owner's email address")
    owner_phone = forms.CharField(max_length=20, label="Owner's phone number")
    password = forms.CharField(widget=forms.PasswordInput, label="Create password")
    confirm_password = forms.CharField(widget=forms.PasswordInput, label="Confirm password")

    class Meta:
        model = Institute
        fields = ["name", "email", "phone", "address", "city", "state", "postal_code"]

    def clean_owner_email(self):
        email = User.objects.normalize_email(self.cleaned_data["owner_email"]).lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")
        if password and confirm_password and password != confirm_password:
            self.add_error("confirm_password", "Passwords do not match.")
        if password:
            try:
                validate_password(password)
            except forms.ValidationError as error:
                self.add_error("password", error)
        return cleaned_data

    @transaction.atomic
    def save(self, commit=True):
        if not commit:
            raise ValueError("Institute registration must be saved atomically.")
        owner = User.objects.create_user(
            email=self.cleaned_data["owner_email"],
            password=self.cleaned_data["password"],
            first_name=self.cleaned_data["owner_name"],
            phone=self.cleaned_data["owner_phone"],
            role=User.Roles.INSTITUTE_OWNER,
            is_active=True,
        )
        institute = super().save(commit=False)
        institute.owner = owner
        institute.email = institute.email.strip()
        institute.phone = institute.phone.strip()
        institute.status = Institute.Status.PENDING
        institute.save()
        return institute


class InstituteAdminEditForm(forms.ModelForm):
    class Meta:
        model = Institute
        fields = ["name", "email", "phone", "address", "city", "state", "postal_code"]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 4}),
        }


class InstituteMemberAddForm(forms.Form):
    email = forms.EmailField(label="Registered account email")
    role = forms.ChoiceField(
        choices=[
            (User.Roles.STUDENT, "Student"),
            (User.Roles.INSTITUTE_STAFF, "Institute staff"),
        ],
        label="Membership type",
    )

    def __init__(self, *args, institute, **kwargs):
        self.institute = institute
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        try:
            user = User.objects.get(email__iexact=email, is_active=True)
        except User.DoesNotExist:
            raise forms.ValidationError(
                "No active account was found for this email. Ask the person to register first."
            )
        if user.role not in {User.Roles.STUDENT, User.Roles.INSTITUTE_STAFF}:
            raise forms.ValidationError(
                "Only student and institute staff accounts can be added."
            )
        self.member_user = user
        return email

    def clean(self):
        cleaned_data = super().clean()
        user = getattr(self, "member_user", None)
        if user and self.institute.memberships.filter(user=user).exists():
            self.add_error("email", "This account already has a membership in this institute.")
        return cleaned_data

    def save(self):
        from .models import InstituteMembership

        user = self.member_user
        role = (
            InstituteMembership.Role.STUDENT
            if user.role == User.Roles.STUDENT
            else InstituteMembership.Role.STAFF
        )
        return InstituteMembership.objects.create(
            institute=self.institute,
            user=user,
            role=role,
            is_active=True,
        )
