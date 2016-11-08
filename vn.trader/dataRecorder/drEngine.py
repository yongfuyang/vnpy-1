# encoding: UTF-8

'''
本文件中实现了行情数据记录引擎，用于汇总TICK数据，并生成K线插入数据库。

使用DR_setting.json来配置需要收集的合约，以及主力合约代码。
'''

import json
import os
import copy
from collections import OrderedDict
from datetime import datetime, timedelta
from threading import Thread
from Queue import Queue

from eventEngine import *
from vtGateway import VtSubscribeReq, VtLogData
from drBase import *
from vtFunction import todayDate


########################################################################
class DrEngine(object):
    """数据记录引擎"""
    
    settingFileName = 'DR_setting.json'
    #settingFileName = os.getcwd() + '/dataRecorder/' + settingFileName
    path = os.path.abspath(os.path.dirname(__file__))
    settingFileName = os.path.join(path, settingFileName)
    #----------------------------------------------------------------------
    def __init__(self, mainEngine, eventEngine):
        """Constructor"""
        self.mainEngine = mainEngine
        self.eventEngine = eventEngine
        
        # 当前日期
        self.today = todayDate()
        
        # 主力合约代码映射字典，key为具体的合约代码（如IF1604），value为主力合约代码（如IF0000）
        self.activeSymbolDict = {}
        
        # Tick对象字典
        self.tickDict = {}
        
        # K线对象字典
        self.barDict = {}
        self.m5barDict = {}
        self.daybarDict = {}

        #负责执行数据库插入的单独线程相关
        self.active = False                     #工作状态
        self.queue = Queue()                    #队列
        self.thread = Thread(target=self.run)   #线程

        # 交易时间字典
        self.timeDict = {}

        # 每分钟的的第一个tick的成交量
        self.firstvolumes ={}

        # 载入设置，订阅行情
        self.loadSetting()
        
    #----------------------------------------------------------------------
    def loadSetting(self):
        """载入设置"""
        with open(self.settingFileName) as f:
            setting = json.load(f)
            
            # 如果working设为False则不启动行情记录功能
            working = setting['working']
            if not working:
                return
            
            if 'tick' in setting:
                l = setting['tick']
                
                for symbol, gatewayName in l:
                    drTick = DrTickData()           # 该tick实例可以用于缓存部分数据（目前未使用）
                    self.tickDict[symbol] = drTick

                    req = VtSubscribeReq()
                    req.symbol = symbol
                    self.mainEngine.subscribe(req, gatewayName)
                    
            if 'bar' in setting:
                l = setting['bar']
                
                for symbol, gatewayName in l:
                    bar = DrBarData()
                    self.barDict[symbol] = bar
                    m5bar = DrBarData()
                    self.m5barDict[symbol] = m5bar
                    daybar = DrBarData()
                    self.daybarDict[symbol] = daybar
                    
                    req = VtSubscribeReq()
                    req.symbol = symbol
                    self.mainEngine.subscribe(req, gatewayName)
                    
            if 'active' in setting:
                d = setting['active']
                
                for activeSymbol, symbol in d.items():
                    self.activeSymbolDict[symbol] = activeSymbol

            if 'time' in setting:
                self.timeDict = setting['time']
            
            #启动数据插入线程
            self.start()

            # 注册事件监听
            self.registerEvent()            

    #----------------------------------------------------------------------
    def procecssTickEvent(self, event):
        """处理行情推送"""
        tick = event.dict_['data']
        vtSymbol = tick.vtSymbol

        # 转化Tick格式
        drTick = DrTickData()
        d = drTick.__dict__
        for key in d.keys():
            if key != 'datetime':
                d[key] = tick.__getattribute__(key)
        drTick.datetime = datetime.strptime(' '.join([tick.date, tick.time]), '%Y%m%d %H:%M:%S.%f')            
        
        # 更新Tick数据
        if vtSymbol in self.tickDict and self.tickInTime(tick):
            self.insertData(TICK_DB_NAME, vtSymbol, drTick)
            
            if vtSymbol in self.activeSymbolDict:
                activeSymbol = self.activeSymbolDict[vtSymbol]
                self.insertData(TICK_DB_NAME, activeSymbol, drTick)
            
            # 发出日志
            self.writeDrLog(u'记录Tick数据%s，时间:%s, last:%s, bid:%s, ask:%s' 
                            %(drTick.vtSymbol, drTick.time, drTick.lastPrice, drTick.bidPrice1, drTick.askPrice1))
            
        # 更新分钟线数据
        if vtSymbol in self.barDict :
            bar = self.barDict[vtSymbol]
            #if bar.datetime  and bar.datetime - drTick.datetime > timedelta(0,600) \
            #       and datetime.strptime(drTick.time,"%H:%M:%S.%f").replace(second=0,microsecond=0) != \
            #              datetime.strptime("00:00","%H:%M"):
            #   bar.vtSymbol = None
            #   bar.datetime = None
            # 如果第一个TICK或者新的一分钟
            if not bar.datetime or bar.datetime.minute != drTick.datetime.minute:
                if bar.vtSymbol and self.barInTime(tick):
                    newBar = copy.copy(bar)
                    newBar.datetime = drTick.datetime.replace(second=0, microsecond=0)
                    newBar.date = drTick.date
                    newBar.time = drTick.time
                    self.insertData(MINUTE_DB_NAME, vtSymbol, newBar)

                    if vtSymbol in self.activeSymbolDict:
                        activeSymbol = self.activeSymbolDict[vtSymbol]
                        self.insertData(MINUTE_DB_NAME, activeSymbol, newBar)

                    self.writeDrLog(u'记录分钟线数据%s，时间:%s, O:%s, H:%s, L:%s, C:%s'
                                        % (newBar.vtSymbol, newBar.time, newBar.open, newBar.high,
                                           newBar.low, newBar.close))
                    #self.procecssBar(newBar)

                bar.vtSymbol = drTick.vtSymbol
                bar.symbol = drTick.symbol
                bar.exchange = drTick.exchange
                
                bar.open = drTick.lastPrice
                bar.high = drTick.lastPrice
                bar.low = drTick.lastPrice
                bar.close = drTick.lastPrice
                
                bar.date = drTick.date
                bar.time = drTick.time
                bar.datetime = drTick.datetime
                self.firstvolumes[vtSymbol] = drTick.volume
                bar.openInterest = drTick.openInterest        
            # 否则继续累加新的K线
            else:                               
                bar.high = max(bar.high, drTick.lastPrice)
                bar.low = min(bar.low, drTick.lastPrice)
                bar.close = drTick.lastPrice
                bar.volume = drTick.volume - self.firstvolumes[vtSymbol]  #最后一个tick的成交量和第一个tick的成交量的差是一分钟的成交量
                bar.openInterest = drTick.openInterest    # 持仓量直接更新
        #更新日线数据
        if vtSymbol in self.daybarDict and self.tickInTime(tick):
            if datetime.strptime(tick.time,"%H:%M:%S.%f").replace(second=0,microsecond=0) == datetime.strptime("15:00","%H:%M"):
                daybar = self.daybarDict[vtSymbol]
                daybar.datetime = drTick.datetime.replace(hour=0,minute=0,second=0,microsecond=0)
                daybar.date = drTick.date
                daybar.time = drTick.time
                daybar.exchange = drTick.exchange
                daybar.open = drTick.openPrice
                daybar.high = drTick.highPrice
                daybar.low = drTick.lowPrice
                daybar.close = drTick.lastPrice
                daybar.volume = drTick.volume
                daybar.openInterest = drTick.openInterest
                self.insertData(DAILY_DB_NAME, vtSymbol, daybar)

                if vtSymbol in self.activeSymbolDict:
                    activeSymbol = self.activeSymbolDict[vtSymbol]
                    self.insertData(DAILY_DB_NAME, activeSymbol, daybar)
                self.writeDrLog(u'记录日线数据%s，时间:%s, O:%s, H:%s, L:%s, C:%s'
                                % (daybar.vtSymbol, daybar.time, daybar.open, daybar.high,
                                   daybar.low, daybar.close))

    #----------------------------------------------------------------------
    def procecssBar(self,bar):
        vtSymbol = bar.vtSymbol
        if vtSymbol in self.m5barDict :
            m5bar = self.m5barDict[vtSymbol]
            if not  m5bar.datetime or bar.datetime.minute % 5 == 1:
                m5bar.vtSymbol = bar.vtSymbol
                m5bar.symbol = bar.vtSymbol
                m5bar.exchange = bar.exchange

                m5bar.open = bar.open
                m5bar.high = bar.high
                m5bar.low = bar.low
                m5bar.close = bar.close
                m5bar.date = bar.date
                m5bar.time = bar.time
                m5bar.datetime = bar.datetime
                m5bar.volume = bar.volume
                m5bar.openInterest = bar.openInterest
            else:
                m5bar.high = max(m5bar.high, bar.high)
                m5bar.low = min(m5bar.low, bar.low)
                m5bar.close = bar.close
                m5bar.volume = m5bar.volume + bar.volume
                m5bar.openInterest = bar.openInterest

            if bar.datetime.minute % 5 == 0:
                newBar = copy.copy(m5bar)
                newBar.datetime = bar.datetime.replace(second=0,microsecond=0)
                newBar.date = bar.date
                newBar.time = bar.time
                self.insertData(MINUTE5_DB_NAME, vtSymbol, newBar)

                if vtSymbol in self.activeSymbolDict:
                    activeSymbol = self.activeSymbolDict[vtSymbol]
                    self.insertData(MINUTE5_DB_NAME, activeSymbol, newBar)

                self.writeDrLog(u'记录5分钟线数据%s，时间:%s, O:%s, H:%s, L:%s, C:%s'
                                    %(newBar.vtSymbol, newBar.time, newBar.open, newBar.high,
                                      newBar.low, newBar.close))






    #----------------------------------------------------------------------
    def registerEvent(self):
        """注册事件监听"""
        self.eventEngine.register(EVENT_TICK, self.procecssTickEvent)
 
    #----------------------------------------------------------------------
    def insertData(self, dbName, collectionName, data):
        """插入数据到数据库（这里的data可以是CtaTickData或者CtaBarData）"""
       # self.mainEngine.dbInsert(dbName, collectionName, data.__dict__)
        self.queue.put((dbName,collectionName,data.__dict__))

    #-----------------------------------------------------------------------
    def run(self):
        """运行插入线程"""
        while self.active:
            try:
                dbName,collectionName,d = self.queue.get(block=True,timeout=1)
                self.mainEngine.dbInsert(dbName,collectionName,d)
            except Empty:
                pass   
    
    #--------------------------------------------------------------------------
    def start(self):
        """启动"""
        self.active = True
        self.thread.start()

    #---------------------------------------------------------------------------
    def stop(self):
        """退出"""
        if self.active:
            self.active = False
            self.thread.join()
  
    #----------------------------------------------------------------------

    def writeDrLog(self, content):
        """快速发出日志事件"""
        log = VtLogData()
        log.logContent = content
        event = Event(type_=EVENT_DATARECORDER_LOG)
        event.dict_['data'] = log
        self.eventEngine.put(event)

    #-----------------------------------------------------------------------
    def tickInTime(self,d):
        isSymbol = False
        isTime = False
        for symbol, times in self.timeDict.items():
            if symbol == d.vtSymbol:
                isSymbol = True
            for time in times:
                start = datetime.strptime(time[0],"%H:%M")
                end = datetime.strptime(time[1],"%H:%M")
                time1 = datetime.strptime(d.time,"%H:%M:%S.%f").replace(second=0,microsecond=0)
                if time1 >= start and time1 <=end :
                    isTime = True
        if isSymbol and isTime:
                return True
       
       
       #-----------------------------------------------------------------------
    def barInTime(self,d):
        isSymbol = False
        isTime = False
        for symbol, times in self.timeDict.items():
            if symbol == d.vtSymbol:
                isSymbol = True
            for time in times:
                start = datetime.strptime(time[0],"%H:%M")
                end = datetime.strptime(time[1],"%H:%M")
                time1 = datetime.strptime(d.time,"%H:%M:%S.%f").replace(second=0,microsecond=0)
                if time1 > start and time1 <=end or time1 == datetime.strptime("00:00","%H:%M"):
                    isTime = True
        if isSymbol and isTime:
                return True

