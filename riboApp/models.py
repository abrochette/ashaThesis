from django.db import models

# Create your models here.
# this is database you can create and add to with classes
# after adding to this, run "python manage.py makemigrations riboApp" then "python manage.py migrate"

class ToDoList(models.Model):
    name = models.CharField(max_length=200)

    def __str__(self):
        return self.name

class Item(models.Model):
    todolist = models.ForeignKey(ToDoList, on_delete=models.CASCADE)
    text = models.CharField(max_length=400)
    complete = models.BooleanField()

    def __str__(self):
        return self.text

class ProcessingInput(models.Model):
    experimentName = models.CharField(max_length=200)
    adapter = models.CharField(max_length=500)
    mouseGenome = models.BooleanField()
    humanGenome = models.BooleanField()
    sampleFile = models.FileField(upload_to='uploads/')

    def __str__(self):
        return self.adapter

class UploadedParquet(models.Model):
    file = models.FileField(upload_to="parquetFiles/")  # Stores uploaded file location
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.file.name
class ParquetData(models.Model):
    transcript_id = models.CharField(max_length=255, db_index=True, default="NA")  # Index for quick lookups
    gene_name = models.CharField(max_length=255, db_index=True, default="NA")  # Gene name as indexed field
    start_position = models.IntegerField(default=0)
    end_position = models.IntegerField(default=0)
    strand = models.CharField(max_length=1, default="NA")  # "+" or "-"
    read_id = models.CharField(max_length=255, default="NA")
    read_length = models.IntegerField(default=0)
    read_count = models.IntegerField(default=0)
    region = models.CharField(max_length=50, default="NA")
    source_file = models.CharField(max_length=50, default="NA")

    # Store any additional columns as JSON (for flexibility)
    additional_data = models.JSONField(null=True, blank=True)

    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transcript_id} ({self.gene_name})"# adding to database from terminal:

class SelectedGene(models.Model):
    gene_name = models.CharField(max_length=255, unique=True)
    selected_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.gene_name

# (InteractiveConsole)
# >>> from riboApp.models import Item, ToDoList
# >>> t = ToDoList(name="Asha\'s list")
# >>> t.save()
# >>> ToDoList.objects.all()
# <QuerySet [<ToDoList: Asha's list>]>
# >>> ToDoList.objects.get(id=1)
# <ToDoList: Asha's list>
# >>> a.filter(name__startswith="Asha")
# <QuerySet [<ToDoList: Asha's list>, <ToDoList: Asha's List>]>
