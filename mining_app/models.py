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
    related_project = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sub_projects'
    )
    is_related = models.BooleanField(default=False)
    copy = models.BooleanField(default=False)
    def __str__(self):
        return f'{self.id} {self.process}'



class DefineColumns(TimeStamp):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    happy_path = models.BooleanField(default=False)
    case_id = models.CharField(max_length=128)
    activity = models.CharField(max_length=128)
    timestamp_start = models.CharField(max_length=128)
    timestamp_end = models.CharField(max_length=128)

    def __str__(self):
        return self.project.process
    


# class HappyPath(TimeStamp):
#     project = models.ForeignKey(Project, on_delete=models.CASCADE)
#     path = models.TextField()

#     def __str__(self):
#         return f"Actual Path for {self.project.process}"
    


class HappyPath(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)     
    serial_number = models.IntegerField()
    activity_name = models.CharField(max_length=100)   
    average_time_minutes = models.DecimalField(max_digits=8, decimal_places=2)
    cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    description = models.JSONField(blank=True, null=True)

    class Meta:        
        ordering = ['serial_number']

    def __str__(self):
        return f"Step {self.serial_number}: {self.activity_name} ({self.average_time_minutes} min)"
    
    def save(self, *args, **kwargs):
        if isinstance(self.description, str):
            self.description = [self.description]
        super().save(*args, **kwargs)
    

class Visualization(TimeStamp):
    type = models.CharField(max_length=128)

    def __str__(self):
        return self.type


class kpiList(TimeStamp):
    kpi_name = models.CharField(max_length=128)
    
    visualizations = models.ManyToManyField(
        Visualization,
        blank=True  
    )

    def __str__(self):
        return self.kpi_name
    

class kpiDashboard(TimeStamp):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    name = models.CharField(max_length=128, blank=True, null=True)
    data = models.JSONField(blank=True, null=True)

    def __str__(self):
        return f"KPI {self.name}"
    


class ProcessVariant(TimeStamp):    
    project = models.ForeignKey(
        Project, 
        on_delete=models.CASCADE, 
        related_name='process_variants',
        verbose_name="Related Project"
    )
    
    variant_path = models.TextField(verbose_name="Process Variant Path")    
    case_count = models.IntegerField(verbose_name="Case Count")
    frequency_pct = models.FloatField(verbose_name="Frequency (%)")    
    median_cycle_time_hours = models.FloatField(
        null=True, 
        blank=True, 
        verbose_name="Median Cycle Time (Hours)"
    )

    class Meta:        
        unique_together = ('project', 'variant_path')       
        ordering = ['-case_count']

    def __str__(self):
        return f"{self.variant_path[:50]}... ({self.case_count} cases)"



class CostPerProcess(TimeStamp):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    activity_name = models.CharField(max_length=128)
    cost_per_h = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.activity_name}"