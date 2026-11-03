# Merge the two independent institute migration branches.
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("institutes", "0002_alter_institute_registration_code"),
        ("institutes", "0002_subscriptionplan_institutesubscription"),
    ]

    operations = []
