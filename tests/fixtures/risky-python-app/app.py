import os
import pickle
import subprocess
import yaml
from flask import Flask
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
DEBUG = True


@app.route('/admin/delete-user', methods=['POST'])
def delete_user():
    return 'deleted'


def run_generated_helper(command, blob, raw_yaml, expression):
    eval(expression)
    os.system(command)
    subprocess.run(command, shell=True)
    pickle.loads(blob)
    return yaml.load(raw_yaml)
