from ihr.hegemony import Hegemony
import datetime


def calculate_heg_time(date):
    t = datetime.datetime.fromtimestamp(date)
    print(t)
    t = datetime.datetime.strftime(t-datetime.timedelta(seconds=3600 * 24*7), '%Y-%m-%dT%H:%M')
    mm = int(t.split('T')[1].split(':')[1])
    mm = int(mm/15) * 15
    if mm == 0:
        mm = '00'
    t = t.split(':')[0] + ':'+str(mm)
    return t

def get_heg_dependency(originasn, asns, timestr):
    dt = datetime.datetime.strptime(timestr, '%Y-%m-%d %H:%M:%S')
    timestamp = int(dt.timestamp())
    heg_time = calculate_heg_time(timestamp)
    
    #heg_time = '2025-05-31T21:15'
    hege = Hegemony(originasns=[originasn], asns = asns, start=heg_time, end=heg_time)
    
    hege_data = []
    if list(hege.get_results()):
        hege_data = list(hege.get_results())[0]
    return hege_data
    
'''
timestr = '2025-11-05 22:06:16'
hege_data = get_heg_dependency(60458, [204384], timestr)
print(hege_data)
'''





