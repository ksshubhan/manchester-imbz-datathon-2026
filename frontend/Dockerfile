# StudentShield front end. Built on the same LinuxONE (s390x) base image as mule-service,
# so the image layers are already on the VM and nothing has to be downloaded from Docker Hub.
FROM registry.linuxone.cloud.marist.edu/l1cc/jupyterlab-image-s390x:latest
USER root
RUN pip install --no-cache-dir flask
WORKDIR /app
COPY . /app
ENV PORT=5000 MODEL_URL=http://mule-service:5000
EXPOSE 5000
CMD ["python3", "/app/app.py"]
