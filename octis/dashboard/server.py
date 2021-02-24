import argparse
import webbrowser
import octis.dashboard.frameworkScanner as fs
import octis.configuration.defaults as defaults
from multiprocessing import Process, Pool
import json
from flask import Flask, render_template, request
import os

app = Flask(__name__)
queueManager = ""


@app.route("/serverClosed")
def serverClosed():
    """
    Reroute to the serverClosed page before server shutdown
    """
    return render_template("serverClosed.html")


@app.route("/shutdown")
def shutdown():
    """
    Save the state of the QueueManager and perform server shutdown
    """
    queueManager.stop()
    shutdown_server()
    return {"DONE": "YES"}


@app.route('/')
def home():
    """
    Return the OCTIS landing page
    """
    return render_template("index.html")


@app.route('/startExperiment', methods=['POST'])
def startExperiment():
    """
    Add a new experiment to the queue
    """
    data = request.form.to_dict(flat=False)
    batch = data["batchId"][0]
    experimentId = data["expId"][0]
    if queueManager.getExperiment(batch, experimentId):
        return VisualizeExperiments()

    expParams = dict()
    expParams["partitioning"] = ("partitioning" in data)
    expParams["path"] = data["path"][0]
    expParams["dataset"] = data["dataset"][0]
    expParams["model"] = {"name": data["model"][0]}
    expParams["optimization"] = {
        "iterations": typed(data["iterations"][0]),
        "model_runs": typed(data["runs"][0]),
        "surrogate_model": data["surrogateModel"][0],
        "n_random_starts": typed(data["n_random_starts"][0]),
        "acquisition_function": data["acquisitionFunction"][0],
        "search_spaces": {}
    }
    expParams["optimize_metrics"] = []
    expParams["track_metrics"] = []

    model_parameters_to_optimize = []

    for key, value in data.items():
        if "_check" in key:
            model_parameters_to_optimize.append(key.replace("_check", ''))

    for key, value in data.items():
        if "model." in key:
            if any(par in key for par in model_parameters_to_optimize):
                if "_xminx" in key:
                    name = key.replace("_xminx", '').replace("model.", '')
                    if name not in expParams["optimization"]["search_spaces"]:
                        expParams["optimization"]["search_spaces"][name] = {}
                    expParams["optimization"]["search_spaces"][name]["low"] = typed(
                        value[0])
                elif "_xmaxx" in key:
                    name = key.replace("_xmaxx", '').replace("model.", '')
                    if name not in expParams["optimization"]["search_spaces"]:
                        expParams["optimization"]["search_spaces"][name] = {}
                    expParams["optimization"]["search_spaces"][name]["high"] = typed(
                        value[0])
                elif "_check" not in key:
                    expParams["optimization"]["search_spaces"][key.replace(
                        "model.", '')] = request.form.getlist(key)
            else:
                if "name" in key:
                    expParams["model"][key.replace("model.", '')] = value[0]
                else:
                    if "parameters" not in expParams["model"]:
                        expParams["model"]["parameters"] = {}
                    expParams["model"]["parameters"][key.replace(
                        "model.", '')] = typed(value[0])

        if "metric." in key:
            optimize = True
            metric = {"name": key.replace("metric.", ''), "parameters": {}}
            for singleValue in value:

                for key, content in json.loads(singleValue).items():
                    if key != "metric" and key != "type":
                        metric["parameters"][key] = typed(content)
                    if key == "type" and content == "track":
                        optimize = False
                if optimize:
                    expParams["optimize_metrics"].append(metric)
                else:
                    expParams["track_metrics"].append(metric)

    print(expParams)

    queueManager.add_experiment(batch, experimentId, expParams)
    return CreateExperiments()


@app.route("/getBatchExperiments", methods=['POST'])
def getBatchExperiments():
    """
    return the information related to the experiments of a batch
    """
    data = request.json['data']
    experiments = []
    for key in data:
        batch_experiments = queueManager.getBatchExperiments(key)
        for experiment in batch_experiments:
            new_exp = experiment
            new_exp["optimization_data"] = queueManager.getExperimentInfo(
                experiment["batchId"],
                experiment["experimentId"])
            experiments.append(new_exp)
    return json.dumps(experiments)


@app.route('/CreateExperiments')
def CreateExperiments():
    """
    Serve the experiment creation page
    """
    models = defaults.model_hyperparameters
    models_descriptions = defaults.model_descriptions
    datasets = fs.scanDatasets()
    metrics = defaults.metric_parameters
    optimization = defaults.optimization_parameters
    return render_template("CreateExperiments.html",  datasets=datasets, models=models, metrics=metrics,
                           optimization=optimization, models_descriptions=models_descriptions)


@app.route('/VisualizeExperiments')
def VisualizeExperiments():
    """
    Serve the experiments visualization page
    """
    batch_names = queueManager.getBatchNames()
    return render_template("VisualizeExperiments.html",
                           batchNames=batch_names)


@app.route('/ManageExperiments')
def ManageExperiments():
    """
    Serve the ManageExperiments page
    """
    exp_list = queueManager.getToRun()
    for exp in exp_list:
        exp_info = queueManager.getExperimentInfo(
            exp_list[exp]["batchId"], exp_list[exp]["experimentId"])
        if exp_info != False:
            exp_list[exp].update(exp_info)
    order = queueManager.getOrder()
    running = queueManager.getRunning()
    return render_template("ManageExperiments.html",
                           order=order,
                           experiments=exp_list,
                           running=running)


@app.route("/pauseExp", methods=["POST"])
def pauseExp():
    """
    Pause the current experiment
    """
    queueManager.pause()
    return {"DONE": "YES"}


@app.route("/startExp", methods=["POST"])
def startExp():
    """
    Start the next experiment in the queue
    """
    print(queueManager.getRunning())
    if queueManager.getRunning() == None:
        queueManager.next()
    return {"DONE": "YES"}


@app.route("/deleteExp", methods=["POST"])
def deleteExp():
    """
    Delete the selected experiment from the queue
    """
    data = request.json['data']
    print(queueManager.getRunning())
    if queueManager.getRunning() != None and queueManager.getRunning() == data:
        queueManager.pause()
        queueManager.deleteFromOrder(data)
    else:
        queueManager.deleteFromOrder(data)
    return {"DONE": "YES"}


@app.route("/updateOrder", methods=["POST"])
def updateOrder():
    """
    Update the order of the experiments in the queue
    """
    data = request.json['data']
    queueManager.editOrder(data)
    return {"DONE": "YES"}


@app.route("/getDocPreview", methods=["POST"])
def getDocPreview():
    """
    Returns the first 40 words of the selected document
    """
    data = request.json['data']
    return json.dumps({"doc": fs.getDocPreview(data["dataset"], int(data["document"]))})


@app.route('/SingleExperiment/<batch>/<exp_id>')
def SingleExperiment(batch="", exp_id=""):
    """
    Serve the single experiment page
    """
    models = defaults.model_hyperparameters
    output = queueManager.getModel(batch, exp_id, 0, 0)
    global_info = queueManager.getExperimentInfo(batch, exp_id)
    iter_info = queueManager.getExperimentIterationInfo(batch, exp_id, 0)
    exp_info = queueManager.getExperiment(batch, exp_id)
    exp_ids = queueManager.getAllExpIds()
    vocabulary_path = os.path.join(exp_info["path"],
                                   exp_info["experimentId"],
                                   "models",
                                   "vocabulary.json")
    vocabulary = fs.getVocabulary(vocabulary_path)

    return render_template("SingleExperiment.html", batchName=batch, experimentName=exp_id,
                           output=output, globalInfo=global_info, iterationInfo=iter_info,
                           expInfo=exp_info, expIds=exp_ids, datasetMetadata=fs.getDatasetMetadata(
            exp_info["dataset"]), vocabulary=vocabulary, models=models)


@app.route("/getIterationData", methods=["POST"])
def getIterationData():
    """
    Return data of a single iteration and model run of an experiment 
    """
    data = request.json['data']
    output = queueManager.getModel(data["batchId"], data["experimentId"],
                                   int(data["iteration"]), data["model_run"])
    iter_info = queueManager.getExperimentIterationInfo(data["batchId"], data["experimentId"],
                                                        int(data["iteration"]))
    return {"iterInfo": iter_info, "output": output}


def typed(value):
    """
    Handles typing of data
    """
    try:
        t = int(value)
        return t
    except ValueError:
        try:
            t = float(value)
            return t
        except ValueError:
            return value


def shutdown_server():
    """
    Perform server shutdown
    """
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()


if __name__ == '__main__':
    """
    Initialize the server
    """
    from octis.dashboard.queueManager import QueueManager

    queueManager = QueueManager()
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, help="port", default=5000)
    parser.add_argument("--host", type=str, help="host", default='localhost')

    args = parser.parse_args()

    url = 'http://' + str(args.host) + ':' + str(args.port)
    webbrowser.open_new(url)
    app.run(port=args.port)
