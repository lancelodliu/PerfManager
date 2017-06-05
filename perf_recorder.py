#!/usr/bin/env python
# -*- coding: utf-8 -*-
__author__ = 'lancelodliu'
import os, time, sys, re
import subprocess
import datetime

def GetPid(device, package):
    adb_str = "adb -s {} shell ps | grep {}".format(device, package) if device else "adb shell ps | grep {}".format(package)
    # 找到进程ID
    proc = subprocess.Popen(adb_str, stdout=subprocess.PIPE)
    _lines = [x.split() for x in proc.stdout.readlines()]
    for line in _lines:
        if line[-1].strip() == package:
            return int(line[1])

def GetUid(device, package):
    adb_str = "adb -s {} shell dumpsys package | grep {} -A 3 | grep userId".format(device, package) if device else "adb shell dumpsys package| grep {} -B 1 -A 1 | grep userId".format(package)
    # 找到进程ID
    proc = subprocess.Popen(adb_str, stdout=subprocess.PIPE)
    _t = proc.stdout.read()
    uid = _t.split('=')[1].split()[0]
    return int(uid)

class PerfManager(object):
    def __init__(self, device, package):
        self.pid = GetPid(device, package)
        self.uid = GetUid(device, package)
        self.device = device
        self.package = package
        self.time_total_last = 0
        self.time_user_last = 0
        self.time_kernel_last = 0
        self.cpu_last = 0
        self.recv_all = 0
        self.send_all = 0
        self.recv_tcp = 0
        self.send_tcp = 0
        self.recv_udp = 0
        self.send_udp = 0

    def mem_sample(self):
        result = {'NativeHeap': -1, 'DalvikHeap': -1, 'PssTotal': -1}
        if self.package is None:
            return result
        # 找到进程ID
        P = None
        if self.device:
            P = subprocess.Popen("adb -s {} shell dumpsys meminfo {}".format(self.device, self.package), stdout=subprocess.PIPE)
        else:
            P = subprocess.Popen("adb shell dumpsys meminfo {}".format(self.package), stdout=subprocess.PIPE)
        _lines = [x.lstrip() for x in P.stdout.readlines()]
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
        if self.package is None:
            return -1
        # 解析所有CPU
        P = None
        if self.device:
            P = subprocess.Popen("adb -s {} shell cat /proc/stat".format(self.device), stdout=subprocess.PIPE)
        else:
            P = subprocess.Popen("adb shell cat /proc/stat", stdout=subprocess.PIPE)
        cpu_line = P.stdout.readline()
        time_total_now = 0
        data = cpu_line.split()
        for d in data:
            if d.isdigit():
                time_total_now += int(d)
        # 解析PID CPU
        if self.device:
            P = subprocess.Popen("adb -s {} shell cat /proc/{}/stat".format(self.device, self.pid), stdout=subprocess.PIPE)
        else:
            P = subprocess.Popen("adb shell cat /proc/{}/stat".format(self.pid), stdout=subprocess.PIPE)
        cpu_line = P.stdout.readline()
        data = cpu_line.split()
        # 没有数据 返回上一次
        if len(data) < 15:
            print "Get Cpu Error"
            return self.cpu_last
        time_user_now = int(data[13])
        time_kernel_now = int(data[14])
        if self.time_total_last != 0:
            cpu = 100.0*(time_user_now - self.time_user_last + time_kernel_now - self.time_kernel_last) / (time_total_now - self.time_total_last)
            if cpu < 1.0:
                cpu = self.cpu_last
            self.cpu_last = cpu
        self.time_total_last = time_total_now
        self.time_user_last = time_user_now
        self.time_kernel_last = time_kernel_now
        return self.cpu_last


    def fps_sample(self):
        P = None
        if self.device:
            P = subprocess.Popen("adb -s {} shell dumpsys SurfaceFlinger --latency SurfaceView".format(self.device), stdout=subprocess.PIPE)
        else:
            P = subprocess.Popen("adb shell dumpsys SurfaceFlinger --latency SurfaceView", stdout=subprocess.PIPE)
        results = P.stdout.readlines()
        timestamps = [] # 以秒为单位的时间戳
        nanoseconds_per_second = 1e9
        refresh_period = long(results[0]) / nanoseconds_per_second
        pending_fence_timestamp = 9223372036854775807
        for line in results[1:]:
            fields = line.split()
            if len(fields) != 3:
                continue
            timestamp = long(fields[1])
            if timestamp == pending_fence_timestamp:
                continue
            timestamp /= nanoseconds_per_second
            timestamps.append(timestamp)
        # 没有有效数据
        if len(timestamps) < 2:
            return -1
        return (len(timestamps) - 1) / (timestamps[-1]-timestamps[0])

    def net_sample(self):
        if self.device:
            P = subprocess.Popen("adb -s {} shell cat /proc/net/xt_qtaguid/stats | grep {}".format(self.device, self.uid), stdout=subprocess.PIPE)
        else:
            P = subprocess.Popen("adb shell cat /proc/net/xt_qtaguid/stats | grep {}".format(self.uid), stdout=subprocess.PIPE)
        # 列5（从0）到列20依次为
        # 5  rx_bytes rx_packets tx_bytes tx_packets
        # 9  rx_tcp_bytes rx_tcp_packets rx_udp_bytes rx_udp_packets rx_other_bytes rx_other_packets
        # 15 tx_tcp_bytes tx_tcp_packets tx_udp_bytes tx_udp_packets tx_other_bytes tx_other_packets
        results = [x.split() for x in P.stdout.readlines()]
        results = filter(lambda x: int(x[3]) == self.uid, results)
        int_results = map(lambda x: [int(d) for d in x[5: 21]], results)
        results = {
            'recvAll': 0,
            'sendAll': 0,
            'recvTcp': 0,
            'sendTcp': 0,
            'recvUdp': 0,
            'sendUdp': 0
        }
        # 最新的累积数据
        recv_all = sum([x[0] for x in int_results])
        send_all = sum([x[2] for x in int_results])
        recv_tcp = sum([x[4] for x in int_results])
        send_tcp = sum([x[10] for x in int_results])
        recv_udp = sum([x[6] for x in int_results])
        send_udp = sum([x[12] for x in int_results])
        # 非第一次执行才进行计算 第一次调用只会返回0
        if self.recv_all != 0 or self.recv_tcp != 0 or self.recv_udp != 0 or \
           self.send_all != 0 or self.send_tcp != 0 or self.send_udp != 0:
            results['recvAll'] = recv_all - self.recv_all
            results['sendAll'] = send_all - self.send_all
            results['recvTcp'] = recv_tcp - self.recv_tcp
            results['sendTcp'] = send_tcp - self.send_tcp
            results['recvUdp'] = recv_udp - self.recv_udp
            results['sendUdp'] = send_udp - self.send_udp
        # 更新已有数据
        self.recv_all = recv_all
        self.send_all = send_all
        self.recv_tcp = recv_tcp
        self.send_tcp = send_tcp
        self.recv_udp = recv_udp
        self.send_udp = send_udp
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
