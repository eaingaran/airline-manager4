FROM selenium/standalone-chrome:latest

WORKDIR /app

RUN sudo apt-get update
RUN sudo apt install -y python3
RUN sudo apt install -y python3-pip

COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY airline-manager4.py airline-manager4.py
COPY logger.cfg logger.cfg
EXPOSE 8080

CMD ["python3", "airline-manager4.py"]