"""
Elastic Beanstalk application entry point.
This file is required by Elastic Beanstalk's default Python platform.
"""
from ashaThesis.wsgi import application

if __name__ == "__main__":
    application()

