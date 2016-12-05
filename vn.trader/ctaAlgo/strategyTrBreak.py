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
import math
from datetime import datetime, timedelta

########################################################################
class TrBreakStrategy(CtaTemplate):
    """结合ATR和RSI指标的一个分钟线交易策略"""
    className = 'TrBreakStrategy'
    author = u'linlin'

    barDbName = DAILY_DB_NAME
    # 策略参数
    atrLength = 11  # 计算ATR指标的窗口数
    atrMaLength = 10  # 计算ATR均线的窗口数
    rsiLength = 5  # 计算RSI的窗口数
    rsiEntry = 16  # RSI的开仓信号
    trailingPercent = 1.0  # 百分比移动止损
    initDays = 200  # 初始化数据所用的天数
    useTrailingStop = False  # 是否使用跟踪止损
    profitLock = 30  # 利润锁定
    trailingStop = 20  # 跟踪止损

    # 策略变量
    bar = None  # K线对象
    barMinute = EMPTY_STRING  # K线当前的分钟


    bufferSize = 100  # 需要缓存的数据的大小
    bufferCount = 0  # 目前已经缓存了的数据的计数
    highArray = np.zeros(bufferSize)  # K线最高价的数组
    lowArray = np.zeros(bufferSize)  # K线最低价的数组
    closeArray = np.zeros(bufferSize)  # K线收盘价的数组
    trArray = np.zeros(bufferSize)  # 波动值的数组
    atrCount = 0  # 目前已经缓存了的ATR的计数
    atrArray = np.zeros(bufferSize)  # ATR指标的数组
    atrValue = 0  # 最新的ATR指标数值
    atrMa = 0  # ATR移动平均的数值



    dtArray = np.zeros(bufferSize)  # 做多条件的数组
    ktArray = np.zeros(bufferSize)  # 做空条件的数组
    dt2Array = np.zeros(bufferSize)  # 做多条件2的数组
    kt2Array = np.zeros(bufferSize)  # 做空条件2的数组
    dtValue = 0
    ktValue = 0
    dt2Value = 0
    kt2Value = 0

    orderList = []  # 保存委托代码的列表
    useDayBar = False  # 使用日线

    # 参数列表，保存了参数的名称
    paramList = ['name',
                 'className',
                 'author',
                 'vtSymbol',
                 'atrLength',
                 ]

    # 变量列表，保存了变量的名称
    varList = ['inited',
               'trading',
               'pos',

               'atrValue',
               'dtValue',
               'ktValue',
               'dt2Value',
               'kt2Value']

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        """Constructor"""
        super(TrBreakStrategy, self).__init__(ctaEngine, setting)

        # 注意策略类中的可变对象属性（通常是list和dict等），在策略初始化时需要重新创建，
        # 否则会出现多个策略实例之间数据共享的情况，有可能导致潜在的策略逻辑错误风险，
        # 策略类中的这些可变对象属性可以选择不写，全都放在__init__下面，写主要是为了阅读
        # 策略时方便（更多是个编程习惯的选择）


        self.isPrePosHaved = False
        self.isAlreadyTraded = False

    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略初始化' % self.name)

        # 初始化RSI入场阈值
        self.rsiBuy = 50 + self.rsiEntry
        self.rsiSell = 50 - self.rsiEntry

        # 载入历史数据，并采用回放计算的方式初始化策略数值
        initData = self.loadBar(self.initDays)
        for bar in initData:
            self.useDayBar = True
            self.onBar(bar)

        self.putEvent()

    # ----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略启动' % self.name)
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        self.writeCtaLog(u'%s策略停止' % self.name)
        self.putEvent()

    # ----------------------------------------------------------------------
    def onTick(self, tick):
        """收到行情TICK推送（必须由用户继承实现）"""
        # 计算K线
        tickMinute = tick.datetime.minute

        if tickMinute != self.barMinute:
            if self.bar:
                self.useDayBar = False
                if datetime.strptime(self.bar.time,"%H:%M:%S.%f").replace(second=0,microsecond=0) == datetime.strptime("15:00","%H:%M"):
                    self.useDayBar = True
                    if self.hasPosOnToday:
                        self.hasPosOnToday = False
                self.onBar(self.bar)

            bar = CtaBarData()
            bar.vtSymbol = tick.vtSymbol
            bar.symbol = tick.symbol
            bar.exchange = tick.exchange

            bar.open = tick.openPrice
            bar.high = tick.highPrice
            bar.low = tick.lowPrice
            bar.close = tick.lastPrice

            bar.date = tick.date
            bar.time = tick.time
            bar.datetime = tick.datetime  # K线的时间设为第一个Tick的时间

            self.bar = bar  # 这种写法为了减少一层访问，加快速度
            self.barMinute = tickMinute  # 更新当前的分钟
        else:  # 否则继续累加新的K线
            bar = self.bar  # 写法同样为了加快速度

            bar.high = max(bar.high, tick.lastPrice)
            bar.low = min(bar.low, tick.lastPrice)
            bar.close = tick.lastPrice

    # ----------------------------------------------------------------------
    def onBar(self, bar):
        """收到Bar推送（必须由用户继承实现）"""
        # 撤销之前发出的尚未成交的委托（包括限价单和停止单）
        if self.orderList != []:
            for orderID in self.orderList:
                self.cancelOrder(orderID)
            self.hasPosOnToday = False
        self.orderList = []

        # 保存K线数据
        if self.useDayBar:
            self.closeArray[0:self.bufferSize - 1] = self.closeArray[1:self.bufferSize]
            self.highArray[0:self.bufferSize - 1] = self.highArray[1:self.bufferSize]
            self.lowArray[0:self.bufferSize - 1] = self.lowArray[1:self.bufferSize]
            self.bufferCount += 1

        self.closeArray[-1] = bar.close
        self.highArray[-1] = bar.high
        self.lowArray[-1] = bar.low


        if self.bufferCount != 0:
            self.trValue = max(max(self.highArray[-1] - self.lowArray[-1],
                                   abs(self.closeArray[-2] - self.highArray[-1])),
                               abs(self.closeArray[-2] - self.lowArray[-1]))

            if self.useDayBar:
                self.trArray[0:self.bufferSize - 1] = self.trArray[1:self.bufferSize]

            self.trArray[-1] = self.trValue


        if self.bufferCount < self.atrLength:
            return

        # 计算指标数值
        self.atrValue = talib.MA(self.trArray, self.atrLength)[-1]
        if self.useDayBar:
            self.atrArray[0:self.bufferSize - 1] = self.atrArray[1:self.bufferSize]
            self.atrCount += 1
        self.atrArray[-1] = self.atrValue

        self.atrValue = self.atrArray[-2]

        if self.atrCount < self.bufferSize - self.atrLength:
            return

        if self.closeArray[-1] > self.closeArray[-2] + self.atrArray[-2] * 1.5:
            self.dtValue = 1
        if self.useDayBar:
            self.dtArray[0:self.bufferSize - 1] = self.dtArray[1:self.bufferSize]
        self.dtArray[-1] = self.dtValue
        self.dtValue = 0
        if self.dtArray[-2] == 0 and self.dtArray[-1] == 1:
            self.dt2Value = 1
        if self.useDayBar:
            self.dt2Array[0:self.bufferSize - 1] = self.dt2Array[1:self.bufferSize]
        self.dt2Array[-1] = self.dt2Value
        self.dt2Value = 0

        if self.closeArray[-1] < self.closeArray[-2] - self.atrArray[-2] * 1.5:
            self.ktValue = 1
        if self.useDayBar:
            self.ktArray[0:self.bufferSize - 1] = self.ktArray[1:self.bufferSize]
        self.ktArray[-1] = self.ktValue
        self.ktValue = 0
        if self.ktArray[-2] == 0 and self.ktArray[-1] == 1:
            self.kt2Value = 1
        if self.useDayBar:
            self.kt2Array[0:self.bufferSize - 1] = self.kt2Array[1:self.bufferSize]
        self.kt2Array[-1] = self.kt2Value
        self.kt2Value = 0

        # 判断是否要进行交易

        # 当前无仓位
        if self.pos == 0:
            if self.dtArray[-1] == 1:  # 做多条件成立
                self.buy(bar.close + 5, 1)
                self.hasPosOnToday = True
            if self.ktArray[-1] == 1:  # 做空条件成立
                self.short(bar.close - 5, 1)
                self.hasPosOnToday = True
        # 持有多头仓位
        elif self.pos == 1:
            if self.ktArray[-1] == 1:  # 做空条件成立，先卖平在卖开
                self.sell(bar.close - 5, 1)
                self.short(bar.close - 5, 1)
                self.hasPosOnToday = True
            if self.dtArray[-6] == 1:
                self.sell(bar.close - 5, 1)
                self.hasPosOnToday = True
            elif not self.hasPosOnToday and self.dt2Array[-1] == 1:
                self.sell(bar.close - 5, 1)
                self.hasPosOnToday = True
        # 持有空头仓位
        elif self.pos == -1:
            if self.dtArray[-1] == 1:  # 做多条件成立，先买平再买开
                self.cover(bar.close + 5, 1)
                self.buy(bar.close + 5, 1)
                self.hasPosOnToday = True
            if self.ktArray[-6] == 1:
                self.cover(bar.close + 5, 1)
                self.hasPosOnToday = True
            elif not self.hasPosOnToday and self.kt2Array[-1] == 1:
                self.cover(bar.close + 5, 1)
                self.hasPosOnToday = True

        # 发出状态更新事件
        self.putEvent()

    # ----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""
        pass

    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        pass

    # ----------------------------------------------------------------------
    def onPosition(self, pos):

        if self.isPrePosHaved or self.isAlreadyTraded:  # 还没有开过仓，或，还没有获取历史仓位
            return
        elif pos.position != 0:
            if pos.direction == DIRECTION_LONG:
                self.pos = pos.position
            else:
                self.pos = -1 * pos.position
            self.lastEntryPrice = pos.price
            self.isPrePosHaved = True

            # print  (u'{0} {1}  历史持仓 {2}  开仓均价 {3}'.format(datetime.now(), self.vtSymbol, self.pos, pos.price))
            # pass


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
    engine.setStartDate('20160101')

    # 设置产品相关参数
    engine.setSlippage(0.2)  # 股指1跳
    engine.setRate(0.3 / 10000)  # 万0.3
    engine.setSize(15)  # 股指合约大小

    # 设置使用的历史数据库
    engine.setDatabase(DAILY_DB_NAME, 'ag1706')

    # 在引擎中创建策略对象
    d = {'atrLength': 11}
    engine.initStrategy(TrBreakStrategy, d)
    engine.writeTrade = True

    # 开始跑回测
    engine.runBacktesting()

    # 显示回测结果
    engine.showBacktestingResult()

    # # 跑优化
    # setting = OptimizationSetting()  # 新建一个优化任务设置对象
    # setting.setOptimizeTarget('capital')  # 设置优化排序的目标是策略净盈利
    # setting.addParameter('atrLength', 11, 20, 1)  # 增加第一个优化参数atrLength，起始11，结束12，步进1
    # setting.addParameter('atrMaLength', 20, 30, 5)  # 增加第二个优化参数atrMa，起始20，结束30，步进1
    #
    # # 性能测试环境：I7-3770，主频3.4G, 8核心，内存16G，Windows 7 专业版
    # # 测试时还跑着一堆其他的程序，性能仅供参考
    # import time
    #
    # start = time.time()
    #
    # # 运行单进程优化函数，自动输出结果，耗时：359秒
    # # engine.runOptimization(AtrRsiStrategy, setting)
    #
    # # 多进程优化，耗时：89秒
    # engine.runParallelOptimization(TrBreakStrategy, setting)
    #
    # print u'耗时：%s' % (time.time() - start)
