# encoding: UTF-8

"""
一个ATR-RSI指标结合的交易策略，适合用在股指的1分钟和5分钟线上。
注意事项：
1. 作者不对交易盈利做任何保证，策略代码仅供参考
2. 本策略需要用到talib，没有安装的用户请先参考www.vnpy.org上的教程安装
3. 将IF0000_1min.csv用ctaHistoryData.py导入MongoDB后，直接运行本文件即可回测策略
"""


from ctaBase import *
from ctaTemplate import CtaTemplate

import talib
import numpy as np


########################################################################
class TurtleStrategy(CtaTemplate):
    """结合ATR和RSI指标的一个分钟线交易策略"""
    className = 'TurtleStrategy'
    author = u'用Python的交易员'

    # 策略参数
    trMaLength = 20         #波动范围均线窗口数
    bigMaLength = 20        #长均线窗口数
    smallMaLength =10       #短均线窗口数
    initDays = 100  # 初始化数据所用的天数

    # 策略变量
    bar = None                  # K线对象
    barDate = EMPTY_STRING    # K线当前的日期

    j = 1
    i = 1
    p = 1

    bufferSize = 50  # 需要缓存的数据的大小
    bufferCount = 0  # 目前已经缓存了的数据的计数
    highArray = np.zeros(bufferSize)  # K线最高价的数组
    lowArray = np.zeros(bufferSize)  # K线最低价的数组
    closeArray = np.zeros(bufferSize)  # K线收盘价的数组
    trArray = np.zeros(bufferSize)   #波动范围的数组
    nArray = np.zeros(bufferSize)    #n值的数组
    hhv1 = np.zeros(bufferSize)  #最高值1
    llv1 = np.zeros(bufferSize)  #最低值1
    hhv2 = np.zeros(bufferSize)  # 最高值2
    llv2 = np.zeros(bufferSize)  # 最低值2
    nValue = 0    #N值
    hhv1Value = 0
    hhv2Value = 0
    llv1Value = 0
    llv2Value = 0

    orderList = []                      # 保存委托代码的列表

    # 参数列表，保存了参数的名称
    paramList = ['name',
                 'className',
                 'author',
                 'vtSymbol',
                 'trMaLength',
                 'bigMaLength',
                 'smallMaLength']

    # 变量列表，保存了变量的名称
    varList = ['inited',
               'trading',
               'pos',
               'hhv1',
               'llv1',
               'hhv2',
               'llv2',
               'nValue']

    #----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        """Constructor"""
        super(TurtleStrategy, self).__init__(ctaEngine, setting)

    #----------------------------------------------------------------------
    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略初始化' %self.name)

        initData = self.loadBar(self.initDays)
        for bar in initData:
            self.onBar(bar)

        self.putEvent()

    #----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略启动' %self.name)
        self.putEvent()

    #----------------------------------------------------------------------
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略停止' %self.name)
        self.putEvent()

    #----------------------------------------------------------------------
    def onTick(self, tick):
        pass

    #----------------------------------------------------------------------
    def onBar(self, bar):
        # 撤销之前发出的尚未成交的委托（包括限价单和停止单）
        for orderID in self.orderList:
            self.cancelOrder(orderID)
        self.orderList = []

        # 保存K线数据
        self.closeArray[0:self.bufferSize-1] = self.closeArray[1:self.bufferSize]
        self.highArray[0:self.bufferSize-1] = self.highArray[1:self.bufferSize]
        self.lowArray[0:self.bufferSize-1] = self.lowArray[1:self.bufferSize]
        self.trArray[0:self.bufferSize-1] = self.trArray[1:self.bufferSize]
        self.closeArray[-1] = bar.close
        self.highArray[-1] = bar.high
        self.lowArray[-1] = bar.low
        self.trArray[-1] = max(bar.high, bar.close) - min(bar.low, bar.close)
        self.hhv1[0:self.bufferSize-1] = self.hhv1[1:self.bufferSize]
        self.hhv2[0:self.bufferSize-1] = self.hhv2[1:self.bufferSize]
        self.llv1[0:self.bufferSize-1] = self.llv1[1:self.bufferSize]
        self.llv2[0:self.bufferSize-1] = self.llv2[1:self.bufferSize]
        self.hhv1Value = talib.MAX(self.highArray,self.smallMaLength)[-1]
        self.hhv2Value = talib.MAX(self.highArray,self.bigMaLength)[-1]
        self.llv1Value = talib.MIN(self.lowArray,self.smallMaLength)[-1]
        self.llv2Value = talib.MIN(self.lowArray,self.bigMaLength)[-1]
        self.hhv1[-1] = self.hhv1Value
        self.hhv2[-1] = self.hhv2Value
        self.llv1[-1] = self.llv1Value
        self.llv2[-1] = self.llv2Value

        self.bufferCount += 1
        if self.bufferCount < self.trMaLength:
            return
        if self.bufferCount >= self.trMaLength:
            if self.bufferCount == self.trMaLength:
                self.nValue = talib.MA(self.trArray,self.trMaLength)[-1]
            if self.p == 5 or self.bufferCount == self.trMaLength:
                self.nValue = (19*self.nValue + self.trArray[-1])/self.trMaLength
                self.p = 1
                self.nArray[0:self.bufferSize-1] = self.nArray[1:self.bufferSize]
                self.nArray[-1] = self.nValue
            self.p += 1


                

    #----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""
        pass

    #----------------------------------------------------------------------
    def onTrade(self, trade):
        pass


if __name__ == '__main__':
    # 提供直接双击回测的功能
    # 导入PyQt4的包是为了保证matplotlib使用PyQt4而不是PySide，防止初始化出错
    from ctaBacktesting import *
    from PyQt4 import QtCore, QtGui

    # 创建回测引擎
    engine = BacktestingEngine()

    # 设置引擎的回测模式为K线
    engine.setBacktestingMode(engine.BAR_MODE)

    # 设置回测用的数据起始日期
    engine.setStartDate('20120101')

    # 载入历史数据到引擎中
    engine.loadHistoryData(MINUTE_DB_NAME, 'IF0000')

    # 设置产品相关参数
    engine.setSlippage(0.2)     # 股指1跳
    engine.setRate(0.3/10000)   # 万0.3
    engine.setSize(300)         # 股指合约大小

    # 在引擎中创建策略对象
    engine.initStrategy(AtrRsiStrategy, {})

    # 开始跑回测
    engine.runBacktesting()

    # 显示回测结果
    engine.showBacktestingResult()