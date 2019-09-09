import logging
import os
import signal
import subprocess
import sys
import threading
import time
import traceback

logging.basicConfig(level=logging.ERROR)

_Worker_Thread = None
exit_evt = threading.Event()

PS_OUTPUT = ''

class UpdateMetricsThread(threading.Thread):
    def __init__(self, params):
        threading.Thread.__init__(self)
        self.running = False
        self.shuttingdown = False
        self.refresh_rate = int(params.get('refresh_rate', 60))

        self._metrics_lock = threading.Lock()

    def shutdown(self):
        self.shuttingdown = True
        if not self.running:
            return
        self.join()

    def run(self):
        global exit_evt
        self.running = True

        while not self.shuttingdown:
            exit_evt.wait(timeout=self.refresh_rate)
            self.refresh_metrics()

        self.running = False 

    def refresh_metrics(self):
        global PS_OUTPUT
        logging.debug('refresh metrics')

        try:
            logging.debug(' calling ps')
            data = UpdateMetricsThread._get_ps_output()
        except:
            logging.warning('error refreshing metrics')
            logging.warning(traceback.print_exc(file=sys.stdout))

        try:
            self._metrics_lock.acquire()
            PS_OUTPUT = data
        except:
            logging.warning('error refreshing metrics')
            logging.warning(traceback.print_exc(file=sys.stdout))
            return False

        finally:
            self._metrics_lock.release()

        logging.debug('success refreshing metrics')
        logging.debug('metrics: %s' % (PS_OUTPUT,))

        return True
    
    @staticmethod
    def _get_ps_output():
        # /bin/ps -C sas o user,rss,etimes --no-headers | awk '{rss[$1] += $2; etimes[$1] = $3} END { for (i in rss) print i","rss[i]","etimes[i];}'
        cmd = '/bin/ps -C sas o user,rss,etimes --no-headers | /usr/bin/awk \'{rss[$1] += $2; etimes[$1] = $3} END { for (i in rss) print i" "rss[i]" "etimes[i];}\''
        try:
            output = subprocess.check_output(cmd, shell=True)
        except Exception as e:
            logging.error(e)
            output = ''
        return [line for line in output.split('\n') if line]

def get_count(name):
    global PS_OUTPUT
    if not PS_OUTPUT:
        return 0
    return len(PS_OUTPUT)

def get_total_rss_in_gb(name):
    # rss is in kilobytes
    global PS_OUTPUT
    if not PS_OUTPUT:
        return 0
    return sum([float(line.split()[1])/1024/1024 for line in PS_OUTPUT])

def get_average_rss_in_gb(name):
    global PS_OUTPUT
    if not PS_OUTPUT:
        return 0
    return sum([float(line.split()[1])/1024/1024 for line in PS_OUTPUT]) / len(PS_OUTPUT)

def get_average_session_length_in_minutes(name):
    global PS_OUTPUT
    if not PS_OUTPUT:
        return 0
    return sum([float(line.split()[2])/60 for line in PS_OUTPUT]) / len(PS_OUTPUT)

def get_max_rss_in_gb(name):
    global PS_OUTPUT
    if not PS_OUTPUT:
        return 0
    return max([float(line.split()[1])/1024/1024 for line in PS_OUTPUT])

def get_max_session_length_in_minutes(name):
    global PS_OUTPUT
    if not PS_OUTPUT:
        return 0
    return max([float(line.split()[2])/60 for line in PS_OUTPUT])

def metric_cleanup(*args):
    global _Worker_Thread
    global exit_evt
    exit_evt.set()
    if _Worker_Thread is not None:
        _Worker_Thread.shutdown()
        logging.shutdown()

def metric_init(params):
    global _Worker_Thread
    _Worker_Thread = UpdateMetricsThread(params)
    _Worker_Thread.refresh_metrics()
    _Worker_Thread.start()

    descriptors = [
        {'name': 'sas_count',
        'call_back': get_count,
        'time_max': 600,
        'value_type': 'uint',
        'units': 'processes',
        'slope': 'both',
        'format': '%d',
        'description': 'Count of sas processes',
        'groups': 'sas_studio,questanalytics'},
        {'name': 'sas_total_mem',
        'call_back': get_total_rss_in_gb,
        'time_max': 600,
        'value_type': 'float',
        'units': 'GB',
        'slope': 'both',
        'format': '%.2f',
        'description': 'Total memory resident set size of sas processes',
        'groups': 'sas_studio,questanalytics'},
        {'name': 'sas_avg_mem',
        'call_back': get_average_rss_in_gb,
        'time_max': 600,
        'value_type': 'float',
        'units': 'GB',
        'slope': 'both',
        'format': '%.2f',
        'description': 'Average memory resident set size of sas processes',
        'groups': 'sas_studio,questanalytics'},
        {'name': 'sas_max_mem',
        'call_back': get_max_rss_in_gb,
        'time_max': 600,
        'value_type': 'float',
        'units': 'GB',
        'slope': 'both',
        'format': '%.2f',
        'description': 'Max memory resident set size of a single sas process',
        'groups': 'sas_studio,questanalytics'},
        {'name': 'sas_avg_session_length',
        'call_back': get_average_session_length_in_minutes,
        'time_max': 600,
        'value_type': 'float',
        'units': 'minutes',
        'slope': 'both',
        'format': '%.2f',
        'description': 'Average session length of sas processes',
        'groups': 'sas_studio,questanalytics'},
        {'name': 'sas_max_session_length',
        'call_back': get_max_session_length_in_minutes,
        'time_max': 600,
        'value_type': 'float',
        'units': 'minutes',
        'slope': 'both',
        'format': '%.2f',
        'description': 'Max session length of a single sas process',
        'groups': 'sas_studio,questanalytics'},
    ]

    signal.signal(signal.SIGINT, metric_cleanup)
    signal.signal(signal.SIGTERM, metric_cleanup)

    return descriptors

if __name__ == '__main__':
    try:
        logging.debug('running from the cmd line')
        descriptors = metric_init({'refresh_rate': 10})

        for d in descriptors:
            v = d['call_back'](d['name'])
            print ' {0}: {1} {2} [{3}]' . format(d['name'], v, d['units'], d['description'])

        time.sleep(20)

        for d in descriptors:
            v = d['call_back'](d['name'])
            print ' {0}: {1} {2} [{3}]' . format(d['name'], v, d['units'], d['description'])

        os._exit(1)

    except StandardError:
        traceback.print_exc()
        os._exit(1)
    finally:
        metric_cleanup() 
