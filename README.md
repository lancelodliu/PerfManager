# perf_recorder
## Description
* ADB tool to collect performance of mobile game:
  * FPS
  * CPU(in percentage)
  * Memory(in KB)
  * Network(in Byte/s)
* Need and only for Android 5.0
* No need for __ROOT__ privilige
## Usage
```python
# None works when there is only one device plugged in your computer
device = None
# set to your pkg name
pkg = "com.group.pkg.name"
pm = PerfManager(device, pkg)
for i in range(100):
    print pm.fps_sample(), pm.cpu_sample(), pm.mem_sample(), pm.net_sample()
    time.sleep(1)
```
1. Plug in your phone, enable USB Debug.
2. Instantialize a PerfManager using your app's package name(essential) and device id(option)
3. Open your app in your phone
4. ```python main.py```
