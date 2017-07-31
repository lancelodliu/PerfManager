#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = 'lancelodliu'
import os, time, sys, re
import subprocess
import datetime


# find process ID
def get_pid(_device, package):
    adb_str = "adb -s {} shell ps | grep {}".format(_device, package) if _device else "adb shell ps | grep {}".format(package)

    proc = subprocess.Popen(adb_str, stdout=subprocess.PIPE)
    _lines = [x.split() for x in proc.stdout.readlines()]
    for line in _lines:
        if line[-1].strip() == package:
            return int(line[1])


# find process UID
def get_uid(_device, package):
    adb_str = "adb -s {} shell dumpsys package | grep {} -A 3 | grep userId".format(_device, package) if _device else "adb shell dumpsys package| grep {} -B 1 -A 1 | grep userId".format(package)

    proc = subprocess.Popen(adb_str, stdout=subprocess.PIPE)
    _t = proc.stdout.read()
    uid = _t.split('=')[1].split()[0]
    return int(uid)


class PerfManager(object):
    def __init__(self, _device, package):
        self.__pid = get_pid(_device, package)
        self.__uid = get_uid(_device, package)
        self.__device = _device
        self.__package = package
        self.__layername = None
        self.__time_total_last = 0
        self.__time_user_last = 0
        self.__time_kernel_last = 0
        self.__cpu_last = 0
        self.__recv_all = 0
        self.__send_all = 0
        self.__recv_tcp = 0
        self.__send_tcp = 0
        self.__recv_udp = 0
        self.__send_udp = 0

    def mem_sample(self):
        result = {'NativeHeap': -1, 'DalvikHeap': -1, 'PssTotal': -1}
        if self.__package is None:
            return result
        _p = None
        if self.__device:
            _p = subprocess.Popen("adb -s {} shell dumpsys meminfo {}".format(self.__device, self.__package), stdout=subprocess.PIPE)
        else:
            _p = subprocess.Popen("adb shell dumpsys meminfo {}".format(self.__package), stdout=subprocess.PIPE)
        _lines = [x.lstrip() for x in _p.stdout.readlines()]
        for line in _lines:
            if line.startswith('Native'):
                memory = int(line.split()[2])
                result['NativeHeap'] = memory
            if line.startswith('Dalvik'):
                memory = int(line.split()[2])
                result['DalvikHeap'] = memory
            if line.startswith('TOTAL'):
                memory = int(line.split()[1])
                result['PssTotal'] = memory
        return result

    def cpu_sample(self):
        if self.__package is None:
            return -1
        # analyse CPU
        _p = None
        if self.__device:
            _p = subprocess.Popen("adb -s {} shell cat /proc/stat".format(self.__device), stdout=subprocess.PIPE)
        else:
            _p = subprocess.Popen("adb shell cat /proc/stat", stdout=subprocess.PIPE)
        cpu_line = _p.stdout.readline()
        time_total_now = 0
        data = cpu_line.split()
        for d in data:
            if d.isdigit():
                time_total_now += int(d)
        if self.__device:
            _p = subprocess.Popen("adb -s {} shell cat /proc/{}/stat".format(self.__device, self.__pid), stdout=subprocess.PIPE)
        else:
            _p = subprocess.Popen("adb shell cat /proc/{}/stat".format(self.__pid), stdout=subprocess.PIPE)
        cpu_line = _p.stdout.readline()
        data = cpu_line.split()
        # no data, use last result
        if len(data) < 15:
            print "Get Cpu Error"
            return self.__cpu_last
        time_user_now = int(data[13])
        time_kernel_now = int(data[14])
        if self.__time_total_last != 0:
            cpu = 100.0*(time_user_now - self.__time_user_last + time_kernel_now - self.__time_kernel_last) / (time_total_now - self.__time_total_last)
            if cpu < 1.0:
                cpu = self.__cpu_last
            self.__cpu_last = cpu
        self.__time_total_last = time_total_now
        self.__time_user_last = time_user_now
        self.__time_kernel_last = time_kernel_now
        return self.__cpu_last

        def __calculate_fps_surfaceview(self, results):
        # timestamp in sec
        timestamps = []
        nanoseconds_per_second = 1e9
        pending_fence_timestamp = 9223372036854775807
        for line in results[1:]:
            fields = line.split()
            if len(fields) != 3:
                continue
            timestamp = long(fields[1])
            if timestamp == pending_fence_timestamp or timestamp == 0:
                continue
            timestamp /= nanoseconds_per_second
            timestamps.append(timestamp)
        # no valid data
        if len(timestamps) < 2:
            return 0
        return (len(timestamps) - 1) / (timestamps[-1] - timestamps[0])

    def __fps_sample_6_or_lower(self):
        _p = None
        if self.__device:
            _p = subprocess.Popen("adb -s {} shell dumpsys SurfaceFlinger --latency SurfaceView".format(self.__device),
                                  stdout=subprocess.PIPE)
        else:
            _p = subprocess.Popen("adb shell dumpsys SurfaceFlinger --latency SurfaceView", stdout=subprocess.PIPE)
        results = _p.stdout.readlines()
        return self.__calculate_fps_surfaceview(results)


    def __get_layername(self):
        if self.__device:
            _p = subprocess.Popen("adb -s {} shell dumpsys SurfaceFlinger | grep {}".format(self.__device, self.__package),
                                  stdout=subprocess.PIPE)
        else:
            _p = subprocess.Popen("adb shell dumpsys SurfaceFlinger | grep {}".format(self.__package), stdout=subprocess.PIPE)
        results = _p.stdout.readlines()
        results = filter(lambda x: x.startswith('0x'), results)
        results = [x.split('|')[-1].strip() for x in results]
        results = set(results)
        bestresults = filter(lambda x: 'SurfaceView' in x, results)
        if len(bestresults) > 0:
            return bestresults.pop()
        else:
            return results.pop()


    def __fps_sample_7_or_higher(self):
        # from GAutomator.sgtesttool.collect import collect
        # result = collect('PerfCollect', 'PerfInfo')
        # return result['Fps']
        # 7.0及以上的需要先获取SurfaceView的layername 一般都包含packagename
        # 如果有SurfaceView开头的 优先用这个
        _p = None
        if self.__layername is None:
            self.__layername = self.__get_layername()
        if self.__device:
            _p = subprocess.Popen("adb -s {} shell dumpsys SurfaceFlinger --latency '{}'".format(self.__device, self.__layername),
                                  stdout=subprocess.PIPE)
        else:
            _p = subprocess.Popen("adb shell dumpsys SurfaceFlinger --latency '{}'".format(self.__layername), stdout=subprocess.PIPE)
        results = _p.stdout.readlines()
        return self.__calculate_fps_surfaceview(results)


    def fps_sample(self):
        if self.__version.startswith('Android OS 7.'):
            return self.__fps_sample_7_or_higher()
        else:
            return self.__fps_sample_6_or_lower()

    def net_sample(self):
        if self.__device:
            P = subprocess.Popen("adb -s {} shell cat /proc/net/xt_qtaguid/stats | grep {}".format(self.__device, self.__uid), stdout=subprocess.PIPE)
        else:
            P = subprocess.Popen("adb shell cat /proc/net/xt_qtaguid/stats | grep {}".format(self.__uid), stdout=subprocess.PIPE)
        # col 5->20 (starting from 0)
        # 5  rx_bytes rx_packets tx_bytes tx_packets
        # 9  rx_tcp_bytes rx_tcp_packets rx_udp_bytes rx_udp_packets rx_other_bytes rx_other_packets
        # 15 tx_tcp_bytes tx_tcp_packets tx_udp_bytes tx_udp_packets tx_other_bytes tx_other_packets
        results = [x.split() for x in P.stdout.readlines()]
        results = filter(lambda x: int(x[3]) == self.__uid, results)
        int_results = map(lambda x: [int(d) for d in x[5: 21]], results)
        results = {
            'recvAll': 0,
            'sendAll': 0,
            'recvTcp': 0,
            'sendTcp': 0,
            'recvUdp': 0,
            'sendUdp': 0
        }
        # latest total data
        recv_all = sum([x[0] for x in int_results])
        send_all = sum([x[2] for x in int_results])
        recv_tcp = sum([x[4] for x in int_results])
        send_tcp = sum([x[10] for x in int_results])
        recv_udp = sum([x[6] for x in int_results])
        send_udp = sum([x[12] for x in int_results])
        # return 0 when is called first time
        if self.__recv_all != 0 or self.__recv_tcp != 0 or self.__recv_udp != 0 or \
           self.__send_all != 0 or self.__send_tcp != 0 or self.__send_udp != 0:
            results['recvAll'] = recv_all - self.__recv_all
            results['sendAll'] = send_all - self.__send_all
            results['recvTcp'] = recv_tcp - self.__recv_tcp
            results['sendTcp'] = send_tcp - self.__send_tcp
            results['recvUdp'] = recv_udp - self.__recv_udp
            results['sendUdp'] = send_udp - self.__send_udp
        # update
        self.__recv_all = recv_all
        self.__send_all = send_all
        self.__recv_tcp = recv_tcp
        self.__send_tcp = send_tcp
        self.__recv_udp = recv_udp
        self.__send_udp = send_udp
        return results


if __name__ == '__main__':
    # None works when there is only one device plugged in your computer
    device = None
    # set to your pkg name
    pkg = "com.group.pkg.name"
    pm = PerfManager(device, pkg)
    for i in range(100):
        print pm.fps_sample(), pm.cpu_sample(), pm.mem_sample(), pm.net_sample()
        time.sleep(1)
