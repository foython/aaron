from django.db import models

# Create your models here.
from accounts.models import TimeStamp
from django.contrib.auth import get_user_model

User = get_user_model()


class Department(TimeStamp):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name
    

class Team(TimeStamp):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name
    


class Project(TimeStamp):
    user = models.ForeignKey(User, on_delete=models.CASCADE)    
    process = models.CharField(max_length=128)
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    csv_file = models.FileField(upload_to='csv_files/')
    status = models.BooleanField(default=False)

    def __str__(self):
        return self.process



class DefineColumns(TimeStamp):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    happy_path = models.BooleanField(default=False)
    case_id = models.CharField(max_length=128)
    activity = models.CharField(max_length=128)
    timestamp_start = models.CharField(max_length=128)
    timestamp_end = models.CharField(max_length=128)

    def __str__(self):
        return self.project.process
    


