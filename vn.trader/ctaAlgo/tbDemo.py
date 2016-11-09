# encoding: UTF-8

import talib as ta
import numpy as np
import copy

from ctaBase import *
from ctaTemplate import CtaTemplate

from datetime import datetime, timedelta

########################################################################
class TalibDoubleSmaDemo(CtaTemplate):
    """基于Talib模块的双指数均线策略Demo"""

    className = 'TalibDoubleSmaDemo'
    author = u'ideaplat'

    # 策略参数
    fastPeriod = 5      # 快速均线参数
    slowPeriod = 20     # 慢速均线参数
    initDays = 30       # 初始化数据所用的天数

    # 策略变量
    bar = None
    barMinute = EMPTY_STRING

    customBar = None
    nextBegin = True
    firstvolumes = 0

    closeHistory = []       # 缓存K线收盘价的数组
    maxHistory = 30        # 最大缓存数量

    fastMa0 = EMPTY_FLOAT   # 当前最新的快速均线数值
    fastMa1 = EMPTY_FLOAT   # 上一根的快速均线数值

    slowMa0 = EMPTY_FLOAT   # 慢速均线数值
    slowMa1 = EMPTY_FLOAT


    # 参数列表，保存了参数的名称
    paramList = ['name',
                 'className',
                 'author',
                 'vtSymbol',
                 'fastPeriod',
                 'slowPeriod']

    # 变量列表，保存了变量的名称
    varList = ['inited',
               'trading',
               'pos',
               'fastMa0',
               'fastMa1',
               'slowMa0',
               'slowMa1']

    # ----------------------------------------------------------------------
    def __init__(self, ctaEngine, setting):
        """Constructor"""
        super(TalibDoubleSmaDemo, self).__init__(ctaEngine, setting)



    # ----------------------------------------------------------------------
    def onInit(self):
        """初始化策略（必须由用户继承实现）"""
        self.writeCtaLog(u'双SMA演示策略初始化')

        initData = self.loadBar(self.initDays)

        for bar in initData:
            if self.timesDict:
                self.procecssCustomBar(bar)
            else:
                self.onBar(bar)

        self.putEvent()

    # ----------------------------------------------------------------------
    def onStart(self):
        """启动策略（必须由用户继承实现）"""
        self.writeCtaLog(u'双SMA演示策略启动')
        self.putEvent()

    # ----------------------------------------------------------------------
    def onStop(self):
        """停止策略（必须由用户继承实现）"""
        self.writeCtaLog(u'双SMA演示策略停止')
        self.putEvent()

    # ----------------------------------------------------------------------
    def onTick(self, tick):
        """收到行情TICK推送（必须由用户继承实现）"""
        # 计算K线
        tickMinute = tick.datetime.minute

        if tickMinute != self.barMinute:
            if self.bar:
                newBar = copy.copy(self.bar)
                newBar.datetime = tick.datetime.replace(second=0, microsecond=0)
                newBar.date = tick.date
                newBar.time = tick.time
                if self.timesDict:
                    self.procecssCustomBar(newBar)
                else:
                    self.onBar(newBar)

            bar = CtaBarData()
            bar.vtSymbol = tick.vtSymbol
            bar.symbol = tick.symbol
            bar.exchange = tick.exchange

            bar.open = tick.lastPrice
            bar.high = tick.lastPrice
            bar.low = tick.lastPrice
            bar.close = tick.lastPrice

            bar.date = tick.date
            bar.time = tick.time
            bar.datetime = tick.datetime  # K线的时间设为第一个Tick的时间

            # 实盘中用不到的数据可以选择不算，从而加快速度

            #self.firstvolumes = tick.volume
            #bar.openInterest = tick.openInterest

            self.bar = bar  # 这种写法为了减少一层访问，加快速度
            self.barMinute = tickMinute  # 更新当前的分钟

        else:  # 否则继续累加新的K线
            bar = self.bar  # 写法同样为了加快速度

            bar.high = max(bar.high, tick.lastPrice)
            bar.low = min(bar.low, tick.lastPrice)
            bar.close = tick.lastPrice
            # 实盘中用不到的数据可以选择不算，从而加快速度
            #bar.volume = tick.volume - self.firstvolumes  # 最后一个tick的成交量和第一个tick的成交量的差是一分钟的成交量
            #bar.openInterest = tick.openInterest  # 持仓量直接更新

    # ----------------------------------------------------------------------
    def onBar(self, bar):
        """收到Bar推送（必须由用户继承实现）"""
        # 把最新的收盘价缓存到列表中
        self.closeHistory.append(bar.close)

        # 检查列表长度，如果超过缓存上限则移除最老的数据
        # 这样是为了减少计算用的数据量，提高速度
        if len(self.closeHistory) > self.maxHistory:
            self.closeHistory.pop(0)
        # 如果小于缓存上限，则说明初始化数据尚未足够，不进行后续计算
        else:
            return

        # 将缓存的收盘价数转化为numpy数组后，传入talib的函数SMA中计算
        closeArray = np.array(self.closeHistory)
        fastSMA = ta.SMA(closeArray, self.fastPeriod)
        slowSMA = ta.SMA(closeArray, self.slowPeriod)

        # 读取当前K线和上一根K线的数值，用于判断均线交叉
        self.fastMa0 = fastSMA[-1]
        self.fastMa1 = fastSMA[-2]
        self.slowMa0 = slowSMA[-1]
        self.slowMa1 = slowSMA[-2]

        # 判断买卖
        crossOver = self.fastMa0>self.slowMa0 and self.fastMa1<self.slowMa1     # 金叉上穿
        crossBelow = self.fastMa0<self.slowMa0 and self.fastMa1>self.slowMa1    # 死叉下穿

        # 金叉和死叉的条件是互斥
        if crossOver:
            # 如果金叉时手头没有持仓，则直接做多
            if self.pos == 0:
                self.buy(bar.close, 1)
            # 如果有空头持仓，则先平空，再做多
            elif self.pos < 0:
                self.cover(bar.close, 1)
                self.buy(bar.close, 1)
        # 死叉和金叉相反
        elif crossBelow:
            if self.pos == 0:
                self.short(bar.close, 1)
            elif self.pos > 0:
                self.sell(bar.close, 1)
                self.short(bar.close, 1)

        # 发出状态更新事件
        self.putEvent()

    # ----------------------------------------------------------------------
    def onOrder(self, order):
        """收到委托变化推送（必须由用户继承实现）"""
        # 对于无需做细粒度委托控制的策略，可以忽略onOrder
        pass

    # ----------------------------------------------------------------------
    def onTrade(self, trade):
        """收到成交推送（必须由用户继承实现）"""
        # 对于无需做细粒度委托控制的策略，可以忽略onOrder
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

    # -----------------------------------------------------------------------
    def barInTime(self, d):
        inTime = False
        if self.timesDict:
            for time in self.timesDict:
                if time == d.time:
                    inTime = True
        return inTime

   #----------------------------------------------------------------------------
    def procecssCustomBar(self,bar):

        if self.nextBegin:
            customBar = CtaBarData()
            customBar.vtSymbol = bar.vtSymbol
            customBar.symbol = bar.vtSymbol
            customBar.exchange = bar.exchange
            customBar.open = bar.open
            customBar.high = bar.high
            customBar.low = bar.low
            customBar.close = bar.close
            customBar.date = bar.date
            customBar.time = bar.time
            customBar.datetime = bar.datetime
            #customBar.volume = int(float(bar.volume))
            #customBar.openInterest = bar.openInterest
            self.customBar = customBar
            self.nextBegin = False
        else:
            customBar = self.customBar
            customBar.high = max(customBar.high, bar.high)
            customBar.low = min(customBar.low, bar.low)
            customBar.close = bar.close
            #customBar.volume = customBar.volume + int(float(bar.volume))
            #customBar.openInterest = bar.openInterest
        if self.barInTime(bar):
            customBar.datetime = bar.datetime.replace(second=0,microsecond=0)
            customBar.date = bar.date
            customBar.time = bar.time
            self.nextBegin = True
            self.onBar(customBar)





