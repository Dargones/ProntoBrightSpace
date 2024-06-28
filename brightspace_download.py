import json
import requests
import datetime
import os
import glob
import zipfile
import re
from requests.auth import HTTPBasicAuth
import shutil

API_VERSION = '1.18'
AUTH_SERVICE = 'https://auth.brightspace.com/'
CONFIG_LOCATION = 'config.json'

TO_DOWNLOAD = ["Users", "Organizational Units", "User Enrollments", "Organizational Unit Descendants"]
ID_LINES = {"Users": 1, "Organizational Units": 1, "User Enrollments": 2, "Organizational Unit Descendants": 2}

def get_config():
    with open(CONFIG_LOCATION, 'r') as f:
        return json.load(f)


def trade_in_refresh_token(config):
    response = requests.post(
        '{}/core/connect/token'.format(config['auth_service']),
        data={
            'grant_type': 'refresh_token',
            'refresh_token': config['refresh_token'],
            'scope': 'datahub:dataexports:*'
        },
        auth=HTTPBasicAuth(config['client_id'], config['client_secret'])
    )

    if response.status_code != 200:
        response.raise_for_status()

    return response.json()


def put_config(config):
    with open(CONFIG_LOCATION, 'w') as f:
        json.dump(config, f, sort_keys=True)


def get_with_auth(endpoint, access_token):
    headers = {'Authorization': 'Bearer {}'.format(token_response['access_token'])}
    response = requests.get(endpoint, headers=headers)

    if response.status_code != 200:
        response.raise_for_status()

    return response


def get_dataset_link_mapping(config, access_token):
    data_sets = []
    next_page_url = '{bspace_url}/d2l/api/lp/{lp_version}/dataExport/bds'.format(
        bspace_url=config['bspace_url'],
        lp_version=API_VERSION
    )

    while next_page_url is not None:
        print("Reading dataset table...")
        list_response = get_with_auth(next_page_url, access_token)
        list_json = list_response.json()

        data_sets += list_json['BrightspaceDataSets']
        next_page_url = list_json['NextPageUrl']

    data_sets = {entry['Name']: [(entry['DownloadLink'], datetime.datetime.strptime(entry['CreatedDate'], "%Y-%m-%dT%H:%M:%S.%fZ"))] +
                                [(previous['DownloadLink'], datetime.datetime.strptime(previous['CreatedDate'], "%Y-%m-%dT%H:%M:%S.%fZ"))
                                 for previous in (entry['PreviousDataSets'] if entry['PreviousDataSets'] is not None else [])]
                 for entry in data_sets}
    return data_sets


if __name__ == '__main__':
    config = get_config()
    config['auth_service'] = config.get('auth_service', AUTH_SERVICE)

    token_response = trade_in_refresh_token(config)

    # Store the new refresh token for getting a new access token next run
    config['refresh_token'] = token_response['refresh_token']
    put_config(config)

    dataset_to_link = get_dataset_link_mapping(config, token_response['access_token'])
    # Create a timestamped directory for the BrightSpace files
    brightspace_dir = "BrightSpace_" + datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    os.makedirs(brightspace_dir, exist_ok=True)
    for dataset in TO_DOWNLOAD:
        print(f"Downloading {dataset}...")
        response = get_with_auth(
            endpoint=dataset_to_link[dataset][0][0],
            access_token=token_response['access_token']
        )
        with open(os.path.join(brightspace_dir, dataset+".zip"), "wb") as file:
            file.write(response.content)
        date = dataset_to_link[dataset][0][1]
        if dataset + " Differential" not in dataset_to_link.keys():
            continue
        for i, differential in enumerate(dataset_to_link[dataset + " Differential"]):
            differential_date = differential[1]
            if differential_date > date:
                response = get_with_auth(
                    endpoint=differential[0],
                    access_token=token_response['access_token']
                )
                with open(os.path.join(brightspace_dir, dataset + f" Differential_{i}.zip"), "wb") as file:
                    file.write(response.content)
    file_names = glob.glob(brightspace_dir + "/*")
    # Unzip all BrightSpace zip files
    print("Unzipping...")
    for i, file_name in enumerate(file_names):
        if file_name.endswith(".zip"):
            match = re.match(".*Differential_([0-9]+).zip", file_name)
            if not match:
                with zipfile.ZipFile(file_name, 'r') as zip_ref:
                    zip_ref.extractall(brightspace_dir)
                continue
            diff_index = match.group(1)
            diff_path = os.path.join(brightspace_dir, f"Tmp{i}")
            with zipfile.ZipFile(file_name, 'r') as zip_ref:
                with zipfile.ZipFile(file_name, 'r') as zip_ref:
                    zip_ref.extractall(diff_path)
            differential_files = glob.glob(diff_path + "/*")
            for diff_file_name in differential_files:
                base_name = os.path.basename(diff_file_name)
                diff_file_name_new = os.path.join(brightspace_dir, base_name[:-4] + f"Differential{diff_index}" + base_name[-4:])
                shutil.copyfile(diff_file_name, diff_file_name_new)
            shutil.rmtree(diff_path)
    print("Merging with Differential...")
    for dataset in TO_DOWNLOAD:
        dataset_name = re.sub(" ", "", dataset)
        lines = open(os.path.join(brightspace_dir, dataset_name + ".csv"), encoding="utf-8").readlines()
        differentials = [filename for filename in glob.glob(brightspace_dir + "/*") if re.match(f".*{dataset_name}Differential[0-9]+.csv", filename)]
        differentials = sorted(differentials, reverse=True)
        for differential in differentials:
            differential_lines = open(differential,encoding="utf-8").readlines()[1:]
            for line in differential_lines:
                ids = ",".join(line.split(",")[:ID_LINES[dataset]]) + ","
                to_remove = [line for line in lines if line.startswith(ids)]
                for line_to_remove in to_remove:
                    lines.remove(line_to_remove)
                lines.append(line)
        with open(os.path.join(brightspace_dir, dataset_name + ".csv"), "w", encoding="utf-8") as file:
            for line in lines:
                file.write(line)



