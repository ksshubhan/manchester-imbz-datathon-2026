# Mule early-warning scoring service for IBM LinuxONE (s390x).
# Built on the LinuxONE Community Cloud Jupyter image, which already has
# s390x builds of numpy and xgboost, so nothing heavy has to compile.
FROM registry.linuxone.cloud.marist.edu/l1cc/jupyterlab-image-s390x:latest

USER root
RUN pip install --no-cache-dir flask

WORKDIR /app
COPY app.py dashboard.html /app/

ENV DATA_DIR=/data \
    PORT=5000
EXPOSE 5000

CMD ["python3", "/app/app.py"]
