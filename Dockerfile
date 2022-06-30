FROM selenium/standalone-chrome:latest

WORKDIR /app

RUN sudo apt-get update
RUN sudo apt install -y python3 python3-pip


COPY ["airline_manager4.py", "logger.cfg", "planes.json", "hubs.json", "airports.json", "requirements.txt", "./"]
RUN pip3 install -r requirements.txt

EXPOSE 8080
CMD ["python3", "airline_manager4.py"]