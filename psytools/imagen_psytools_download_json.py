#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Download Psytools JSON files (FU3).

==========
Attributes
==========

Output
------

PSYTOOLS_FU3_MASTER_DIR : str
    Location of FU3 PSC1-encoded files.

"""

import os
import requests
import json
import base64
from urllib.parse import urlparse
import logging
logging.basicConfig(level=logging.INFO)

PSYTOOLS_FU3_MASTER_DIR = '/neurospin/imagen/FU3/RAW/PSC1/psytools'

JSON_BASE_URL = 'https://www.delosis.com/qs/index.php/admin/remotecontrol'

NETRC_FILE = '~/.lsrc2'


class LimeSurveyError(Exception):
    def __init__(self, message, code):
        super(LimeSurveyError, self).__init__(message)
        self.code = code


def error2exception(func):
    def wrapper(*args, **kwargs):
        response, error = func(*args, **kwargs)
        if error:
            try:
                code = error['code']
                message = error['message']
            except (TypeError, KeyError):
                code = -32603  # internal JSON-RPC error
                message = 'Unexpected JSON-RPC error type'
            raise LimeSurveyError(message, code)
        return response
    return wrapper


class LimeSurveySession(object):
    """LimeSurvey JSON-RPC LSRC2 session

    Documented here:
    https://www.delosis.com/qs/index.php/admin/remotecontrol
    https://manual.limesurvey.org/RemoteControl_2_API

    """
    __request_id = 0

    def __init__(self, url, username, password):
        self.url = url
        # start a Requests session
        self.session = requests.Session()
        # Keep-alive is 100% automatic in Requests, thanks to urllib3
        self.session.headers.update({'content-type': 'application/json'})
        # start a LimeSurvey RemoteControl 2 session
        self.key = self._get_session_key(username, password)

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.close()
        return False  # re-raises the exception

    def close(self):
        """Release LimeSurvey session key, then close Requests session"""
        self._release_session_key(self.key)
        self.key = None
        self.session.close()

    @staticmethod
    def _generate_request_id():
        LimeSurveySession.__request_id += 1
        return LimeSurveySession.__request_id

    @staticmethod
    def _request(method, params):
        return {
            'jsonrpc': '2.0',
            'id': LimeSurveySession._generate_request_id(),
            'method': method,
            'params': params,
        }

    def _post(self, request):
        logging.debug('JSON-RPC request: {0}'.format(request))
        assert 'method' in request and 'params' in request and 'id' in request
        response = self.session.post(self.url, data=json.dumps(request))
        response = response.json()
        logging.debug('JSON-RPC response: {0}'.format(response))
        assert response['id'] == request['id']
        result = response['result']
        error = response['error']
        if error:
            logging.error('JSON-RPC error: {0}'.format(error))
        return result, error

    def _get_session_key(self, username, password):
        request = self._request('get_session_key', [username, password])
        response, error = self._post(request)

        # fix non-sensical LSRC2 error handling
        # completely at odds with JSON-RPC error handling
        try:
            status = response['status']
        except (TypeError, KeyError):
            if error is not None:
                logging.error('LSRC2 failed to create a session key')
                response = None
            else:
                logging.info('LSRC2 new session key: {0}'.format(response))
        else:
            logging.error(status)
            error = {
                'code': -32099,  # implementation-defined error in JSON-RPC
                'message': status,
            }
            response = None

        return response

    def _release_session_key(self, key):
        request = self._request('release_session_key', [key])
        logging.info('LSRC2 release session key: {0}'.format(key))
        response, error = self._post(request)  # returns ('OK', None) even if bogus key

    @error2exception
    def surveys(self):
        request = self._request('list_surveys', [self.key])
        return self._post(request)

    @error2exception
    def participants(self, survey, attributes=False):
        request = self._request('list_participants',
                                [self.key, survey, 0, 5000, False, attributes])
        responses, error = self._post(request)

        # fix non-sensical LSRC2 error handling
        # completely at odds with JSON-RPC error handling
        try:
            status = responses['status']
        except (TypeError, KeyError):
            pass
        else:
            # LSRC2 returns errors as a dict with a 'status' attribute
            if status == 'No Tokens found':
                # When a survey is empty, LSRC2 also returns a dict:
                # {"status": "No Tokens found"}
                if error is not None:
                    logging.error('JSON-RPC error report does not match "status"')
                    error = None
            else:
                error = {
                    'code': -32099,  # implementation-defined error in JSON-RPC
                    'message': status,
                }
            responses = []

        return responses, error

    @error2exception
    def participant_properties(self, survey, participant, attributes):
        request = self._request('get_participant_properties',
                                [self.key, survey, participant, attributes])
        return self._post(request)

    @error2exception
    def responses(self, survey, status='all'):
        request = self._request('export_responses',
                                [self.key, survey, 'json', 'fr', status])
        responses, error = self._post(request)

        try:
            responses = json.loads(base64.b64decode(responses).decode('utf_8'))
        except TypeError:
            # fix non-sensical LSRC2 error handling
            # completely at odds with JSON-RPC error handling
            try:
                status = responses['status']
            except (TypeError, KeyError):
                message = 'JSON-RPC function "export_responses" expected a Base64-encoded string'
                logging.error(message)
                error = {
                    'code': -32099,  # implementation-defined error in JSON-RPC
                    'message': message,
                }
            else:
                # LSRC2 returns errors as a dict with a 'status' attribute
                if status == 'No Data, could not get max id.':
                    # When a survey is empty, LSRC2 also returns a dict:
                    # {"status": "No Data, could not get max id."}
                    if error is not None:
                        logging.error('JSON-RPC error report does not match "status"')
                        error = None
                else:
                    error = {
                        'code': -32099,  # implementation-defined error in JSON-RPC
                        'message': status,
                    }
            responses = {'responses': []}

        return responses, error


def _get_netrc_auth(url):
    try:
        netrc_path = os.path.expanduser(NETRC_FILE)
    except KeyError:
        import warnings
        warnings.warn('Unable to find home directory')
        return
    if not os.path.exists(netrc_path):
        return

    netloc = urlparse(url).netloc

    try:
        from netrc import netrc, NetrcParseError
        try:
            authenticators = netrc(netrc_path).authenticators(netloc)
        except (NetrcParseError, IOError):
            return
        if authenticators:
            return (authenticators[0], authenticators[2])
    except (ImportError):
        return


def download_json(base_url):
    """JSON RPC calls to retrieve new questionnaires.

    """
    username, password = _get_netrc_auth(base_url)
    with LimeSurveySession(base_url, username, password) as session:
        surveys = session.surveys()
        for survey in surveys:
            title = survey['surveyls_title']
            sid = survey['sid']
            print('▶', sid, '▶',  title)

            # subjects in surveys are identified by "sid" and "token"
            # retrieve correlation between "token" and PSC1 code
            psc1_from_token = {}
            participants = session.participants(sid, ['attribute_1'])
            for participant in participants:
                tid = participant['tid']
                token = participant['token']
                psc1_from_token[token] = participant['attribute_1']

            # retrieve survey
            responses = session.responses(sid, 'all')

            # dump survey to JSON format:
            # * change "tid" into PSC1 code
            # * keep "token"
            if 'responses' in responses:
                responses['responses'] = [{psc1_from_token[v['token']]: v
                                           for k, v in r.items()}
                                          for r in responses['responses']]
            data = json.dumps(responses,
                              indent=4, separators=(',', ': '), sort_keys=True)

            # save survey to this file name
            psytools_path = title
            psytools_path = psytools_path.replace(' - ', '-')
            psytools_path = psytools_path.replace(' ', '_')
            psytools_path = os.path.join(PSYTOOLS_FU3_MASTER_DIR,
                                         psytools_path + '.json')

            # skip file that have not changed since last update
            # note that "sort_keys=True" is required for this to work!
            if os.path.isfile(psytools_path):
                with open(psytools_path, 'r') as psytools:
                    if psytools.read() == data:
                        logging.info('skip unchanged file: {0}'
                                     .format(psytools_path))
                        continue

            # write survey into JSON file
            with open(psytools_path, 'w') as psytools:
                logging.info('write file: {0}'.format(psytools_path))
                psytools.write(data)


def main():
    download_json(JSON_BASE_URL)


if __name__ == "__main__":
    main()