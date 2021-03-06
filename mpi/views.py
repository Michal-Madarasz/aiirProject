import os, io, re, json
import numpy as np
from subprocess import Popen, PIPE, TimeoutExpired
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.conf import settings
from django.core.files.base import ContentFile
from time import gmtime, strftime
from django.http import HttpResponse
from scipy.cluster.hierarchy import dendrogram

from matplotlib import pylab
from pylab import *
import PIL, PIL.Image

from .forms import MpiParameters, DocumentForm, ResultForm
from .models import Document, ResultDocument
from .tasks import *
from background_task.models import Task


@login_required
def task(request):
    if request.method == 'POST':
        m_form = MpiParameters(request.user, request.POST)
        if m_form.is_valid():
            n_process = m_form.cleaned_data['amount_of_process']
            document_id = m_form.cleaned_data['document_id']
            document = Document.objects.filter(id=document_id)[0]
            document_path = os.path.join(settings.MEDIA_ROOT, document.file.name)
            # print(document.file.name)

            # create empty file to save
            content = ''.encode()
            time = strftime("%Y-%m-%d_%H:%M:%S", gmtime())
            result_document = ResultDocument();
            result_document.name = document.name + '_' + time
            result_document.user = request.user
            result_document.file.save('result.txt', ContentFile(content))
            result_document.save()
            result_document_path = os.path.join(settings.MEDIA_ROOT, result_document.file.name)

            mpiTask(n_process, document_path, result_document_path, result_document.id)

            messages.success(request, f'mpirun succesful')
            redirect('task')

    if request.user.is_superuser:
        documents = Document.objects.all()
    else:
        documents = Document.objects.filter(user=request.user)

    context = {
        'm_form': MpiParameters(request.user),
        # 'documents': documents,
        'tasks': getQueue(),
    }

    return render(request, 'task.html', context)


@login_required
def document(request):
    if request.method == 'POST':
        d_form = DocumentForm(request.POST, request.FILES)
        if d_form.is_valid():
            document = Document()
            document.name = d_form.cleaned_data['name']
            document.file = d_form.cleaned_data['file']
            document.user = request.user
            document.save()
            messages.success(request, f'Your file has been added!')
        else:
            messages.error(request, f'Your file has not been added!')

        return redirect('document')

    if request.user.is_superuser:
        documents = Document.objects.all()
    else:
        documents = Document.objects.filter(user=request.user)

    context = {
        'd_form': DocumentForm(),
        'documents': documents,
    }

    return render(request, 'document.html', context)


@login_required
def documentDelete(request, delete_id):
    document = Document.objects.get(id=delete_id)

    if document.user == request.user or request.user.is_superuser:
        if document.delete():
            messages.success(request, f'File has been deleted.')
        else:
            messages.error(request, f'File hasn\'t been delete.')
    else:
        messages.error(request, f'It isn\'t your file.')

    return redirect('document')


@login_required
def resultDocument(request):
    is_show_image = False
    image_id = 0

    if request.method == 'POST':
        rd_form = ResultForm(request.user, request.POST)
        if rd_form.is_valid():
            image_id = rd_form.cleaned_data['result_document_id']
            is_show_image = True

    if request.user.is_superuser:
        result_documents = ResultDocument.objects.filter(ready=True)
    else:
        result_documents = ResultDocument.objects.filter(user=request.user, ready=True)

    context = {
        'rd_form': ResultForm(request.user),
        'result_documents': result_documents,
        'is_show_image': is_show_image,
        'image_id': image_id,
    }

    return render(request, 'result.html', context)





def showimage(request, id):
    # matrix = np.array()
    result_document = ResultDocument.objects.filter(id=id)[0]
    result_document_path = os.path.join(settings.MEDIA_ROOT, result_document.file.name)

    with open(result_document_path, 'r') as file:
        text = file.read().splitlines()
        file.close()

    tmp_array = []
    for line in text:
        line = re.sub("[\[\] ]+|,$|,]$", "", line)
        line = line.split(',')
        line = [float(z) for z in line]
        tmp_array.append(line)

    matrix = np.array(tmp_array)

    figure(figsize=(15, 10))
    title(result_document.name)
    dendogram = dendrogram(matrix, truncate_mode="none")
 
    # Store image in a string buffer
    buffer = io.BytesIO()
    canvas = pylab.get_current_fig_manager().canvas
    canvas.draw()
    pilImage = PIL.Image.frombytes("RGB", canvas.get_width_height(), canvas.tostring_rgb())
    pilImage.save(buffer, "PNG")
    pylab.close()
 
    # Send buffer in a http response the the browser with the mime type image/png set
    return HttpResponse(buffer.getvalue(), content_type="image/png")


def getQueue():
    tasks = Task.objects.order_by('run_at')
    result = []
    for task in tasks:
        line = re.sub("[\[\] ]+|, \{\}", "", task.task_params)
        line = line.split(',')
        result_document = ResultDocument.objects.filter(id=int(line[3]))[0]
        tmp_array = {
            'id' : task.id,
            'name' : result_document.name,
            'n_process' : line[0],
            'time' : task.run_at,
            'locked_by' : task.locked_by,
            'locked_by_pid_running' : task.locked_by_pid_running,
        }
        result.append(tmp_array)

    return result


@login_required
def taskDelete(request, delete_id):
    task = Task.objects.get(id=delete_id)

    if task.delete():
        messages.success(request, f'Task has been deleted.')
    else:
        messages.error(request, f'Task hasn\'t been delete.')

    return redirect('task')